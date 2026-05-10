from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.signals.service import get_weekly_signals
from modules.signals.schemas import WeeklySignalResponse
from .live_engine import run_live_execution
import csv
import io

router = APIRouter()

@router.get("/latest")
def get_latest_signals():
    return run_live_execution()

@router.get("/weekly", response_model=WeeklySignalResponse)
def weekly_signals(
    friday: str | None = Query(None, description="YYYY-MM-DD"),
    threshold: float = Query(0.50, ge=0.0, le=1.0),
    db: Session = Depends(get_db)
):
    return get_weekly_signals(db, friday, threshold)


@router.get("/weekly/csv")
def weekly_signals_csv(
    friday: str | None = Query(None),
    threshold: float = Query(0.50, ge=0.0, le=1.0),
    db: Session = Depends(get_db)
):
    """Download weekly signals as CSV file."""
    data = get_weekly_signals(db, friday, threshold)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ratio_id", "pair", "direction", "long_ticker",
        "bet_quality", "status", "tfm_t5", "current_ratio",
        "realized_return"
    ])

    for s in data["signals"]:
        writer.writerow([
            s["ratio_id"],
            f"{s['numerator']}/{s['denominator']}",
            s["direction"],
            s["long_ticker"],
            s["bet_quality"],
            s["status"],
            s.get("tfm_t5", ""),
            s.get("current_ratio", ""),
            s.get("realized_return", ""),
        ])

    output.seek(0)
    filename = f"signals_{data['friday_date']}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
