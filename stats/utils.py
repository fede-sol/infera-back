from typing import Dict, Any, List
from sqlalchemy.orm import Session
from slack_module.models import SlackChannel
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime
import os


def get_user_messages_count(user_id: int, db: Session) -> int:
    """
    Cuenta el total de mensajes procesados para un usuario.
    
    Args:
        user_id: ID del usuario
        db: Sesión de base de datos
    
    Returns:
        int: Total de mensajes procesados
    """
    try:
        # Obtener el team_id de Slack del usuario
        from auth.models import User
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.slack_team_id:
            return 0
        
        # Conectar a DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('TABLE_NAME', 'classification_results')
        table = dynamodb.Table(table_name)
        
        # Escanear la tabla buscando mensajes del team_id del usuario
        response = table.scan(
            FilterExpression=Attr('userId').eq(user.id)
        )
        
        count = len(response.get('Items', []))
        
        # Manejar paginación si hay muchos resultados
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('userId').eq(user.id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            count += len(response.get('Items', []))
        
        return count
        
    except Exception as e:
        print(f"Error contando mensajes: {e}")
        return 0


def get_user_decisions_count(user_id: int, db: Session) -> int:
    """
    Cuenta el total de decisiones detectadas para un usuario.
    
    Args:
        user_id: ID del usuario
        db: Sesión de base de datos
    
    Returns:
        int: Total de decisiones detectadas
    """
    try:
        # Obtener el team_id de Slack del usuario
        from auth.models import User
        user = db.query(User).filter(User.id == user_id).first()

        if not user or not user.slack_team_id:
            return 0

        # Conectar a DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('classification_results')

        # Escanear la tabla buscando decisiones del team_id del usuario
        response = table.scan(
            FilterExpression=Attr('userId').eq(user.id) & Attr('classification').eq('DECISION')
        )

        count = len(response.get('Items', []))

        # Manejar paginación si hay muchos resultados
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('teamId').eq(user.slack_team_id) & Attr('classification').eq('DECISION'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            count += len(response.get('Items', []))

        return count

    except Exception as e:
        print(f"Error contando decisiones: {e}")
        return 0


def get_user_slack_channels_count(user_id: int, db: Session) -> int:
    """
    Cuenta el total de canales de Slack analizados por un usuario.
    Solo cuenta canales que están siendo usados en asociaciones con Notion.
    
    Args:
        user_id: ID del usuario
        db: Sesión de base de datos
    
    Returns:
        int: Total de canales de Slack con asociaciones activas
    """
    try:
        from slack_module.models import NotionSlackAssociation
        
        # Contar canales únicos que tienen asociaciones activas
        count = db.query(SlackChannel).join(
            NotionSlackAssociation,
            SlackChannel.id == NotionSlackAssociation.slack_channel_id
        ).filter(
            SlackChannel.user_id == user_id,
            SlackChannel.is_active == True
        ).distinct().count()
        
        return count
        
    except Exception as e:
        print(f"Error contando canales: {e}")
        return 0


def get_user_stats(user_id: int, db: Session) -> Dict[str, Any]:
    """
    Obtiene todas las estadísticas de un usuario.
    
    Args:
        user_id: ID del usuario
        db: Sesión de base de datos
    
    Returns:
        Dict con las estadísticas del usuario
    """
    return {
        "total_messages_processed": get_user_messages_count(user_id, db),
        "decisions_detected": get_user_decisions_count(user_id, db),
        "slack_channels_analyzed": get_user_slack_channels_count(user_id, db)
    }


def get_user_recent_messages(user_id: int, db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Obtiene los últimos mensajes analizados de un usuario, ordenados por fecha.
    
    Args:
        user_id: ID del usuario
        db: Sesión de base de datos
        limit: Número máximo de mensajes a retornar (default: 20)
    
    Returns:
        Lista de mensajes ordenados por fecha (más reciente primero)
    """
    try:
        # Obtener el usuario
        from auth.models import User
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return []
        
        # Conectar a DynamoDB
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('TABLE_NAME', 'classification_results')
        table = dynamodb.Table(table_name)
        
        # Escanear la tabla buscando mensajes del usuario
        all_items = []
        response = table.scan(
            FilterExpression=Attr('userId').eq(user.id)
        )
        
        all_items.extend(response.get('Items', []))
        
        # Manejar paginación
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('userId').eq(user.id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            all_items.extend(response.get('Items', []))
        
        # Ordenar por fecha (usar datetime, eventTime, o processedAt según disponibilidad)
        def get_sort_key(item):
            # Intentar obtener una fecha válida en orden de preferencia
            if 'datetime' in item and item['datetime']:
                try:
                    return datetime.fromisoformat(item['datetime'])
                except:
                    pass
            
            if 'eventTime' in item and item['eventTime']:
                try:
                    # eventTime es un timestamp Unix
                    return datetime.fromtimestamp(int(item['eventTime']))
                except:
                    pass
            
            if 'processedAt' in item and item['processedAt']:
                try:
                    return datetime.fromtimestamp(float(item['processedAt']) / 1000000)
                except:
                    pass
            
            # Si no hay fecha, usar época (estos irán al final)
            return datetime.fromtimestamp(0)
        
        # Ordenar por fecha descendente (más reciente primero)
        sorted_items = sorted(all_items, key=get_sort_key, reverse=True)
        
        # Limitar resultados
        limited_items = sorted_items[:limit]
        
        # Formatear los resultados
        formatted_messages = []
        for item in limited_items:
            formatted_msg = {
                "message_id": item.get('messageId'),
                "message_text": item.get('originalMessage') or item.get('messageText'),
                "classification": item.get('classification'),
                "confidence": item.get('confidence'),
                "channel_id": item.get('channelId'),
                "timestamp": item.get('timestamp'),
                "event_time": item.get('eventTime'),
                "datetime": item.get('datetime'),
            }
            
            # Añadir fecha formateada para facilitar visualización
            sort_date = get_sort_key(item)
            if sort_date != datetime.fromtimestamp(0):
                formatted_msg["processed_date"] = sort_date.isoformat()
            
            formatted_messages.append(formatted_msg)
        
        return formatted_messages
        
    except Exception as e:
        print(f"Error obteniendo mensajes recientes: {e}")
        import traceback
        traceback.print_exc()
        return []

