#!/usr/bin/env python3
"""
Script de prueba para el sistema de batching de mensajes.

Este script prueba las funcionalidades del sistema de batching sin necesidad
de tener el servidor completo corriendo.
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock

# Agregar el directorio actual al path para importar módulos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import MessageBatch, add_message_to_batch, process_message_batch, get_batch_status, BATCH_TIMEOUT_SECONDS


def test_message_batch_creation():
    """Prueba la creación de un batch de mensajes."""
    print("🧪 Probando creación de MessageBatch...")

    # Crear un batch simulado
    batch = MessageBatch(channel_id="C01TEST123", user_id=1, db=None)

    assert batch.channel_id == "C01TEST123"
    assert batch.user_id == 1
    assert len(batch.messages) == 0
    assert batch.has_messages() == False

    print("✅ Creación de MessageBatch funciona correctamente")


def test_add_message_to_batch():
    """Prueba agregar mensajes a un batch."""
    print("\n🧪 Probando agregar mensajes al batch...")

    # Crear datos de prueba
    slack_item = {
        "messageId": "test123",
        "channelId": "C01TEST123",
        "userId": "U456",
        "messageText": "Hola, esto es un mensaje de prueba",
        "timestamp": "1234567890.123"
    }

    user_profile = {
        "rol": "Desarrollador",
        "nombre": "Juan Pérez",
        "enlace_mensaje": "https://slack.com/message/123"
    }

    openai_agent = Mock()  # Simular agente de OpenAI

    # Agregar mensaje al batch
    add_message_to_batch(
        channel_id="C01TEST123",
        slack_item=slack_item,
        user_profile=user_profile,
        openai_agent=openai_agent,
        user_id=1,
        db=None
    )

    # Verificar que se agregó correctamente
    status = get_batch_status("C01TEST123")
    assert status["status"] == "active"
    assert status["message_count"] == 1

    print(f"✅ Mensaje agregado al batch. Estado: {status}")


def test_batch_timeout():
    """Prueba el timeout del batch."""
    print("\n🧪 Probando timeout del batch...")

    # Crear un batch con timeout corto para testing
    import utils
    original_timeout = utils.BATCH_TIMEOUT_SECONDS
    utils.BATCH_TIMEOUT_SECONDS = 2  # 2 segundos para testing rápido

    try:
        # Crear un batch
        slack_item = {
            "messageId": "test_timeout",
            "channelId": "C01TIMEOUT",
            "userId": "U456",
            "messageText": "Mensaje para timeout test",
            "timestamp": "1234567890.123"
        }

        add_message_to_batch(
            channel_id="C01TIMEOUT",
            slack_item=slack_item,
            user_profile={"nombre": "Test User"},
            openai_agent=Mock(),
            user_id=1,
            db=None
        )

        # Verificar que el batch está activo
        status = get_batch_status("C01TIMEOUT")
        print(f"📊 Estado inicial del batch: {status}")

        # Esperar a que se procese el timeout
        print("⏳ Esperando timeout (2 segundos)...")
        import time
        time.sleep(3)  # Esperar más del timeout

        # Verificar que el batch se procesó
        status_after = get_batch_status("C01TIMEOUT")
        print(f"📊 Estado después del timeout: {status_after}")

        if status_after["status"] == "no_batch":
            print("✅ Timeout del batch funcionó correctamente")
        else:
            print("⚠️ El batch aún está activo después del timeout")

    finally:
        # Restaurar timeout original
        utils.BATCH_TIMEOUT_SECONDS = original_timeout


def test_multiple_messages():
    """Prueba agregar múltiples mensajes al mismo batch."""
    print("\n🧪 Probando múltiples mensajes en el mismo batch...")

    # Agregar múltiples mensajes
    for i in range(3):
        slack_item = {
            "messageId": f"test_multi_{i}",
            "channelId": "C01MULTI",
            "userId": f"U{i}",
            "messageText": f"Mensaje de prueba número {i + 1}",
            "timestamp": f"123456789{i}.123"
        }

        add_message_to_batch(
            channel_id="C01MULTI",
            slack_item=slack_item,
            user_profile={"nombre": f"User {i}"},
            openai_agent=Mock(),
            user_id=1,
            db=None
        )

    # Verificar que se agregaron todos
    status = get_batch_status("C01MULTI")
    assert status["message_count"] == 3

    print(f"✅ Múltiples mensajes agregados: {status}")


def test_different_channels():
    """Prueba que los canales tienen batches independientes."""
    print("\n🧪 Probando batches independientes por canal...")

    # Agregar mensajes a diferentes canales
    for channel_id in ["C01CHAN1", "C01CHAN2", "C01CHAN3"]:
        slack_item = {
            "messageId": f"test_chan_{channel_id}",
            "channelId": channel_id,
            "userId": "U123",
            "messageText": f"Mensaje para {channel_id}",
            "timestamp": "1234567890.123"
        }

        add_message_to_batch(
            channel_id=channel_id,
            slack_item=slack_item,
            user_profile={"nombre": "Test User"},
            openai_agent=Mock(),
            user_id=1,
            db=None
        )

    # Verificar que cada canal tiene su propio batch
    total_active = 0
    for channel_id in ["C01CHAN1", "C01CHAN2", "C01CHAN3"]:
        status = get_batch_status(channel_id)
        if status["status"] == "active":
            total_active += 1
            print(f"📊 Canal {channel_id}: {status['message_count']} mensajes")

    assert total_active == 3
    print(f"✅ Canales independientes funcionando: {total_active} canales activos")


def test_force_process():
    """Prueba el procesamiento forzado de un batch."""
    print("\n🧪 Probando procesamiento forzado de batch...")

    # Crear un batch
    slack_item = {
        "messageId": "test_force",
        "channelId": "C01FORCE",
        "userId": "U123",
        "messageText": "Mensaje para procesamiento forzado",
        "timestamp": "1234567890.123"
    }

    add_message_to_batch(
        channel_id="C01FORCE",
        slack_item=slack_item,
        user_profile={"nombre": "Test User"},
        openai_agent=Mock(),
        user_id=1,
        db=None
    )

    # Procesar forzosamente
    process_message_batch("C01FORCE")

    # Verificar que se procesó
    status = get_batch_status("C01FORCE")
    assert status["status"] == "no_batch"

    print("✅ Procesamiento forzado funcionó correctamente")


def run_all_tests():
    """Ejecuta todas las pruebas."""
    print("🚀 Iniciando pruebas del sistema de batching...\n")

    try:
        test_message_batch_creation()
        test_add_message_to_batch()
        test_multiple_messages()
        test_different_channels()
        test_force_process()
        # test_batch_timeout()  # Descomentar para probar timeout real

        print("\n🎉 Todas las pruebas completadas exitosamente!")

    except Exception as e:
        print(f"\n❌ Error en las pruebas: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)