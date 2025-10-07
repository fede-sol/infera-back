from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth.utils import get_current_user_token, get_current_user
from database import get_db
from stats.utils import get_user_stats, get_user_recent_messages

router = APIRouter(prefix="/stats", tags=["Estadísticas"])


@router.get("/dashboard")
def get_my_stats(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene las estadísticas del usuario actual.
    
    Incluye:
    - Total de mensajes procesados
    - Cantidad de decisiones detectadas
    - Cantidad de canales de Slack analizados
    """
    current_user = get_current_user(payload, db)
    
    stats = get_user_stats(current_user.id, db)
    
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "statistics": stats
    }


@router.get("/recent-messages")
def get_recent_messages(
    limit: int = Query(default=20, ge=1, le=100, description="Número de mensajes a retornar (máximo 100)"),
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene los últimos mensajes analizados del usuario, ordenados por fecha (más reciente primero).
    
    Args:
        limit: Número máximo de mensajes a retornar (entre 1 y 100, default: 20)
    
    Returns:
        Lista de mensajes con su clasificación, confianza y fecha de procesamiento
    """
    current_user = get_current_user(payload, db)
    
    messages = get_user_recent_messages(current_user.id, db, limit)
    
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "total_returned": len(messages),
        "limit": limit,
        "messages": messages
    }

