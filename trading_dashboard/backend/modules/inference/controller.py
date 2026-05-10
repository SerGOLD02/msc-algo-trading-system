from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database.connection import get_db
from modules.inference.service import (get_latest_inferences,
                                        trigger_fm_update,
                                        recompute_stale_inference)
from modules.inference.schemas import InferenceResponseDTO

router = APIRouter()

@router.get("/latest", response_model=InferenceResponseDTO)
def latest_inferences(db: Session = Depends(get_db)):
    return get_latest_inferences(db)

@router.post("/update")
def update_inferences(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Avvia il ricalcolo di TimesFM e Chronos in background.
    Chiamato dallo scheduler il venerdì dopo 16:00 ET,
    oppure manualmente dall'utente.
    """
    background_tasks.add_task(trigger_fm_update, db)
    return {"status": "update_started"}

@router.post("/recompute")
def recompute_inferences(db: Session = Depends(get_db)):
    """
    Ri-calcola le inferenze 2026 che usano il proxy OLS (tfm == chr).
    Chiamare DOPO aver piazzato il checkpoint TimesFM sul PC.
    """
    result = recompute_stale_inference(db)
    return result
