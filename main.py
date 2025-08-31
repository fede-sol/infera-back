import os
import uuid
import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import pipeline

# --- 1. Carga del Modelo y Configuración Inicial ---
# Esto se ejecuta una sola vez cuando la aplicación arranca.
print("Cargando el modelo de clasificación...")
CLASSIFIER = pipeline("zero-shot-classification", model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
print("Modelo cargado exitosamente.")

# Conexión a DynamoDB
try:
    DYNAMODB = boto3.resource('dynamodb')
    TABLE_NAME = os.environ.get('TABLE_NAME', 'classification_results') # Usamos un valor por defecto para pruebas locales
    TABLE = DYNAMODB.Table(TABLE_NAME)
except Exception as e:
    print(f"ADVERTENCIA: No se pudo conectar a DynamoDB. Error: {e}")
    TABLE = None

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

        # 2. Preparar el item para guardar
        item_id = str(uuid.uuid4())
        item_to_save = {
            'messageId': item_id,
            'originalMessage': message,
            'classification': result.get('classification'),
            'confidence': str(result.get('confidence')),
        }

        # 3. Guardar en DynamoDB (si la conexión fue exitosa)
        if TABLE:
            print(f"Guardando item en DynamoDB: {item_to_save}")
            TABLE.put_item(Item=item_to_save)
            print("Item guardado exitosamente.")
        else:
            print("ADVERTENCIA: No se guardó en DynamoDB (conexión no disponible).")


        # 4. Devolver una respuesta exitosa (FastAPI la convierte a JSON automáticamente)
        return item_to_save

    except Exception as e:
        print(f"Error procesando la petición: {e}")
        # FastAPI maneja los errores con un sistema de excepciones HTTP
        raise HTTPException(status_code=500, detail="Ocurrió un error interno en el servidor.")
