import os
import uuid
import boto3
from typing import Optional, Dict, Any

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
        print(f"Guardando item en DynamoDB: {item}")
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
