"""
HRP (Hierarchical Risk Parity) position sizing.
Carica i pesi pre-calcolati dal Drive per il periodo storico,
calcola live per nuove date.
"""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform
from config import HRP_WEIGHTS_PATH


_hrp_cache: pd.DataFrame | None = None


def _load_hrp_weights() -> pd.DataFrame:
    global _hrp_cache
    if _hrp_cache is None:
        try:
            _hrp_cache = pd.read_parquet(HRP_WEIGHTS_PATH)
            _hrp_cache.index = pd.to_datetime(_hrp_cache.index)
        except Exception as e:
            print(f"HRP weights load error: {e}")
            _hrp_cache = pd.DataFrame()
    return _hrp_cache


def _compute_hrp_weights(cov: pd.DataFrame, corr: pd.DataFrame) -> pd.Series:
    """
    Calcola i pesi HRP da matrice di covarianza e correlazione.
    Implementazione standard dell'algoritmo di De Prado.
    """
    n = cov.shape[0]
    if n <= 1:
        return pd.Series(1.0, index=cov.columns)

    dist = np.sqrt(0.5 * (1 - corr.values))
    np.fill_diagonal(dist, 0.0)
    dist = np.nan_to_num(dist, nan=0.0)
    condensed = squareform(dist, checks=False)
    condensed = np.nan_to_num(condensed, nan=0.0)

    link = linkage(condensed, method="single")
    order = list(leaves_list(link))

    tickers = [cov.columns[i] for i in order]
    weights = pd.Series(1.0, index=tickers)

    cluster_items = [[t] for t in tickers]
    while len(cluster_items) > 1:
        new_items = []
        for i in range(0, len(cluster_items) - 1, 2):
            c0 = cluster_items[i]
            c1 = cluster_items[i + 1]
            cov0 = cov.loc[c0, c0]
            cov1 = cov.loc[c1, c1]

            ivp0 = 1.0 / np.diag(cov0.values)
            ivp0 /= ivp0.sum()
            var0 = float(ivp0 @ cov0.values @ ivp0)

            ivp1 = 1.0 / np.diag(cov1.values)
            ivp1 /= ivp1.sum()
            var1 = float(ivp1 @ cov1.values @ ivp1)

            alpha = 1.0 - var0 / (var0 + var1) if (var0 + var1) > 0 else 0.5

            for t in c0:
                weights[t] *= alpha
            for t in c1:
                weights[t] *= (1.0 - alpha)

            new_items.append(c0 + c1)

        if len(cluster_items) % 2 == 1:
            new_items.append(cluster_items[-1])
        cluster_items = new_items

    weights /= weights.sum()
    return weights


def compute_blended_weights(returns_df: pd.DataFrame,
                            active_tickers: list,
                            alpha: float) -> dict:
    """
    Calcola i pesi blended HRP/EW per i ticker attivi.

    Formula: w_final = alpha * w_HRP + (1 - alpha) * (1/N)
    Cap: max 15% per singolo asset.

    Args:
        returns_df: DataFrame di rendimenti settimanali (index=dates, cols=tickers)
        active_tickers: lista ticker con trade attivo
        alpha: peso HRP nel blending (0=puro EW, 1=puro HRP)
    Returns:
        dict { ticker: peso_finale }
    """
    valid_tickers = [t for t in active_tickers if t in returns_df.columns]
    if not valid_tickers:
        return {}

    n = len(valid_tickers)
    ew = 1.0 / n

    sub = returns_df[valid_tickers].dropna()
    if len(sub) < 10:
        return {t: ew for t in valid_tickers}

    cov = sub.cov()
    corr = sub.corr()

    try:
        hrp_w = _compute_hrp_weights(cov, corr)
    except Exception:
        return {t: ew for t in valid_tickers}

    weights = {}
    for t in valid_tickers:
        w_hrp = hrp_w.get(t, ew)
        w = alpha * w_hrp + (1.0 - alpha) * ew
        weights[t] = min(w, 0.15)  # Cap 15%

    total = sum(weights.values())
    if total > 0:
        weights = {t: w / total for t, w in weights.items()}

    return weights
