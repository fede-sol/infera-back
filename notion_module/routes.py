from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from auth.utils import get_current_user_token, get_current_user
from database import get_db
from notion_module.models import NotionDatabase
from notion_module.utils import get_notion_databases, get_notion_database_details

router = APIRouter(prefix="/notion", tags=["Notion"])


# --- Schemas de Pydantic ---

class NotionDatabaseCreate(BaseModel):
    notion_database_id: str
    database_name: str
    database_url: Optional[str] = None


class NotionDatabaseResponse(BaseModel):
    id: int
    user_id: int
    notion_database_id: str
    database_name: str
    database_url: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.get("/databases")
async def list_notion_databases(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Lista todas las databases disponibles en Notion usando el token del usuario.
    No las guarda en la base de datos, solo las consulta.
    """
    current_user = get_current_user(payload, db)
    
    if not current_user.notion_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Notion no configurado. Configure su token en /auth/credentials"
        )
    
    databases = await get_notion_databases(current_user.notion_token)
    
    return {
        "count": len(databases),
        "databases": databases
    }


@router.get("/databases/{database_id}")
async def get_database_details(
    database_id: str,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene los detalles de una database específica de Notion.
    """
    current_user = get_current_user(payload, db)
    
    if not current_user.notion_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Notion no configurado"
        )
    
    database = await get_notion_database_details(current_user.notion_token, database_id)
    
    return database


@router.get("/saved-databases", response_model=List[NotionDatabaseResponse])
def list_saved_databases(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Lista todas las databases de Notion guardadas en la base de datos del usuario.
    """
    current_user = get_current_user(payload, db)
    
    databases = db.query(NotionDatabase).filter(
        NotionDatabase.user_id == current_user.id,
        NotionDatabase.is_active == True
    ).all()
    
    return databases


@router.post("/saved-databases", status_code=status.HTTP_201_CREATED)
def save_notion_database(
    database: NotionDatabaseCreate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Guarda una database de Notion en la base de datos local para poder asociarla con channels de Slack.
    """
    current_user = get_current_user(payload, db)
    
    # Verificar si ya existe
    existing = db.query(NotionDatabase).filter(
        NotionDatabase.user_id == current_user.id,
        NotionDatabase.notion_database_id == database.notion_database_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta database ya está guardada"
        )
    
    # Crear nueva database
    new_database = NotionDatabase(
        user_id=current_user.id,
        notion_database_id=database.notion_database_id,
        database_name=database.database_name,
        database_url=database.database_url
    )
    
    db.add(new_database)
    db.commit()
    db.refresh(new_database)
    
    print(f"✅ Database de Notion guardada: {new_database.database_name} (Usuario: {current_user.username})")
    
    return new_database.to_dict()


@router.delete("/saved-databases/{database_id}")
def delete_saved_database(
    database_id: int,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Elimina una database guardada. También elimina todas sus asociaciones con channels.
    """
    current_user = get_current_user(payload, db)
    
    database = db.query(NotionDatabase).filter(
        NotionDatabase.id == database_id,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not database:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database no encontrada"
        )
    
    db.delete(database)
    db.commit()
    
    print(f"✅ Database de Notion eliminada: {database.database_name} (Usuario: {current_user.username})")
    
    return {
        "message": "Database eliminada exitosamente"
    }

