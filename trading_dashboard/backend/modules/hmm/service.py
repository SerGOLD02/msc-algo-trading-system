import pickle
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from database.models import PriceCache
from config import HMM_MODEL_PATH, HMM_REGIMES_PATH, CRISIS_STATE_IDX

REGIME_NAMES = {
    0: "Bassa Volatilità",
    1: "Transizione Rialzo",
    2: "Transizione Ribasso",
    3: "Alta Volatilità",
    4: "Crisis State",
}

_hmm_model = None
_regimes_cache: pd.DataFrame | None = None


def load_hmm():
    global _hmm_model
    if _hmm_model is None:
        with open(HMM_MODEL_PATH, "rb") as f:
            loaded = pickle.load(f)
        # Handle both dict format and direct model
        if isinstance(loaded, dict):
            _hmm_model = loaded.get("model", loaded)
            print(f"[HMM] Loaded model from dict (n_components={getattr(_hmm_model, 'n_components', '?')})")
        else:
            _hmm_model = loaded
    return _hmm_model


def _load_precomputed_regimes() -> pd.DataFrame:
    """Carica i regimi pre-calcolati dalla tesi (read-only)."""
    global _regimes_cache
    if _regimes_cache is None:
        try:
            _regimes_cache = pd.read_parquet(HMM_REGIMES_PATH)
            if "Date" in _regimes_cache.columns:
                _regimes_cache["Date"] = pd.to_datetime(_regimes_cache["Date"])
                _regimes_cache = _regimes_cache.set_index("Date")
            else:
                _regimes_cache.index = pd.to_datetime(_regimes_cache.index)
        except Exception as e:
            print(f"[HMM] Cannot load pre-computed regimes: {e}")
            _regimes_cache = pd.DataFrame()
    return _regimes_cache


def compute_hmm_features(prices: dict,
                         fridays: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Calcola le feature di input per l'HMM:
      - spy_ret: rendimento settimanale SPY
      - vix: livello VIX
      - corr: correlazione rolling 60gg SPY-TLT

    Tutto con lag +1 e z-score rolling 60.
    """
    spy = prices.get("SPY", {}).get("Close") if isinstance(prices.get("SPY"), dict) else prices.get("SPY", pd.DataFrame()).get("Close")
    tlt = prices.get("TLT", {}).get("Close") if isinstance(prices.get("TLT"), dict) else prices.get("TLT", pd.DataFrame()).get("Close")
    vix = prices.get("VIX", {}).get("Close") if isinstance(prices.get("VIX"), dict) else prices.get("VIX", pd.DataFrame()).get("Close")

    if spy is None or tlt is None or vix is None:
        return pd.DataFrame()

    spy_ret = spy.pct_change()
    tlt_ret = tlt.pct_change()
    corr60 = spy_ret.rolling(60).corr(tlt_ret)

    spy_w = spy_ret.reindex(fridays)
    vix_w = vix.reindex(fridays, method="ffill")
    corr_w = corr60.reindex(fridays, method="ffill")

    df = pd.DataFrame({
        "spy_ret": spy_w, "vix": vix_w, "corr": corr_w
    }).shift(1)  # Lag +1

    # Z-score rolling 60
    roll_m = df.rolling(60).mean()
    roll_s = df.rolling(60).std() + 1e-9
    df_z = ((df - roll_m) / roll_s).clip(-5, 5).dropna()

    return df_z


def run_hmm_inference(hmm_features: pd.DataFrame) -> pd.DataFrame:
    """
    Esegue l'HMM sulle feature e restituisce la serie dei regimi
    con il filtro anti-whipsaw (2 venerdì consecutivi).

    Strategy:
    - Use pre-computed regimes for dates up to 2025-12-26
    - Run live HMM on new data and merge results
    """
    if len(hmm_features) == 0:
        return pd.DataFrame(columns=["Regime_Raw", "Regime_Final"])

    # Always run live HMM on the provided features
    model = load_hmm()
    X = hmm_features.values
    states = model.predict(X)

    # Remap states by VIX level (stato 0=bassa vol, stato 4=crisis)
    vix_by_state = {}
    for s in range(model.n_components):
        mask = states == s
        vix_by_state[s] = hmm_features["vix"].values[mask].mean() \
            if mask.sum() > 0 else 0
    sorted_states = sorted(vix_by_state, key=lambda s: vix_by_state[s])
    state_map = {old: new for new, old in enumerate(sorted_states)}

    raw_regimes = [state_map[s] for s in states]

    # Filtro anti-whipsaw: 2 venerdì consecutivi per entrare/uscire da Crisis
    final_regimes = _apply_persistence_filter(raw_regimes, CRISIS_STATE_IDX)

    live_result = pd.DataFrame({
        "Regime_Raw": raw_regimes,
        "Regime_Final": final_regimes,
    }, index=hmm_features.index)

    # Try to merge with pre-computed regimes for older dates
    precomputed = _load_precomputed_regimes()
    if len(precomputed) > 0 and "Regime_Final" in precomputed.columns:
        # Only keep pre-computed dates NOT in live result
        pre_only = precomputed[~precomputed.index.isin(live_result.index)]
        if "Regime_Raw" not in pre_only.columns:
            pre_only = pre_only.copy()
            pre_only["Regime_Raw"] = pre_only["Regime_Final"]
        merged = pd.concat([
            pre_only[["Regime_Raw", "Regime_Final"]],
            live_result
        ]).sort_index()
        return merged

    return live_result


def _apply_persistence_filter(raw: list[int], crisis_idx: int) -> list[int]:
    """
    Filtro anti-whipsaw: lo stato Crisis richiede 2 venerdì consecutivi
    per attivarsi e 2 consecutivi non-crisis per disattivarsi.
    """
    final = list(raw)
    in_crisis = False

    for i in range(len(final)):
        if not in_crisis:
            # Per entrare in crisis: 2 venerdì consecutivi crisis
            if i > 0 and raw[i] == crisis_idx and raw[i - 1] == crisis_idx:
                in_crisis = True
                final[i] = crisis_idx
            else:
                if raw[i] == crisis_idx:
                    final[i] = final[i - 1] if i > 0 else 0
        else:
            # Per uscire da crisis: 2 venerdì consecutivi non-crisis
            if i > 0 and raw[i] != crisis_idx and raw[i - 1] != crisis_idx:
                in_crisis = False
                final[i] = raw[i]
            else:
                final[i] = crisis_idx

    return final


def get_current_regime(db: Session) -> dict:
    """
    Restituisce il regime per l'ultimo venerdì disponibile.
    Per date <= 2025-12-26: usa regimi pre-calcolati.
    Per date > 2025-12-26: esegue HMM live sui dati freschi.
    """
    from config import DISPLAY_START
    from modules.backtest.service import _get_prices_from_db, _get_operational_fridays

    # Try live HMM inference first for 2026+ data
    try:
        spy_s = _get_prices_from_db("SPY", db)
        tlt_s = _get_prices_from_db("TLT", db)
        vix_s = _get_prices_from_db("VIX", db)

        if len(spy_s) > 60 and len(tlt_s) > 60 and len(vix_s) > 60:
            prices = {
                "SPY": pd.DataFrame({"Close": spy_s}),
                "TLT": pd.DataFrame({"Close": tlt_s}),
                "VIX": pd.DataFrame({"Close": vix_s}),
            }
            # Fix 6: Use operational fridays
            fridays = _get_operational_fridays(db)
            
            # Only consider Fridays in 2026+
            fridays_2026 = fridays[fridays >= DISPLAY_START]

            if len(fridays_2026) > 0:
                hmm_feats = compute_hmm_features(prices, fridays)
                if len(hmm_feats) > 2:
                    regimes = run_hmm_inference(hmm_feats)
                    if len(regimes) > 0 and "Regime_Final" in regimes.columns:
                        # Get the latest regime
                        last_idx = regimes.index[-1]
                        last_state = int(regimes.iloc[-1]["Regime_Final"])
                        last_fri = str(last_idx.date()) if hasattr(last_idx, 'date') else str(last_idx)

                        return {
                            "regime_id": last_state,
                            "regime_name": REGIME_NAMES.get(last_state, f"Stato {last_state}"),
                            "is_crisis": last_state == CRISIS_STATE_IDX,
                            "decay_value": 1.0,
                            "last_friday": last_fri,
                            "prob_crisis": 0.0,
                        }
    except Exception as e:
        print(f"[HMM] Live inference failed, falling back to pre-computed: {e}")

    # Fallback to pre-computed regimes
    precomputed = _load_precomputed_regimes()
    if len(precomputed) > 0 and "Regime_Final" in precomputed.columns:
        last_row = precomputed.iloc[-1]
        last_state = int(last_row["Regime_Final"])
        last_fri = str(precomputed.index[-1].date())

        prob_crisis = 0.0
        for col in precomputed.columns:
            if "Prob" in col and "2" in col:
                prob_crisis = float(last_row[col])

        return {
            "regime_id": last_state,
            "regime_name": REGIME_NAMES.get(last_state, f"Stato {last_state}"),
            "is_crisis": last_state == CRISIS_STATE_IDX,
            "decay_value": 1.0,
            "last_friday": last_fri,
            "prob_crisis": round(prob_crisis, 4),
        }

    return {
        "regime_id": 0, "regime_name": "N/D",
        "is_crisis": False, "decay_value": 1.0,
        "last_friday": "", "prob_crisis": 0.0
    }
