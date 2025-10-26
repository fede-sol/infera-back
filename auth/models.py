from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class IntegrationType(enum.Enum):
    """Tipos de integraciones soportadas"""
    SLACK = "slack"
    GITHUB = "github"
    NOTION = "notion"
    OPENAI = "openai"
    JIRA = "jira"
    TEAMS = "teams"
    CONFLUENCE = "confluence"
    # Fácil agregar más...


class ResourceType(enum.Enum):
    """Tipos de recursos en las plataformas"""
    MESSAGING_CHANNEL = "messaging_channel"  # Slack channel, Teams channel
    DOCUMENTATION_DATABASE = "documentation_database"  # Notion DB, Confluence space
    CODE_REPOSITORY = "code_repository"  # GitHub repo, GitLab repo
    ISSUE_TRACKER = "issue_tracker"  # Jira project
    # Fácil agregar más...


class User(Base):
    """
    Modelo de usuario simplificado - sin credenciales específicas
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)

    # CAMPOS LEGACY - mantener temporalmente para migración
    github_token = Column(String, nullable=True)
    slack_token = Column(String, nullable=True)
    slack_team_id = Column(String, nullable=True)
    notion_token = Column(String, nullable=True)
    openai_api_key = Column(String, nullable=True)

    # Metadata
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    integrations = relationship("Integration", back_populates="user", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "has_github_token": bool(self.github_token),
            "has_slack_token": bool(self.slack_token),
            "has_notion_token": bool(self.notion_token),
            "has_openai_key": bool(self.openai_api_key),
        }


class Integration(Base):
    """
    Tabla genérica para almacenar credenciales de cualquier integración.
    Reemplaza las columnas específicas en User (slack_token, github_token, etc.)
    """
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Tipo de integración
    integration_type = Column(SQLEnum(IntegrationType), nullable=False, index=True)

    # Credenciales (pueden variar por plataforma)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)

    # Metadata adicional específica de la plataforma (JSON flexible)
    # Ejemplos:
    # - Slack: {"team_id": "T123", "team_name": "Mi Empresa"}
    # - GitHub: {"username": "johndoe", "account_id": "123"}
    # - OAuth: {"expires_at": "2025-12-31", "scope": "read,write"}
    integration_metadata = Column(JSON, nullable=True, default={})

    # Estado
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)

    # Relaciones
    user = relationship("User", back_populates="integrations")
    resources = relationship("Resource", back_populates="integration", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Integration(id={self.id}, type={self.integration_type.value}, user_id={self.user_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "integration_type": self.integration_type.value,
            "has_access_token": bool(self.access_token),
            "has_refresh_token": bool(self.refresh_token),
            "metadata": self.integration_metadata,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class Resource(Base):
    """
    Tabla genérica para almacenar recursos de cualquier plataforma.
    Reemplaza SlackChannel, NotionDatabase, JiraProject, etc.
    """
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=False)

    # Tipo de recurso
    resource_type = Column(SQLEnum(ResourceType), nullable=False, index=True)

    # ID externo en la plataforma (ej: channel_id de Slack, database_id de Notion)
    external_id = Column(String, nullable=False, index=True)

    # Información básica
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)

    # Metadata específica de la plataforma (JSON flexible)
    # Ejemplos:
    # - Slack: {"is_private": true, "num_members": 25, "topic": "Backend discussions"}
    # - Notion: {"parent_id": "abc123", "icon": "📝"}
    # - Jira: {"project_key": "PROJ", "lead": "john@example.com"}
    resource_metadata = Column(JSON, nullable=True, default={})

    # Estado
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    user = relationship("User", back_populates="resources")
    integration = relationship("Integration", back_populates="resources")

    # Asociaciones como fuente o destino
    associations_as_source = relationship(
        "ResourceAssociation",
        foreign_keys="ResourceAssociation.source_resource_id",
        back_populates="source_resource",
        cascade="all, delete-orphan"
    )
    associations_as_target = relationship(
        "ResourceAssociation",
        foreign_keys="ResourceAssociation.target_resource_id",
        back_populates="target_resource",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Resource(id={self.id}, type={self.resource_type.value}, name={self.name})>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "integration_id": self.integration_id,
            "resource_type": self.resource_type.value,
            "external_id": self.external_id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "metadata": self.resource_metadata,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def migrate_legacy_credentials(db):
    """
    Migra credenciales legacy del modelo User a las nuevas tablas Integration y Resource
    """
    from auth.models import User, Integration, IntegrationType, Resource, ResourceType

    users = db.query(User).all()

    for user in users:
        # Migrar GitHub
        if user.github_token and not db.query(Integration).filter(
            Integration.user_id == user.id,
            Integration.integration_type == IntegrationType.GITHUB
        ).first():
            integration = Integration(
                user_id=user.id,
                integration_type=IntegrationType.GITHUB,
                access_token=user.github_token,
                integration_metadata={}
            )
            db.add(integration)

        # Migrar Slack
        if user.slack_token and not db.query(Integration).filter(
            Integration.user_id == user.id,
            Integration.integration_type == IntegrationType.SLACK
        ).first():
            integration = Integration(
                user_id=user.id,
                integration_type=IntegrationType.SLACK,
                access_token=user.slack_token,
                integration_metadata={"team_id": user.slack_team_id} if user.slack_team_id else {}
            )
            db.add(integration)

        # Migrar Notion
        if user.notion_token and not db.query(Integration).filter(
            Integration.user_id == user.id,
            Integration.integration_type == IntegrationType.NOTION
        ).first():
            integration = Integration(
                user_id=user.id,
                integration_type=IntegrationType.NOTION,
                access_token=user.notion_token,
                integration_metadata={}
            )
            db.add(integration)

        # Migrar OpenAI
        if user.openai_api_key and not db.query(Integration).filter(
            Integration.user_id == user.id,
            Integration.integration_type == IntegrationType.OPENAI
        ).first():
            integration = Integration(
                user_id=user.id,
                integration_type=IntegrationType.OPENAI,
                access_token=user.openai_api_key,
                integration_metadata={}
            )
            db.add(integration)

    db.commit()
    print("✅ Migración de credenciales legacy completada")


class ResourceAssociation(Base):
    """
    Tabla genérica para asociar recursos entre sí.
    Reemplaza NotionSlackAssociation y permite cualquier combinación.

    Ejemplos:
    - Slack Channel → Notion Database
    - Teams Channel → Confluence Space
    - Jira Project → GitHub Repository
    - Slack Channel → Multiple Notion Databases
    """
    __tablename__ = "resource_associations"

    id = Column(Integer, primary_key=True, index=True)

    # Recurso fuente (ej: Slack channel, Teams channel)
    source_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)

    # Recurso destino (ej: Notion database, Confluence space)
    target_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)

    # Configuración de la asociación
    auto_sync = Column(Boolean, default=True)
    sync_direction = Column(String, default="source_to_target")  # "source_to_target", "bidirectional"

    # Metadata adicional (JSON flexible)
    # Ejemplos:
    # - Filtros: {"only_decisions": true, "min_confidence": 0.8}
    # - Reglas: {"template_id": "abc", "prefix": "[AUTO]"}
    config = Column(JSON, nullable=True, default={})
    notes = Column(Text, nullable=True)

    # Estado
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)

    # Relaciones
    source_resource = relationship(
        "Resource",
        foreign_keys=[source_resource_id],
        back_populates="associations_as_source"
    )
    target_resource = relationship(
        "Resource",
        foreign_keys=[target_resource_id],
        back_populates="associations_as_target"
    )

    def __repr__(self):
        return f"<ResourceAssociation(id={self.id}, source={self.source_resource_id}, target={self.target_resource_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "source_resource_id": self.source_resource_id,
            "target_resource_id": self.target_resource_id,
            "auto_sync": self.auto_sync,
            "sync_direction": self.sync_direction,
            "config": self.config,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }

    def to_dict_with_details(self):
        return {
            "id": self.id,
            "source_resource": self.source_resource.to_dict() if self.source_resource else None,
            "target_resource": self.target_resource.to_dict() if self.target_resource else None,
            "auto_sync": self.auto_sync,
            "sync_direction": self.sync_direction,
            "config": self.config,
            "notes": self.notes,
            "is_active": self.is_active,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }

