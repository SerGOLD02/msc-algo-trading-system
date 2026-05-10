from sqlalchemy import (Column, String, Float, Integer,
                         Boolean, DateTime, Text, Index)
from sqlalchemy.sql import func
from database.connection import Base


class PriceCache(Base):
    """
    Prezzi OHLCV giornalieri per ogni ticker.
    Aggiornato ogni 2 minuti durante le ore di mercato.
    """
    __tablename__ = "price_cache"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    ticker    = Column(String(20), nullable=False)
    date      = Column(String(10), nullable=False)   # YYYY-MM-DD
    open      = Column(Float)
    high      = Column(Float)
    low       = Column(Float)
    close     = Column(Float, nullable=False)
    volume    = Column(Float)
    updated_at = Column(DateTime, server_default=func.now(),
                         onupdate=func.now())

    __table_args__ = (
        Index("ix_price_ticker_date", "ticker", "date", unique=True),
    )


class InferenceCache(Base):
    """
    Inferenze TimesFM e Chronos per ogni (venerdì, ratio).
    Calcolate solo il venerdì dopo chiusura NYSE.
    """
    __tablename__ = "inference_cache"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    friday_date    = Column(String(10), nullable=False)
    ratio_id       = Column(String(5),  nullable=False)
    tfm_t1         = Column(Float)
    tfm_t5         = Column(Float)
    tfm_t20        = Column(Float)
    chr_median_t5  = Column(Float)
    chr_width_t5   = Column(Float)
    created_at     = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_inference_date_ratio",
              "friday_date", "ratio_id", unique=True),
    )


class BacktestResult(Base):
    """
    Risultati backtest settimanali dal 2026-01-01.
    Una riga per venerdì. Aggiornata solo il venerdì sera.
    Salvata sia per parametri default che per parametri custom.
    """
    __tablename__ = "backtest_results"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    friday_date       = Column(String(10), nullable=False)
    params_hash       = Column(String(64), nullable=False)
    portfolio_value   = Column(Float, nullable=False)
    weekly_return     = Column(Float)
    regime            = Column(Integer)
    decay_value       = Column(Float)
    n_trades          = Column(Integer)
    is_crisis         = Column(Boolean)
    cagr              = Column(Float)
    sharpe            = Column(Float)
    max_drawdown      = Column(Float)
    calmar            = Column(Float)
    total_return      = Column(Float)
    created_at        = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_backtest_date_params",
              "friday_date", "params_hash", unique=True),
    )


class SystemParams(Base):
    """
    Parametri di configurazione del sistema.
    Una riga per params_hash (default + ogni combinazione custom).
    """
    __tablename__ = "system_params"

    params_hash       = Column(String(64), primary_key=True)
    bet_quality       = Column(Float, nullable=False)
    hrp_alpha         = Column(Float, nullable=False)
    k_sigmoid         = Column(Float, nullable=False)
    c_soglia          = Column(Float, nullable=False)
    k_up              = Column(Float, nullable=False)
    k_down            = Column(Float, nullable=False)
    is_default        = Column(Boolean, default=False)
    created_at        = Column(DateTime, server_default=func.now())


class Metadata(Base):
    """
    Metadati di sistema: ultimo aggiornamento, stato scheduler.
    """
    __tablename__ = "metadata"

    key        = Column(String(100), primary_key=True)
    value      = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(),
                         onupdate=func.now())


class MacroCache(Base):
    """
    Dati macroeconomici da EODHD/YFinance.
    Un record per (indicator, date).
    """
    __tablename__ = "macro_cache"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    indicator  = Column(String(50), nullable=False)
    date       = Column(String(10), nullable=False)  # YYYY-MM-DD
    value      = Column(Float, nullable=False)
    source     = Column(String(20))  # "eodhd" or "yfinance" or "proxy"
    updated_at = Column(DateTime, server_default=func.now(),
                         onupdate=func.now())

    __table_args__ = (
        Index("ix_macro_indicator_date", "indicator", "date", unique=True),
    )
