"""
Feature engineering: log-ratios, ML features per i 20 ratio, macro features,
volatility features, spread shock, cross-sectional momentum, market breadth.
Replica esatta delle 192 feature del DATASET_INFERENCE_READY della tesi.
"""
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from config import RATIOS, MACRO_YFINANCE, MOVE_PROXY_SCALE


def compute_log_ratios(prices: dict) -> pd.DataFrame:
    """
    Calcola i 20 log-ratio dalla dict di prezzi.
    Input:  prices = { "SPY": DataFrame(Close, ...), "TLT": ..., ... }
    Output: DataFrame con colonne R01..R20, index = date
    """
    ratios = {}
    for ratio_id, (num, den) in RATIOS.items():
        if num not in prices or den not in prices:
            continue
        p_num = prices[num]["Close"]
        p_den = prices[den]["Close"]
        common = p_num.index.intersection(p_den.index)
        if len(common) == 0:
            continue
        ratios[ratio_id] = np.log(p_num.reindex(common)) - np.log(p_den.reindex(common))

    if not ratios:
        return pd.DataFrame()

    df = pd.DataFrame(ratios)
    df.sort_index(inplace=True)
    return df


def compute_ml_features(prices: dict, log_ratios: pd.DataFrame) -> pd.DataFrame:
    """
    Per ogni ratio, calcola 4 feature tecniche con LAG +1 giorno.
    Feature per ratio:
      - EMA_Cross:   EMA(10) - EMA(50)
      - Mom_Acc:     diff(20) - shift(20).diff(20)
      - ZScore_252:  (ratio - rolling_mean_252) / rolling_std_252, clipped [-5, 5]
      - VTS:         std(10) / std(60)

    Output: DataFrame index=date, colonne = ML_FEAT_{ratio_id}_{feat_name}
    """
    all_features = {}

    for ratio_id in log_ratios.columns:
        series = log_ratios[ratio_id].dropna()
        if len(series) < 252:
            continue

        ema10 = series.ewm(span=10, adjust=False).mean()
        ema50 = series.ewm(span=50, adjust=False).mean()
        ema_cross = ema10 - ema50

        mom20 = series.diff(20)
        mom_acc = mom20 - mom20.shift(20)

        roll_mean = series.rolling(252).mean()
        roll_std = series.rolling(252).std() + 1e-9
        zscore = ((series - roll_mean) / roll_std).clip(-5, 5)

        std10 = series.rolling(10).std()
        std60 = series.rolling(60).std() + 1e-9
        vts = std10 / std60

        prefix = f"ML_FEAT_{ratio_id}"
        all_features[f"{prefix}_EMA_Cross"] = ema_cross
        all_features[f"{prefix}_Mom_Acc"] = mom_acc
        all_features[f"{prefix}_ZScore_252"] = zscore
        all_features[f"{prefix}_VTS"] = vts

    if not all_features:
        return pd.DataFrame()

    df = pd.DataFrame(all_features)
    df = df.shift(1)  # LAG +1 giorno
    df.dropna(how="all", inplace=True)
    return df


def compute_macro_features(prices: dict, db: Session = None) -> pd.DataFrame:
    """
    Computes 8 macro features + 5 derived features.
    Macro: VIX, MOVE, USGG10YR, USGG2YR, US0003M, CONSSENT, CPI_YOY, DXY
    Derived: YieldCurve_Spread, Real_Yield, CrossVol_Ratio, MoneyMarket_Stress, VIX_Premium
    """
    macro = {}

    # VIX from prices
    if "VIX" in prices:
        macro["VIX"] = prices["VIX"]["Close"]
    elif "^VIX" in prices:
        macro["VIX"] = prices["^VIX"]["Close"]

    # USGG10YR from TNX (YFinance ^TNX = 10Y yield)
    if "TNX" in prices:
        macro["USGG10YR"] = prices["TNX"]["Close"]
    elif "^TNX" in prices:
        macro["USGG10YR"] = prices["^TNX"]["Close"]

    # US0003M from IRX (YFinance ^IRX = 3M T-bill)
    if "IRX" in prices:
        macro["US0003M"] = prices["IRX"]["Close"]
    elif "^IRX" in prices:
        macro["US0003M"] = prices["^IRX"]["Close"]

    # DXY
    if "DXY" in prices:
        macro["DXY"] = prices["DXY"]["Close"]
    elif "DX-Y.NYB" in prices:
        macro["DXY"] = prices["DX-Y.NYB"]["Close"]

    # MOVE proxy: TLT 20-day realized vol
    if "TLT" in prices:
        tlt_ret = prices["TLT"]["Close"].pct_change()
        macro["MOVE"] = tlt_ret.rolling(20).std() * np.sqrt(252) * MOVE_PROXY_SCALE

    # From MacroCache (EODHD data)
    if db is not None:
        from database.models import MacroCache

        for indicator in ["USGG2YR", "CPI_YOY", "CONSSENT"]:
            rows = (db.query(MacroCache)
                      .filter(MacroCache.indicator == indicator)
                      .order_by(MacroCache.date.asc())
                      .all())
            if rows:
                macro[indicator] = pd.Series(
                    {r.date: r.value for r in rows}, dtype=float
                )

    if not macro:
        return pd.DataFrame()

    # Align all to common index
    df = pd.DataFrame(macro)
    df.sort_index(inplace=True)
    df = df.ffill()  # Forward fill for monthly/sparse data

    # Rename to match thesis columns
    rename_map = {col: f"ML_FEAT_MACRO_{col}" for col in df.columns}
    df = df.rename(columns=rename_map)

    # Derived features
    derived = pd.DataFrame(index=df.index)

    if "ML_FEAT_MACRO_USGG10YR" in df and "ML_FEAT_MACRO_USGG2YR" in df:
        derived["ML_FEAT_M01_YieldCurve_Spread"] = (
            df["ML_FEAT_MACRO_USGG10YR"] - df["ML_FEAT_MACRO_USGG2YR"]
        )
    if "ML_FEAT_MACRO_USGG10YR" in df and "ML_FEAT_MACRO_CPI_YOY" in df:
        derived["ML_FEAT_M02_Real_Yield"] = (
            df["ML_FEAT_MACRO_USGG10YR"] - df["ML_FEAT_MACRO_CPI_YOY"]
        )
    if "ML_FEAT_MACRO_VIX" in df and "ML_FEAT_MACRO_MOVE" in df:
        derived["ML_FEAT_M03_CrossVol_Ratio"] = (
            df["ML_FEAT_MACRO_VIX"] / (df["ML_FEAT_MACRO_MOVE"] + 1e-9)
        )
    if "ML_FEAT_MACRO_US0003M" in df and "ML_FEAT_MACRO_USGG2YR" in df:
        derived["ML_FEAT_M04_MoneyMarket_Stress"] = (
            df["ML_FEAT_MACRO_US0003M"] - df["ML_FEAT_MACRO_USGG2YR"]
        )
    if "ML_FEAT_MACRO_VIX" in df:
        # VIX Premium = VIX - SPY 20-day realized vol (annualized)
        spy_rvol = pd.Series(dtype=float)
        for key in ["SPY"]:
            if key in prices:
                spy_ret = prices[key]["Close"].pct_change()
                spy_rvol = spy_ret.rolling(20).std() * np.sqrt(252) * 100
                break
        if len(spy_rvol) > 0:
            spy_rvol_aligned = spy_rvol.reindex(df.index, method="ffill")
            derived["ML_FEAT_M05_VIX_Premium"] = (
                df["ML_FEAT_MACRO_VIX"] - spy_rvol_aligned
            )

    result = pd.concat([df, derived], axis=1)
    # Apply lag +1
    result = result.shift(1)
    return result


def compute_volatility_features(prices: dict) -> pd.DataFrame:
    """
    Computes ~11 volatility features:
    - MKT vol indices (realized vol of SPY, QQQ, IWM, EFA, EEM)
    - Equity vol (SPY, QQQ aggregated)
    - Bond vol (TLT, IEF)
    - Alt vol (GLD, VIXY)
    - Realized vol for SPY, TLT, GLD, VIXY
    """
    vol_features = {}

    # Market vol: 20-day realized vol (annualized) for major indices
    mkt_tickers = ["SPY", "QQQ", "IWM", "EFA", "EEM"]
    for i, ticker in enumerate(mkt_tickers, 1):
        if ticker in prices:
            ret = prices[ticker]["Close"].pct_change()
            vol_features[f"ML_FEAT_VOL_MKT_{i:02d}"] = (
                ret.rolling(20).std() * np.sqrt(252)
            )

    # Equity vol aggregate
    eq_tickers = ["SPY", "QQQ"]
    eq_vols = []
    for ticker in eq_tickers:
        if ticker in prices:
            ret = prices[ticker]["Close"].pct_change()
            eq_vols.append(ret.rolling(20).std() * np.sqrt(252))
    if eq_vols:
        for i, v in enumerate(eq_vols, 1):
            vol_features[f"ML_FEAT_VOL_EQ_{i:02d}"] = v

    # Bond vol
    bd_tickers = ["TLT", "IEF"]
    for i, ticker in enumerate(bd_tickers, 1):
        if ticker in prices:
            ret = prices[ticker]["Close"].pct_change()
            vol_features[f"ML_FEAT_VOL_BD_{i:02d}"] = (
                ret.rolling(20).std() * np.sqrt(252)
            )

    # Alternative vol
    alt_tickers = ["GLD", "VIXY"]
    for i, ticker in enumerate(alt_tickers, 1):
        if ticker in prices:
            ret = prices[ticker]["Close"].pct_change()
            vol_features[f"ML_FEAT_VOL_ALT_{i:02d}"] = (
                ret.rolling(20).std() * np.sqrt(252)
            )

    # Realized vol (60-day) for key assets
    rvol_tickers = ["SPY", "TLT", "GLD", "VIXY"]
    for ticker in rvol_tickers:
        if ticker in prices:
            ret = prices[ticker]["Close"].pct_change()
            vol_features[f"ML_FEAT_VOL_{ticker}_RVOL"] = (
                ret.rolling(60).std() * np.sqrt(252)
            )

    if not vol_features:
        return pd.DataFrame()

    df = pd.DataFrame(vol_features)
    df = df.shift(1)  # LAG +1
    return df


def compute_spread_features(prices: dict) -> pd.DataFrame:
    """
    Computes spread shock features: (High-Low)/Close as bid-ask proxy.
    One feature per tradable asset (24 assets).
    """
    spread_tickers = [
        "SPY", "QQQ", "IWM", "MDY", "DIA", "EFA", "EEM",
        "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU",
        "XLV", "XLY", "IYR", "VNQ", "SOXX",
        "TLT", "IEF", "SHY", "LQD", "GLD"
    ]

    spread_features = {}
    for ticker in spread_tickers:
        if ticker in prices:
            p = prices[ticker]
            if "High" in p and "Low" in p and "Close" in p:
                high = p["High"]
                low = p["Low"]
                close = p["Close"]
                spread = (high - low) / (close + 1e-9)
                # Compute rolling z-score of spread shock
                roll_m = spread.rolling(60).mean()
                roll_s = spread.rolling(60).std() + 1e-9
                spread_z = ((spread - roll_m) / roll_s).clip(-5, 5)
                spread_features[f"ML_FEAT_L02_{ticker}_US_Equity_SpreadShock"] = spread_z

    if not spread_features:
        return pd.DataFrame()

    df = pd.DataFrame(spread_features)
    df = df.shift(1)  # LAG +1
    return df


def compute_csm_features(prices: dict) -> pd.DataFrame:
    """
    Cross-Sectional Momentum: rank each asset's 20-day return
    relative to all other assets, then normalize to [-1, 1].
    """
    csm_tickers = [
        "SPY", "QQQ", "IWM", "MDY", "DIA", "EFA", "EEM",
        "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU",
        "XLV", "XLY", "IYR", "VNQ", "SOXX",
        "TLT", "IEF", "SHY", "LQD", "GLD"
    ]

    returns_20d = {}
    for ticker in csm_tickers:
        if ticker in prices:
            close = prices[ticker]["Close"]
            returns_20d[ticker] = close.pct_change(20)

    if len(returns_20d) < 5:
        return pd.DataFrame()

    ret_df = pd.DataFrame(returns_20d)
    # Cross-sectional rank (normalized to [-1, 1])
    ranked = ret_df.rank(axis=1, pct=True) * 2 - 1

    csm_features = {}
    for ticker in ranked.columns:
        csm_features[f"ML_FEAT_CSM_{ticker}_US_Equity"] = ranked[ticker]

    df = pd.DataFrame(csm_features)
    df = df.shift(1)  # LAG +1
    return df


def compute_breadth_feature(prices: dict) -> pd.DataFrame:
    """
    Market Breadth: fraction of ETFs above their 200-day moving average.
    """
    breadth_tickers = [
        "SPY", "QQQ", "IWM", "MDY", "DIA", "EFA", "EEM",
        "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU",
        "XLV", "XLY", "IYR", "VNQ", "SOXX",
        "TLT", "IEF", "SHY", "LQD", "GLD", "SLV"
    ]

    above_ma200 = {}
    for ticker in breadth_tickers:
        if ticker in prices:
            close = prices[ticker]["Close"]
            ma200 = close.rolling(200).mean()
            above_ma200[ticker] = (close > ma200).astype(float)

    if not above_ma200:
        return pd.DataFrame()

    above_df = pd.DataFrame(above_ma200)
    breadth = above_df.mean(axis=1)

    df = pd.DataFrame({"ML_FEAT_X06_Market_Breadth": breadth})
    df = df.shift(1)  # LAG +1
    return df


def compute_all_features(prices: dict, db: Session = None) -> pd.DataFrame:
    """
    Master function: computes all 192 features matching thesis structure.
    Returns DataFrame with proper column ordering.
    """
    log_ratios = compute_log_ratios(prices)
    if log_ratios.empty:
        return pd.DataFrame()

    # Core ratio features (80)
    ratio_feats = compute_ml_features(prices, log_ratios)

    # Macro features (8 + 5 derived = 13)
    macro_feats = compute_macro_features(prices, db)

    # Volatility features (~11)
    vol_feats = compute_volatility_features(prices)

    # Spread shock features (~24)
    spread_feats = compute_spread_features(prices)

    # Cross-sectional momentum (~24)
    csm_feats = compute_csm_features(prices)

    # Market breadth (1)
    breadth_feats = compute_breadth_feature(prices)

    # Combine all
    all_dfs = [ratio_feats, macro_feats, vol_feats,
               spread_feats, csm_feats, breadth_feats]
    all_dfs = [df for df in all_dfs if not df.empty]

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, axis=1)
    combined.sort_index(inplace=True)
    return combined
