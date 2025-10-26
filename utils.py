import os
import uuid
import boto3
from typing import Optional, Dict, Any, List
import json
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict, deque
import threading
from sqlalchemy.orm import Session

# Conexión a DynamoDB
def get_dynamodb_connection() -> Optional[boto3.resource]:
    """
    Establece conexión con DynamoDB.
    Retorna None si no se puede conectar.
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        return dynamodb
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo conectar a DynamoDB. Error: {e}")
        return None

def get_table(table_name: str = None) -> Optional[Any]:
    """
    Obtiene la tabla de DynamoDB especificada.
    """
    if table_name is None:
        table_name = os.environ.get('TABLE_NAME', 'classification_results')

    dynamodb = get_dynamodb_connection()
    if dynamodb:
        try:
            table = dynamodb.Table(table_name)
            return table
        except Exception as e:
            print(f"Error obteniendo tabla '{table_name}': {e}")
            return None
    return None

def save_to_dynamodb(table: Any, item: Dict[str, Any]) -> bool:
    """
    Guarda un item en DynamoDB.

    Args:
        table: Tabla de DynamoDB
        item: Diccionario con los datos a guardar

    Returns:
        bool: True si se guardó exitosamente, False en caso contrario
    """
    try:
        table.put_item(Item=item)
        print("Item guardado exitosamente.")
        return True
    except Exception as e:
        print(f"Error guardando en DynamoDB: {e}")
        return False

def create_classification_item(message: str, classification_result: Dict[str, Any], user_id: int = None, slack_channel_id: str = None, slack_channel_name: str = None) -> Dict[str, Any]:
    """
    Crea un item para guardar resultados de clasificación.

    Args:
        message: Mensaje original
        classification_result: Resultado de la clasificación
        user_id: ID del usuario (opcional)
        slack_channel_id: ID del canal de Slack (opcional)
        slack_channel_name: Nombre del canal de Slack (opcional)

    Returns:
        Dict con el item formateado para DynamoDB
    """
    item_id = str(uuid.uuid4())
    item = {
        'messageId': item_id,
        'originalMessage': message,
        'classification': classification_result.get('classification'),
        'confidence': str(classification_result.get('confidence')),
        'datetime': datetime.now().isoformat(),
    }

    # Agregar campos opcionales solo si están presentes
    if user_id is not None:
        item['userId'] = user_id
    if slack_channel_id is not None:
        item['slackChannelId'] = slack_channel_id
    if slack_channel_name is not None:
        item['slackChannelName'] = slack_channel_name

    return item

def create_slack_message_item(slack_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea un item para guardar mensajes de Slack.

    Args:
        slack_data: Datos del webhook de Slack

    Returns:
        Dict con el item formateado para DynamoDB
    """
    item_id = str(uuid.uuid4())
    event = slack_data.get('event', {})

    # Extraer información relevante del evento
    return {
        'messageId': item_id,
        'slackToken': slack_data.get('token'),
        'teamId': slack_data.get('team_id'),
        'channelId': event.get('channel'),
        'userId': event.get('user'),
        'messageText': event.get('text'),
        'timestamp': event.get('ts'),
        'eventType': event.get('type'),
        'channelType': event.get('channel_type'),
        'eventId': slack_data.get('event_id'),
        'eventTime': slack_data.get('event_time'),
        'rawData': slack_data,  # Guardar los datos completos por si acaso
        'processedAt': str(uuid.uuid1().time),  # Timestamp de procesamiento
    }


def background_analysis_task(message: str, user_profile: Dict[str, Any], openai_adapter, table):
    """Función que se ejecuta en segundo plano"""
    print("---------------------------------background_analysis_task---------------------------------")


    try:
        # Verificar que los adaptadores estén disponibles
        if not openai_adapter:
            print("❌ Adaptadores no disponibles")
            return {
                "response": "Lo siento, los servicios de IA no están disponibles en este momento.",
                "error": "Adaptadores no inicializados",
                "tool_results": []
            }
        input = f'Perfil del usuario: {user_profile}\nMensaje: "{message}"'

        result = openai_adapter.chat(
            message=input,
        )

        print("✅ Respuesta de OpenAI recibida")
        response_data = {
            "message": message,
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "tool_stats": result["tool_stats"],
            #"conversation_length": len(result["conversation_history"]),
            "timestamp": json.dumps({"processed": True})
        }

        # Si se ejecutaron tools, agregar información adicional
        if result["tool_calls"]:
            # Usar estadísticas pre-calculadas del adapter
            response_data["tools_executed"] = result["tool_stats"]["total"]
            response_data["successful_tools"] = result["tool_stats"]["successful"]
            response_data["failed_tools"] = result["tool_stats"]["failed"]
            response_data["success_rate"] = result["tool_stats"]["success_rate"]

            print(f"📊 RESULTADOS: {response_data['tools_executed']} tools ejecutadas - {response_data['successful_tools']} exitosas ({response_data['success_rate']}% éxito)")

        # Opcional: guardar en DynamoDB si hay resultados de tools
        if table and result["tool_calls"]:
            try:
                analysis_item = {
                    "messageId": f"analysis_{hash(message)}",
                    "originalMessage": message,
                    "aiResponse": result["content"] if result.get("content") else str(result["response"]),
                    "toolsUsed": result["tool_stats"]["total"],
                    "toolsSuccessful": result["tool_stats"]["successful"],
                    "toolsFailed": result["tool_stats"]["failed"],
                    "successRate": int(result["tool_stats"]["success_rate"]),
                    "timestamp": str(hash(str(result["tool_calls"])))
                }
                success = save_to_dynamodb(table, analysis_item)
                response_data["saved_to_db"] = success
                if success:
                    print("💾 Guardado en base de datos")
            except Exception as db_error:
                print(f"❌ Error guardando en DB: {db_error}")
                response_data["saved_to_db"] = False

        print("🎉 Análisis completado exitosamente")
        return response_data
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return {
            "response": f"Error procesando la solicitud: {str(e)}",
            "error": True,
            "tool_results": []
        }
def background_batch_analysis_task(messages: List[Dict[str, Any]], openai_adapter, table):
    """Función que se ejecuta en segundo plano"""
    print("---------------------------------background_batch_analysis_task---------------------------------")


    try:
        # Verificar que los adaptadores estén disponibles
        if not openai_adapter:
            print("❌ Adaptadores no disponibles")
            return {
                "response": "Lo siento, los servicios de IA no están disponibles en este momento.",
                "error": "Adaptadores no inicializados",
                "tool_results": []
            }
        inputs = [{"usuario": message["user_profile"], "mensaje": message["slack_item"]["messageText"]} for message in messages]
        #print(f"Inputs: {json.dumps(inputs, indent=2)}")

        messages_text = ""
        for message in inputs:
            messages_text += f"Usuario: {message['usuario']}\nMensaje: {message['mensaje']}\n"

        print(f"Messages text: {messages_text}")

        result = openai_adapter.chat(
            message=messages_text,
        )

        print("✅ Respuesta de OpenAI recibida")
        response_data = {
            "message": messages_text,
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "tool_stats": result["tool_stats"],
            #"conversation_length": len(result["conversation_history"]),
            "timestamp": json.dumps({"processed": True})
        }

        # Si se ejecutaron tools, agregar información adicional
        if result["tool_calls"]:
            # Usar estadísticas pre-calculadas del adapter
            response_data["tools_executed"] = result["tool_stats"]["total"]
            response_data["successful_tools"] = result["tool_stats"]["successful"]
            response_data["failed_tools"] = result["tool_stats"]["failed"]
            response_data["success_rate"] = result["tool_stats"]["success_rate"]

            print(f"📊 RESULTADOS: {response_data['tools_executed']} tools ejecutadas - {response_data['successful_tools']} exitosas ({response_data['success_rate']}% éxito)")

        # Opcional: guardar en DynamoDB si hay resultados de tools
        if table and result["tool_calls"]:
            try:
                analysis_item = {
                    "messageId": f"analysis_{hash(messages_text)}",
                    "originalMessage": inputs,
                    "aiResponse": result["content"] if result.get("content") else str(result["response"]),
                    "toolsUsed": result["tool_stats"]["total"],
                    "toolsSuccessful": result["tool_stats"]["successful"],
                    "toolsFailed": result["tool_stats"]["failed"],
                    "successRate": int(result["tool_stats"]["success_rate"]),
                    "timestamp": str(hash(str(result["tool_calls"])))
                }
                success = save_to_dynamodb(table, analysis_item)
                response_data["saved_to_db"] = success
                if success:
                    print("💾 Guardado en base de datos")
            except Exception as db_error:
                print(f"❌ Error guardando en DB: {db_error}")
                response_data["saved_to_db"] = False

        print("🎉 Análisis completado exitosamente")
        return response_data
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return {
            "response": f"Error procesando la solicitud: {str(e)}",
            "error": True,
            "tool_results": []
        }


# === SISTEMA DE BATCHING PARA MENSAJES ===

class MessageBatch:
    """Clase para representar un batch de mensajes"""

    def __init__(self, channel_id: str, user_id: int, db: Session = None):
        self.channel_id = channel_id
        self.user_id = user_id
        self.db = db
        self.messages: List[Dict[str, Any]] = []
        self.created_at = datetime.now()
        self.timeout_timer = None

    def add_message(self, slack_item: Dict[str, Any], user_profile: Dict[str, Any], openai_agent):
        """Agrega un mensaje al batch"""
        self.messages.append({
            'slack_item': slack_item,
            'user_profile': user_profile,
            'openai_agent': openai_agent,
            'added_at': datetime.now()
        })

    def is_ready_to_process(self, batch_timeout_seconds: int = 30) -> bool:
        """Verifica si el batch está listo para procesar"""
        return len(self.messages) > 0 and (datetime.now() - self.created_at).seconds >= batch_timeout_seconds

    def has_messages(self) -> bool:
        """Verifica si el batch tiene mensajes"""
        return len(self.messages) > 0


# Estructuras globales para el sistema de batching
message_batches: Dict[str, MessageBatch] = defaultdict(lambda: None)
batch_timers: Dict[str, threading.Timer] = {}
BATCH_TIMEOUT_SECONDS = int(os.getenv('BATCH_TIMEOUT_SECONDS', '30'))  # 30 segundos por defecto


def add_message_to_batch(channel_id: str, slack_item: Dict[str, Any], user_profile: Dict[str, Any], openai_agent, user_id: int, db: Session):
    """
    Agrega un mensaje al batch correspondiente al canal.
    Si no existe un batch para el canal, crea uno nuevo.
    """
    global message_batches, batch_timers

    # Obtener o crear batch para el canal
    if message_batches[channel_id] is None:
        message_batches[channel_id] = MessageBatch(channel_id, user_id, db)

    batch = message_batches[channel_id]

    # Agregar mensaje al batch
    batch.add_message(slack_item, user_profile, openai_agent)

    # Cancelar timer existente si hay uno
    if channel_id in batch_timers and batch_timers[channel_id]:
        batch_timers[channel_id].cancel()

    # Iniciar nuevo timer para procesar el batch
    batch_timers[channel_id] = threading.Timer(
        BATCH_TIMEOUT_SECONDS,
        process_message_batch,
        args=[channel_id]
    )
    batch_timers[channel_id].start()

    print(f"📥 Mensaje agregado al batch del canal {channel_id}. Total mensajes en batch: {len(batch.messages)}")


def process_message_batch(channel_id: str):
    """
    Procesa todos los mensajes acumulados en el batch de un canal.
    Se ejecuta cuando se cumple el timeout.
    """
    global message_batches, batch_timers

    print(f"⏰ Procesando batch del canal {channel_id}")

    batch = message_batches.get(channel_id)
    if not batch or not batch.has_messages():
        print(f"⚠️ No hay mensajes para procesar en el canal {channel_id}")
        return

    # Cancelar timer si existe
    if channel_id in batch_timers and batch_timers[channel_id]:
        batch_timers[channel_id].cancel()
        del batch_timers[channel_id]

    try:
        print(f"🔄 Procesando batch del canal {channel_id}")

        # Ejecutar el background analysis task para este mensaje
        background_batch_analysis_task(
            messages=batch.messages,
            openai_adapter=batch.messages[0]["openai_agent"],
            table=get_table()
        )

        print(f"✅ Batch del canal {channel_id} procesado completamente ({len(batch.messages)} mensajes)")

        # Limpiar el batch después del procesamiento
        message_batches[channel_id] = None

    except Exception as e:
        print(f"❌ Error procesando batch del canal {channel_id}: {e}")
        # En caso de error, limpiar el batch también
        message_batches[channel_id] = None


def get_batch_status(channel_id: str) -> Dict[str, Any]:
    """
    Obtiene el estado actual del batch para un canal específico.
    """
    batch = message_batches.get(channel_id)
    if not batch:
        return {"status": "no_batch", "message_count": 0}

    return {
        "status": "active",
        "message_count": len(batch.messages),
        "created_at": batch.created_at.isoformat(),
        "timeout_seconds": BATCH_TIMEOUT_SECONDS,
        "seconds_since_creation": (datetime.now() - batch.created_at).seconds
    }