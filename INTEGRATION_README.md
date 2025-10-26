# Documentación de Integración Notion-Slack

## Resumen

Este módulo permite configurar la integración entre Notion y Slack para crear páginas de documentación en Notion basadas en mensajes de channels de Slack.

## Arquitectura

### Modelos de Base de Datos

#### 1. `NotionDatabase`
Guarda información de las databases de Notion que el usuario quiere usar.
- `notion_database_id`: ID de la database en Notion
- `database_name`: Nombre de la database
- `database_url`: URL de la database

#### 2. `SlackChannel`
Guarda información de los channels de Slack que el usuario quiere monitorear.
- `slack_channel_id`: ID del channel en Slack
- `channel_name`: Nombre del channel
- `is_private`: Si es un channel privado

#### 3. `NotionSlackAssociation`
Asocia databases de Notion con channels de Slack (1 database → N channels).
- `notion_database_id`: Referencia a la database
- `slack_channel_id`: Referencia al channel
- `auto_sync`: Si debe sincronizar automáticamente
- `notes`: Notas adicionales sobre la configuración

## Configuración Inicial

### 1. Configurar Tokens

Primero, el usuario debe configurar sus tokens de Notion y Slack:

```bash
PUT /auth/credentials
Content-Type: application/json
Authorization: Bearer {token}

{
  "notion_token": "secret_...",
  "slack_token": "xoxb-..."
}
```

O para Slack, usar el flujo OAuth:
```bash
GET /auth/slack/oauth?code={code}&state={user_id}
```

### 2. Verificar Credenciales

```bash
GET /auth/credentials
Authorization: Bearer {token}
```

Respuesta:
```json
{
  "has_github_token": false,
  "has_slack_token": true,
  "has_notion_token": true,
  "has_openai_key": false
}
```

## Endpoints de Notion

### Listar Databases Disponibles

Consulta las databases de Notion usando la API (no las guarda en BD):

```bash
GET /notion/databases
Authorization: Bearer {token}
```

Respuesta:
```json
{
  "count": 2,
  "databases": [
    {
      "notion_database_id": "abc123...",
      "database_name": "Documentación Técnica",
      "database_url": "https://notion.so/...",
      "created_time": "2025-01-01T00:00:00.000Z",
      "last_edited_time": "2025-01-15T00:00:00.000Z"
    }
  ]
}
```

### Obtener Detalles de una Database

```bash
GET /notion/databases/{database_id}
Authorization: Bearer {token}
```

### Guardar Database en BD Local

Para poder asociar la database con channels, primero hay que guardarla:

```bash
POST /notion/saved-databases
Authorization: Bearer {token}
Content-Type: application/json

{
  "notion_database_id": "abc123...",
  "database_name": "Documentación Técnica",
  "database_url": "https://notion.so/..."
}
```

### Listar Databases Guardadas

```bash
GET /notion/saved-databases
Authorization: Bearer {token}
```

### Eliminar Database Guardada

```bash
DELETE /notion/saved-databases/{id}
Authorization: Bearer {token}
```

⚠️ Esto también eliminará todas las asociaciones con channels.

## Endpoints de Slack

### Listar Channels Disponibles

Consulta los channels de Slack usando la API (no los guarda en BD):

```bash
GET /slack/channels?include_private=true
Authorization: Bearer {token}
```

Respuesta:
```json
{
  "count": 5,
  "channels": [
    {
      "slack_channel_id": "C01ABC123",
      "channel_name": "general",
      "is_private": false,
      "is_member": true,
      "num_members": 25,
      "topic": "General discussion",
      "purpose": "Company-wide announcements"
    }
  ]
}
```

### Obtener Detalles de un Channel

```bash
GET /slack/channels/{channel_id}
Authorization: Bearer {token}
```

### Guardar Channel en BD Local

```bash
POST /slack/saved-channels
Authorization: Bearer {token}
Content-Type: application/json

{
  "slack_channel_id": "C01ABC123",
  "channel_name": "general",
  "is_private": false
}
```

### Listar Channels Guardados

```bash
GET /slack/saved-channels
Authorization: Bearer {token}
```

### Eliminar Channel Guardado

```bash
DELETE /slack/saved-channels/{id}
Authorization: Bearer {token}
```

## Endpoints de Asociaciones

### Crear Asociaciones Inteligentes (RECOMENDADO) 🚀

Este es el método más fácil. Crea automáticamente la database y channels si no existen:

```bash
POST /slack/associations/smart
Authorization: Bearer {token}
Content-Type: application/json

{
  "notion_database_id_external": "abc123-notion-database-id",
  "slack_channel_ids_external": ["C01ABC123", "C02DEF456"],
  "auto_sync": true,
  "notes": "Configuración para documentación de desarrollo"
}
```

**Ventajas**:
- ✅ No necesitas guardar previamente la database ni los channels
- ✅ Usa los IDs externos de Notion y Slack (los que ves en las APIs)
- ✅ Crea automáticamente lo que no existe en la BD local
- ✅ Más rápido: 1 solo request en vez de 3+

**¿Cómo obtener los IDs?**
- Database de Notion: usa `GET /notion/databases` y copia el campo `notion_database_id`
- Channels de Slack: usa `GET /slack/channels` y copia el campo `slack_channel_id`

### Crear Asociaciones (Método Manual)

Si ya guardaste la database y channels, puedes usar este endpoint:

```bash
POST /slack/associations
Authorization: Bearer {token}
Content-Type: application/json

{
  "notion_database_id": 1,
  "slack_channel_ids": [1, 2, 3],
  "auto_sync": true,
  "notes": "Configuración para documentación de desarrollo"
}
```

**Nota**: Este método requiere que hayas guardado previamente la database y channels con:
- `POST /notion/saved-databases`
- `POST /slack/saved-channels`

### Listar Asociaciones

Listar todas las asociaciones, con opción de filtrar:

```bash
# Todas las asociaciones
GET /slack/associations
Authorization: Bearer {token}

# Filtrar por database
GET /slack/associations?notion_database_id=1
Authorization: Bearer {token}

# Filtrar por channel
GET /slack/associations?slack_channel_id=1
Authorization: Bearer {token}
```

Respuesta:
```json
{
  "count": 3,
  "associations": [
    {
      "id": 1,
      "notion_database": {
        "id": 1,
        "notion_database_id": "abc123...",
        "database_name": "Documentación Técnica"
      },
      "slack_channel": {
        "id": 1,
        "slack_channel_id": "C01ABC123",
        "channel_name": "general"
      },
      "auto_sync": true,
      "notes": "...",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ]
}
```

### Obtener Asociación

```bash
GET /slack/associations/{association_id}
Authorization: Bearer {token}
```

### Actualizar Asociación

```bash
PUT /slack/associations/{association_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "auto_sync": false,
  "notes": "Temporalmente deshabilitado"
}
```

### Eliminar Asociación

```bash
DELETE /slack/associations/{association_id}
Authorization: Bearer {token}
```

## Flujo de Trabajo Típico

### Método Rápido (Recomendado) 🚀

1. **Configurar tokens**
   ```bash
   PUT /auth/credentials
   ```

2. **Explorar databases de Notion**
   ```bash
   GET /notion/databases
   # Anotar el "notion_database_id" de la database deseada
   ```

3. **Explorar channels de Slack**
   ```bash
   GET /slack/channels
   # Anotar los "slack_channel_id" de los channels deseados
   ```

4. **Crear asociaciones (automáticamente crea todo)**
   ```bash
   POST /slack/associations/smart
   {
     "notion_database_id_external": "abc123...",
     "slack_channel_ids_external": ["C01ABC", "C02DEF"]
   }
   ```

5. **¡Listo!** Verificar configuración:
   ```bash
   GET /slack/associations
   ```

### Método Manual (Si prefieres control total)

1. **Configurar tokens**
   ```bash
   PUT /auth/credentials
   ```

2. **Explorar databases de Notion**
   ```bash
   GET /notion/databases
   ```

3. **Guardar database de interés**
   ```bash
   POST /notion/saved-databases
   ```

4. **Explorar channels de Slack**
   ```bash
   GET /slack/channels
   ```

5. **Guardar channels de interés**
   ```bash
   POST /slack/saved-channels
   # Repetir para cada channel
   ```

6. **Crear asociaciones**
   ```bash
   POST /slack/associations
   {
     "notion_database_id": 1,
     "slack_channel_ids": [1, 2, 3]
   }
   ```

7. **Verificar configuración**
   ```bash
   GET /slack/associations
   ```

## Notas Importantes

- Todos los endpoints requieren autenticación JWT (header `Authorization: Bearer {token}`)
- Los usuarios solo pueden ver/modificar sus propias configuraciones
- Las asociaciones se eliminan en cascada cuando se elimina una database o channel
- Los tokens de Notion y Slack deben tener los permisos necesarios:
  - **Notion**: Leer databases
  - **Slack**: Leer channels (`channels:read`, `groups:read`)

## Testing con curl

### Método Rápido (Recomendado)

```bash
# 1. Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' \
  | jq -r '.access_token')

# 2. Configurar tokens (Notion y Slack)
curl -X PUT http://localhost:8000/auth/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notion_token":"secret_...","slack_token":"xoxb-..."}'

# 3. Ver databases de Notion
curl http://localhost:8000/notion/databases \
  -H "Authorization: Bearer $TOKEN" | jq

# 4. Ver channels de Slack
curl http://localhost:8000/slack/channels \
  -H "Authorization: Bearer $TOKEN" | jq

# 5. Crear asociación (automáticamente guarda todo)
curl -X POST http://localhost:8000/slack/associations/smart \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "notion_database_id_external":"abc123-notion-id",
    "slack_channel_ids_external":["C01ABC123","C02DEF456"],
    "auto_sync":true
  }' | jq

# 6. Ver asociaciones
curl http://localhost:8000/slack/associations \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Método Manual

```bash
# 1. Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' \
  | jq -r '.access_token')

# 2. Configurar Notion token
curl -X PUT http://localhost:8000/auth/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notion_token":"secret_..."}'

# 3. Ver databases
curl http://localhost:8000/notion/databases \
  -H "Authorization: Bearer $TOKEN"

# 4. Guardar database
curl -X POST http://localhost:8000/notion/saved-databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notion_database_id":"abc","database_name":"Docs"}'

# 5. Ver channels
curl http://localhost:8000/slack/channels \
  -H "Authorization: Bearer $TOKEN"

# 6. Guardar channel
curl -X POST http://localhost:8000/slack/saved-channels \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"slack_channel_id":"C01","channel_name":"general"}'

# 7. Crear asociación
curl -X POST http://localhost:8000/slack/associations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notion_database_id":1,"slack_channel_ids":[1],"auto_sync":true}'

# 8. Ver asociaciones
curl http://localhost:8000/slack/associations \
  -H "Authorization: Bearer $TOKEN"
```

## Documentación Interactiva

Una vez que la aplicación esté corriendo, puedes acceder a la documentación interactiva de Swagger en:

```
http://localhost:8000/docs
```

## Sistema de Batching para Mensajes

### Descripción

El sistema de batching permite procesar múltiples mensajes de Slack de forma agrupada en lugar de procesarlos individualmente. Esto mejora la eficiencia y reduce la carga del servidor.

### Configuración

Configura la variable de entorno `BATCH_TIMEOUT_SECONDS` para definir el tiempo en segundos que se espera antes de procesar un batch:

```bash
# En tu archivo .env
BATCH_TIMEOUT_SECONDS=30  # Espera 30 segundos antes de procesar
```

### Cómo Funciona

1. **Recepción de Mensajes**: Cuando llega un mensaje de Slack, se agrega a un batch específico del canal
2. **Timer de Espera**: Se inicia un timer con el timeout configurado
3. **Procesamiento**: Si llega otro mensaje antes del timeout, se reinicia el timer. Cuando se cumple el timeout sin nuevos mensajes:
   - Se procesa cada mensaje individualmente con el servicio NLP
   - Se ejecuta el `background_analysis_task` para cada mensaje con su remitente y link
   - Se limpia el batch del canal

### Endpoints del Sistema de Batching

#### Ver Estado de Batches

```bash
# Ver todos los batches activos
GET /orchestration/batch-status

# Ver estado de un canal específico
GET /orchestration/batch-status?channel_id=C01ABC123
```

Respuesta:
```json
{
  "active_channels": 2,
  "batch_timeout_seconds": 30,
  "channels": {
    "C01ABC123": {
      "status": "active",
      "message_count": 3,
      "created_at": "2025-01-01T10:00:00",
      "timeout_seconds": 30,
      "seconds_since_creation": 15
    }
  }
}
```

#### Forzar Procesamiento de Batch

```bash
POST /orchestration/force-process-batch
Content-Type: application/json

{
  "channel_id": "C01ABC123"
}
```

Respuesta:
```json
{
  "success": true,
  "message": "Batch del canal C01ABC123 procesado exitosamente"
}
```

### Ventajas del Sistema de Batching

- ✅ **Mejor Rendimiento**: Reduce la cantidad de llamadas a servicios externos
- ✅ **Contexto Completo**: Procesa mensajes relacionados que llegan en secuencia
- ✅ **Configurable**: Ajusta el timeout según las necesidades del canal
- ✅ **Monitoreo**: Endpoints para verificar el estado de los batches

### Configuración por Canal

Cada canal de Slack tiene su propio batch independiente. Esto permite:
- Canales de alta actividad: timeout más corto
- Canales de baja actividad: timeout más largo
- Conversaciones relacionadas se procesan juntas

### Logs del Sistema

El sistema genera logs informativos para monitorear su funcionamiento:

```
📥 Mensaje agregado al batch del canal C01ABC123. Total mensajes en batch: 2
⏳ Mensaje agregado al batch. Se procesará en 30 segundos si no llegan más mensajes.
⏰ Procesando batch del canal C01ABC123
🔄 Procesando mensaje: Hola equipo, ¿cómo están?...
✅ Batch del canal C01ABC123 procesado completamente (2 mensajes)
```

