from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from auth.models import Base, migrate_legacy_credentials
import os


# Configuración de la base de datos SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3")

# Crear engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Crear sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Inicializa la base de datos creando todas las tablas y migrando datos legacy"""
    print("🗄️  Inicializando base de datos...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas")

    # Migrar datos legacy
    db = SessionLocal()
    try:
        migrate_legacy_credentials(db)
    except Exception as e:
        print(f"⚠️  Error en migración: {e}")
    finally:
        db.close()

    print("✅ Base de datos inicializada")


def get_db():
    """
    Dependency para obtener una sesión de base de datos
    
    Yields:
        Session: Sesión de base de datos
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

