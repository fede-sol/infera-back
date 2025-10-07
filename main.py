from fastapi import FastAPI
from dotenv import load_dotenv

# Importar autenticación y base de datos
from auth.routes import router as auth_router
from orchestration.routes import router as orchestration_router
from notion_module.routes import router as notion_router
from slack_module.routes import router as slack_router
from stats.routes import router as stats_router
from database import init_db
from fastapi.middleware.cors import CORSMiddleware


origins = [
    "http://localhost:3000",
]

load_dotenv()

# --- Inicializar Base de Datos ---
init_db()

# --- Creación de la Aplicación FastAPI ---
app = FastAPI(
    title="Infera API",
    description="API de clasificación de texto con autenticación y gestión de conocimiento.",
    version="2.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(auth_router)
app.include_router(orchestration_router)
app.include_router(notion_router)
app.include_router(slack_router)
app.include_router(stats_router)


@app.get("/")
def read_root():
    """Endpoint raíz"""
    return {
        "message": "Bienvenido a Infera API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "auth": "/auth",
            "orchestration": ["/classify", "/messages-webhook", "/analyze"],
            "notion": "/notion",
            "slack": "/slack",
            "stats": "/stats"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
