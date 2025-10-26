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


async def get_slack_user_info(slack_token: str, user_id: str) -> Dict:
    """
    Obtiene información detallada del perfil de un usuario de Slack usando su ID.

    Args:
        slack_token: Token de autenticación de Slack
        user_id: ID del usuario de Slack (ej: 'U1234567890')

    Returns:
        Diccionario con información del perfil del usuario

    Raises:
        HTTPException: Si hay error en la comunicación con Slack
    """
    if not slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado. Configure su token primero."
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de usuario de Slack requerido"
        )

    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://slack.com/api/users.profile.get",
                headers=headers,
                params={"user": user_id},
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
            elif error_msg == "user_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Usuario de Slack no encontrado: {user_id}"
                )
            elif error_msg == "users_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Usuario de Slack no encontrado: {user_id}"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error de Slack: {error_msg}"
            )

        # Extraer información del perfil del usuario
        profile = data.get("profile", {})

        # Retornar información del perfil del usuario
        return {
            "slack_user_id": user_id,  # El user_id viene como parámetro
            "display_name": profile.get("display_name"),
            "display_name_normalized": profile.get("display_name_normalized"),
            "real_name": profile.get("real_name"),
            "real_name_normalized": profile.get("real_name_normalized"),
            "first_name": profile.get("first_name"),
            "last_name": profile.get("last_name"),
            "email": profile.get("email"),
            "phone": profile.get("phone"),
            "skype": profile.get("skype"),
            "title": profile.get("title"),
            "status_text": profile.get("status_text"),
            "status_emoji": profile.get("status_emoji"),
            "status_expiration": profile.get("status_expiration"),
            "team": profile.get("team"),
            "avatar_hash": profile.get("avatar_hash"),
            "image_24": profile.get("image_24"),
            "image_32": profile.get("image_32"),
            "image_48": profile.get("image_48"),
            "image_72": profile.get("image_72"),
            "image_192": profile.get("image_192"),
            "image_512": profile.get("image_512"),
            "image_1024": profile.get("image_1024"),
            "image_original": profile.get("image_original"),
            "is_custom_image": profile.get("is_custom_image"),
            "fields": profile.get("fields", {}),
            "pronouns": profile.get("pronouns"),
            "huddle_state": profile.get("huddle_state"),
            "huddle_state_expiration_ts": profile.get("huddle_state_expiration_ts")
        }


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
    from auth.models import Resource, ResourceAssociation, Integration, IntegrationType, ResourceType

    # 1. Buscar el canal en la base de datos local
    slack_channel = db.query(Resource).join(Integration).filter(
        Resource.external_id == slack_channel_id_external,
        Resource.user_id == user_id,
        Integration.integration_type == IntegrationType.SLACK,
        Resource.resource_type == ResourceType.MESSAGING_CHANNEL,
        Resource.is_active == True
    ).first()

    if not slack_channel:
        print(f"⚠️ Canal de Slack {slack_channel_id_external} no encontrado en la base de datos local")
        return []

    print(f"Canal de Slack encontrado: {slack_channel}")

    # 2. Buscar todas las asociaciones activas donde este canal es fuente
    associations = db.query(ResourceAssociation).filter(
        ResourceAssociation.source_resource_id == slack_channel.id,
        ResourceAssociation.is_active == True
    ).all()

    print(f"Asociaciones encontradas: {len(associations)}")

    if not associations:
        print(f"⚠️ Canal {slack_channel.name} no tiene asociaciones con Notion")
        return []

    # 3. Obtener las databases de Notion asociadas
    notion_databases = []
    for association in associations:
        notion_db = association.target_resource

        if notion_db and notion_db.is_active:
            notion_databases.append({
                "association_id": association.id,
                "notion_database_id": notion_db.id,
                "notion_database_id_external": notion_db.external_id,
                "database_name": notion_db.name,
                "database_url": notion_db.url,
                "auto_sync": association.auto_sync,
                "notes": association.notes
            })

    if notion_databases:
        print(f"✅ Canal {slack_channel.name} tiene {len(notion_databases)} database(s) de Notion asociada(s)")

    return notion_databases


async def get_slack_message_link(slack_token: str, channel_id: str, message_ts: str) -> str:
    """
    Obtiene el enlace de un mensaje de Slack.

    Args:
        slack_token: Token de autenticación de Slack
        channel_id: ID del canal de Slack
        message_ts: ID del mensaje de Slack

    Returns:
        Enlace permanente al mensaje de Slack

    Raises:
        HTTPException: Si hay error en la comunicación con Slack
    """
    if not slack_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Slack no configurado. Configure su token primero."
        )

    if not channel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID del canal de Slack requerido"
        )

    if not message_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timestamp del mensaje de Slack requerido"
        )

    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://slack.com/api/chat.getPermalink",
                headers=headers,
                params={
                    "channel": channel_id,
                    "message_ts": message_ts
                },
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
            elif error_msg == "channel_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Canal de Slack no encontrado"
                )
            elif error_msg == "message_not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Mensaje de Slack no encontrado"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error de Slack: {error_msg}"
            )

        # Retornar el enlace permanente
        permalink = data.get("permalink")
        if not permalink:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo obtener el enlace del mensaje"
            )

        return permalink