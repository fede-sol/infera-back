from adapters.langchain_mcp_agent import LangChainMCPAgent
from resources.system_prompt import ai_instructions
import os
from auth.utils import get_user_credentials
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from adapters.openai_adapter_v2 import OpenAIAdapterV2

load_dotenv()

def initialize_langchain_agent(user_id: str, db: Session) -> LangChainMCPAgent:
# --- Inicialización de Agente LangChain con MCP ---
    print("🚀 Iniciando agente LangChain MCP...")
    user_credentials = get_user_credentials(user_id,db)
    try:
        # Inicializar agente de LangChain con MCP oficial
        langchain_agent = LangChainMCPAgent(
            api_key=os.getenv('OPENAI_TOKEN'),
            model="openai:gpt-5-mini",
            instructions=ai_instructions,
            temperature=0,
            max_iterations=30,
            langsmith_project="infera-back-mcp"
        )
        print("✅ Agente de LangChain MCP inicializado")

        # Configurar servidores MCP
        langchain_agent.add_mcp_tool(
            server_label="Notion",
            server_description="Realizar acciones en Notion",
            server_url="https://f2a65189bb2c.ngrok-free.app/mcp",
            authorization=user_credentials["notion_token"],
            allowed_tools=["get_notion_page_content","create_page","search_a_page_in_notion","get_notion_page_content","append_text_block","append_title_block","append_code_block","update_block"]
        )
        
        langchain_agent.add_mcp_tool(
            server_label="GitHub",
            server_description="Realizar acciones en GitHub",
            server_url="https://api.githubcopilot.com/mcp/",
            authorization=user_credentials["github_token"],
            allowed_tools=["search_code", "search_repositories"]
        )
        
        langchain_agent.add_mcp_tool(
            server_label="GitHubFile",
            server_description="Obtener contenido de archivos en GitHub",
            server_url="https://f2a65189bb2c.ngrok-free.app/mcp",
            authorization=user_credentials["github_token"],
            allowed_tools=["get_github_file_content"]
        )
        
        print("✅ Todos los servidores MCP configurados")
        return langchain_agent
        
    except Exception as e:
        print(f"❌ Error inicializando agente: {e}")
        langchain_agent = None

def initialize_openai_agent(user_id: str,db: Session) -> OpenAIAdapterV2:
    # --- Inicialización de Adaptadores ---
    print("🚀 Iniciando OpenAI Adapter...")
    user_credentials = get_user_credentials(user_id,db)
    try:
        # Inicializar adaptador de OpenAI
        openai_adapter = OpenAIAdapterV2(api_key=os.getenv('OPENAI_TOKEN'), instructions=ai_instructions)
        print("✅ Adaptador de OpenAI inicializado")

        # Configurar integraciones
        openai_adapter.add_mcp_tool(server_label="Notion", server_description="Realizar acciones en Notion", server_url="https://infera.fastmcp.app/mcp", allowed_tools=["get_notion_page_content","create_page","search_a_page_in_notion","get_notion_page_content","append_text_block","append_title_block","append_code_block","update_block"], authorization=user_credentials["notion_token"])
        openai_adapter.add_mcp_tool(server_label="GitHub", server_description="Realizar acciones en GitHub", server_url="https://api.githubcopilot.com/mcp/", allowed_tools=["search_code","search_repositories"], authorization=user_credentials["github_token"])
        openai_adapter.add_mcp_tool(server_label="Get_Github_File_Content", server_description="Obtener el contenido de un archivo en GitHub", server_url="https://infera.fastmcp.app/mcp", allowed_tools=["get_github_file_content"], authorization=user_credentials["github_token"])
        print("✅ Todas las herramientas configuradas")

        return openai_adapter


    except Exception as e:
        print(f"❌ Error inicializando adaptadores: {e}")
        openai_adapter = None