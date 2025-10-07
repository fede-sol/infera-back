# 🔐 Sistema de Autenticación

Sistema completo de autenticación con JWT y SQLite para gestionar usuarios y sus credenciales de integración.

## 🚀 Quick Start

### 1. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar Variables de Entorno

Crea un archivo `.env` con:

```bash
# Secret Key para JWT (cambiar en producción!)
SECRET_KEY=tu-secret-key-super-secreta-genera-una-random

# Base de Datos (opcional, por defecto usa SQLite local)
DATABASE_URL=sqlite:///./infera.db

# Otras configuraciones...
OPENAI_TOKEN=sk-...
GITHUB_TOKEN=ghp_...
```

### 3. Iniciar Servidor

```bash
uvicorn main:app --reload
```

La base de datos se crea automáticamente en `infera.db`.

## 📚 Endpoints Disponibles

### Autenticación

#### Registrar Usuario
```bash
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "usuario",
  "password": "contraseña-segura",
  "full_name": "Nombre Completo"
}
```

Respuesta:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "usuario",
    "is_admin": true,  // El primer usuario es admin
    ...
  }
}
```

**Nota**: El primer usuario que se registre será automáticamente administrador.

#### Login
```bash
POST /auth/login
Content-Type: application/json

{
  "username": "usuario",
  "password": "contraseña"
}
```

Respuesta:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {...}
}
```

### Perfil de Usuario

#### Obtener Mi Perfil
```bash
GET /auth/me
Authorization: Bearer eyJ...
```

#### Actualizar Mi Perfil
```bash
PUT /auth/me
Authorization: Bearer eyJ...
Content-Type: application/json

{
  "full_name": "Nuevo Nombre",
  "email": "nuevo@example.com"
}
```

### Credenciales de Integración

#### Ver Credenciales
```bash
GET /auth/credentials
Authorization: Bearer eyJ...
```

Respuesta:
```json
{
  "has_github_token": true,
  "has_slack_token": false,
  "has_notion_token": true,
  "has_openai_key": false
}
```

#### Actualizar Credenciales
```bash
PUT /auth/credentials
Authorization: Bearer eyJ...
Content-Type: application/json

{
  "github_token": "ghp_nuevo_token",
  "slack_token": "xoxb-nuevo-token",
  "notion_token": "secret_nuevo_token",
  "openai_api_key": "sk-nuevo-key"
}
```

**Nota**: Solo envía las credenciales que quieras actualizar. No es necesario enviar todas.

#### Eliminar Credencial
```bash
DELETE /auth/credentials/{service}
Authorization: Bearer eyJ...

# Servicios: github, slack, notion, openai
```

### Administración (Solo Admin)

#### Listar Usuarios
```bash
GET /auth/users
Authorization: Bearer eyJ...
```

#### Eliminar Usuario
```bash
DELETE /auth/users/{user_id}
Authorization: Bearer eyJ...
```

## 🔒 Uso del Token JWT

Una vez que obtengas el token en `/auth/login` o `/auth/register`, úsalo en todas las peticiones protegidas:

```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

El token expira en **7 días** por defecto.

## 💾 Modelo de Datos

### Usuario

```python
{
  "id": 1,
  "email": "user@example.com",
  "username": "usuario",
  "full_name": "Nombre Completo",
  "is_active": true,
  "is_admin": false,
  "created_at": "2025-01-01T00:00:00",
  
  # Credenciales (encriptadas en la base de datos)
  "github_token": "ghp_...",      # null si no está configurado
  "slack_token": "xoxb_...",      # null si no está configurado
  "notion_token": "secret_...",   # null si no está configurado
  "openai_api_key": "sk-..."      # null si no está configurado
}
```

## 🔐 Seguridad

### Passwords
- Los passwords se hashean con **bcrypt**
- Nunca se almacenan en texto plano
- Nunca se retornan en las respuestas de la API

### Tokens
- Las credenciales de integración se almacenan en la base de datos
- Solo el dueño puede ver/modificar sus credenciales
- Los tokens JWT tienen expiración configurable

### Secret Key
**IMPORTANTE**: Genera una secret key segura para producción:

```python
import secrets
print(secrets.token_urlsafe(32))
```

Y configúrala en `.env`:
```bash
SECRET_KEY=tu-secret-key-super-secreta-generada
```

## 🛠️ Integración con Endpoints Existentes

### Proteger Endpoints

Para proteger cualquier endpoint con autenticación:

```python
from auth import get_current_user_token, get_current_user
from database import get_db
from sqlalchemy.orm import Session

@app.post("/mi-endpoint-protegido")
async def mi_endpoint(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db)
):
    # Obtener usuario actual
    current_user = get_current_user(payload, db)
    
    # Usar credenciales del usuario
    github_token = current_user.github_token
    notion_token = current_user.notion_token
    
    # Tu lógica aquí...
    return {"message": "OK"}
```

### Solo Admin

```python
from auth import require_admin

@app.post("/admin-only")
async def admin_endpoint(
    current_user = Depends(require_admin)
):
    # Solo usuarios admin pueden acceder
    return {"message": "Eres admin!"}
```

## 📊 Base de Datos

### SQLite

Por defecto usa SQLite en `infera.db`. Perfecto para desarrollo y aplicaciones pequeñas.

### PostgreSQL (Producción)

Para producción, cambia en `.env`:

```bash
DATABASE_URL=postgresql://user:password@localhost/infera_db
```

Y en `database.py` el engine se configura automáticamente.

## 🧪 Testing

### Registrar y Login

```bash
# Registrar primer usuario (será admin)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "username": "admin",
    "password": "admin123",
    "full_name": "Admin User"
  }'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'

# Guardar el token de la respuesta
export TOKEN="eyJ..."

# Obtener mi perfil
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Actualizar Credenciales

```bash
curl -X PUT http://localhost:8000/auth/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "github_token": "ghp_mi_token_personal",
    "notion_token": "secret_mi_token_notion"
  }'
```

## 🔄 Flujo Completo

1. **Usuario se registra** → Obtiene token JWT
2. **Usuario configura credenciales** → GitHub, Slack, Notion, OpenAI
3. **Usuario hace requests** → Usa su token en el header `Authorization`
4. **Backend usa credenciales del usuario** → Para llamar a APIs externas

## 🚨 Troubleshooting

### Error: "Token inválido"
- Verifica que el header sea: `Authorization: Bearer TOKEN`
- Verifica que el token no haya expirado (7 días)
- Haz login de nuevo para obtener un token nuevo

### Error: "SECRET_KEY not configured"
- Configura `SECRET_KEY` en tu `.env`
- Reinicia el servidor

### Error: "Database not found"
- La base de datos se crea automáticamente
- Verifica permisos de escritura en el directorio

## 📖 Documentación Interactiva

FastAPI genera documentación automática:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Puedes probar todos los endpoints directamente desde el navegador!

