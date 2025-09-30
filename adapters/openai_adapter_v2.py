import os
from typing import List, Dict, Any, Optional
from openai import OpenAI


class OpenAIAdapterV2:
    """
    Adaptador simple de OpenAI usando la nueva API responses.create()
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-mini", instructions: str = ""):
        """
        Inicializa el adaptador de OpenAI v2.

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
        self.tools = []
        self.instructions = instructions

    def add_mcp_tool(self, server_label: str, server_description: str, server_url: str, require_approval: str = "always", authorization: str = None, allowed_tools: list = None):
        """
        Agrega una tool MCP al adaptador.

        Args:
            server_label: Etiqueta del servidor MCP
            server_description: Descripción del servidor
            server_url: URL del servidor MCP
            require_approval: Nivel de aprobación requerido ('never', 'always', 'auto')
        """
        tool = {
            "type": "mcp",
            "server_label": server_label,
            "server_description": server_description,
            "server_url": server_url,
            "require_approval": require_approval,
        }

        if authorization:
            tool["authorization"] = authorization

        if allowed_tools:
            tool["allowed_tools"] = allowed_tools

        self.tools.append(tool)

    def _extract_response_content(self, response) -> Dict[str, Any]:
        """
        Extrae el contenido, tool calls y approval requests de la respuesta compleja de OpenAI.

        Args:
            response: Objeto Response de OpenAI

        Returns:
            Diccionario con content, tool_calls y approval_requests extraídos
        """
        content = ""
        tool_calls = []
        approval_requests = []

        # Verificar si hay output en la respuesta
        if hasattr(response, 'output') and response.output:
            for item in response.output:
                # Extraer contenido de texto de ResponseOutputMessage
                if hasattr(item, 'type') and item.type == 'message':
                    if hasattr(item, 'content') and item.content:
                        for content_item in item.content:
                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                if hasattr(content_item, 'text'):
                                    content = content_item.text
                                    break

                # Extraer tool calls de McpCall
                elif hasattr(item, 'type') and item.type == 'mcp_call':
                    tool_call_info = {
                        "id": getattr(item, 'id', ''),
                        "name": getattr(item, 'name', ''),
                        "server_label": getattr(item, 'server_label', ''),
                        "arguments": getattr(item, 'arguments', ''),
                        "success": item.error is None,
                        "error": getattr(item.error, 'message', None) if item.error else None,
                        "output": getattr(item, 'output', None)
                    }
                    tool_calls.append(tool_call_info)

                # Extraer approval requests
                elif hasattr(item, 'type') and item.type == 'mcp_approval_request':
                    approval_request = {
                        "id": getattr(item, 'id', ''),
                        "type": getattr(item, 'type', ''),
                        "name": getattr(item, 'name', ''),
                        "server_label": getattr(item, 'server_label', ''),
                        "arguments": getattr(item, 'arguments', '')
                    }
                    approval_requests.append(approval_request)

        return {
            "content": content,
            "tool_calls": tool_calls,
            "approval_requests": approval_requests
        }

    def _handle_approval_requests(self, approval_requests: List[Dict[str, Any]], previous_response_id: str) -> Dict[str, Any]:
        """
        Maneja automáticamente las solicitudes de aprobación de MCP tools.
        Siempre aprueba todas las solicitudes.

        Args:
            approval_requests: Lista de approval requests
            previous_response_id: ID de la respuesta anterior

        Returns:
            Resultado de la nueva llamada con approvals procesados
        """
        if not approval_requests:
            return None

        # Crear input con approvals automáticos
        input_data = []
        for request in approval_requests:
            approval_response = {
                "type": "mcp_approval_response",
                "approve": True,  # Siempre aprobar
                "approval_request_id": request["id"]
            }
            input_data.append(approval_response)

        try:
            # Hacer nueva llamada con approvals
            response = self.client.responses.create(
                instructions=self.instructions,
                model=self.model,
                tools=self.tools if self.tools else None,
                previous_response_id=previous_response_id,
                input=input_data,
            )

            # Extraer contenido de la nueva respuesta
            extracted = self._extract_response_content(response)

            return {
                "success": True,
                "response": response,
                "content": extracted["content"],
                "tool_calls": extracted["tool_calls"],
                "approval_requests": extracted["approval_requests"],
                "approvals_processed": len(approval_requests)
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Error procesando approvals: {str(e)}",
                "approvals_processed": 0
            }

    def chat(self, message: str, system_prompt: Optional[str] = None, max_approval_iterations: int = 50, debug_duplicates: bool = True) -> Dict[str, Any]:
        """
        Envía un mensaje usando la nueva API responses.create().
        Maneja automáticamente las solicitudes de aprobación de MCP tools.

        Args:
            message: Mensaje del usuario
            system_prompt: Prompt del sistema (opcional, sobreescribe self.instructions)
            max_approval_iterations: Máximo número de iteraciones para procesar approvals
            debug_duplicates: Si mostrar logs detallados de deduplicación (default: True)

        Returns:
            Respuesta del modelo con posibles resultados de tools
        """
        try:
            # Usar system_prompt si se proporciona, sino usar self.instructions
            instructions = system_prompt if system_prompt else self.instructions

            # Primera llamada
            response = self.client.responses.create(
                instructions=instructions,
                model=self.model,
                tools=self.tools if self.tools else None,
                input=message,
            )

            # Procesar approvals automáticamente si es necesario
            all_tool_calls = []
            approval_iterations = 0
            total_approvals_processed = 0

            current_response = response
            while approval_iterations < max_approval_iterations:
                # Extraer contenido de la respuesta actual
                extracted = self._extract_response_content(current_response)

                # DEBUG: Mostrar tool calls encontrados en esta iteración
                if debug_duplicates and extracted["tool_calls"]:
                    print(f"\n🔧 DEBUG - Iteración {approval_iterations}: Encontrados {len(extracted['tool_calls'])} tool calls")
                    for i, tc in enumerate(extracted["tool_calls"]):
                        tc_id = tc.get("id", "unknown")
                        tc_name = tc.get("name", "unknown")
                        print(f"   Tool {i+1}: {tc_name} (ID: {tc_id})")

                # Agregar tool calls encontrados (SOLO si no están duplicados)
                # Verificar duplicados por ID
                existing_ids = {tc.get("id") for tc in all_tool_calls}
                new_tool_calls = [tc for tc in extracted["tool_calls"] if tc.get("id") not in existing_ids]
                
                if new_tool_calls:
                    if debug_duplicates:
                        print(f"   ➕ Agregando {len(new_tool_calls)} tool calls nuevos")
                    all_tool_calls.extend(new_tool_calls)
                else:
                    if debug_duplicates:
                        if extracted["tool_calls"]:
                            print(f"   ⚠️  DUPLICADOS DETECTADOS: {len(extracted['tool_calls'])} tool calls ya existían")
                        else:
                            print(f"   ℹ️  No hay tool calls en esta iteración")

                # Verificar si hay approval requests
                if extracted["approval_requests"]:
                    approval_iterations += 1
                    total_approvals_processed += len(extracted["approval_requests"])

                    # Mostrar approval requests (parámetros que el LLM quiere enviar)
                    print(f"\n🔍 APPROVAL REQUESTS ({len(extracted['approval_requests'])} herramientas):")
                    for i, req in enumerate(extracted["approval_requests"], 1):
                        print(f"   {i}. 🛠️  Herramienta: {req.get('name', 'unknown')}")
                        print(f"      📡 Servidor: {req.get('server_label', 'unknown')}")
                        print(f"      📋 Argumentos: {req.get('arguments', 'N/A')}")

                    # Procesar approvals
                    approval_result = self._handle_approval_requests(
                        extracted["approval_requests"],
                        getattr(current_response, 'id', None)
                    )
                    # Mostrar resultados detallados de la ejecución
                    if approval_result and approval_result["success"]:
                        print(f"\n📊 RESULTADOS DE EJECUCIÓN:")
                        tool_calls = approval_result.get("tool_calls", [])
                        
                        for i, tc in enumerate(tool_calls, 1):
                            status_icon = "✅" if tc.get("success", False) else "❌"
                            tool_name = tc.get("name", "unknown")
                            server = tc.get("server_label", "unknown")
                            
                            print(f"   {i}. {status_icon} {tool_name} ({server})")
                            
                            if tc.get("success", False):
                                output = tc.get("output", "")
                                if output:
                                    # Mostrar solo un preview del output si es muy largo
                                    output_preview = str(output)[:100] + "..." if len(str(output)) > 100 else str(output)
                                    print(f"      📤 Output: {output_preview}")
                                else:
                                    print(f"      📤 Output: (vacío)")
                            else:
                                error = tc.get("error", "Error desconocido")
                                print(f"      ⚠️  Error: {error}")
                        
                        approvals_count = approval_result.get("approvals_processed", 0)
                        successful_count = sum(1 for tc in tool_calls if tc.get("success", False))
                        print(f"\n📈 Resumen: {successful_count}/{len(tool_calls)} herramientas exitosas")
                    else:
                        error_msg = approval_result.get("error", "Error desconocido") if approval_result else "Sin resultado"
                        print(f"❌ Error procesando approvals: {error_msg}")

                    if approval_result and approval_result["success"]:
                        current_response = approval_result["response"]
                        
                        # DEBUG: Mostrar tool calls del approval result
                        approval_tool_calls = approval_result.get("tool_calls", [])
                        if debug_duplicates and approval_tool_calls:
                            print(f"\n🔧 DEBUG - Approval result: {len(approval_tool_calls)} tool calls")
                            for i, tc in enumerate(approval_tool_calls):
                                tc_id = tc.get("id", "unknown")
                                tc_name = tc.get("name", "unknown")
                                print(f"   Approval Tool {i+1}: {tc_name} (ID: {tc_id})")
                        
                        # Agregar tool calls del approval processing (SOLO si no están duplicados)
                        existing_ids = {tc.get("id") for tc in all_tool_calls}
                        new_approval_calls = [tc for tc in approval_tool_calls if tc.get("id") not in existing_ids]
                        
                        if new_approval_calls:
                            if debug_duplicates:
                                print(f"   ➕ Agregando {len(new_approval_calls)} approval tool calls nuevos")
                            all_tool_calls.extend(new_approval_calls)
                        else:
                            if debug_duplicates and approval_tool_calls:
                                print(f"   ⚠️  DUPLICADOS DETECTADOS en approval: {len(approval_tool_calls)} tool calls ya existían")

                        # Si no hay más approvals en esta respuesta, salir del loop
                        if not approval_result["approval_requests"]:
                            break
                    else:
                        # Error procesando approvals
                        break
                else:
                    # No hay más approvals, salir del loop
                    break

            # Extraer contenido final
            final_extracted = self._extract_response_content(current_response)

            # DEBUG: Mostrar tool calls finales
            final_tool_calls = final_extracted.get("tool_calls", [])
            if debug_duplicates and final_tool_calls:
                print(f"\n🔧 DEBUG - Respuesta final: {len(final_tool_calls)} tool calls")
                for i, tc in enumerate(final_tool_calls):
                    tc_id = tc.get("id", "unknown")
                    tc_name = tc.get("name", "unknown")
                    print(f"   Final Tool {i+1}: {tc_name} (ID: {tc_id})")

            # Combinar tool calls finales (SOLO si no están duplicados)
            existing_ids = {tc.get("id") for tc in all_tool_calls}
            new_final_calls = [tc for tc in final_tool_calls if tc.get("id") not in existing_ids]
            
            if new_final_calls:
                if debug_duplicates:
                    print(f"   ➕ Agregando {len(new_final_calls)} tool calls finales nuevos")
                all_tool_calls.extend(new_final_calls)
            else:
                if debug_duplicates and final_tool_calls:
                    print(f"   ⚠️  DUPLICADOS DETECTADOS en respuesta final: {len(final_tool_calls)} tool calls ya existían")

            # Obtener estadísticas de tool calls únicos
            tool_stats = self.get_tool_call_stats(all_tool_calls)
            if debug_duplicates:
                print(f"\n📊 RESUMEN DE DEDUPLICACIÓN: {len(all_tool_calls)} tool calls únicos procesados")

            # Usar el contenido de la respuesta final
            final_content = final_extracted["content"] if final_extracted["content"] else extracted["content"]

            # Print resumen final completo para demo
            print(f"\n🎯 CONVERSACIÓN COMPLETADA")
            print(f"   🔄 Iteraciones de approval: {approval_iterations}")
            print(f"   📊 Total tool calls: {len(all_tool_calls)}")
            
            if tool_stats["total"] > 0:
                print(f"   📈 Éxito: {tool_stats['successful']}/{tool_stats['total']} ({tool_stats['success_rate']}%)")
                
                # Mostrar herramientas que fallaron (si las hay)
                failed_tools = [tc for tc in all_tool_calls if not tc.get("success", True)]
                if failed_tools:
                    print(f"   ⚠️  Herramientas fallidas:")
                    for failed in failed_tools:
                        tool_name = failed.get("name", "unknown")
                        error = failed.get("error", "Error desconocido")
                        print(f"      • {tool_name}: {error}")
            else:
                print(f"   ℹ️  No se ejecutaron herramientas")

            return {
                "success": True,
                "response": current_response,
                "content": final_content,
                "tool_calls": all_tool_calls,
                "tool_stats": tool_stats,
                # Información adicional útil
                "response_id": getattr(current_response, 'id', None),
                "status": getattr(current_response, 'status', None),
                "usage": getattr(current_response, 'usage', None),
                "approval_iterations": approval_iterations,
                "total_approvals_processed": total_approvals_processed,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response": None,
            }

    def get_tool_call_stats(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Obtiene estadísticas de los tool calls ejecutados.

        Args:
            tool_calls: Lista de tool calls

        Returns:
            Estadísticas de tool calls
        """
        if not tool_calls:
            return {"total": 0, "successful": 0, "failed": 0, "success_rate": 0.0}

        total = len(tool_calls)
        successful = sum(1 for call in tool_calls if call.get("success", False))
        failed = total - successful
        success_rate = (successful / total) * 100 if total > 0 else 0.0

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(success_rate, 2)
        }

    def get_failed_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Obtiene solo los tool calls que fallaron.

        Args:
            tool_calls: Lista de tool calls

        Returns:
            Lista de tool calls fallidos
        """
        return [call for call in tool_calls if not call.get("success", True)]

    def clear_tools(self):
        """Limpia todas las tools configuradas."""
        self.tools = []
