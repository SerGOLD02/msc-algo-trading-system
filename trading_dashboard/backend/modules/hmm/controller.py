from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.hmm.service import get_current_regime
from modules.hmm.schemas import RegimeStatusDTO

router = APIRouter()

@router.get("/current", response_model=RegimeStatusDTO)
def current_regime(db: Session = Depends(get_db)):
    return get_current_regime(db)
