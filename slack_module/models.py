from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from auth.models import Base


class SlackChannel(Base):
    """
    Modelo para guardar información de los channels de Slack
    """
    __tablename__ = "slack_channels"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Información del channel de Slack
    slack_channel_id = Column(String, nullable=False, index=True)
    channel_name = Column(String, nullable=False)
    is_private = Column(Boolean, default=False)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con asociaciones
    database_associations = relationship("NotionSlackAssociation", back_populates="slack_channel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SlackChannel(id={self.id}, name={self.channel_name}, user_id={self.user_id})>"
    
    def to_dict(self):
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "slack_channel_id": self.slack_channel_id,
            "channel_name": self.channel_name,
            "is_private": self.is_private,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NotionSlackAssociation(Base):
    """
    Modelo para asociar databases de Notion con channels de Slack.
    Una database de Notion puede estar asociada a múltiples channels de Slack.
    """
    __tablename__ = "notion_slack_associations"

    id = Column(Integer, primary_key=True, index=True)
    
    # Relaciones
    notion_database_id = Column(Integer, ForeignKey("notion_databases.id"), nullable=False)
    slack_channel_id = Column(Integer, ForeignKey("slack_channels.id"), nullable=False)
    
    # Configuración adicional (opcional)
    auto_sync = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones inversas
    notion_database = relationship("NotionDatabase", back_populates="channel_associations")
    slack_channel = relationship("SlackChannel", back_populates="database_associations")

    def __repr__(self):
        return f"<NotionSlackAssociation(id={self.id}, notion_db={self.notion_database_id}, slack_channel={self.slack_channel_id})>"
    
    def to_dict(self):
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "notion_database_id": self.notion_database_id,
            "slack_channel_id": self.slack_channel_id,
            "auto_sync": self.auto_sync,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_dict_with_details(self):
        """Convertir a diccionario con detalles de las relaciones"""
        return {
            "id": self.id,
            "notion_database": self.notion_database.to_dict() if self.notion_database else None,
            "slack_channel": self.slack_channel.to_dict() if self.slack_channel else None,
            "auto_sync": self.auto_sync,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

