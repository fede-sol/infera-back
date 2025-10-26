import json
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from utils import get_table, save_to_dynamodb, create_classification_item, create_slack_message_item, background_analysis_task, add_message_to_batch, get_batch_status, message_batches
from slack_module.utils import get_notion_databases_for_slack_channel, get_slack_message_link, get_slack_user_info
import os
from dotenv import load_dotenv
from .utils import initialize_langchain_agent, initialize_openai_agent
from sqlalchemy.orm import Session
from database import get_db
from auth.utils import get_user_by_slack_team_id
import httpx

load_dotenv()

router = APIRouter(tags=["Orquestación"])


# Inicializar tabla de DynamoDB
TABLE = get_table()


# --- Modelos de Datos ---

class ClassifyRequest(BaseModel):
    message: str


class AnalyzeRequest(BaseModel):
    message: str


# --- Funciones Auxiliares ---

async def classify_decision(text: str) -> dict:
    """Clasifica un texto usando el servicio de clasificación externo"""

    # Obtener la URL del servicio de clasificación
    classification_service_url = os.getenv("CLASSIFICATION_SERVICE")

    if not classification_service_url:
        print("⚠️ CLASSIFICATION_SERVICE no configurado, retornando clasificación por defecto")
        return {"classification": "GENERAL_CONVERSATION", "confidence": 0.5}

    # Construir URL completa
    analyze_url = f"{classification_service_url}/analyze"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                analyze_url,
                json={"text": text}
            )
            response.raise_for_status()
            result = response.json()
            return {
                "classification": result.get("classification", "GENERAL_CONVERSATION"),
                "confidence": round(result.get("confidence", 0.0), 4)
            }
    except httpx.HTTPError as e:
        print(f"❌ Error al llamar al servicio de clasificación: {e}")
        return {"classification": "GENERAL_CONVERSATION", "confidence": 0.5}
    except Exception as e:
        print(f"❌ Error inesperado en clasificación: {e}")
        return {"classification": "GENERAL_CONVERSATION", "confidence": 0.5}


# --- Endpoints ---

@router.post("/classify")
async def classify_and_store(request: ClassifyRequest):
    """
    Recibe un mensaje, lo clasifica y guarda el resultado en DynamoDB.
    """
    try:
        # 1. Clasificar el mensaje
        message = request.message
        print(f"Clasificando el mensaje: '{message}'")
        result = await classify_decision(message)
        print(f"Resultado de la clasificación: {result}")

        # 2. Preparar el item para guardar
        item_to_save = create_classification_item(message, result)

        # 3. Guardar en DynamoDB
        if TABLE:
            save_to_dynamodb(TABLE, item_to_save)
        else:
            print("ADVERTENCIA: No se guardó en DynamoDB (conexión no disponible).")

        # 4. Devolver respuesta
        return item_to_save

    except Exception as e:
        print(f"Error procesando la petición: {e}")
        raise HTTPException(status_code=500, detail="Ocurrió un error interno en el servidor.")


@router.post("/messages-webhook")
async def slack_messages_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Webhook para recibir mensajes de Slack y guardarlos en DynamoDB.
    Maneja tanto la verificación inicial como los eventos de mensajes.
    """
    try:
        data = await request.json()
        print(f"Webhook recibido: {json.dumps(data, indent=2)}")

        # 1. Verificar si es un challenge de Slack
        if "challenge" in data:
            print("Recibido challenge de verificación de Slack")
            return Response(content=json.dumps({"challenge": data["challenge"]}), media_type="application/json")

        # 2. Verificar que sea un event_callback
        if data.get("type") != "event_callback":
            print(f"Tipo de evento no soportado: {data.get('type')}")
            return Response(content=json.dumps({"ok": True, "error": "Tipo de evento no soportado"}), media_type="application/json")

        # 3. Verificar que sea un evento de mensaje
        event = data.get("event", {})
        if event.get("type") != "message" or event.get("subtype") == "message_deleted":
            print(f"Tipo de evento interno no es mensaje: {event.get('type')}")
            return Response(content=json.dumps({"ok": True, "message": "Evento no es mensaje, ignorado"}), media_type="application/json")

        # 4. Verificar que no sea un mensaje de bot
        if event.get("bot_id"):
            print("Mensaje de bot ignorado")
            return Response(content=json.dumps({"ok": True, "message": "Mensaje de bot ignorado"}), media_type="application/json")
        
        # 5. Crear el item para guardar
        slack_item = create_slack_message_item(data)
        user = get_user_by_slack_team_id(slack_item["teamId"], db)
        
        if not user:
            print(f"❌ Usuario no encontrado para team_id: {slack_item['teamId']}")
            return Response(content=json.dumps({"ok": True, "error": "Usuario no encontrado"}), media_type="application/json")
        
        # 6. Verificar si el canal tiene asociaciones con Notion
        slack_channel_id = slack_item["channelId"]

        notion_databases = get_notion_databases_for_slack_channel(
            slack_channel_id_external=slack_channel_id,
            user_id=user.id,
            db=db
        )

        # Obtener el nombre del canal si existe en las asociaciones
        channel_name = "unknown"
        if notion_databases:
            print(f"📊 Mensaje de canal asociado detectado!")
            for notion_db in notion_databases:
                print(f"   - Database: {notion_db['database_name']} (ID: {notion_db['notion_database_id_external']})")
                print(f"     Auto-sync: {notion_db['auto_sync']}")
            # Obtener el nombre del canal desde la base de datos
            from slack_module.models import SlackChannel
            slack_channel_obj = db.query(SlackChannel).filter(
                SlackChannel.slack_channel_id == slack_channel_id,
                SlackChannel.user_id == user.id
            ).first()
            if slack_channel_obj:
                channel_name = slack_channel_obj.channel_name
        else:
            print(f"ℹ️ Canal {slack_channel_id} no tiene asociaciones con Notion")
            return Response(content=json.dumps({"ok": True, "error": "Canal no tiene asociaciones con Notion"}), media_type="application/json")

        # 7. Preparar datos para el batch
        slack_user_info = await get_slack_user_info(user.slack_token, slack_item["userId"])
        slack_message_link = await get_slack_message_link(user.slack_token, slack_item["channelId"], slack_item["timestamp"])
        user_profile = {
            "rol": slack_user_info['title'],
            "nombre": slack_user_info['real_name'],
            "enlace_mensaje": slack_message_link,
        }

        # 8. Inicializar agente de OpenAI
        open_ai_agent = initialize_openai_agent(user.id, db)
        if not open_ai_agent:
            print("❌ Agente no disponible")
            return Response(content=json.dumps({"ok": True, "error": "Agente no disponible"}), media_type="application/json")

        # 9. Clasificar el mensaje para guardarlo en DynamoDB
        result = await classify_decision(slack_item["messageText"])
        item_to_save = create_classification_item(
            slack_item["messageText"],
            result,
            user.id,  # Usuario de nuestro sistema
            slack_item["channelId"],
            channel_name
        )

        # 10. Guardar clasificación en DynamoDB (esto se mantiene inmediato)
        if TABLE:
            success = save_to_dynamodb(TABLE, item_to_save)
            if success:
                print("✅ Mensaje de Slack guardado exitosamente en DynamoDB")
            else:
                print("❌ Error guardando mensaje en DynamoDB")
        else:
            print("⚠️ ADVERTENCIA: No se guardó el mensaje (conexión DynamoDB no disponible)")

        # 11. Agregar mensaje al sistema de batching para procesamiento posterior
        print(f"📥 Agregando mensaje al batch del canal {slack_item['channelId']}")
        add_message_to_batch(
            channel_id=slack_item["channelId"],
            slack_item=slack_item,
            user_profile=user_profile,
            openai_agent=open_ai_agent,
            user_id=user.id,
            db=db
        )

        print(f"⏳ Mensaje agregado al batch. Se procesará en {os.getenv('BATCH_TIMEOUT_SECONDS', '30')} segundos si no llegan más mensajes.")
        return Response(content=json.dumps({"ok": True, "message": "Mensaje agregado al batch para procesamiento"}), media_type="application/json")
    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return Response(content=json.dumps({"ok": True, "error": "JSON inválido"}), media_type="application/json", status_code=200)

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return Response(content=json.dumps({"ok": True, "error": "Error interno del servidor"}), media_type="application/json", status_code=200)


@router.post("/analyze")
async def analyze_message(request: AnalyzeRequest, background_tasks: BackgroundTasks,db: Session = Depends(get_db)):
    """
    Analiza un mensaje usando LangChain MCP con tools de Notion y GitHub.
    Retorna una respuesta inteligente con posibles acciones realizadas.
    """
    print(f"📨 ANALYZE: {request.message[:50]}...")

    try:
        # Verificar que el agente esté disponible
        langchain_agent = initialize_openai_agent(1,db)
        if not langchain_agent:
            print("❌ Agente no disponible")
            return {
                "response": "Lo siento, los servicios de IA no están disponibles en este momento.",
                "error": "Agente no inicializado",
                "tool_results": []
            }

        background_tasks.add_task(background_analysis_task, message=request.message, openai_adapter=langchain_agent, table=TABLE)
        
        return {
            "message": "Análisis iniciado en background",
            "status": "processing"
        }

    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return {
            "response": f"Error procesando la solicitud: {str(e)}",
            "error": True,
            "tool_results": []
        }


@router.get("/batch-status")
async def get_batch_status_endpoint(channel_id: str = None):
    """
    Obtiene el estado de los batches de mensajes.
    Si se especifica channel_id, muestra el estado de ese canal específico.
    Si no, muestra el estado de todos los canales con batches activos.
    """
    try:
        if channel_id:
            # Estado de un canal específico
            status = get_batch_status(channel_id)
            return {
                "channel_id": channel_id,
                "batch_status": status
            }
        else:
            # Estado de todos los canales
            all_status = {}
            for ch_id, batch in message_batches.items():
                if batch is not None:
                    all_status[ch_id] = get_batch_status(ch_id)

            return {
                "active_channels": len(all_status),
                "batch_timeout_seconds": int(os.getenv('BATCH_TIMEOUT_SECONDS', '30')),
                "channels": all_status
            }

    except Exception as e:
        print(f"❌ Error obteniendo estado de batches: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/force-process-batch")
async def force_process_batch_endpoint(channel_id: str):
    """
    Fuerza el procesamiento inmediato del batch de un canal específico.
    Útil para testing o cuando se necesita procesar inmediatamente.
    """
    try:
        from utils import process_message_batch

        print(f"🔧 Procesamiento forzado del batch del canal {channel_id}")

        # Verificar si el canal tiene un batch
        if channel_id not in message_batches or message_batches[channel_id] is None:
            return {
                "success": False,
                "message": f"No hay batch activo para el canal {channel_id}"
            }

        # Procesar el batch inmediatamente
        process_message_batch(channel_id)

        return {
            "success": True,
            "message": f"Batch del canal {channel_id} procesado exitosamente"
        }

    except Exception as e:
        print(f"❌ Error procesando batch forzado: {e}")
        raise HTTPException(status_code=500, detail="Error procesando batch")

