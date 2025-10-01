import os
from typing import Dict, Any, Optional
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from langsmith import Client
from langsmith.run_helpers import traceable


class LangChainMCPAgent:
    """
    Agente de LangChain que utiliza servidores MCP a través de MultiServerMCPClient oficial
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "openai:gpt-5-mini",
        instructions: str = "",
        temperature: float = 0,
        max_iterations: int = 30,
        langsmith_project: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("Se requiere OPENAI_API_KEY")
        
        self.model = model
        self.instructions = instructions
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.mcp_client = None
        self.agent = None
        self.tools = []
        self.server_configs = {}
        
        # Configurar LangSmith si está disponible
        self.langsmith_enabled = False
        langsmith_api_key = os.getenv('LANGSMITH_API_KEY')
        
        if langsmith_api_key:
            try:
                # Configurar variables de entorno para LangSmith
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
                
                # Configurar proyecto si se proporciona
                if langsmith_project:
                    os.environ["LANGCHAIN_PROJECT"] = langsmith_project
                else:
                    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "langchain-mcp-agent")
                
                # Inicializar cliente de LangSmith
                self.langsmith_client = Client(api_key=langsmith_api_key)
                self.langsmith_enabled = True
                print(f"✅ LangSmith habilitado - Proyecto: {os.environ['LANGCHAIN_PROJECT']}")
            except Exception as e:
                print(f"⚠️  LangSmith no disponible: {e}")
                self.langsmith_enabled = False
        else:
            print("ℹ️  LangSmith deshabilitado (no se encontró LANGSMITH_API_KEY)")
    
    def add_mcp_tool(
        self,
        server_label: str,
        server_description: str,
        server_url: str,
        authorization: Optional[str] = None,
        allowed_tools: Optional[list] = None,
        require_approval: str = "always"
    ):
        """
        Agrega configuración de servidor MCP.
        
        Args:
            server_label: Etiqueta del servidor
            server_description: Descripción del servidor
            server_url: URL del servidor MCP
            authorization: Token de autorización (opcional)
            allowed_tools: Lista de herramientas permitidas (opcional)
            require_approval: Nivel de aprobación (no usado, compatibilidad con API anterior)
        """
        # Configuración para streamable_http
        config = {
            "transport": "streamable_http",
            "url": server_url
        }
        
        # Agregar headers de autenticación si se proporciona
        if authorization:
            config["headers"] = {
                "Authorization": f"Bearer {authorization}"
            }
        
        # Guardar allowed_tools en la configuración para filtrado posterior
        if allowed_tools:
            config["allowed_tools"] = allowed_tools
        
        self.server_configs[server_label] = config
        tools_info = f" (permitidas: {', '.join(allowed_tools)})" if allowed_tools else ""
        print(f"✅ Servidor MCP agregado: {server_label} ({server_url}){tools_info}")
    
    async def _initialize_agent(self):
        """Inicializa el cliente MCP y el agente"""
        if not self.server_configs:
            raise ValueError("No se han configurado servidores MCP")
        
        # Preparar configuraciones para MultiServerMCPClient (sin allowed_tools)
        mcp_configs = {}
        for server_label, config in self.server_configs.items():
            # Crear copia sin allowed_tools
            mcp_config = {k: v for k, v in config.items() if k != "allowed_tools"}
            mcp_configs[server_label] = mcp_config
        
        # Crear cliente MCP con todos los servidores
        self.mcp_client = MultiServerMCPClient(mcp_configs)
        
        # Obtener todas las herramientas de todos los servidores
        all_tools = await self.mcp_client.get_tools()
        print(f"✅ Herramientas MCP cargadas: {len(all_tools)}")
        
        # Filtrar herramientas según allowed_tools (si existe)
        self.tools = []
        for server_label, config in self.server_configs.items():
            allowed_tools = config.get("allowed_tools")
            if allowed_tools:
                # Filtrar por nombre exacto
                for tool in all_tools:
                    if tool.name in allowed_tools:
                        self.tools.append(tool)
                        print(f"   ✓ {tool.name} (permitida en {server_label})")
            else:
                # Sin filtro, agregar todas las herramientas de este servidor
                for tool in all_tools:
                    if tool not in self.tools:
                        print(f"   ✓ {tool.name} (permitida en {server_label})")
                        self.tools.append(tool)
        
        # Si no hay configuración de allowed_tools en ningún servidor, agregar todas
        if not self.tools:
            self.tools = all_tools
            print(f"   ℹ️  Sin filtros, usando todas las herramientas")
        
        print(f"✅ Herramientas finales: {len(self.tools)}")
        
        # Inicializar modelo de chat
        llm = init_chat_model(self.model, temperature=self.temperature)
        
        # Crear agente ReAct con las herramientas MCP filtradas
        # Nota: create_react_agent no acepta state_modifier ni max_iterations
        # Las instrucciones se pasarán en el mensaje del sistema al invocar
        self.agent = create_react_agent(llm, self.tools)
        
        print(f"✅ Agente LangChain inicializado con {len(self.tools)} herramientas")
    
    async def chat(self, message: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta el agente con un mensaje
        
        Args:
            message: Mensaje del usuario
            system_prompt: Prompt del sistema (opcional, sobreescribe self.instructions)
            
        Returns:
            Resultado del agente con información de herramientas ejecutadas
        """
        try:
            # Inicializar agente si no existe
            if self.agent is None:
                await self._initialize_agent()
            
            print(f"\n🤖 Ejecutando agente LangChain MCP...")
            print(f"📝 Mensaje del usuario: {message[:100]}..." if len(message) > 100 else f"📝 Mensaje del usuario: {message}")
            
            # Preparar mensajes con instrucciones del sistema
            from langchain_core.messages import SystemMessage, HumanMessage
            
            instructions = system_prompt if system_prompt else self.instructions
            messages = []
            
            # Agregar mensaje del sistema si hay instrucciones
            if instructions:
                messages.append(SystemMessage(content=instructions))
                print(f"💼 System prompt agregado ({len(instructions)} caracteres)")
            
            # Agregar mensaje del usuario
            messages.append(HumanMessage(content=message))
            
            # Ejecutar agente con configuración de LangSmith
            print(f"\n⚙️  Iniciando agente con {len(self.tools)} herramientas disponibles...")
            
            # Configurar metadata para LangSmith
            config = {
                "recursion_limit": self.max_iterations,
                "run_name": "LangChain MCP Agent",
                "metadata": {
                    "model": self.model,
                    "num_tools": len(self.tools),
                    "max_iterations": self.max_iterations,
                    "temperature": self.temperature
                }
            }
            
            if self.langsmith_enabled:
                print(f"📊 LangSmith tracking habilitado")
            
            result = await self.agent.ainvoke({"messages": messages}, config)
            
            # Extraer mensajes y herramientas usadas
            messages = result.get("messages", [])
            tool_calls = []
            response_content = ""
            
            print(f"\n📨 Procesando {len(messages)} mensajes del agente...")
            
            # Procesar mensajes para extraer tool calls y respuesta final
            for i, msg in enumerate(messages):
                print(f"\n   Mensaje {i+1}/{len(messages)}:")
                print(f"      Tipo: {type(msg).__name__}")
                # Mensaje del agente
                if hasattr(msg, 'content') and isinstance(msg.content, str):
                    if msg.content:
                        response_content = msg.content
                        content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                        print(f"      Contenido: {content_preview}")
                
                # Tool calls
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    print(f"      🔧 Tool calls encontrados: {len(msg.tool_calls)}")
                    for j, tc in enumerate(msg.tool_calls, 1):
                        tool_name = tc.get("name", "")
                        tool_args = tc.get("args", {})
                        print(f"         {j}. {tool_name}")
                        print(f"            Args: {tool_args}")
                        
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": tool_name,
                            "server_label": tool_name.split("__")[0] if "__" in tool_name else "unknown",
                            "arguments": str(tool_args),
                            "success": True,  # LangChain maneja errores internamente
                            "error": None,
                            "output": None  # Se llena con el siguiente mensaje
                        })
                
                # Tool responses
                if hasattr(msg, 'content') and hasattr(msg, 'tool_call_id'):
                    print(f"      📤 Tool response para: {msg.tool_call_id}")
                    response_preview = msg.content[:150] + "..." if len(str(msg.content)) > 150 else msg.content
                    print(f"         Respuesta: {response_preview}")
                    
                    # Encontrar el tool call correspondiente
                    for tc in tool_calls:
                        if tc["id"] == msg.tool_call_id:
                            tc["output"] = msg.content
                            # Verificar si hay error en la respuesta
                            if "error" in str(msg.content).lower():
                                tc["success"] = False
                                tc["error"] = msg.content
                                print(f"         ⚠️  Error detectado en respuesta")
            
            # Calcular estadísticas
            tool_stats = self._calculate_stats(tool_calls)
            
            # Mostrar resumen
            print(f"\n🎯 AGENTE COMPLETADO")
            print(f"   📊 Total mensajes procesados: {len(messages)}")
            print(f"   🔧 Total herramientas ejecutadas: {tool_stats['total']}")
            
            # Verificar si alcanzó el límite de iteraciones
            if len(messages) >= (self.max_iterations * 2):  # Aproximado, cada iteración genera ~2 mensajes
                print(f"   ⚠️  ADVERTENCIA: Puede haber alcanzado el límite de {self.max_iterations} iteraciones")
            
            if tool_stats["total"] > 0:
                print(f"   ✅ Exitosas: {tool_stats['successful']}/{tool_stats['total']} ({tool_stats['success_rate']}%)")
                
                # Mostrar herramientas ejecutadas
                print(f"\n   Herramientas ejecutadas:")
                for tc in tool_calls:
                    status = "✅" if tc["success"] else "❌"
                    print(f"      {status} {tc['name']}")
            
            # Mostrar respuesta final
            if response_content:
                preview = response_content[:200] + "..." if len(response_content) > 200 else response_content
                print(f"\n   💬 Respuesta final: {preview}")
            
            return {
                "success": True,
                "response": response_content,
                "content": response_content,
                "tool_calls": tool_calls,
                "tool_stats": tool_stats,
                "messages": messages
            }
            
        except Exception as e:
            print(f"❌ Error en agente: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "response": f"Error: {str(e)}",
                "tool_calls": [],
                "tool_stats": {"total": 0, "successful": 0, "failed": 0, "success_rate": 0}
            }
    
    def _calculate_stats(self, tool_calls: list) -> Dict[str, Any]:
        """Calcula estadísticas de tool calls"""
        if not tool_calls:
            return {"total": 0, "successful": 0, "failed": 0, "success_rate": 0}
        
        total = len(tool_calls)
        successful = sum(1 for tc in tool_calls if tc.get("success", False))
        failed = total - successful
        success_rate = round((successful / total) * 100, 2) if total > 0 else 0
        
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": success_rate
        }
    
    def clear_tools(self):
        """Limpia todas las herramientas"""
        self.tools = []
        self.server_configs = {}
        self.mcp_client = None
        self.agent = None

