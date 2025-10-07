from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from auth.utils import get_current_user_token, get_current_user
from database import get_db
from slack_module.models import SlackChannel, NotionSlackAssociation
from slack_module.utils import get_slack_channels, get_slack_channel_details
from notion_module.models import NotionDatabase
from notion_module.utils import get_notion_database_details

router = APIRouter(prefix="/slack", tags=["Slack"])


# --- Schemas de Pydantic ---

class SlackChannelCreate(BaseModel):
    slack_channel_id: str
    channel_name: str
    is_private: bool = False


class SlackChannelResponse(BaseModel):
    id: int
    user_id: int
    slack_channel_id: str
    channel_name: str
    is_private: bool
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class AssociationCreate(BaseModel):
    notion_database_id: int
    slack_channel_ids: List[int]
    auto_sync: bool = True
    notes: Optional[str] = None


class SmartAssociationCreate(BaseModel):
    """
    Schema para crear asociaciones de forma inteligente.
    Si la database o channels no existen localmente, se crean automáticamente.
    """
    # ID externo de Notion (el que devuelve la API de Notion)
    notion_database_id_external: str
    # Lista de IDs externos de Slack (los que devuelve la API de Slack)
    slack_channel_ids_external: List[str]
    auto_sync: bool = True
    notes: Optional[str] = None


class AssociationUpdate(BaseModel):
    auto_sync: Optional[bool] = None
    notes: Optional[str] = None


# --- Endpoints ---

@router.get("/channels")
async def list_slack_channels(
    include_private: bool = True,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Lista todos los channels disponibles en Slack usando el token del usuario.
    No los guarda en la base de datos, solo los consulta.
    """
    current_user = get_current_user(payload, db)
    
    if not current_user.slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado. Configure su token en /auth/credentials o use /auth/slack/oauth"
        )
    
    channels = await get_slack_channels(current_user.slack_token, include_private)
    
    return {
        "count": len(channels),
        "channels": channels
    }


@router.get("/channels/{channel_id}")
async def get_channel_details(
    channel_id: str,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene los detalles de un channel específico de Slack.
    """
    current_user = get_current_user(payload, db)
    
    if not current_user.slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado"
        )
    
    channel = await get_slack_channel_details(current_user.slack_token, channel_id)
    
    return channel


@router.get("/saved-channels", response_model=List[SlackChannelResponse])
def list_saved_channels(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Lista todos los channels de Slack guardados en la base de datos del usuario.
    """
    current_user = get_current_user(payload, db)
    
    channels = db.query(SlackChannel).filter(
        SlackChannel.user_id == current_user.id,
        SlackChannel.is_active == True
    ).all()
    
    return channels


@router.post("/saved-channels", status_code=status.HTTP_201_CREATED)
def save_slack_channel(
    channel: SlackChannelCreate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Guarda un channel de Slack en la base de datos local para poder asociarlo con databases de Notion.
    """
    current_user = get_current_user(payload, db)

    # Verificar si ya existe
    existing = db.query(SlackChannel).filter(
        SlackChannel.user_id == current_user.id,
        SlackChannel.slack_channel_id == channel.slack_channel_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este channel ya está guardado"
        )

    # Crear nuevo channel
    new_channel = SlackChannel(
        user_id=current_user.id,
        slack_channel_id=channel.slack_channel_id,
        channel_name=channel.channel_name,
        is_private=channel.is_private
    )

    db.add(new_channel)
    db.commit()
    db.refresh(new_channel)
    
    print(f"✅ Channel de Slack guardado: {new_channel.channel_name} (Usuario: {current_user.username})")
    
    return new_channel.to_dict()


@router.delete("/saved-channels/{channel_id}")
def delete_saved_channel(
    channel_id: int,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Elimina un channel guardado. También elimina todas sus asociaciones con databases.
    """
    current_user = get_current_user(payload, db)
    
    channel = db.query(SlackChannel).filter(
        SlackChannel.id == channel_id,
        SlackChannel.user_id == current_user.id
    ).first()
    
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel no encontrado"
        )
    
    db.delete(channel)
    db.commit()
    
    print(f"✅ Channel de Slack eliminado: {channel.channel_name} (Usuario: {current_user.username})")
    
    return {
        "message": "Channel eliminado exitosamente"
    }


# --- Endpoints de Asociaciones ---

@router.post("/associations", status_code=status.HTTP_201_CREATED)
def create_associations(
    association_data: AssociationCreate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Crea asociaciones entre una database de Notion y múltiples channels de Slack.
    Una database puede estar asociada a varios channels.
    
    NOTA: Este endpoint requiere que la database y los channels ya estén guardados localmente.
    Si quieres crear asociaciones sin guardar previamente, usa POST /slack/associations/smart
    """
    current_user = get_current_user(payload, db)
    
    # Verificar que la database existe y pertenece al usuario
    notion_db = db.query(NotionDatabase).filter(
        NotionDatabase.id == association_data.notion_database_id,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not notion_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database de Notion no encontrada"
        )
    
    created_associations = []
    
    for channel_id in association_data.slack_channel_ids:
        # Verificar que el channel existe y pertenece al usuario
        slack_channel = db.query(SlackChannel).filter(
            SlackChannel.id == channel_id,
            SlackChannel.user_id == current_user.id
        ).first()
        
        if not slack_channel:
            print(f"⚠️ Channel {channel_id} no encontrado, saltando...")
            continue
        
        # Verificar si ya existe la asociación
        existing = db.query(NotionSlackAssociation).filter(
            NotionSlackAssociation.notion_database_id == association_data.notion_database_id,
            NotionSlackAssociation.slack_channel_id == channel_id
        ).first()
        
        if existing:
            print(f"⚠️ Asociación ya existe entre {notion_db.database_name} y {slack_channel.channel_name}")
            continue
        
        # Crear asociación
        new_association = NotionSlackAssociation(
            notion_database_id=association_data.notion_database_id,
            slack_channel_id=channel_id,
            auto_sync=association_data.auto_sync,
            notes=association_data.notes
        )
        
        db.add(new_association)
        created_associations.append(new_association)
    
    db.commit()
    
    # Refrescar para obtener las relaciones
    for assoc in created_associations:
        db.refresh(assoc)
    
    print(f"✅ {len(created_associations)} asociación(es) creada(s) para database: {notion_db.database_name}")
    
    return {
        "message": f"{len(created_associations)} asociación(es) creada(s) exitosamente",
        "associations": [assoc.to_dict_with_details() for assoc in created_associations]
    }


@router.post("/associations/smart", status_code=status.HTTP_201_CREATED)
async def create_smart_associations(
    association_data: SmartAssociationCreate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Crea asociaciones de forma inteligente. Si la database o los channels no existen 
    localmente, los crea automáticamente consultando las APIs de Notion y Slack.
    
    Este endpoint es más conveniente porque no requiere guardar previamente la database
    y los channels. Solo necesitas los IDs externos de Notion y Slack.
    """
    current_user = get_current_user(payload, db)
    
    if not current_user.notion_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Notion no configurado"
        )
    
    if not current_user.slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado"
        )
    
    # 1. Verificar/Crear la database de Notion
    notion_db = db.query(NotionDatabase).filter(
        NotionDatabase.notion_database_id == association_data.notion_database_id_external,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not notion_db:
        # La database no existe localmente, obtenerla de Notion y crearla
        print(f"📥 Database no existe localmente, obteniendo de Notion: {association_data.notion_database_id_external}")
        try:
            notion_data = await get_notion_database_details(
                current_user.notion_token,
                association_data.notion_database_id_external
            )

            notion_db = NotionDatabase(
                user_id=current_user.id,
                notion_database_id=notion_data["notion_database_id"],
                database_name=notion_data["database_name"],
                database_url=notion_data.get("database_url")
            )

            db.add(notion_db)
            db.commit()
            db.refresh(notion_db)

            print(f"✅ Database creada localmente: {notion_db.database_name}")

        except HTTPException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo obtener la database de Notion: {e.detail}"
            )
    else:
        print(f"✓ Database ya existe localmente: {notion_db.database_name}")

    # 2. Verificar/Crear los channels de Slack
    created_associations = []

    for slack_channel_id_ext in association_data.slack_channel_ids_external:
        # Verificar si el channel ya existe localmente
        slack_channel = db.query(SlackChannel).filter(
            SlackChannel.slack_channel_id == slack_channel_id_ext,
            SlackChannel.user_id == current_user.id
        ).first()

        if not slack_channel:
            # El channel no existe localmente, obtenerlo de Slack y crearlo
            print(f"📥 Channel no existe localmente, obteniendo de Slack: {slack_channel_id_ext}")
            try:
                slack_data = await get_slack_channel_details(
                    current_user.slack_token,
                    slack_channel_id_ext
                )

                slack_channel = SlackChannel(
                    user_id=current_user.id,
                    slack_channel_id=slack_data["slack_channel_id"],
                    channel_name=slack_data["channel_name"],
                    is_private=slack_data.get("is_private", False)
                )

                db.add(slack_channel)
                db.commit()
                db.refresh(slack_channel)

                print(f"✅ Channel creado localmente: {slack_channel.channel_name}")

            except HTTPException as e:
                print(f"⚠️ No se pudo obtener el channel {slack_channel_id_ext}: {e.detail}")
                continue
        else:
            print(f"✓ Channel ya existe localmente: {slack_channel.channel_name}")

        # 3. Verificar si ya existe la asociación
        existing = db.query(NotionSlackAssociation).filter(
            NotionSlackAssociation.notion_database_id == notion_db.id,
            NotionSlackAssociation.slack_channel_id == slack_channel.id
        ).first()

        if existing:
            print(f"⚠️ Asociación ya existe entre {notion_db.database_name} y {slack_channel.channel_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Asociación ya existe entre {notion_db.database_name} y {slack_channel.channel_name}"
            )
        
        # 4. Crear la asociación
        new_association = NotionSlackAssociation(
            notion_database_id=notion_db.id,
            slack_channel_id=slack_channel.id,
            auto_sync=association_data.auto_sync,
            notes=association_data.notes
        )
        
        db.add(new_association)
        created_associations.append(new_association)
    
    db.commit()
    
    # Refrescar para obtener las relaciones
    for assoc in created_associations:
        db.refresh(assoc)
    
    print(f"✅ {len(created_associations)} asociación(es) creada(s) para database: {notion_db.database_name}")
    
    return {
        "message": f"{len(created_associations)} asociación(es) creada(s) exitosamente",
        "database": notion_db.to_dict(),
        "associations": [assoc.to_dict_with_details() for assoc in created_associations]
    }


@router.get("/associations")
def list_associations(
    notion_database_id: Optional[int] = None,
    slack_channel_id: Optional[int] = None,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Lista todas las asociaciones del usuario. Puede filtrar por database o channel.
    """
    current_user = get_current_user(payload, db)
    
    query = db.query(NotionSlackAssociation).join(NotionDatabase).filter(
        NotionDatabase.user_id == current_user.id
    )
    
    if notion_database_id:
        query = query.filter(NotionSlackAssociation.notion_database_id == notion_database_id)
    
    if slack_channel_id:
        query = query.filter(NotionSlackAssociation.slack_channel_id == slack_channel_id)
    
    associations = query.all()
    
    return {
        "count": len(associations),
        "associations": [assoc.to_dict_with_details() for assoc in associations]
    }


@router.get("/associations/{association_id}")
def get_association(
    association_id: int,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene los detalles de una asociación específica.
    """
    current_user = get_current_user(payload, db)
    
    association = db.query(NotionSlackAssociation).join(NotionDatabase).filter(
        NotionSlackAssociation.id == association_id,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asociación no encontrada"
        )
    
    return association.to_dict_with_details()


@router.put("/associations/{association_id}")
def update_association(
    association_id: int,
    update_data: AssociationUpdate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Actualiza una asociación existente (solo auto_sync y notes).
    """
    current_user = get_current_user(payload, db)
    
    association = db.query(NotionSlackAssociation).join(NotionDatabase).filter(
        NotionSlackAssociation.id == association_id,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asociación no encontrada"
        )
    
    # Actualizar campos
    if update_data.auto_sync is not None:
        association.auto_sync = update_data.auto_sync
    
    if update_data.notes is not None:
        association.notes = update_data.notes
    
    db.commit()
    db.refresh(association)
    
    print(f"✅ Asociación actualizada (ID: {association_id})")
    
    return association.to_dict_with_details()


@router.delete("/associations/{association_id}")
def delete_association(
    association_id: int,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Elimina una asociación específica entre una database y un channel.
    """
    current_user = get_current_user(payload, db)
    
    association = db.query(NotionSlackAssociation).join(NotionDatabase).filter(
        NotionSlackAssociation.id == association_id,
        NotionDatabase.user_id == current_user.id
    ).first()
    
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asociación no encontrada"
        )
    
    db.delete(association)
    db.commit()
    
    print(f"✅ Asociación eliminada (ID: {association_id})")
    
    return {
        "message": "Asociación eliminada exitosamente"
    }

