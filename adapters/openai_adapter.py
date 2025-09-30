import os
import json
import requests
from typing import List, Dict, Any, Optional, Callable
from openai import OpenAI
from .notion_adapter import NotionAdapter


class OpenAIAdapter:
    """
    Adaptador de OpenAI con integración de tools MCP y funciones de Notion.
    Permite ejecutar herramientas externas y mantener conversaciones con contexto.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-mini"):
        """
        Inicializa el adaptador de OpenAI.

        Args:
            api_key: Token de API de OpenAI. Si no se proporciona,
                    se busca en la variable de entorno OPENAI_API_KEY
            model: Modelo de OpenAI a utilizar
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("Se requiere un token de API de OpenAI. Configure OPENAI_API_KEY en las variables de entorno.")

        self.model = model
        self.client = OpenAI(api_key=self.api_key)
        self.notion_adapter = None
        self.tools = {}
        self.conversation_history = []

        # Inicializar tools disponibles
        self._initialize_tools()

    def set_notion_adapter(self, notion_adapter: NotionAdapter):
        """
        Configura el adaptador de Notion para usar sus funciones como tools.

        Args:
            notion_adapter: Instancia del NotionAdapter
        """
        self.notion_adapter = notion_adapter

    def add_github_mcp_tool(self, github_token: Optional[str] = None):
        """
        Agrega la tool MCP de GitHub.

        Args:
            github_token: Token de acceso de GitHub. Si no se proporciona,
                         se busca en GITHUB_TOKEN
        """
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        if self.github_token:
            self._register_github_tools()

    def chat(self, message: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Envía un mensaje al modelo y ejecuta tools si es necesario.

        Args:
            message: Mensaje del usuario
            system_prompt: Prompt del sistema (opcional)

        Returns:
            Respuesta del modelo con posibles resultados de tools
        """
        print("🤖 OpenAIAdapter.chat() - Iniciando conversación")
        print(f"📝 Message: {message}")
        print(f"🤖 System prompt: {system_prompt}")
        print(f"💬 Historial actual: {len(self.conversation_history)} mensajes")

        try:
            # Preparar mensajes
            print("📦 Preparando mensajes para OpenAI...")
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
                print("✅ System prompt agregado")

            # Agregar historial de conversación
            messages.extend(self.conversation_history)
            messages.append({"role": "user", "content": message})
            print(f"📨 Total mensajes enviados: {len(messages)}")

            # Obtener tools disponibles
            print("🔧 Obteniendo tools disponibles...")
            available_tools = self._get_available_tools()
            print(f"🛠️ Tools disponibles: {len(available_tools)}")

            if available_tools:
                print("📋 Lista de tools:")
                for i, tool in enumerate(available_tools):
                    print(f"  {i+1}. {tool.get('function', {}).get('name', 'unknown')}")

            # Primera llamada al modelo
            print("🚀 Enviando primera petición a OpenAI...")
            print(f"🤖 Modelo: {self.model}")
            print(f"🛠️ Tools incluidos: {len(available_tools) if available_tools else 0}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=available_tools if available_tools else None,
                tool_choice="auto"
            )

            print("✅ Respuesta inicial de OpenAI recibida")
            response_message = response.choices[0].message
            print(f"📥 Content: {response_message.content[:200] if response_message.content else 'None'}...")

            # Verificar si hay tool_calls
            has_tool_calls = hasattr(response_message, 'tool_calls') and response_message.tool_calls
            print(f"🔧 Tool calls detectados: {len(response_message.tool_calls) if has_tool_calls else 0}")

            # Detectar si el modelo está explicando en lugar de usar tools
            content = response_message.content or ""
            is_explaining_instead_of_using_tools = (
                not has_tool_calls and
                any(keyword in content.lower() for keyword in [
                    "voy a", "procedo a", "ahora voy a", "primero", "luego",
                    "después", "a continuación", "siguiente paso", "aplicaré"
                ]) and
                available_tools  # Solo si hay tools disponibles
            )

            if is_explaining_instead_of_using_tools:
                print("⚠️ Modelo está explicando en lugar de usar tools - forzando segunda iteración")
                print(f"📝 Contenido explicativo detectado: {content[:100]}...")

                # Agregar al historial como respuesta del assistant
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": getattr(response_message, 'tool_calls', None)
                })

                # Forzar una segunda llamada pidiendo específicamente usar tools
                print("🔄 Forzando segunda iteración con instrucciones claras...")
                follow_up_message = f"{message}\n\nPor favor, ejecuta las herramientas necesarias para completar esta tarea. No expliques, solo usa las tools disponibles."

                # Crear nueva conversación para la segunda iteración
                follow_up_messages = [
                    {"role": "system", "content": system_prompt + "\n\nIMPORTANTE: Usa las herramientas directamente, no expliques lo que vas a hacer."},
                    {"role": "user", "content": follow_up_message}
                ]

                follow_up_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=follow_up_messages,
                    tools=available_tools,
                    tool_choice="auto"
                )

                follow_up_message_response = follow_up_response.choices[0].message
                follow_up_has_tools = hasattr(follow_up_message_response, 'tool_calls') and follow_up_message_response.tool_calls

                print(f"🔧 Tool calls en segunda iteración: {len(follow_up_message_response.tool_calls) if follow_up_has_tools else 0}")

                # Reemplazar la respuesta original con la de follow-up
                response_message = follow_up_message_response
                has_tool_calls = follow_up_has_tools

            # Agregar respuesta al historial
            print("📝 Actualizando historial de conversación...")
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": getattr(response_message, 'tool_calls', None)
            })
            print(f"💬 Historial actualizado: {len(self.conversation_history)} mensajes")

            # Ejecutar tools si fueron llamadas
            all_tool_results = []
            if has_tool_calls:
                print("⚙️ Ejecutando tools llamadas por OpenAI...")
                tool_results = self._execute_tools(response_message.tool_calls)
                all_tool_results.extend(tool_results)
                print(f"✅ Primera tanda de tools ejecutadas: {len(tool_results)}")

                # Log detallado de cada tool result
                for i, result in enumerate(tool_results):
                    status = "✅" if result.get("success") else "❌"
                    print(f"🔧 Tool {i+1}: {result.get('function_name')} - {status}")

                # Agregar resultados al historial
                print("📝 Agregando resultados de tools al historial...")
                for result in tool_results:
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": json.dumps(result["result"])
                    })

                # Verificar si necesitamos más iteraciones
                max_iterations = 5  # Máximo de iteraciones para evitar loops infinitos
                iteration = 1

                while iteration < max_iterations:
                    print(f"🔄 Iteración {iteration + 1}: Verificando si se necesitan más tools...")

                    # Enviar consulta de seguimiento para ver si el modelo necesita más tools
                    follow_up_messages = self.conversation_history.copy()
                    follow_up_messages.append({
                        "role": "system",
                        "content": "Si necesitas ejecutar más herramientas para completar la tarea, hazlo ahora. Si ya tienes suficiente información, proporciona la respuesta final."
                    })

                    follow_up_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=follow_up_messages,
                        tools=available_tools,
                        tool_choice="auto"
                    )

                    follow_up_message = follow_up_response.choices[0].message
                    follow_up_has_tools = hasattr(follow_up_message, 'tool_calls') and follow_up_message.tool_calls

                    if not follow_up_has_tools:
                        print(f"✅ No se necesitan más tools después de iteración {iteration}")
                        final_message = follow_up_message.content
                        break

                    print(f"🔄 Iteración {iteration + 1}: Ejecutando {len(follow_up_message.tool_calls)} tools adicionales")

                    # Ejecutar tools adicionales
                    additional_results = self._execute_tools(follow_up_message.tool_calls)
                    all_tool_results.extend(additional_results)

                    # Agregar al historial
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": follow_up_message.content,
                        "tool_calls": follow_up_message.tool_calls
                    })

                    for result in additional_results:
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": result["tool_call_id"],
                            "content": json.dumps(result["result"])
                        })

                    iteration += 1

                # Respuesta final
                if iteration >= max_iterations:
                    print(f"⚠️ Se alcanzó el máximo de iteraciones ({max_iterations})")

                # Si no tenemos una respuesta final, obtenerla
                if 'final_message' not in locals():
                    print("🚀 Obteniendo respuesta final...")
                    final_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.conversation_history
                    )
                    final_message = final_response.choices[0].message.content

                print("✅ Respuesta final de OpenAI recibida")
                print(f"📥 Final response: {final_message[:200] if final_message else 'None'}...")

                # Actualizar historial
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_message
                })

                result_data = {
                    "response": final_message,
                    "tool_results": all_tool_results,
                    "conversation_history": self.conversation_history.copy()
                }

                print(f"🎉 Conversación con tools completada: {len(all_tool_results)} tools totales")
                return result_data

            # Respuesta sin tools
            print("💬 Respuesta sin tools - conversación completada")
            result_data = {
                "response": response_message.content,
                "tool_results": all_tool_results,
                "conversation_history": self.conversation_history.copy()
            }

            return result_data

        except Exception as e:
            print(f"❌ Error en conversación: {e}")
            print("Stack trace completo:")
            error_msg = f"Error en la conversación: {str(e)}"
            return {
                "response": error_msg,
                "tool_results": all_tool_results if 'all_tool_results' in locals() else [],
                "conversation_history": self.conversation_history.copy(),
                "error": True
            }

    def clear_conversation(self):
        """Limpia el historial de conversación."""
        self.conversation_history = []

    def _initialize_tools(self):
        """Inicializa las tools disponibles."""
        # Tools de Notion (se registrarán cuando se configure el adaptador)
        self.notion_tools_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "search_notion_pages",
                    "description": "Buscar páginas en Notion por título o contenido",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Término de búsqueda"
                            },
                            "filter_type": {
                                "type": "string",
                                "enum": ["page", "database"],
                                "description": "Tipo de filtro (opcional)"
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Número máximo de resultados (máximo 100)",
                                "default": 20
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_notion_page",
                    "description": "Leer el contenido completo de una página de Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "ID de la página de Notion"
                            }
                        },
                        "required": ["page_id"]
                    }
                }
            },
            
            {
                "type": "function",
                "function": {
                    "name": "create_notion_page",
                    "description": "Crear una nueva página en Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "parent_id": {
                                "type": "string",
                                "description": "ID del padre (página o base de datos)"
                            },
                            "title": {
                                "type": "string",
                                "description": "Título de la nueva página"
                            },
                            "content": {
                                "type": "array",
                                "description": "Lista de bloques de contenido inicial (opcional)",
                                "items": {
                                    "type": "object",
                                    "description": "Block de Notion con tipo y contenido"
                                }
                            },
                            "is_database": {
                                "type": "boolean",
                                "description": "True si el padre es una base de datos",
                                "default": False
                            }
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_notion_block",
                    "description": "Actualizar un block específico en una página de Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {
                                "type": "string",
                                "description": "ID del block a actualizar"
                            },
                            "updates": {
                                "type": "object",
                                "description": "Actualizaciones a aplicar al block",
                                "properties": {
                                    "paragraph": {
                                        "type": "object",
                                        "description": "Contenido para block de párrafo"
                                    },
                                    "heading_1": {
                                        "type": "object",
                                        "description": "Contenido para heading 1"
                                    },
                                    "heading_2": {
                                        "type": "object",
                                        "description": "Contenido para heading 2"
                                    },
                                    "heading_3": {
                                        "type": "object",
                                        "description": "Contenido para heading 3"
                                    },
                                    "bulleted_list_item": {
                                        "type": "object",
                                        "description": "Contenido para item de lista"
                                    },
                                    "numbered_list_item": {
                                        "type": "object",
                                        "description": "Contenido para item de lista numerada"
                                    }
                                }
                            }
                        },
                        "required": ["block_id", "updates"]
                    }
                }
            },
            {
                "type": "function",
                "function":                 {
                    "name": "append_notion_blocks",
                    "description": "Agregar múltiples blocks al final de una página de Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "parent_id": {
                                "type": "string",
                                "description": "ID de la página o block padre donde agregar los blocks"
                            },
                            "blocks": {
                                "type": "array",
                                "description": "Lista de blocks a agregar con formato simple",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "description": "Tipo de block (paragraph, heading_1, heading_2, heading_3, bulleted_list_item, numbered_list_item, to_do, code, quote, callout, divider)",
                                            "enum": ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do", "code", "quote", "callout", "divider"]
                                        },
                                        "content": {
                                            "type": "string",
                                            "description": "Contenido de texto del block"
                                        }
                                    },
                                    "required": ["type", "content"],
                                    "additionalProperties": True
                                }
                            }
                        },
                        "required": ["parent_id", "blocks"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notion_page_blocks",
                    "description": "Obtener lista simplificada de blocks de una página de Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "ID de la página de la que obtener los blocks"
                            }
                        },
                        "required": ["page_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_notion_block",
                    "description": "Eliminar un block específico de Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {
                                "type": "string",
                                "description": "ID del block a eliminar"
                            }
                        },
                        "required": ["block_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_notion_block_smart",
                    "description": "Actualizar un block de manera inteligente, respetando las restricciones de la API",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {
                                "type": "string",
                                "description": "ID del block a actualizar"
                            },
                            "updates": {
                                "type": "object",
                                "description": "Actualizaciones a aplicar al block",
                                "properties": {
                                    "content": {
                                        "type": "string",
                                        "description": "Nuevo contenido de texto del block"
                                    },
                                    "checked": {
                                        "type": "boolean",
                                        "description": "Estado checked para blocks de tipo to_do"
                                    },
                                    "language": {
                                        "type": "string",
                                        "description": "Lenguaje para blocks de tipo code"
                                    },
                                    "icon": {
                                        "type": "string",
                                        "description": "Emoji para blocks de tipo callout"
                                    }
                                }
                            }
                        },
                        "required": ["block_id", "updates"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reorganize_notion_blocks_completely",
                    "description": "Reorganiza completamente los blocks de una página creando un nuevo orden al final. Más efectiva que reorganize_notion_blocks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "ID de la página a reorganizar completamente"
                            },
                            "block_order": {
                                "type": "array",
                                "description": "Lista ordenada de IDs de blocks en el orden deseado",
                                "items": {
                                    "type": "string",
                                    "description": "ID de un block a incluir en el orden"
                                }
                            }
                        },
                        "required": ["page_id", "block_order"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cleanup_notion_duplicate_blocks",
                    "description": "Limpia bloques duplicados después de una reorganización, eliminando automáticamente blocks con contenido idéntico.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "ID de la página donde limpiar duplicados"
                            },
                            "block_ids": {
                                "type": "array",
                                "description": "Lista de IDs de blocks a verificar por duplicados",
                                "items": {
                                    "type": "string",
                                    "description": "ID de un block a verificar"
                                }
                            }
                        },
                        "required": ["page_id", "block_ids"]
                    }
                }
            }

        ]

    def _register_github_tools(self):
        """Registra las tools de GitHub MCP."""
        self.github_tools_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "github_search_repositories",
                    "description": "Buscar repositorios en GitHub",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Término de búsqueda"
                            },
                            "sort": {
                                "type": "string",
                                "enum": ["stars", "forks", "updated"],
                                "description": "Criterio de ordenamiento",
                                "default": "stars"
                            },
                            "per_page": {
                                "type": "integer",
                                "description": "Número de resultados por página",
                                "default": 10,
                                "maximum": 100
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "github_get_repository",
                    "description": "Obtener información detallada de un repositorio",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "owner": {
                                "type": "string",
                                "description": "Propietario del repositorio"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Nombre del repositorio"
                            }
                        },
                        "required": ["owner", "repo"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "github_list_issues",
                    "description": "Listar issues de un repositorio",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "owner": {
                                "type": "string",
                                "description": "Propietario del repositorio"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Nombre del repositorio"
                            },
                            "state": {
                                "type": "string",
                                "enum": ["open", "closed", "all"],
                                "description": "Estado de los issues",
                                "default": "open"
                            },
                            "per_page": {
                                "type": "integer",
                                "description": "Número de issues por página",
                                "default": 10,
                                "maximum": 100
                            }
                        },
                        "required": ["owner", "repo"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "github_create_issue",
                    "description": "Crear un nuevo issue en un repositorio",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "owner": {
                                "type": "string",
                                "description": "Propietario del repositorio"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Nombre del repositorio"
                            },
                            "title": {
                                "type": "string",
                                "description": "Título del issue"
                            },
                            "body": {
                                "type": "string",
                                "description": "Contenido del issue"
                            },
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista de etiquetas"
                            }
                        },
                        "required": ["owner", "repo", "title"]
                    }
                }
            }
        ]

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Obtiene la lista de tools disponibles."""
        tools = []

        # Agregar tools de Notion si el adaptador está configurado
        if self.notion_adapter:
            tools.extend(self.notion_tools_definitions)

        # Agregar tools de GitHub si están registradas
        if hasattr(self, 'github_tools_definitions'):
            tools.extend(self.github_tools_definitions)

        return tools

    def _execute_tools(self, tool_calls) -> List[Dict[str, Any]]:
        """Ejecuta las tools llamadas por el modelo."""
        print(f"⚙️ Ejecutando {len(tool_calls)} tool calls")
        results = []

        for i, tool_call in enumerate(tool_calls, 1):
            print(f"🔧 Tool call {i}: ID={tool_call.id}")
            try:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                print(f"📝 Función: {function_name}")
                print(f"📋 Argumentos: {function_args}")

                result = self._execute_tool_function(function_name, function_args)

                tool_result = {
                    "tool_call_id": tool_call.id,
                    "function_name": function_name,
                    "result": result,
                    "success": True
                }

                results.append(tool_result)
                print(f"✅ Tool {function_name} ejecutada exitosamente")

            except Exception as e:
                print(f"❌ Error ejecutando tool {tool_call.function.name}: {e}")
                print(f"Stack trace:")

                tool_result = {
                    "tool_call_id": tool_call.id,
                    "function_name": tool_call.function.name,
                    "result": {"error": str(e)},
                    "success": False
                }

                results.append(tool_result)

        print(f"📊 Resultado: {sum(1 for r in results if r['success'])}/{len(results)} tools exitosas")
        return results

    def _execute_tool_function(self, function_name: str, args: Dict[str, Any]) -> Any:
        """Ejecuta una función específica de tool."""
        print(f"🔍 Ejecutando función: {function_name}")

        if "notion" in function_name:
            if not self.notion_adapter:
                print("❌ Adaptador de Notion no configurado")
                raise Exception("El adaptador de Notion no está configurado")
            print("📝 Redirigiendo a función de Notion")
            return self._execute_notion_function(function_name, args)

        elif "github" in function_name:
            print("🐙 Redirigiendo a función de GitHub")
            return self._execute_github_function(function_name, args)

        else:
            print(f"❓ Función no reconocida: {function_name}")
            raise Exception(f"Función no reconocida: {function_name}")

    def _execute_notion_function(self, function_name: str, args: Dict[str, Any]) -> Any:
        """Ejecuta funciones del adaptador de Notion."""
        print(f"📝 Ejecutando función de Notion: {function_name}")
        print(f"📋 Argumentos: {args}")

        try:
            if function_name == "search_notion_pages":
                print("🔍 Buscando páginas en Notion...")
                result = self.notion_adapter.search_pages(**args)
                print(f"📄 Páginas encontradas: {len(result) if isinstance(result, list) else 'N/A'}")
                return result

            elif function_name == "read_notion_page":
                page_id = args["page_id"]
                print(f"📖 Leyendo página de Notion: {page_id}")
                result = self.notion_adapter.read_page(page_id)
                print(f"📄 Página leída: {result.get('title', 'Sin título')}")
                return result

            elif function_name == "update_notion_page":
                page_id = args["page_id"]
                print(f"✏️ Actualizando página de Notion: {page_id}")
                result = self.notion_adapter.update_page(page_id, args["updates"])
                print("✅ Página actualizada")
                return result

            elif function_name == "create_notion_page":
                print("➕ Creando nueva página en Notion...")
                result = self.notion_adapter.create_page(**args)
                print(f"✅ Página creada: {result.get('id', 'ID desconocido')}")
                return result

            elif function_name == "update_notion_block":
                block_id = args["block_id"]
                updates = args["updates"]
                print(f"🔧 Actualizando block específico: {block_id}")
                result = self.notion_adapter.update_block(block_id, updates)
                print("✅ Block actualizado")
                return result

            elif function_name == "append_notion_blocks":
                parent_id = args["parent_id"]
                blocks = args["blocks"]
                print(f"➕ Agregando {len(blocks)} blocks a {parent_id}")
                result = self.notion_adapter.append_blocks(parent_id, blocks)
                print(f"✅ {result.get('blocks_added', 0)} blocks agregados")
                return result

            elif function_name == "get_notion_page_blocks":
                page_id = args["page_id"]
                print(f"📋 Obteniendo blocks de página: {page_id}")
                result = self.notion_adapter.get_page_blocks(page_id)
                print(f"✅ {len(result)} blocks obtenidos")
                return result

            elif function_name == "delete_notion_block":
                block_id = args["block_id"]
                print(f"🗑️ Eliminando block: {block_id}")
                result = self.notion_adapter.delete_block(block_id)
                print("✅ Block eliminado")
                return result

            elif function_name == "update_notion_block_smart":
                block_id = args["block_id"]
                updates = args["updates"]
                print(f"🔧 Actualizando block (smart): {block_id}")
                result = self.notion_adapter.update_block_smart(block_id, updates)
                print("✅ Block actualizado (smart)")
                return result

            elif function_name == "reorganize_notion_blocks":
                page_id = args["page_id"]
                operations = args["operations"]
                print(f"🔄 Reorganizando blocks en página: {page_id}")
                result = self.notion_adapter.reorganize_blocks(page_id, operations)
                print(f"✅ {result.get('operations_completed', 0)} operaciones completadas")
                return result

            elif function_name == "reorganize_notion_blocks_completely":
                page_id = args["page_id"]
                block_order = args["block_order"]
                print(f"🔄 Reorganizando completamente blocks en página: {page_id}")
                result = self.notion_adapter.reorganize_blocks_completely(page_id, block_order)
                print(f"✅ Reorganización completa: {result.get('blocks_created', 0)} blocks creados")
                return result

            elif function_name == "cleanup_notion_duplicate_blocks":
                page_id = args["page_id"]
                block_ids = args["block_ids"]
                print(f"🧹 Limpiando duplicados en página: {page_id}")
                result = self.notion_adapter.cleanup_duplicate_blocks(page_id, block_ids)
                print(f"✅ Duplicados eliminados: {result.get('duplicates_removed', 0)}")
                return result

            else:
                print(f"❓ Función de Notion no reconocida: {function_name}")
                raise Exception(f"Función de Notion no reconocida: {function_name}")

        except Exception as e:
            print(f"❌ Error en función de Notion {function_name}: {e}")
            raise

    def _execute_github_function(self, function_name: str, args: Dict[str, Any]) -> Any:
        """Ejecuta funciones de GitHub MCP."""
        print(f"🐙 Ejecutando función de GitHub: {function_name}")
        print(f"📋 Argumentos: {args}")

        base_url = "https://api.github.com"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            if function_name == "github_search_repositories":
                query = args["query"]
                sort = args.get("sort", "stars")
                per_page = min(args.get("per_page", 10), 100)

                print(f"🔍 Buscando repositorios en GitHub: '{query}' (orden: {sort})")
                url = f"{base_url}/search/repositories?q={query}&sort={sort}&per_page={per_page}"
                print(f"🌐 URL: {url}")

                response = requests.get(url, headers=headers)
                print(f"📡 HTTP Status: {response.status_code}")
                response.raise_for_status()

                result = response.json()
                print(f"📊 Repositorios encontrados: {result.get('total_count', 0)}")
                return result

            elif function_name == "github_get_repository":
                owner = args["owner"]
                repo = args["repo"]

                print(f"📖 Obteniendo repositorio: {owner}/{repo}")
                url = f"{base_url}/repos/{owner}/{repo}"
                print(f"🌐 URL: {url}")

                response = requests.get(url, headers=headers)
                print(f"📡 HTTP Status: {response.status_code}")
                response.raise_for_status()

                result = response.json()
                print(f"✅ Repositorio obtenido: {result.get('name', 'N/A')}")
                return result

            elif function_name == "github_list_issues":
                owner = args["owner"]
                repo = args["repo"]
                state = args.get("state", "open")
                per_page = min(args.get("per_page", 10), 100)

                print(f"📋 Listando issues de {owner}/{repo} (estado: {state})")
                url = f"{base_url}/repos/{owner}/{repo}/issues?state={state}&per_page={per_page}"
                print(f"🌐 URL: {url}")

                response = requests.get(url, headers=headers)
                print(f"📡 HTTP Status: {response.status_code}")
                response.raise_for_status()

                result = response.json()
                print(f"📊 Issues encontrados: {len(result) if isinstance(result, list) else 0}")
                return result

            elif function_name == "github_create_issue":
                owner = args["owner"]
                repo = args["repo"]
                title = args["title"]

                print(f"➕ Creando issue en {owner}/{repo}: '{title}'")
                issue_data = {
                    "title": title,
                    "body": args.get("body", ""),
                    "labels": args.get("labels", [])
                }
                print(f"📝 Datos del issue: {issue_data}")

                url = f"{base_url}/repos/{owner}/{repo}/issues"
                print(f"🌐 URL: {url}")

                response = requests.post(url, headers=headers, json=issue_data)
                print(f"📡 HTTP Status: {response.status_code}")
                response.raise_for_status()

                result = response.json()
                print(f"✅ Issue creado: #{result.get('number', 'N/A')}")
                return result

            else:
                print(f"❓ Función de GitHub no reconocida: {function_name}")
                raise Exception(f"Función de GitHub no reconocida: {function_name}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Error HTTP en función de GitHub {function_name}: {e}")
            raise
        except Exception as e:
            print(f"❌ Error en función de GitHub {function_name}: {e}")
            raise


# Función de conveniencia para crear instancia del adaptador
def create_openai_adapter(api_key: Optional[str] = None, model: str = "gpt-5-mini") -> OpenAIAdapter:
    """
    Crea una instancia del adaptador de OpenAI.

    Args:
        api_key: Token de API de OpenAI (opcional)
        model: Modelo a utilizar (opcional)

    Returns:
        Instancia de OpenAIAdapter
    """
    return OpenAIAdapter(api_key, model)
