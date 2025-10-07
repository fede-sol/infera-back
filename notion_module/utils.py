import httpx
from typing import List, Dict, Optional
from fastapi import HTTPException, status


async def get_notion_databases(notion_token: str) -> List[Dict]:
    """
    Obtiene todas las databases de Notion disponibles para el usuario.
    
    Args:
        notion_token: Token de integración de Notion
        
    Returns:
        Lista de databases con su información
        
    Raises:
        HTTPException: Si hay error en la comunicación con Notion
    """
    if not notion_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Notion no configurado. Configure su token primero."
        )
    
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # Buscar todas las databases
            response = await client.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json={
                    "filter": {
                        "property": "object",
                        "value": "database"
                    },
                    "sort": {
                        "direction": "descending",
                        "timestamp": "last_edited_time"
                    }
                },
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            error_msg = "Error al comunicarse con Notion"
            if e.response.status_code == 401:
                error_msg = "Token de Notion inválido o expirado"
            elif e.response.status_code == 403:
                error_msg = "Sin permisos para acceder a las databases de Notion"
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error de red al comunicarse con Notion: {str(e)}"
            )
    
    # Procesar resultados
    databases = []
    for db in data.get("results", []):
        # Extraer el título de la database
        title = "Sin título"
        if db.get("title"):
            title_parts = db["title"]
            if title_parts and len(title_parts) > 0:
                title = title_parts[0].get("plain_text", "Sin título")
        
        databases.append({
            "notion_database_id": db.get("id"),
            "database_name": title,
            "database_url": db.get("url"),
            "created_time": db.get("created_time"),
            "last_edited_time": db.get("last_edited_time"),
        })
    
    return databases


async def get_notion_database_details(notion_token: str, database_id: str) -> Dict:
    """
    Obtiene los detalles de una database específica de Notion.
    
    Args:
        notion_token: Token de integración de Notion
        database_id: ID de la database de Notion
        
    Returns:
        Información detallada de la database
        
    Raises:
        HTTPException: Si hay error en la comunicación con Notion
    """
    if not notion_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de Notion no configurado"
        )
    
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://api.notion.com/v1/databases/{database_id}",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Database de Notion no encontrada"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error al obtener detalles de la database"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error de red: {str(e)}"
            )
    
    # Extraer el título
    title = "Sin título"
    if data.get("title"):
        title_parts = data["title"]
        if title_parts and len(title_parts) > 0:
            title = title_parts[0].get("plain_text", "Sin título")
    
    return {
        "notion_database_id": data.get("id"),
        "database_name": title,
        "database_url": data.get("url"),
        "created_time": data.get("created_time"),
        "last_edited_time": data.get("last_edited_time"),
        "properties": data.get("properties", {}),
    }

