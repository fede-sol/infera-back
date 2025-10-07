from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """
    Modelo de usuario con credenciales de integración
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    
    # Credenciales de integraciones
    github_token = Column(String, nullable=True)
    slack_token = Column(String, nullable=True)
    slack_team_id = Column(String, nullable=True)

    notion_token = Column(String, nullable=True)
    
    # Configuraciones adicionales
    openai_api_key = Column(String, nullable=True)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"
    
    def to_dict(self):
        """Convertir a diccionario (sin passwords ni tokens)"""
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

