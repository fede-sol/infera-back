from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from auth.models import Base


class NotionDatabase(Base):
    """
    Modelo para guardar información de las databases de Notion
    """
    __tablename__ = "notion_databases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Información de la database de Notion
    notion_database_id = Column(String, nullable=False, index=True)
    database_name = Column(String, nullable=False)
    database_url = Column(String, nullable=True)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con asociaciones
    channel_associations = relationship("NotionSlackAssociation", back_populates="notion_database", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<NotionDatabase(id={self.id}, name={self.database_name}, user_id={self.user_id})>"
    
    def to_dict(self):
        """Convertir a diccionario"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notion_database_id": self.notion_database_id,
            "database_name": self.database_name,
            "database_url": self.database_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

