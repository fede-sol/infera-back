import json
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from transformers import pipeline
from adapters.openai_adapter_v2 import OpenAIAdapterV2
from utils import get_table, save_to_dynamodb, create_classification_item, create_slack_message_item, background_analysis_task
from adapters.openai_adapter import OpenAIAdapter
from adapters.notion_adapter import NotionAdapter
from resources.system_prompt import ai_instructions
from dotenv import load_dotenv
import os
load_dotenv()


# --- 1. Carga del Modelo y Configuración Inicial ---
# Esto se ejecuta una sola vez cuando la aplicación arranca.
print("Cargando el modelo de clasificación...")
CLASSIFIER = pipeline("zero-shot-classification", model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
print("Modelo cargado exitosamente.")

# Inicializar tabla de DynamoDB
TABLE = get_table()

# --- Inicialización de Adaptadores ---
print("🚀 Iniciando adaptadores...")
try:
    # Inicializar adaptador de Notion
    notion_adapter = NotionAdapter(api_key=os.getenv('NOTION_TOKEN'))
    print("✅ Adaptador de Notion inicializado")

    # Inicializar adaptador de OpenAI
    openai_adapter = OpenAIAdapterV2(api_key=os.getenv('OPENAI_TOKEN'),instructions=ai_instructions)
    print("✅ Adaptador de OpenAI inicializado")

    # Configurar integraciones
    openai_adapter.add_mcp_tool(server_label="Notion", server_description="Realizar acciones en Notion", server_url="https://f2a65189bb2c.ngrok-free.app/mcp")
    openai_adapter.add_mcp_tool(server_label="GitHub", server_description="Realizar acciones en GitHub", server_url="https://api.githubcopilot.com/mcp/",allowed_tools=["search_code","search_repositories"], authorization=os.getenv('GITHUB_TOKEN'))
    openai_adapter.add_mcp_tool(server_label="Get_Github_File_Content", server_description="Obtener el contenido de un archivo en GitHub", server_url="https://f2a65189bb2c.ngrok-free.app/mcp")
    print("✅ Todas las herramientas configuradas")


except Exception as e:
    print(f"❌ Error inicializando adaptadores: {e}")
    notion_adapter = None
    openai_adapter = None

# --- 2. Modelo de Datos de Entrada (con Pydantic) ---
# Define la estructura del JSON que tu API espera recibir.
# FastAPI lo usará para validar automáticamente los datos.
class ClassifyRequest(BaseModel):
    message: str

class AnalyzeRequest(BaseModel):
    message: str
    use_notion: bool = False
    use_github: bool = False
    system_prompt: str = """Eres un motor de gestión de conocimiento autónomo y asíncrono. Tu propósito es documentar decisiones técnicas y funcionalidades de un equipo de software.

**Tu flujo de trabajo es el siguiente:**

1.  **Analiza el mensaje del usuario.** El mensaje es una pieza de una conversación que necesita ser documentada. Extrae los conceptos clave (ej. 'autenticación', 'base de datos', 'JWT').
2.  **Decide si necesitas buscar contexto.** Basándote en los conceptos clave, determina si es probable que ya exista documentación en Notion o código fuente relevante en GitHub.
3.  **Llama a las herramientas de notion y/o github** si es necesario. Usa consultas claras y concisas. Puedes llamar a ambas si el tema lo requiere.
4.  **Recibe los resultados de las herramientas.** Estos resultados serán el contexto (documentación existente o código fuente).
5.  **Sintetiza y genera la salida final.** Usando el mensaje original y el contexto que encontraste, tu ÚNICA salida final debe ser un objeto JSON.

**Lógica de Creación vs. Actualización:**
* Si tus herramientas **no encuentran resultados relevantes**, crea un nuevo artefacto de documentación. El estado debe ser "CREATED".
* Si tus herramientas **encuentran documentación o código existente**, actualiza o fusiona la información nueva con la existente. El estado debe ser "UPDATED".
"""

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
async def slack_messages_webhook(request: Request, background_tasks: BackgroundTasks):
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
            return Response(content=json.dumps({"ok": True, "error": "Tipo de evento no soportado"}), media_type="application/json")

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
        #print(f"Item preparado para guardar: {item_to_save}")
        print(f"Mensaje de Slack: {slack_item["messageText"]}")
        print(f"Resultado de la clasificación: {result}")

        # 6. Guardar en DynamoDB
        if TABLE:
            success = save_to_dynamodb(TABLE, item_to_save)
            if success:
                print("Mensaje de Slack guardado exitosamente en DynamoDB")
                print("Análisis en background iniciado")
                print("111111111111111111111111111111111111111111111111111111111111111")
                background_tasks.add_task(background_analysis_task,message=slack_item["messageText"], openai_adapter=openai_adapter, table=TABLE)
                return Response(content=json.dumps({"ok": True, "messageId": item_to_save["messageId"]}), media_type="application/json")
            else:
                print("Error guardando mensaje en DynamoDB")
                print("222222222222222222222222222222222222222222222222222222222222222222222222")
                background_tasks.add_task(background_analysis_task,message=slack_item["messageText"], openai_adapter=openai_adapter, table=TABLE)
                return Response(content=json.dumps({"ok": True, "error": "Error guardando en base de datos"}), media_type="application/json")
        else:
            print('333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333333')
            background_tasks.add_task(background_analysis_task,message=slack_item["messageText"], openai_adapter=openai_adapter, table=TABLE)
            print("ADVERTENCIA: No se guardó el mensaje (conexión DynamoDB no disponible)")
            return Response(content=json.dumps({"ok": True, "error": "Base de datos no disponible"}), media_type="application/json")

    except json.JSONDecodeError as e:
        print(f"Error decodificando JSON: {e}")
        return Response(content=json.dumps({"ok": True, "error": "JSON inválido"}), media_type="application/json", status_code=200)

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return Response(content=json.dumps({"ok": True, "error": "Error interno del servidor"}), media_type="application/json", status_code=200)


@app.post("/analyze")
async def analyze_message(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Analiza un mensaje usando OpenAI con tools de Notion y GitHub.
    Retorna una respuesta inteligente con posibles acciones realizadas.
    """
    print(f"📨 ANALYZE: {request.message[:50]}...")

    try:
        # Verificar que los adaptadores estén disponibles
        if not openai_adapter:
            print("❌ Adaptadores no disponibles")
            return {
                "response": "Lo siento, los servicios de IA no están disponibles en este momento.",
                "error": "Adaptadores no inicializados",
                "tool_results": []
            }




        background_tasks.add_task(background_analysis_task,message=request.message, openai_adapter=openai_adapter, table=TABLE)

    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return {
            "response": f"Error procesando la solicitud: {str(e)}",
            "error": True,
            "tool_results": []
        }


