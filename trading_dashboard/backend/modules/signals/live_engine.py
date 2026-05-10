import yfinance as yf
import pandas_market_calendars as mcal
import pandas as pd
import numpy as np
import datetime
import pytz
import torch
import warnings
import os
import json
import pickle
import matplotlib.pyplot as plt
import seaborn as sns
import re
from pathlib import Path
from config import DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA, CRISIS_STATE_IDX, DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA

warnings.filterwarnings('ignore')
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

_LGB_MODEL = None
def get_lgb_model():
    global _LGB_MODEL
    if _LGB_MODEL is None:
        try:
            import lightgbm as lgb
            from config import LGB_MODEL_PATH
            import joblib
            pkl_path = LGB_MODEL_PATH.with_suffix(".pkl")
            if pkl_path.exists():
                _LGB_MODEL = joblib.load(pkl_path)
            elif LGB_MODEL_PATH.exists():
                _LGB_MODEL = joblib.load(LGB_MODEL_PATH) if str(LGB_MODEL_PATH).endswith(".pkl") else lgb.Booster(model_file=str(LGB_MODEL_PATH))
            print("[meta_labeler] LGB Model loaded.")
        except Exception as e:
            print(f"[meta_labeler] LGB Model load failed: {e}")
    return _LGB_MODEL

_TFM_MODEL = None
_CHRONOS_MODEL = None

def load_foundation_models():
    global _TFM_MODEL, _CHRONOS_MODEL
    has_gpu = torch.cuda.is_available()
    device_str = "cuda" if has_gpu else "cpu"
    dtype_chronos = torch.bfloat16 if has_gpu else torch.float32

    if _TFM_MODEL is None:
        try:
            import timesfm
            _TFM_MODEL = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", backend=device_str)
            print("[FOUNDATION MODELS] TimesFM loaded.")
        except Exception as e:
            print(f"[FOUNDATION MODELS] [WARNING] TimesFM load failed: {e}")

    if _CHRONOS_MODEL is None:
        try:
            from chronos import ChronosPipeline
            _CHRONOS_MODEL = ChronosPipeline.from_pretrained("amazon/chronos-t5-base", device_map=device_str, torch_dtype=dtype_chronos)
            print("[FOUNDATION MODELS] Chronos loaded.")
        except Exception as e:
            print(f"[FOUNDATION MODELS] [WARNING] Chronos load failed: {e}")

def run_live_execution():
    print("\n" + "="*90)
    print("AVVIO MODULO OPERATIVO LIVE (YFINANCE)")
    print("="*90)

    # ------------------------------------------------------------------------------
    # SETUP PERCORSI LOCALI E MAPPATURE
    # ------------------------------------------------------------------------------
    DATASET_DIR = Path(os.getenv("DATASET_DIR", "/app/models"))
    DATASET_DIR.mkdir(exist_ok=True, parents=True)

    BBG_TO_YF = {
        'SPY US Equity': 'SPY', 'TLT US Equity': 'TLT', 'GLD US Equity': 'GLD',
        'UUP US Equity': 'UUP', 'FXE US Equity': 'FXE', 'LQD US Equity': 'LQD',
        'IEF US Equity': 'IEF', 'SHY US Equity': 'SHY', 'XLF US Equity': 'XLF',
        'XLU US Equity': 'XLU', 'QQQ US Equity': 'QQQ', 'IWM US Equity': 'IWM',
        'MDY US Equity': 'MDY', 'DIA US Equity': 'DIA', 'XLY US Equity': 'XLY',
        'XLP US Equity': 'XLP', 'XLK US Equity': 'XLK', 'XLE US Equity': 'XLE',
        'XLV US Equity': 'XLV', 'XLI US Equity': 'XLI', 'XLB US Equity': 'XLB',
        'EEM US Equity': 'EEM', 'EFA US Equity': 'EFA', 'SLV US Equity': 'SLV',
        'SOXX US Equity': 'SOXX', 'VNQ US Equity': 'VNQ', 'SH US Equity': 'SH',
        'PSQ US Equity': 'PSQ', 'RWM US Equity': 'RWM', 'VIXY US Equity': 'VIXY'
    }
    YF_TICKERS = list(BBG_TO_YF.values())
    YF_TO_BBG = {v: k for k, v in BBG_TO_YF.items()}

    # ------------------------------------------------------------------------------
    # REGOLA 1: GESTIONE CALENDARIO OPERATIVO
    # ------------------------------------------------------------------------------
    print("[NOTA METODOLOGICA] In caso di ambiguità intraday, si assegna priorità allo Stop Loss.")

    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    nyse = mcal.get_calendar('NYSE')

    schedule = nyse.schedule(start_date=now - datetime.timedelta(days=30), end_date=now + datetime.timedelta(days=7))
    valid_market_dates = [d.date() for d in schedule.index]

    target_date = now.date() 
    is_friday = target_date.weekday() == 4
    market_closed = now.time() >= datetime.time(16, 5)

    if is_friday and market_closed and target_date in valid_market_dates:
        oper_date = pd.Timestamp(target_date)
    else:
        last_friday = target_date - datetime.timedelta(days=(target_date.weekday() - 4) % 7)
        if target_date.weekday() == 4 and not market_closed:
            last_friday -= datetime.timedelta(days=7) 
        
        while last_friday not in valid_market_dates:
            last_friday -= datetime.timedelta(days=1)
            
        oper_date = pd.Timestamp(last_friday)

    print(f"[CALENDARIO] Data operativa richiesta: {oper_date.date()}")

    # ------------------------------------------------------------------------------
    # REGOLA 2 E 3: DOWNLOAD YFINANCE E FALLBACK STORICO
    # ------------------------------------------------------------------------------
    start_dl = oper_date - datetime.timedelta(days=400) 
    print(f"[DOWNLOAD] Richiesta dati YFinance dal {start_dl.date()} al {oper_date.date()}...")

    yf_data = pd.DataFrame()
    live_data_available = True

    try:
        yf_data = yf.download(YF_TICKERS, start=start_dl, end=oper_date + datetime.timedelta(days=1), 
                              interval='1d', auto_adjust=True, progress=False)['Close']
        
        yf_data.index = yf_data.index.tz_localize(None)
        yf_data = yf_data[yf_data.index.isin(valid_market_dates)]
        
        missing_pct = yf_data.isna().mean()
        for col, pct in missing_pct.items():
            if pct > 0.10:
                print(f"[WARNING] Ticker {col} ha >10% dati mancanti. Escluso.")
                yf_data = yf_data.drop(columns=[col])
        yf_data = yf_data.ffill().dropna()
    except Exception as e:
        print(f"[WARNING] Fallimento download YFinance: {e}")

    # FALLBACK STORICO ULTRA-ROBUSTO
    if yf_data.empty or len(yf_data) < 100:
        print("[FALLBACK] YFinance non disponibile. Accesso a DATASET_INFERENCE_READY.parquet...")
        live_data_available = False
        
        try:
            PATH_HIST = DATASET_DIR / "DATASET_INFERENCE_READY.parquet" 
            if PATH_HIST.exists():
                df_hist = pd.read_parquet(PATH_HIST)
                
                ticker_col = next((c for c in df_hist.columns if str(c).lower() in ['etf_traded', 'etf_traded_x', 'ticker', 'symbol', 'asset']), None)
                price_col = next((c for c in df_hist.columns if str(c).lower() in ['close', 'adj close', 'price', 'adj_close']), None)
                date_col = next((c for c in df_hist.columns if str(c).lower() in ['date', 'data', 'index']), None)
                
                if ticker_col and price_col and date_col:
                    yf_data = df_hist.pivot(index=date_col, columns=ticker_col, values=price_col).dropna(how='all')
                else:
                    yf_data = df_hist.copy()
                    if date_col:
                        yf_data.set_index(date_col, inplace=True)
                
                yf_data.index = pd.to_datetime(yf_data.index)
                yf_data = yf_data[yf_data.index <= pd.Timestamp(now.date())].copy()
                
                if yf_data.empty: raise Exception("Nessuna data passata disponibile nel file.")
                    
                oper_date = pd.Timestamp(yf_data.index[-1])
                print(f"[CALENDARIO CORRETTO] Data operativa riallineata all'ultima disponibile nel file: {oper_date.date()}")
                
            else:
                raise FileNotFoundError(f"File non trovato: {PATH_HIST}")
        except Exception as e:
            print(f"[ERRORE FATALE] Fallback fallito: {e}")
            import sys; sys.exit(1)

    # ------------------------------------------------------------------------------
    # ALLINEAMENTO DINAMICO COLONNE (LA PRESSA IDRAULICA)
    # ------------------------------------------------------------------------------
    print("[ALLINEAMENTO] Normalizzazione dinamica dei ticker in corso...")

    if isinstance(yf_data.columns, pd.MultiIndex):
        yf_data.columns = [str(c[-1]).strip() for c in yf_data.columns]

    aligned_columns = {}
    for col in yf_data.columns:
        col_str = str(col).upper().replace('_', ' ').replace(',', ' ').replace("'", "").replace('"', '').replace('(', '').replace(')', '')
        
        matched = False
        for yf_tick in YF_TICKERS:
            if re.search(r'\b' + yf_tick + r'\b', col_str):
                aligned_columns[col] = yf_tick
                matched = True
                break
                
        if not matched:
            for bbg_tick, yf_tick in BBG_TO_YF.items():
                if bbg_tick.upper() in col_str:
                    aligned_columns[col] = yf_tick
                    break

    yf_data.rename(columns=aligned_columns, inplace=True)
    yf_data = yf_data.loc[:, ~yf_data.columns.duplicated()]

    valid_cols = [c for c in yf_data.columns if c in YF_TICKERS]
    yf_data = yf_data[valid_cols]

    print(f"[ALLINEAMENTO] Ticker validi mappati per il calcolo: {len(valid_cols)}/{len(YF_TICKERS)}")

    # ------------------------------------------------------------------------------
    # REGOLA 4 E 5: CALCOLO LOG-RATIO E FEATURE ML
    # ------------------------------------------------------------------------------
    print("\n[PREPROCESSING] Calcolo Log-Ratios e Mappatura Dinamica Feature ML...")
    df_live_ratios = pd.DataFrame(index=yf_data.index)
    df_live_ml = pd.DataFrame(index=yf_data.index)

    RATIOS_DEF = {
        'R01_Risk Sentiment': ('SPY', 'TLT'), 'R02_Real Rates Hedge': ('GLD', 'TLT'),
        'R03_Safe Haven Pivot': ('GLD', 'SPY'), 'R04_Currency War': ('UUP', 'FXE'),
        'R05_Credit Stress': ('LQD', 'IEF'), 'R06_Yield Curve': ('TLT', 'SHY'),
        'R07_Rate Bets': ('XLF', 'XLU'), 'R08_Tech Alpha': ('QQQ', 'SPY'),
        'R09_Small Cap Health': ('IWM', 'SPY'), 'R10_Mid Cap Cycle': ('MDY', 'SPY'),
        'R11_Value Rotation': ('DIA', 'QQQ'), 'R12_Consumer Cycle': ('XLY', 'XLP'),
        'R13_New/Old Economy': ('XLK', 'XLE'), 'R14_Defensive Rotation': ('XLV', 'SPY'),
        'R15_Industrial Momentum': ('XLI', 'SPY'), 'R16_Commodity Infl Pulse': ('XLE', 'XLB'),
        'R17_Global Risk': ('EEM', 'EFA'), 'R18_Industrial Cycle': ('GLD', 'SLV'),
        'R19_Semiconductor Cycle': ('SOXX', 'SPY'), 'R20_Real Estate vs Rates': ('VNQ', 'IEF')
    }

    try:
        for r_name, (num, den) in RATIOS_DEF.items():
            if num in yf_data.columns and den in yf_data.columns:
                raw_ratio = np.log(yf_data[num] / yf_data[den])
                df_live_ratios[r_name] = (raw_ratio - raw_ratio.rolling(252, min_periods=20).mean()) / raw_ratio.rolling(252, min_periods=20).std()

        clf_lgb_test = get_lgb_model()
        if clf_lgb_test is not None:
            csm_features = []
            feature_names = clf_lgb_test.feature_name() if hasattr(clf_lgb_test, 'feature_name') else clf_lgb_test.feature_name_ if hasattr(clf_lgb_test, 'feature_name_') else []
            for fname in feature_names:
                if not fname.startswith('ML_FEAT_'): continue
                
                if 'CSM' in fname:
                    csm_features.append(fname)
                    continue
                
                target_ratio = None
                for r in RATIOS_DEF.keys():
                    if r in fname or r.replace(' ', '_') in fname:
                        target_ratio = r
                        break
                
                if not target_ratio or target_ratio not in df_live_ratios.columns:
                    df_live_ml[fname] = 0.0 
                    continue
                
                s = df_live_ratios[target_ratio]
                
                if 'Mom' in fname:
                    if '1w' in fname or '5' in fname: df_live_ml[fname] = s.pct_change(5)
                    elif '12w' in fname or '60' in fname: df_live_ml[fname] = s.pct_change(60)
                    else: df_live_ml[fname] = s.pct_change(20) 
                elif 'EMA' in fname: df_live_ml[fname] = s.ewm(span=12).mean() - s.ewm(span=26).mean()
                elif 'ZScore' in fname: df_live_ml[fname] = (s - s.rolling(60).mean()) / s.rolling(60).std()
                elif 'VTS' in fname: df_live_ml[fname] = s.rolling(20).std() / s.rolling(60).std()
                elif 'Shock' in fname: df_live_ml[fname] = s.diff(1) / s.rolling(20).std()
                else: df_live_ml[fname] = s.pct_change(5) 
                    
            if csm_features:
                temp_mom = pd.DataFrame(index=df_live_ratios.index)
                for r_name in RATIOS_DEF.keys():
                    if r_name in df_live_ratios.columns: 
                        temp_mom[r_name] = df_live_ratios[r_name].pct_change(20)
                ranks = temp_mom.rank(axis=1, pct=True)
                
                for fname in csm_features:
                    target_ratio = None
                    for r in RATIOS_DEF.keys():
                        if r in fname or r.replace(' ', '_') in fname:
                            target_ratio = r
                            break
                    if target_ratio and target_ratio in ranks.columns: 
                        df_live_ml[fname] = ranks[target_ratio]
                    else:
                        df_live_ml[fname] = 0.5 

        df_live_ml = df_live_ml.shift(1).ffill().bfill().fillna(0.0)
        final_ml_features = df_live_ml.iloc[-1].to_dict() 
        
        print(f"[PREPROCESSING] Mappatura completata. ({len(final_ml_features)} features estratte rigorosamente).")
    except Exception as e:
        print(f"[ERRORE CRITICO] Generazione feature ML fallita: {e}")
        final_ml_features = {}

    # ------------------------------------------------------------------------------
    # FUNZIONE DI INIZIALIZZAZIONE CACHE SICURA
    # ------------------------------------------------------------------------------
    def load_cache_safe(cache_path):
        default_cols = ['Date', 'Ratio', 'TFM_t1', 'TFM_t5', 'TFM_t20', 'CHR_Median_t5', 'CHR_Width_t5']
        if not cache_path.exists():
            return pd.DataFrame(columns=default_cols)
        try:
            df = pd.read_parquet(cache_path)
        except Exception as e:
            print(f"  > Errore lettura cache: {e}. Verrà ricreata.")
            return pd.DataFrame(columns=default_cols)
            
        if df.empty: return pd.DataFrame(columns=default_cols)
        
        if 'Date' not in df.columns:
            possible_date_cols = [col for col in df.columns if 'date' in col.lower()]
            if possible_date_cols:
                df.rename(columns={possible_date_cols[0]: 'Date'}, inplace=True)
            elif df.index.name == 'Date' or isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                if 'index' in df.columns: df.rename(columns={'index': 'Date'}, inplace=True)
            else:
                backup = cache_path.with_suffix('.old.parquet')
                cache_path.rename(backup)
                return pd.DataFrame(columns=default_cols)
        
        if df['Date'].dtype != 'object': df['Date'] = df['Date'].astype(str)
        for col in default_cols:
            if col not in df.columns: df[col] = np.nan
        return df

    # ------------------------------------------------------------------------------
    # REGOLA 6: INFERENZA FOUNDATION MODELS (BATCH PROCESSING SEPARATO)
    # ------------------------------------------------------------------------------
    CACHE_PATH = DATASET_DIR / "FM_LIVE_CACHE.parquet"
    has_gpu = torch.cuda.is_available()
    device_str = "cuda" if has_gpu else "cpu"
    dtype_chronos = torch.bfloat16 if has_gpu else torch.float32

    print(f"\n[FOUNDATION MODELS] Hardware: {'GPU' if has_gpu else 'CPU'} (Batch Optimizzato)")
    fm_predictions = {}
    df_cache = load_cache_safe(CACHE_PATH)
    cached_keys = set(zip(df_cache['Date'].astype(str), df_cache['Ratio']))

    needed_ratios = [r for r in RATIOS_DEF.keys() if (str(oper_date.date()), r) not in cached_keys]

    if needed_ratios:
        print(f"  > Ratio da calcolare (cold start per la data {oper_date.date()}): {len(needed_ratios)}")
        batch_sequences, batch_ratio_names = [], []
        
        for r_name in needed_ratios:
            if r_name in df_live_ratios.columns:
                hist = df_live_ratios[r_name].dropna().values
                if len(hist) > 0:
                    batch_sequences.append(hist[-512:])
                    batch_ratio_names.append(r_name)
        
        if batch_sequences:
            print(f"  > Caricamento modelli in VRAM/RAM ({device_str})...")
            
            # --- BATCH TIMESFM INDIPENDENTE ---
            tfm = _TFM_MODEL
            if tfm is not None:
                try:
                    print("  > Esecuzione TimesFM (Batch vettorizzato)...")
                    tfm_p_res, _ = tfm.forecast(inputs=batch_sequences, horizon=20)
                except Exception as e:
                    print(f"  > [WARNING] Inferenza TimesFM fallita ({e}). Uso parametri standard.")
            
            # --- BATCH CHRONOS INDIPENDENTE ---
            chronos = _CHRONOS_MODEL
            if chronos is not None:
                try:
                    print("  > Esecuzione Chronos (Batch con Padding vettorizzato)...")
                    max_len = max(len(seq) for seq in batch_sequences)
                    padded = [np.pad(s, (max_len - len(s), 0), mode='edge') if len(s) < max_len else s for s in batch_sequences]
                    batch_tensor = torch.tensor(np.array(padded), dtype=torch.float32)
                    
                    with torch.no_grad():
                        chronos_out = chronos.predict(batch_tensor, prediction_length=20, num_samples=100, limit_prediction_length=False)
                    samples_all = chronos_out.cpu().numpy() 
                except Exception as e:
                    print(f"  > [WARNING] Inferenza Chronos fallita ({e}). Uso parametri standard.")

            print("  > Assemblaggio e salvataggio risultati...")
            new_rows = []
            for idx, r_name in enumerate(batch_ratio_names):
                # Assegna valori sicuri se uno dei modelli è fallito
                pred_tfm = tfm_p_res[idx] if 'tfm_p_res' in locals() else [0.001] * 20
                
                if 'samples_all' in locals():
                    samples_t5 = samples_all[idx, :, 4] 
                    med_val = float(np.median(samples_t5))
                    width_val = float(np.percentile(samples_t5, 95) - np.percentile(samples_t5, 5))
                else:
                    med_val, width_val = 0.005, 0.15
                
                res = {
                    'TFM_t1': pred_tfm[0], 'TFM_t5': pred_tfm[4], 'TFM_t20': pred_tfm[19],
                    'CHR_Median_t5': med_val, 'CHR_Width_t5': width_val
                }
                fm_predictions[r_name] = res
                new_rows.append({'Date': str(oper_date.date()), 'Ratio': r_name, **res})
                print(f"  > [BATCH OK] {r_name}")
            
            if new_rows:
                df_new = pd.DataFrame(new_rows, columns=['Date', 'Ratio', 'TFM_t1', 'TFM_t5', 'TFM_t20', 'CHR_Median_t5', 'CHR_Width_t5'])
                df_cache = pd.concat([df_cache, df_new], ignore_index=True).drop_duplicates(subset=['Date', 'Ratio'], keep='last')
                df_cache.to_parquet(CACHE_PATH, index=False)

    # Ripopola dizionario e applica Hard Fallback per ratio assenti
    for _, row in df_cache[df_cache['Date'].astype(str) == str(oper_date.date())].iterrows():
        if row['Ratio'] not in fm_predictions:
            fm_predictions[row['Ratio']] = {k: row[k] for k in ['TFM_t1', 'TFM_t5', 'TFM_t20', 'CHR_Median_t5', 'CHR_Width_t5']}

    for r_name in RATIOS_DEF.keys():
        if r_name not in fm_predictions:
            fm_predictions[r_name] = {'TFM_t1': 0.001, 'TFM_t5': 0.005, 'TFM_t20': 0.02, 'CHR_Median_t5': 0.005, 'CHR_Width_t5': 0.15}

    # ------------------------------------------------------------------------------
    # REGOLA 8: INFERENZA HMM CON ESTRAZIONE DIZIONARIO SICURA
    # ------------------------------------------------------------------------------
    print("\n[REGIME DETECTION] Inferenza HMM...")
    current_regime = 0 
    try:
        PATH_HMM = DATASET_DIR / "HMM_MODEL.pkl"
        if PATH_HMM.exists():
            with open(PATH_HMM, "rb") as f:
                loaded_obj = pickle.load(f)
                
                # SCASSINATORE DIZIONARI: Cerca l'oggetto col metodo predict()
                if isinstance(loaded_obj, dict):
                    for k, v in loaded_obj.items():
                        if hasattr(v, 'predict'):
                            hmm_model = v
                            break
                else:
                    hmm_model = loaded_obj
                    
                yf_macro = yf_data[['SPY', 'TLT', 'VIXY']].copy() if 'VIXY' in yf_data else yf_data[['SPY', 'TLT']].copy()
                if 'VIXY' not in yf_macro: yf_macro['VIXY'] = 0.0 
                
                iso_cal = yf_macro.index.isocalendar()
                yf_macro['Year'], yf_macro['Week'] = iso_cal.year, iso_cal.week
                weekly_macro = yf_macro.groupby(['Year', 'Week']).last().pct_change().dropna()
                
                if len(weekly_macro) >= 52:
                    hmm_features_array = weekly_macro.tail(52).values
                    raw_regimes = hmm_model.predict(hmm_features_array)
                    final = list(raw_regimes)
                    in_crisis = False
                    for i in range(1, len(final)):
                        if not in_crisis:
                            if raw_regimes[i] == CRISIS_STATE_IDX and raw_regimes[i-1] == CRISIS_STATE_IDX:
                                in_crisis = True; final[i] = CRISIS_STATE_IDX; final[i-1] = CRISIS_STATE_IDX 
                        else:
                            if raw_regimes[i] != CRISIS_STATE_IDX and raw_regimes[i-1] != CRISIS_STATE_IDX:
                                in_crisis = False; final[i] = raw_regimes[i]
                            else: final[i] = CRISIS_STATE_IDX
                    current_regime = final[-1] 
                    print(f"[REGIME] HMM Rilevato (su {len(hmm_features_array)} settimane): Stato {current_regime}")
                else:
                    print(f"[WARNING] Storico YFinance insufficiente per HMM ({len(weekly_macro)}/52 sett). Forzato Stato 0.")
        else:
            print(f"[REGIME] Modello HMM non trovato. Assunto regime NORMALE (Stato 0).")
    except Exception as e:
        print(f"[WARNING] Errore HMM: {e}. Fallback a Regime Normale.")

    # ------------------------------------------------------------------------------
    # REGOLA 9: RISCHI (HRP E SIGMOID 52 WEEKS)
    # ------------------------------------------------------------------------------
    print("[RISK MANAGEMENT] Calcolo pesi HRP e Sigmoid Decay...")

    crisis_etfs_bbg = ['SH US Equity', 'PSQ US Equity', 'RWM US Equity', 'VIXY US Equity']
    active_tickers = [YF_TO_BBG[tk] for tk in yf_data.columns if tk in YF_TO_BBG and YF_TO_BBG[tk] not in crisis_etfs_bbg]

    EQUAL_WEIGHT = 1.0 / len(active_tickers) if len(active_tickers) > 0 else 0.0
    hrp_weights = {ticker: EQUAL_WEIGHT for ticker in active_tickers}

    try:
        PATH_HRP = DATASET_DIR / "HRP_WEIGHTS.parquet"
        if PATH_HRP.exists():
            df_hrp = pd.read_parquet(PATH_HRP)
            last_hrp = df_hrp.iloc[-1].to_dict()
            hrp_weights.update({k: v for k, v in last_hrp.items() if k in hrp_weights})
    except Exception as e:
        print(f"[WARNING] Errore caricamento HRP: {e}")

    try:
        rets_52w = yf_data.iloc[-252:].pct_change().dropna()
        corr_matrix = rets_52w.corr().values
        avg_corr = np.nanmean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)])
        sigmoid_decay = 1.0 / (1.0 + np.exp(DEFAULT_K_SIGMOID * (avg_corr - DEFAULT_C_SOGLIA)))
    except Exception as e:
        sigmoid_decay = 1.0

    # ------------------------------------------------------------------------------
    # REGOLA 7: EXACT MAPPING E WATERFILLING
    # ------------------------------------------------------------------------------
    print("[META-LABELING] Calcolo reale della Bet_Quality con LightGBM...")
    signals = []

    if current_regime == CRISIS_STATE_IDX:
        print("\n[CRISIS STATE] Disattivazione Universe Normale. Attivazione Crisis Basket.")
        for c_etf in crisis_etfs_bbg:
            signals.append({'Ratio': 'CRISIS_BASKET', 'ETF_Long': c_etf, 'Bet_Quality': 1.0, 
                            'HRP_Weight': 0.25, 'Sigmoid_Decay': 1.0, 'Weight_Finale': 0.25, 'Segnale': 'ESEGUI'})
    else:
        raw_weights = {}
        check_done = False
        clf_lgb_test = get_lgb_model()
        
        for r_name, (num, den) in RATIOS_DEF.items():
            long_ticker = f"{num} US Equity"
            hrp_w = hrp_weights.get(long_ticker, EQUAL_WEIGHT)
            
            fm_feats = fm_predictions.get(r_name, {})
            X_dict = {**fm_feats, **final_ml_features}
            
            if clf_lgb_test is not None:
                X_row = {}
                matched = 0
                feature_names = clf_lgb_test.feature_name() if hasattr(clf_lgb_test, 'feature_name') else clf_lgb_test.feature_name_ if hasattr(clf_lgb_test, 'feature_name_') else []
                for fname in feature_names:
                    if fname in X_dict:
                        X_row[fname] = X_dict[fname]; matched += 1
                    else: X_row[fname] = 0.0
                
                if not check_done and feature_names:
                    tot_feat = len(feature_names)
                    miss_ratio = 1 - (matched / tot_feat)
                    if miss_ratio > 0.20:
                        print(f"[WARNING] Troppe feature non allineate ({miss_ratio*100:.1f}%).")
                    check_done = True
                    
                X_df = pd.DataFrame([X_row], columns=feature_names)
                try:
                    if hasattr(clf_lgb_test, 'predict_proba'):
                        bq = float(clf_lgb_test.predict_proba(X_df)[0, 1])
                    else:
                        bq = float(clf_lgb_test.predict(X_df)[0])
                except:
                    bq = 0.0
            else: bq = 0.0 
            
            signals.append({'Ratio': r_name, 'ETF_Long': long_ticker, 'Bet_Quality': bq, 
                            'HRP_Weight': hrp_w, 'Sigmoid_Decay': sigmoid_decay})
            if bq > DEFAULT_BET_QUALITY:
                raw_weights[long_ticker] = (DEFAULT_HRP_ALPHA * hrp_w) + ((1 - DEFAULT_HRP_ALPHA) * EQUAL_WEIGHT)

        if len(raw_weights) > 0:
            sum_w = sum(raw_weights.values())
            raw_weights = {k: v/sum_w for k, v in raw_weights.items()} 
            w_array = np.array(list(raw_weights.values()))
            keys = list(raw_weights.keys())
            
            while True:
                capped_mask = w_array > 0.15
                if not capped_mask.any(): break
                excess = np.sum(w_array[capped_mask] - 0.15)
                w_array[capped_mask] = 0.15
                non_capped_mask = ~capped_mask
                if not non_capped_mask.any(): break
                w_array[non_capped_mask] += excess * (w_array[non_capped_mask] / w_array[non_capped_mask].sum())
            
            final_weights = dict(zip(keys, w_array))
        else: final_weights = {}

        for sig in signals:
            if sig['Bet_Quality'] > DEFAULT_BET_QUALITY:
                sig['Weight_Finale'] = final_weights.get(sig['ETF_Long'], 0.0) * sigmoid_decay
                sig['Segnale'] = 'ESEGUI'
            else:
                sig['Weight_Finale'] = 0.0; sig['Segnale'] = 'SKIP'

    # ------------------------------------------------------------------------------
    # REGOLA 10: OUTPUT E GRAFICI
    # ------------------------------------------------------------------------------
    df_out = pd.DataFrame(signals)
    print("\n" + "="*90)
    print(f"TABELLA ALLOCAZIONE OPERATIVA — Data: {oper_date.date()} {'(Storico Simulato)' if not live_data_available else '(Live)'}")
    print("="*90)

    df_print = df_out.copy()
    for col in ['Bet_Quality', 'HRP_Weight', 'Sigmoid_Decay', 'Weight_Finale']:
        df_print[col] = df_print[col].astype(float).round(4)
    print(df_print.to_string(index=False))

    peso_tot = df_out['Weight_Finale'].sum()
    print("-" * 90)
    print(f"RIEPILOGO | Regime: {current_regime} | Attivi: {len(df_out[df_out['Segnale']=='ESEGUI'])} | "
          f"Scartati: {len(df_out[df_out['Segnale']=='SKIP'])} | Peso Allocato: {peso_tot:.2f} | Decay: {sigmoid_decay:.3f}")
    print("=" * 90)
    
    return {"status": "ok", "date": str(oper_date.date()), "signals": df_out.to_dict(orient="records")}
