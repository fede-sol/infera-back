from sqlalchemy.orm import Session
from auth.models import Resource, Integration, IntegrationType, ResourceType


def get_notion_databases_for_user(db: Session, user_id: int):
    """
    Helper para obtener todas las databases de Notion de un usuario.
    Ahora usa el modelo Resource genérico.
    """
    return db.query(Resource).join(Integration).filter(
        Resource.user_id == user_id,
        Integration.integration_type == IntegrationType.NOTION,
        Resource.resource_type == ResourceType.DOCUMENTATION_DATABASE,
        Resource.is_active == True
    ).all()


def get_notion_database_by_external_id(db: Session, user_id: int, external_id: str):
    """
    Helper para obtener una database específica por su ID externo.
    """
    return db.query(Resource).join(Integration).filter(
        Resource.user_id == user_id,
        Resource.external_id == external_id,
        Integration.integration_type == IntegrationType.NOTION,
        Resource.resource_type == ResourceType.DOCUMENTATION_DATABASE,
        Resource.is_active == True
    ).first()


def create_notion_database_resource(db: Session, user_id: int, database_data: dict):
    """
    Helper para crear un recurso de tipo database de Notion.
    Busca o crea la integración de Notion para el usuario.
    """
    # Buscar integración de Notion del usuario
    integration = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.integration_type == IntegrationType.NOTION,
        Integration.is_active == True
    ).first()

    if not integration:
        raise ValueError("Usuario no tiene integración de Notion configurada")

    # Crear el recurso
    resource = Resource(
        user_id=user_id,
        integration_id=integration.id,
        resource_type=ResourceType.DOCUMENTATION_DATABASE,
        external_id=database_data["notion_database_id"],
        name=database_data["database_name"],
        url=database_data.get("database_url"),
        resource_metadata=database_data.get("metadata", {})
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource

