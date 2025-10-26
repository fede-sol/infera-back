from sqlalchemy.orm import Session
from auth.models import Resource, Integration, IntegrationType, ResourceType, ResourceAssociation


def get_slack_channels_for_user(db: Session, user_id: int):
    """
    Helper para obtener todos los channels de Slack de un usuario.
    Ahora usa el modelo Resource genérico.
    """
    return db.query(Resource).join(Integration).filter(
        Resource.user_id == user_id,
        Integration.integration_type == IntegrationType.SLACK,
        Resource.resource_type == ResourceType.MESSAGING_CHANNEL,
        Resource.is_active == True
    ).all()


def get_slack_channel_by_external_id(db: Session, user_id: int, external_id: str):
    """
    Helper para obtener un channel específico por su ID externo.
    """
    return db.query(Resource).join(Integration).filter(
        Resource.user_id == user_id,
        Resource.external_id == external_id,
        Integration.integration_type == IntegrationType.SLACK,
        Resource.resource_type == ResourceType.MESSAGING_CHANNEL,
        Resource.is_active == True
    ).first()


def create_slack_channel_resource(db: Session, user_id: int, channel_data: dict):
    """
    Helper para crear un recurso de tipo channel de Slack.
    Busca o crea la integración de Slack para el usuario.
    """
    # Buscar integración de Slack del usuario
    integration = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.integration_type == IntegrationType.SLACK,
        Integration.is_active == True
    ).first()

    if not integration:
        raise ValueError("Usuario no tiene integración de Slack configurada")

    # Crear el recurso
    resource = Resource(
        user_id=user_id,
        integration_id=integration.id,
        resource_type=ResourceType.MESSAGING_CHANNEL,
        external_id=channel_data["slack_channel_id"],
        name=channel_data["channel_name"],
        resource_metadata={
            "is_private": channel_data.get("is_private", False),
            **channel_data.get("metadata", {})
        }
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def create_resource_association(db: Session, source_resource_id: int, target_resource_id: int, config: dict = None):
    """
    Helper para crear una asociación entre recursos.
    """
    association = ResourceAssociation(
        source_resource_id=source_resource_id,
        target_resource_id=target_resource_id,
        auto_sync=config.get("auto_sync", True) if config else True,
        sync_direction=config.get("sync_direction", "source_to_target") if config else "source_to_target",
        config=config.get("config", {}) if config else {},
        notes=config.get("notes") if config else None
    )

    db.add(association)
    db.commit()
    db.refresh(association)
    return association


def get_resource_associations_for_user(db: Session, user_id: int, source_resource_id: int = None, target_resource_id: int = None):
    """
    Helper para obtener asociaciones de recursos de un usuario.
    Puede filtrar por recurso fuente o destino.
    """
    query = db.query(ResourceAssociation).join(
        Resource, ResourceAssociation.source_resource_id == Resource.id
    ).filter(Resource.user_id == user_id)

    if source_resource_id:
        query = query.filter(ResourceAssociation.source_resource_id == source_resource_id)

    if target_resource_id:
        query = query.filter(ResourceAssociation.target_resource_id == target_resource_id)

    return query.filter(ResourceAssociation.is_active == True).all()

