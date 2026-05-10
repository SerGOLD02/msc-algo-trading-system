from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from zoneinfo import ZoneInfo
from database.connection import SessionLocal
from config import PRICES_REFRESH_MINUTES

scheduler = BackgroundScheduler(timezone=ZoneInfo("America/New_York"))

# Timezone references
ET = ZoneInfo("America/New_York")
IT = ZoneInfo("Europe/Rome")


def _refresh_prices_job():
    from modules.market_data.service import refresh_prices
    db = SessionLocal()
    try:
        refresh_prices(db)
    except Exception as e:
        print(f"[scheduler] refresh_prices error: {e}")
    finally:
        db.close()


def _eodhd_macro_job():
    """
    Refresh macro data from EODHD.
    Scheduled 4x/day on weekdays: 09:00, 15:30, 18:00, 21:00 IT.
    """
    from modules.eodhd.service import refresh_all_macro
    db = SessionLocal()
    try:
        refresh_all_macro(db)
    except Exception as e:
        print(f"[scheduler] EODHD macro refresh error: {e}")
    finally:
        db.close()


def _initial_data_load():
    """
    Scarica dati storici al primo avvio (se DB vuoto).
    Also triggers initial EODHD macro fetch.
    """
    from database.models import PriceCache
    db = SessionLocal()
    try:
        count = db.query(PriceCache).count()
        if count < 100:
            print("[scheduler] DB empty or sparse, running initial data load...")
            from modules.market_data.service import refresh_prices
            refresh_prices(db, initial=True)
            print("[scheduler] Initial data load complete.")
        else:
            print(f"[scheduler] DB has {count} price records, skipping initial load.")
            from modules.market_data.service import refresh_prices
            refresh_prices(db)

        # Initial EODHD macro fetch
        try:
            from modules.eodhd.service import refresh_all_macro
            refresh_all_macro(db)
        except Exception as e:
            print(f"[scheduler] Initial EODHD load error: {e}")
            db.rollback()

    except Exception as e:
        print(f"[scheduler] Initial load error: {e}")
    finally:
        db.close()

    # Backfill inference for missing 2026 Fridays (separate session)
    db2 = SessionLocal()
    try:
        from modules.inference.service import backfill_inference
        backfill_inference(db2)
    except Exception as e:
        print(f"[scheduler] Inference backfill error: {e}")
    finally:
        db2.close()

    # Compute initial backtest after inference is ready (separate session)
    db3 = SessionLocal()
    try:
        from modules.backtest.service import get_or_compute_backtest
        from modules.backtest.schemas import BacktestParams
        from config import (DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
                            DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA,
                            DEFAULT_K_UP, DEFAULT_K_DOWN)
        params = BacktestParams(
            bet_quality=DEFAULT_BET_QUALITY,
            hrp_alpha=DEFAULT_HRP_ALPHA,
            k_sigmoid=DEFAULT_K_SIGMOID,
            c_soglia=DEFAULT_C_SOGLIA,
            k_up=DEFAULT_K_UP,
            k_down=DEFAULT_K_DOWN,
        )
        result = get_or_compute_backtest(params, db3)
        pts = len(result.get("series", []))
        print(f"[scheduler] Initial backtest computed: {pts} points")
    except Exception as e:
        print(f"[scheduler] Initial backtest error: {e}")
    finally:
        db3.close()


def _friday_close_job():
    """
    Eseguito ogni venerdì alle 16:05 ET (5 minuti dopo chiusura NYSE).
    Full pipeline: prices → inference → backtest.
    """
    from modules.market_data.service import refresh_prices
    from modules.inference.service import trigger_fm_update
    from modules.backtest.service import get_or_compute_backtest
    from modules.backtest.schemas import BacktestParams
    from config import (DEFAULT_BET_QUALITY, DEFAULT_HRP_ALPHA,
                        DEFAULT_K_SIGMOID, DEFAULT_C_SOGLIA,
                        DEFAULT_K_UP, DEFAULT_K_DOWN)

    db = SessionLocal()
    try:
        # Step 1: Final price update
        refresh_prices(db)
        print("[scheduler] Friday prices updated.")

        # Step 2: Run TimesFM + Chronos inference (background, may take 5-15 min)
        import threading
        def _run_inference():
            idb = SessionLocal()
            try:
                trigger_fm_update(idb)
                print("[scheduler] Friday inference complete.")
            except Exception as e:
                print(f"[scheduler] Inference error: {e}")
            finally:
                idb.close()

        t = threading.Thread(target=_run_inference, daemon=True)
        t.start()

        # Step 3: Compute backtest with default params
        params = BacktestParams(
            bet_quality=DEFAULT_BET_QUALITY,
            hrp_alpha=DEFAULT_HRP_ALPHA,
            k_sigmoid=DEFAULT_K_SIGMOID,
            c_soglia=DEFAULT_C_SOGLIA,
            k_up=DEFAULT_K_UP,
            k_down=DEFAULT_K_DOWN,
        )
        get_or_compute_backtest(params, db)
        print("[scheduler] Friday close job completed.")

    except Exception as e:
        print(f"[scheduler] Friday close job error: {e}")
    finally:
        db.close()


def start_scheduler():
    import threading

    # Caricamento dati iniziale in background (non blocca avvio server)
    t = threading.Thread(target=_initial_data_load, daemon=True)
    t.start()

    # Aggiornamento prezzi ogni 2 minuti
    scheduler.add_job(
        _refresh_prices_job,
        trigger=IntervalTrigger(minutes=PRICES_REFRESH_MINUTES),
        id="refresh_prices",
        replace_existing=True,
    )

    # EODHD macro refresh: 4x/day on weekdays
    # Times in Italian: 09:00, 15:30, 18:00, 21:00
    # Converted to ET: 03:00, 09:30, 12:00, 15:00
    for job_id, (hour, minute) in [
        ("eodhd_morning", (3, 0)),
        ("eodhd_us_open", (9, 30)),
        ("eodhd_midday", (12, 0)),
        ("eodhd_evening", (15, 0)),
    ]:
        scheduler.add_job(
            _eodhd_macro_job,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=hour,
                minute=minute,
                timezone=ET
            ),
            id=job_id,
            replace_existing=True,
        )

    # Job venerdì sera: full pipeline
    scheduler.add_job(
        _friday_close_job,
        trigger=CronTrigger(
            day_of_week="fri",
            hour=16,
            minute=5,
            timezone=ET
        ),
        id="friday_close",
        replace_existing=True,
    )

    scheduler.start()
    print("[scheduler] Scheduler avviato (prices 2min, EODHD 4x/day, Friday pipeline).")


def stop_scheduler():
    scheduler.shutdown()
    print("[scheduler] Scheduler fermato.")
