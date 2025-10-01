import os
import uuid
import boto3
from typing import Optional, Dict, Any
import json

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

def create_classification_item(message: str, classification_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea un item para guardar resultados de clasificación.

    Args:
        message: Mensaje original
        classification_result: Resultado de la clasificación

    Returns:
        Dict con el item formateado para DynamoDB
    """
    item_id = str(uuid.uuid4())
    return {
        'messageId': item_id,
        'originalMessage': message,
        'classification': classification_result.get('classification'),
        'confidence': str(classification_result.get('confidence')),
    }

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


def background_analysis_task(message: str, openai_adapter, table):
    """Función que se ejecuta en segundo plano"""
    print("---------------------------------background_analysis_task---------------------------------")

    try:
        # Verificar que el adaptador/agente esté disponible
        if not openai_adapter:
            print("❌ Adaptador/agente no disponible")
            return {
                "response": "Lo siento, los servicios de IA no están disponibles en este momento.",
                "error": "Adaptador no inicializado",
                "tool_results": []
            }

        # Ejecutar el chat (maneja async si es LangChain, sync si es OpenAI v2)
        import asyncio
        import inspect
        
        # Verificar si el método chat es asíncrono
        if inspect.iscoroutinefunction(openai_adapter.chat):
            # Ejecutar de forma asíncrona (LangChain MCP Agent)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(openai_adapter.chat(message=message))
            loop.close()


        print("✅ Respuesta del agente recibida")
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