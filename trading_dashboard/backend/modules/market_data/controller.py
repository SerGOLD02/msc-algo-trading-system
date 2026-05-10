from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.market_data.service import get_market_snapshot
from modules.market_data.schemas import MarketSnapshotDTO

router = APIRouter()

@router.get("/snapshot", response_model=MarketSnapshotDTO)
def snapshot(db: Session = Depends(get_db)):
    return get_market_snapshot(db)
