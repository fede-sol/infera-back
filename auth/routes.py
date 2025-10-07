from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import httpx
import os
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from auth.models import User
from auth.utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user_token,
    get_current_user,
    require_admin,
    security,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import get_db

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Autenticación"])


# --- Schemas de Pydantic ---

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


class CredentialsUpdate(BaseModel):
    github_token: Optional[str] = None
    slack_token: Optional[str] = None
    notion_token: Optional[str] = None
    openai_api_key: Optional[str] = None


# --- Endpoints ---

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario
    """
    # Verificar si el email ya existe
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    
    # Verificar si el username ya existe
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El username ya está en uso"
        )
    
    # Crear usuario
    hashed_password = get_password_hash(user_data.password)
    
    # Si es el primer usuario, hacerlo admin
    is_first_user = db.query(User).count() == 0
    
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        is_admin=is_first_user
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Crear token (sub debe ser string en JWT)
    access_token = create_access_token(
        data={"sub": str(new_user.id), "username": new_user.username}
    )
    
    print(f"✅ Usuario registrado: {new_user.username} (Admin: {is_first_user})")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user.to_dict()
    }


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Inicia sesión y retorna un token JWT
    """
    # Buscar usuario
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    
    # Crear token (sub debe ser string en JWT)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    
    print(f"✅ Login exitoso: {user.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user.to_dict()
    }


@router.get("/me")
def get_me(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene información del usuario actual
    """
    current_user = get_current_user(payload, db)
    return current_user.to_dict()


@router.put("/me")
def update_me(
    user_update: UserUpdate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Actualiza información del usuario actual
    """
    current_user = get_current_user(payload, db)
    
    # Actualizar campos
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    
    if user_update.email is not None:
        # Verificar que el email no esté en uso
        existing = db.query(User).filter(
            User.email == user_update.email,
            User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está en uso"
            )
        current_user.email = user_update.email
    
    db.commit()
    db.refresh(current_user)
    
    print(f"✅ Usuario actualizado: {current_user.username}")
    
    return current_user.to_dict()


@router.put("/credentials")
def update_credentials(
    creds: CredentialsUpdate,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Actualiza las credenciales de integraciones del usuario
    """
    current_user = get_current_user(payload, db)
    
    # Actualizar credenciales (solo las que se envíen)
    if creds.github_token is not None:
        current_user.github_token = creds.github_token
        print(f"✅ GitHub token actualizado para: {current_user.username}")
    
    if creds.slack_token is not None:
        current_user.slack_token = creds.slack_token
        print(f"✅ Slack token actualizado para: {current_user.username}")
    
    if creds.notion_token is not None:
        current_user.notion_token = creds.notion_token
        print(f"✅ Notion token actualizado para: {current_user.username}")
    
    if creds.openai_api_key is not None:
        current_user.openai_api_key = creds.openai_api_key
        print(f"✅ OpenAI API key actualizada para: {current_user.username}")
    
    db.commit()
    db.refresh(current_user)
    
    return {
        "message": "Credenciales actualizadas exitosamente",
        "user": current_user.to_dict()
    }


@router.get("/credentials")
def get_credentials(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene las credenciales del usuario (solo muestra si existen, no los valores)
    """
    current_user = get_current_user(payload, db)
    
    return {
        "has_github_token": bool(current_user.github_token),
        "has_slack_token": bool(current_user.slack_token),
        "has_notion_token": bool(current_user.notion_token),
        "has_openai_key": bool(current_user.openai_api_key),
    }


@router.delete("/credentials/{service}")
def delete_credential(
    service: str,
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    """
    Elimina una credencial específica
    """
    current_user = get_current_user(payload, db)
    
    service_map = {
        "github": "github_token",
        "slack": "slack_token",
        "notion": "notion_token",
        "openai": "openai_api_key"
    }
    
    if service not in service_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Servicio inválido. Opciones: {', '.join(service_map.keys())}"
        )
    
    # Eliminar credencial
    setattr(current_user, service_map[service], None)
    db.commit()
    
    print(f"✅ Credencial {service} eliminada para: {current_user.username}")
    
    return {
        "message": f"Credencial de {service} eliminada exitosamente"
    }

@router.get("/slack/oauth")
async def slack_oauth(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """
    Callback de OAuth de Slack. Intercambia el código temporal por un token de acceso.
    
    Args:
        code: Código temporal de Slack
        state: ID del usuario que inició el flujo OAuth
        db: Sesión de base de datos
    
    Returns:
        Mensaje de éxito y datos del usuario actualizados
    """
    # Obtener credenciales de la app de Slack desde variables de entorno
    slack_client_id = os.getenv("SLACK_CLIENT_ID")
    slack_client_secret = os.getenv("SLACK_CLIENT_SECRET")
    slack_redirect_uri = os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/auth/slack/oauth")
    
    if not slack_client_id or not slack_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credenciales de Slack no configuradas en el servidor"
        )
    
    # Obtener el usuario del state
    try:
        user_id = int(state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State inválido: debe ser un ID de usuario"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Intercambiar el código por un token de acceso
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": slack_client_id,
                    "client_secret": slack_client_secret,
                    "code": code,
                    "redirect_uri": slack_redirect_uri
                }
            )
            response.raise_for_status()
            slack_data = response.json()
            
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al comunicarse con Slack: {str(e)}"
            )
    
    # Verificar que la respuesta de Slack sea exitosa
    if not slack_data.get("ok"):
        error_msg = slack_data.get("error", "Error desconocido")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error de Slack: {error_msg}"
        )
    
    # Guardar el token y team_id en la base de datos
    print(slack_data)
    user.slack_token = slack_data.get("authed_user", {}).get("access_token")
    user.slack_team_id = slack_data.get("team", {}).get("id")
    
    db.commit()
    db.refresh(user)
    
    print(f"✅ Token de Slack configurado para usuario: {user.username} (Team: {user.slack_team_id})")
    
    return RedirectResponse(url=f"{os.getenv('FRONTEND_URL')}/integrations")

