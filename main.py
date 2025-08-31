import json
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from transformers import pipeline
from utils import get_table, save_to_dynamodb, create_classification_item, create_slack_message_item

# --- 1. Carga del Modelo y Configuración Inicial ---
# Esto se ejecuta una sola vez cuando la aplicación arranca.
print("Cargando el modelo de clasificación...")
CLASSIFIER = pipeline("zero-shot-classification", model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
print("Modelo cargado exitosamente.")

# Inicializar tabla de DynamoDB
TABLE = get_table()

# --- 2. Modelo de Datos de Entrada (con Pydantic) ---
# Define la estructura del JSON que tu API espera recibir.
# FastAPI lo usará para validar automáticamente los datos.
class ClassifyRequest(BaseModel):
    message: str

# --- 3. Creación de la Aplicación FastAPI ---
app = FastAPI(
    title="API de Clasificación de Texto",
    description="Una API para clasificar si un texto contiene una decisión de diseño."
)

# --- Lógica de Clasificación (función auxiliar) ---
def classify_decision(text: str) -> dict:
    if len(text.split()) < 4:
        return {"classification": "NONE", "confidence": 0.0, "reason": "Texto demasiado corto."}

    candidate_labels = ["DECISION", "EXPLANATION", "QUESTION", "GENERAL_CONVERSATION"]
    hypothesis_template = "Este texto es sobre {}."
    prediction = CLASSIFIER(text, candidate_labels, hypothesis_template=hypothesis_template)

    return {
        "classification": prediction['labels'][0],
        "confidence": round(prediction['scores'][0], 4)
    }

# --- 4. Definición del Endpoint de la API ---
@app.post("/classify")
async def classify_and_store(request: ClassifyRequest):
    """
    Recibe un mensaje, lo clasifica y guarda el resultado en DynamoDB.
    """
    try:
        # 1. Clasificar el mensaje (ahora viene del request validado)
        message = request.message
        print(f"Clasificando el mensaje: '{message}'")
        result = classify_decision(message)
        print(f"Resultado de la clasificación: {result}")

        # 2. Preparar el item para guardar usando la función de utils
        item_to_save = create_classification_item(message, result)

        # 3. Guardar en DynamoDB (si la conexión fue exitosa)
        if TABLE:
            save_to_dynamodb(TABLE, item_to_save)
        else:
            print("ADVERTENCIA: No se guardó en DynamoDB (conexión no disponible).")

        # 4. Devolver una respuesta exitosa (FastAPI la convierte a JSON automáticamente)
        return item_to_save

    except Exception as e:
        print(f"Error procesando la petición: {e}")
        # FastAPI maneja los errores con un sistema de excepciones HTTP
        raise HTTPException(status_code=500, detail="Ocurrió un error interno en el servidor.")

# --- 5. Webhook para Mensajes de Slack ---
@app.post("/messages-webhook")
async def slack_messages_webhook(request: Request):
    """
    Webhook para recibir mensajes de Slack y guardarlos en DynamoDB.
    Maneja tanto la verificación inicial como los eventos de mensajes.
    """
    try:
        data = await request.json()
        print(f"Webhook recibido: {json.dumps(data, indent=2)}")

        # 1. Verificar si es un challenge de Slack (para verificación inicial)
        if "challenge" in data:
            print("Recibido challenge de verificación de Slack")
            return Response(content=json.dumps({"challenge": data["challenge"]}), media_type="application/json")

        # 2. Verificar que sea un event_callback
        if data.get("type") != "event_callback":
            print(f"Tipo de evento no soportado: {data.get('type')}")
            return Response(content=json.dumps({"ok": False, "error": "Tipo de evento no soportado"}), media_type="application/json")

        # 3. Verificar que sea un evento de mensaje
        event = data.get("event", {})
        if event.get("type") != "message":
            print(f"Tipo de evento interno no es mensaje: {event.get('type')}")
            return Response(content=json.dumps({"ok": True, "message": "Evento no es mensaje, ignorado"}), media_type="application/json")

        # 4. Verificar que no sea un mensaje de bot (opcional)
        if event.get("bot_id"):
            print("Mensaje de bot ignorado")
            return Response(content=json.dumps({"ok": True, "message": "Mensaje de bot ignorado"}), media_type="application/json")

        # 5. Crear el item para guardar usando la función de utils
        slack_item = create_slack_message_item(data)
        result = classify_decision(slack_item["messageText"])
        item_to_save = create_classification_item(slack_item["messageText"], result)
        print(f"Item preparado para guardar: {item_to_save}")

        # 6. Guardar en DynamoDB
        if TABLE:
            success = save_to_dynamodb(TABLE, item_to_save)
            if success:
                print("Mensaje de Slack guardado exitosamente en DynamoDB")
                return Response(content=json.dumps({"ok": True, "messageId": item_to_save["messageId"]}), media_type="application/json")
            else:
                print("Error guardando mensaje en DynamoDB")
                return Response(content=json.dumps({"ok": False, "error": "Error guardando en base de datos"}), media_type="application/json")
        else:
            print("ADVERTENCIA: No se guardó el mensaje (conexión DynamoDB no disponible)")
            return Response(content=json.dumps({"ok": False, "error": "Base de datos no disponible"}), media_type="application/json")

    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return Response(content=json.dumps({"ok": False, "error": "JSON inválido"}), media_type="application/json", status_code=400)

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return Response(content=json.dumps({"ok": False, "error": "Error interno del servidor"}), media_type="application/json", status_code=500)

