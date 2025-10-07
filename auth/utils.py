from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
from auth.models import User

load_dotenv()

# Configuración de seguridad
SECRET_KEY = os.getenv("SECRET_KEY", "tu-secret-key-super-secreta-cambiar-en-produccion")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 días

# Security scheme para FastAPI
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña coincide con su hash"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """
    Genera un hash de una contraseña usando bcrypt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token JWT
    
    Args:
        data: Datos a codificar en el token
        expires_delta: Tiempo de expiración del token
        
    Returns:
        Token JWT codificado
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Decodifica un token JWT
    
    Args:
        token: Token JWT a decodificar
        
    Returns:
        Datos decodificados del token
        
    Raises:
        HTTPException: Si el token es inválido
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Extrae y valida el token del header Authorization
    
    Args:
        credentials: Credenciales HTTP Bearer
        
    Returns:
        Payload del token decodificado
        
    Raises:
        HTTPException: Si el token es inválido o no está presente
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    # Verificar que el token tenga un subject (user_id como string)
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: falta subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


def get_current_user(
    payload: dict = Depends(get_current_user_token),
    db: Session = None  # Se inyectará desde routes
):
    """
    Obtiene el usuario actual desde el token
    
    Args:
        payload: Payload del token JWT
        db: Sesión de base de datos
        
    Returns:
        Usuario actual
        
    Raises:
        HTTPException: Si el usuario no existe o no está activo
    """
    from auth.models import User
    
    user_id_str = payload.get("sub")
    user_id = int(user_id_str)  # Convertir de string a int
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    
    return user


def require_admin(current_user = Depends(get_current_user)):
    """
    Dependency que requiere que el usuario sea admin
    
    Args:
        current_user: Usuario actual
        
    Returns:
        Usuario admin
        
    Raises:
        HTTPException: Si el usuario no es admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador"
        )
    return current_user

def get_user_credentials(user_id: str,db: Session):
    """
    Obtiene las credenciales del usuario
    """
    from auth.models import User
    user = db.query(User).filter(User.id == user_id).first()
    return {
        "github_token": user.github_token,
        "slack_token": user.slack_token,
        "notion_token": user.notion_token,
        "openai_api_key": user.openai_api_key
    }

def get_user_by_slack_team_id(slack_team_id: str,db: Session) -> User:
    """
    Obtiene el usuario por el team_id de Slack
    """
    from auth.models import User
    user = db.query(User).filter(User.slack_team_id == slack_team_id).first()
    return user