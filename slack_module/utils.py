import httpx
from typing import List, Dict, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session


async def get_slack_channels(slack_token: str, include_private: bool = True) -> List[Dict]:
    """
    Obtiene todos los channels de Slack disponibles para el usuario.
    
    Args:
        slack_token: Token de autenticación de Slack
        include_private: Si incluir channels privados
        
    Returns:
        Lista de channels con su información
        
    Raises:
        HTTPException: Si hay error en la comunicación con Slack
    """
    if not slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado. Configure su token primero."
        )
    
    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json"
    }
    
    all_channels = []
    cursor = None
    
    async with httpx.AsyncClient() as client:
        # Obtener channels públicos y privados
        while True:
            try:
                params = {
                    "types": "public_channel,private_channel" if include_private else "public_channel",
                    "exclude_archived": "true",
                    "limit": 200
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                response = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers=headers,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                
            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error al comunicarse con Slack: {str(e)}"
                )
            
            # Verificar respuesta de Slack
            if not data.get("ok"):
                error_msg = data.get("error", "Error desconocido")
                if error_msg == "invalid_auth":
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token de Slack inválido o expirado"
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error de Slack: {error_msg}"
                )
            
            # Agregar channels a la lista
            channels = data.get("channels", [])
            for channel in channels:
                all_channels.append({
                    "slack_channel_id": channel.get("id"),
                    "channel_name": channel.get("name"),
                    "is_private": channel.get("is_private", False),
                    "is_member": channel.get("is_member", False),
                    "num_members": channel.get("num_members", 0),
                    "topic": channel.get("topic", {}).get("value", ""),
                    "purpose": channel.get("purpose", {}).get("value", ""),
                })
            
            # Verificar si hay más páginas
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    
    return all_channels


async def get_slack_channel_details(slack_token: str, channel_id: str) -> Dict:
    """
    Obtiene los detalles de un channel específico de Slack.
    
    Args:
        slack_token: Token de autenticación de Slack
        channel_id: ID del channel de Slack
        
    Returns:
        Información detallada del channel
        
    Raises:
        HTTPException: Si hay error en la comunicación con Slack
    """
    if not slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado"
        )
    
    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://slack.com/api/conversations.info",
                headers=headers,
                params={"channel": channel_id},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al comunicarse con Slack: {str(e)}"
            )
        
        if not data.get("ok"):
            error_msg = data.get("error", "Error desconocido")
            if error_msg == "channel_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Channel de Slack no encontrado"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error de Slack: {error_msg}"
            )
        
        channel = data.get("channel", {})
        return {
            "slack_channel_id": channel.get("id"),
            "channel_name": channel.get("name"),
            "is_private": channel.get("is_private", False),
            "is_member": channel.get("is_member", False),
            "num_members": channel.get("num_members", 0),
            "topic": channel.get("topic", {}).get("value", ""),
            "purpose": channel.get("purpose", {}).get("value", ""),
            "created": channel.get("created"),
        }


def get_notion_databases_for_slack_channel(
    slack_channel_id_external: str,
    user_id: int,
    db: Session
) -> List[Dict]:
    """
    Obtiene las databases de Notion asociadas a un canal de Slack específico.
    
    Args:
        slack_channel_id_external: ID externo del canal de Slack (ej. "C123456")
        user_id: ID del usuario propietario
        db: Sesión de base de datos
        
    Returns:
        Lista de databases de Notion asociadas con sus detalles.
        Retorna lista vacía si el canal no tiene asociaciones.
    """
    from slack_module.models import SlackChannel, NotionSlackAssociation
    from notion_module.models import NotionDatabase

    # 1. Buscar el canal en la base de datos local
    slack_channel = db.query(SlackChannel).filter(
        SlackChannel.slack_channel_id == slack_channel_id_external,
        SlackChannel.user_id == user_id,
        SlackChannel.is_active == True
    ).first()
    
    if not slack_channel:
        print(f"⚠️ Canal de Slack {slack_channel_id_external} no encontrado en la base de datos local")
        return []

    print(f"Canal de Slack encontrado: {slack_channel}")

    associationsNotion = db.query(NotionSlackAssociation).all()
    print(f"ID externo del canal: {associationsNotion}")
    
    # 2. Buscar todas las asociaciones activas de este canal
    associations = db.query(NotionSlackAssociation).filter(
        NotionSlackAssociation.slack_channel_id == slack_channel.id
    ).all()

    print(f"Asociaciones encontradas: {len(associations)}")
    
    if not associations:
        print(f"⚠️ Canal {slack_channel.channel_name} no tiene asociaciones con Notion")
        return []
    
    # 3. Obtener las databases de Notion asociadas
    notion_databases = []
    for association in associations:
        notion_db = db.query(NotionDatabase).filter(
            NotionDatabase.id == association.notion_database_id,
            NotionDatabase.is_active == True
        ).first()
        
        if notion_db:
            notion_databases.append({
                "association_id": association.id,
                "notion_database_id": notion_db.id,
                "notion_database_id_external": notion_db.notion_database_id,
                "database_name": notion_db.database_name,
                "database_url": notion_db.database_url,
                "auto_sync": association.auto_sync,
                "notes": association.notes
            })
    
    if notion_databases:
        print(f"✅ Canal {slack_channel.channel_name} tiene {len(notion_databases)} database(s) de Notion asociada(s)")
    
    return notion_databases

