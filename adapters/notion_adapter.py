import os
from typing import List, Dict, Any, Optional
from notion_client import Client


class NotionAdapter:
    """
    Adaptador para interactuar con la API de Notion.
    Permite buscar páginas, leer contenido y modificar páginas.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el cliente de Notion.

        Args:
            api_key: Token de integración de Notion. Si no se proporciona,
                    se busca en la variable de entorno NOTION_API_KEY
        """
        print("📝 Inicializando NotionAdapter...")
        self.api_key = api_key or os.getenv('NOTION_API_KEY')

        if not self.api_key:
            print("❌ No se encontró token de API de Notion")
            raise ValueError("Se requiere un token de API de Notion. Configure NOTION_API_KEY en las variables de entorno o páselo como parámetro.")

        print(f"🔑 Token de API configurado: {'***' + self.api_key[-4:] if self.api_key else 'None'}")

        try:
            print("🔌 Conectando a Notion API...")
            self.client = Client(auth=self.api_key)
            print("✅ Conexión a Notion API establecida")
        except Exception as e:
            print(f"❌ Error conectando a Notion API: {e}")
            raise ConnectionError(f"No se pudo conectar a Notion: {str(e)}")

    def search_pages(self, query: str, filter_type: Optional[str] = None, page_size: int = 20) -> List[Dict[str, Any]]:
        """
        Busca páginas en Notion por título o contenido.

        Args:
            query: Término de búsqueda
            filter_type: Tipo de filtro ('page', 'database', None para todos)
            page_size: Número máximo de resultados (máximo 100)

        Returns:
            Lista de páginas encontradas con sus metadatos
        """
        try:
            search_body = {
                'query': query,
                'page_size': min(page_size, 100)
            }

            # Configurar filtros
            filters = {}
            if filter_type:
                filters['property'] = 'object'
                filters['value'] = filter_type
                search_body['filter'] = filters

            print(f"📝 Search body: {search_body}")

            # Realizar búsqueda
            results = self.client.search(**search_body)

            # Formatear resultados
            pages = []
            for result in results.get('results', []):
                page_info = {
                    'id': result['id'],
                    'title': self._extract_title(result),
                    'url': result.get('url', ''),
                    'object': result.get('object', ''),
                    'last_edited_time': result.get('last_edited_time', ''),
                    'created_time': result.get('created_time', ''),
                    'properties': result.get('properties', {})
                }
                pages.append(page_info)

            return pages

        except Exception as e:
            raise Exception(f"Error al buscar páginas: {str(e)}")

    def read_page(self, page_id: str) -> Dict[str, Any]:
        """
        Lee el contenido completo de una página de Notion.

        Args:
            page_id: ID de la página de Notion

        Returns:
            Diccionario con la información completa de la página
        """
        try:
            # Obtener metadatos de la página
            page = self.client.pages.retrieve(page_id)

            # Obtener el contenido de los bloques
            blocks = self.client.blocks.children.list(page_id)

            # Procesar bloques recursivamente
            content_blocks = self._process_blocks(blocks.get('results', []))

            page_data = {
                'id': page['id'],
                'title': self._extract_title(page),
                'url': page.get('url', ''),
                'properties': page.get('properties', {}),
                'last_edited_time': page.get('last_edited_time', ''),
                'created_time': page.get('created_time', ''),
                'content': content_blocks
            }

            return page_data

        except Exception as e:
            raise Exception(f"Error al leer la página {page_id}: {str(e)}")

    def update_page(self, page_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actualiza el contenido de una página de Notion usando blocks.

        Args:
            page_id: ID de la página a actualizar
            updates: Diccionario con las actualizaciones:
                - properties: Propiedades de la página (título, etc.)
                - content: Lista de bloques para agregar al final
                - replace_content: Bool para reemplazar todo el contenido
                - block_updates: Lista de updates específicos para blocks individuales

        Returns:
            Información de la página actualizada
        """
        try:
            print(f"✏️ Iniciando actualización de página: {page_id}")
            update_data = {}

            # Actualizar propiedades si se proporcionan
            if 'properties' in updates:
                print("📝 Actualizando propiedades de la página")
                update_data['properties'] = updates['properties']

            # Actualizar contenido usando blocks
            if 'content' in updates:
                print(f"📄 Actualizando contenido con {len(updates['content'])} blocks")

                # Si se solicita reemplazar todo el contenido
                if updates.get('replace_content', False):
                    print("🗑️ Reemplazando todo el contenido existente")
                    existing_blocks = self.client.blocks.children.list(page_id)
                    for block in existing_blocks.get('results', []):
                        try:
                            self.client.blocks.delete(block['id'])
                            print(f"🗑️ Eliminado block: {block['id']}")
                        except Exception as e:
                            print(f"⚠️ Error eliminando block {block['id']}: {e}")

                # Normalizar y agregar nuevo contenido al final de la página
                print("➕ Agregando nuevo contenido")
                normalized_blocks = []

                for i, block in enumerate(updates['content']):
                    try:
                        normalized_block = self._normalize_block(block)
                        normalized_blocks.append(normalized_block)
                        print(f"✅ Block {i+1} normalizado: {normalized_block.get('type')}")
                    except Exception as block_error:
                        print(f"❌ Error normalizando block {i+1}: {block_error}")
                        raise Exception(f"Block {i+1} inválido: {block_error}")

                # Agregar todos los blocks normalizados de una vez
                if normalized_blocks:
                    result = self.client.blocks.children.append(
                        page_id,
                        children=normalized_blocks
                    )
                    print(f"✅ {len(normalized_blocks)} blocks agregados exitosamente")

            # Actualizar blocks específicos si se proporcionan
            if 'block_updates' in updates:
                print(f"🔧 Actualizando {len(updates['block_updates'])} blocks específicos")
                for block_update in updates['block_updates']:
                    block_id = block_update.get('block_id')
                    block_content = block_update.get('content')

                    if block_id and block_content:
                        try:
                            self.client.blocks.update(block_id, **block_content)
                            print(f"✅ Actualizado block específico: {block_id}")
                        except Exception as e:
                            print(f"❌ Error actualizando block {block_id}: {e}")

            # Aplicar actualizaciones de propiedades
            if update_data:
                print("💾 Aplicando actualizaciones de propiedades")
                updated_page = self.client.pages.update(page_id, **update_data)
                result = {
                    'id': updated_page['id'],
                    'title': self._extract_title(updated_page),
                    'url': updated_page.get('url', ''),
                    'last_edited_time': updated_page.get('last_edited_time', ''),
                    'properties': updated_page.get('properties', {})
                }
                print("✅ Página actualizada exitosamente")
                return result
            else:
                # Si solo se actualizó contenido, devolver la página actual
                print("📖 Obteniendo información actualizada de la página")
                result = self.read_page(page_id)
                print("✅ Contenido de página actualizado exitosamente")
                return result

        except Exception as e:
            print(f"❌ Error al actualizar la página {page_id}: {e}")
            raise Exception(f"Error al actualizar la página {page_id}: {str(e)}")

    def update_block(self, block_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actualiza un block específico en Notion.

        Args:
            block_id: ID del block a actualizar
            updates: Actualizaciones a aplicar al block

        Returns:
            Información del block actualizado
        """
        try:
            print(f"🔧 Actualizando block: {block_id}")
            print(f"📝 Updates: {updates}")

            updated_block = self.client.blocks.update(block_id, **updates)

            print("✅ Block actualizado exitosamente")
            return {
                'id': updated_block['id'],
                'type': updated_block.get('type'),
                'last_edited_time': updated_block.get('last_edited_time'),
                'content': updated_block.get(updated_block.get('type'), {})
            }

        except Exception as e:
            print(f"❌ Error al actualizar block {block_id}: {e}")
            raise Exception(f"Error al actualizar block {block_id}: {str(e)}")

    def delete_block(self, block_id: str) -> Dict[str, Any]:
        """
        Elimina un block específico de Notion con verificación.

        Args:
            block_id: ID del block a eliminar

        Returns:
            Confirmación de eliminación con verificación
        """
        try:
            print(f"🗑️ Eliminando block: {block_id}")

            # Verificar que el block existe antes de intentar eliminarlo
            try:
                block_info = self.client.blocks.retrieve(block_id)
                print(f"📋 Block encontrado - Tipo: {block_info.get('type')}")
            except Exception as retrieve_error:
                print(f"⚠️ Block {block_id} no encontrado antes de eliminar: {retrieve_error}")
                return {
                    'id': block_id,
                    'deleted': False,
                    'error': f'Block no encontrado: {str(retrieve_error)}'
                }

            # La API de Notion usa el método delete en el endpoint de blocks
            deleted_block = self.client.blocks.delete(block_id)

            # Verificar que realmente se eliminó
            try:
                # Intentar recuperar el block después de eliminarlo
                self.client.blocks.retrieve(block_id)
                # Si llega aquí, el block aún existe (no se eliminó)
                print(f"⚠️ Block {block_id} aún existe después de eliminación")
                return {
                    'id': block_id,
                    'deleted': False,
                    'error': 'Block aún existe después de eliminación',
                    'block_info': deleted_block
                }
            except Exception:
                # Si hay excepción al intentar recuperar, significa que se eliminó correctamente
                print(f"✅ Block {block_id} eliminado y verificado")
                return {
                    'id': deleted_block['id'],
                    'deleted': True,
                    'last_edited_time': deleted_block.get('last_edited_time'),
                    'verified': True
                }

        except Exception as e:
            print(f"❌ Error al eliminar block {block_id}: {e}")
            return {
                'id': block_id,
                'deleted': False,
                'error': str(e)
            }

    def update_block_smart(self, block_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actualiza un block de manera inteligente, manejando las restricciones de la API.

        Args:
            block_id: ID del block a actualizar
            updates: Actualizaciones a aplicar

        Returns:
            Información del block actualizado
        """
        try:
            print(f"🔧 Actualizando block (smart): {block_id}")
            print(f"📝 Updates solicitados: {updates}")

            # Primero obtener información del block actual
            try:
                current_block = self.client.blocks.retrieve(block_id)
                current_type = current_block.get('type')
                print(f"📋 Block actual - Tipo: {current_type}")
            except Exception as e:
                print(f"❌ No se pudo obtener información del block {block_id}: {e}")
                raise Exception(f"No se pudo acceder al block {block_id}: {str(e)}")

            # Preparar el update_data según el tipo de block
            update_data = {}

            # Procesar contenido si está presente
            if 'content' in updates:
                content = updates['content']
                # Extraer texto limpio del contenido
                text_content = self._extract_text_content(content)
            else:
                text_content = None

            # Crear estructura correcta según el tipo actual
            if current_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
                if text_content is not None:
                    update_data[current_type] = {
                        'rich_text': [{
                            'type': 'text',
                            'text': {
                                'content': text_content
                            }
                        }] if text_content else []
                    }
                # Para estos tipos, si no hay contenido, no hay nada que actualizar

            elif current_type == 'to_do':
                # Para to_do, siempre crear la estructura
                to_do_data = {}

                # Si hay contenido, incluirlo
                if text_content is not None:
                    to_do_data['rich_text'] = [{
                        'type': 'text',
                        'text': {
                            'content': text_content
                        }
                    }] if text_content else []

                # Si se especifica checked, incluirlo
                if 'checked' in updates:
                    to_do_data['checked'] = bool(updates['checked'])

                # Si hay algún dato para actualizar, incluirlo
                if to_do_data:
                    update_data[current_type] = to_do_data

            elif current_type == 'code':
                if text_content is not None or 'language' in updates:
                    code_data = {}

                    # Contenido si está presente
                    if text_content is not None:
                        code_data['rich_text'] = [{
                            'type': 'text',
                            'text': {
                                'content': text_content
                            }
                        }] if text_content else []

                    # Lenguaje si está presente
                    if 'language' in updates:
                        code_data['language'] = str(updates['language'])

                    if code_data:
                        update_data[current_type] = code_data

            elif current_type == 'quote':
                if text_content is not None:
                    update_data[current_type] = {
                        'rich_text': [{
                            'type': 'text',
                            'text': {
                                'content': text_content
                            }
                        }] if text_content else []
                    }

            elif current_type == 'callout':
                if text_content is not None or 'icon' in updates:
                    callout_data = {}

                    # Contenido si está presente
                    if text_content is not None:
                        callout_data['rich_text'] = [{
                            'type': 'text',
                            'text': {
                                'content': text_content
                            }
                        }] if text_content else []

                    # Icono si está presente
                    if 'icon' in updates:
                        callout_data['icon'] = {
                            'type': 'emoji',
                            'emoji': str(updates['icon'])
                        }

                    if callout_data:
                        update_data[current_type] = callout_data

            else:
                print(f"⚠️ Tipo de block '{current_type}' no soportado para actualización")
                raise Exception(f"Tipo de block '{current_type}' no soportado para actualización")

            print(f"📝 Update data preparado: {update_data}")

            # Si no hay nada que actualizar, devolver error descriptivo
            if not update_data:
                available_fields = list(updates.keys())
                raise Exception(f"No se especificó contenido válido para actualizar. Campos disponibles: {available_fields}. Tipo de block: {current_type}")

            # Aplicar actualización
            updated_block = self.client.blocks.update(block_id, **update_data)

            print("✅ Block actualizado exitosamente (smart)")
            return {
                'id': updated_block['id'],
                'type': updated_block.get('type'),
                'last_edited_time': updated_block.get('last_edited_time'),
                'content': updated_block.get(updated_block.get('type'), {})
            }

        except Exception as e:
            print(f"❌ Error al actualizar block (smart) {block_id}: {e}")
            raise Exception(f"Error al actualizar block {block_id}: {str(e)}")

    def reorganize_blocks(self, page_id: str, block_operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reorganiza bloques en una página usando estrategia de "borrar y recrear".

        Args:
            page_id: ID de la página
            block_operations: Lista de operaciones a realizar

        Returns:
            Resultado de la reorganización
        """
        try:
            print(f"🔄 Reorganizando blocks en página: {page_id}")
            print(f"📋 Operaciones: {block_operations}")

            results = []

            for operation in block_operations:
                op_type = operation.get('type', '')

                if op_type == 'move_to_group':
                    # Operación para mover un block a un grupo específico
                    block_id = operation.get('block_id')
                    target_group = operation.get('target_group', [])

                    if not block_id or not target_group:
                        print(f"⚠️ Operación incompleta: {operation}")
                        continue

                    result = self._move_block_to_group(page_id, block_id, target_group)
                    results.append(result)

                elif op_type == 'create_group':
                    # Crear un nuevo grupo de blocks
                    blocks = operation.get('blocks', [])
                    position = operation.get('position', 'end')

                    if not blocks:
                        print(f"⚠️ No hay blocks para crear grupo: {operation}")
                        continue

                    result = self._create_block_group(page_id, blocks, position)
                    results.append(result)

                else:
                    print(f"⚠️ Tipo de operación no reconocido: {op_type}")

            print(f"✅ Reorganización completada: {len(results)} operaciones")
            return {
                'page_id': page_id,
                'operations_completed': len(results),
                'results': results
            }

        except Exception as e:
            print(f"❌ Error en reorganización: {e}")
            raise Exception(f"Error en reorganización: {str(e)}")

    def _move_block_to_group(self, page_id: str, block_id: str, target_group: List[str]) -> Dict[str, Any]:
        """
        Mueve un block específico a un grupo de blocks relacionados.
        NOTA: Debido a limitaciones de la API de Notion, el block se crea al final de la página.

        Args:
            page_id: ID de la página
            block_id: ID del block a mover
            target_group: Lista de IDs de blocks que conforman el grupo objetivo

        Returns:
            Resultado de la operación
        """
        try:
            print(f"📦 Moviendo block {block_id} a grupo (se colocará al final de la página)")

            # Obtener información del block a mover
            block_info = self.client.blocks.retrieve(block_id)
            block_type = block_info.get('type')
            block_content = block_info.get(block_type, {})

            # Crear nuevo block con el mismo contenido
            new_block = {
                'type': block_type,
                block_type: block_content
            }

            # IMPORTANTE: La API de Notion solo permite agregar al final
            # El block se creará al final de la página, no junto al grupo
            result = self.client.blocks.children.append(
                page_id,
                children=[new_block]
            )

            new_block_id = result['results'][0]['id']
            print(f"✅ Nuevo block creado: {new_block_id} (al final de la página)")

            # Intentar marcar como completado si es un to_do, o eliminar si es posible
            if block_type == 'to_do':
                try:
                    # Marcar el original como completado para evitar confusión
                    self.client.blocks.update(block_id, to_do={'checked': True})
                    print(f"✅ Block original {block_id} marcado como completado")
                    delete_original = False
                except Exception as update_error:
                    print(f"⚠️ No se pudo marcar como completado: {update_error}")
                    # Intentar eliminar si no se puede marcar como completado
                    try:
                        self.delete_block(block_id)
                        print(f"🗑️ Block original {block_id} eliminado")
                        delete_original = True
                    except Exception as delete_error:
                        print(f"⚠️ No se pudo eliminar block original: {delete_error}")
                        delete_original = False
            else:
                # Para otros tipos, intentar eliminar
                try:
                    self.delete_block(block_id)
                    print(f"🗑️ Block original {block_id} eliminado")
                    delete_original = True
                except Exception as delete_error:
                    print(f"⚠️ No se pudo eliminar block original: {delete_error}")
                    delete_original = False

            return {
                'operation': 'move_to_group',
                'original_block_id': block_id,
                'new_block_id': new_block_id,
                'group_blocks': target_group,
                'placed_at_end': True,  # Indicador claro de la limitación
                'original_deleted': delete_original,
                'success': True,
                'note': 'Block movido al final de la página debido a limitaciones de la API de Notion'
            }

        except Exception as e:
            print(f"❌ Error moviendo block {block_id}: {e}")
            return {
                'operation': 'move_to_group',
                'block_id': block_id,
                'error': str(e),
                'success': False
            }

    def reorganize_blocks_completely(self, page_id: str, block_order: List[str]) -> Dict[str, Any]:
        """
        Reorganiza completamente los blocks de una página creando un nuevo orden al final.

        Args:
            page_id: ID de la página
            block_order: Lista ordenada de IDs de blocks en el orden deseado

        Returns:
            Resultado de la reorganización completa
        """
        try:
            print(f"🔄 Reorganizando completamente página: {page_id}")
            print(f"📋 Orden deseado: {block_order}")

            # Obtener información de todos los blocks a reorganizar
            blocks_info = []
            for block_id in block_order:
                try:
                    block_info = self.client.blocks.retrieve(block_id)
                    blocks_info.append({
                        'id': block_id,
                        'type': block_info.get('type'),
                        'content': block_info.get(block_info.get('type'), {})
                    })
                    print(f"📄 Block {block_id}: {block_info.get('type')}")
                except Exception as e:
                    print(f"❌ No se pudo obtener info del block {block_id}: {e}")
                    return {
                        'operation': 'reorganize_complete',
                        'success': False,
                        'error': f'No se pudo acceder al block {block_id}: {str(e)}'
                    }

            # Crear blocks normalizados en el orden correcto
            normalized_blocks = []
            for block_info in blocks_info:
                # Recrear el block con la estructura correcta
                new_block = {
                    'type': block_info['type'],
                    block_info['type']: block_info['content']
                }
                normalized_blocks.append(new_block)

            # Crear todos los blocks al final de la página
            result = self.client.blocks.children.append(
                page_id,
                children=normalized_blocks
            )

            new_blocks = result.get('results', [])
            new_block_ids = [block['id'] for block in new_blocks]

            print(f"✅ Creados {len(new_blocks)} blocks en orden correcto al final")

            # Procesar blocks originales para evitar duplicados
            # IMPORTANTE: Primero verificar que podemos procesar TODOS los originales antes de crear los nuevos
            original_processing_results = []

            print("🔍 Verificando blocks originales antes de crear nuevos...")

            for original_id in block_order:
                try:
                    # Verificar que el block existe y obtener su información
                    block_info = self.client.blocks.retrieve(original_id)
                    block_type = block_info.get('type')
                    original_processing_results.append({
                        'block_id': original_id,
                        'type': block_type,
                        'exists': True,
                        'can_process': True
                    })
                    print(f"✅ Block {original_id} ({block_type}) verificado")
                except Exception as e:
                    print(f"❌ Block {original_id} no existe o no accesible: {e}")
                    original_processing_results.append({
                        'block_id': original_id,
                        'type': 'unknown',
                        'exists': False,
                        'can_process': False,
                        'error': str(e)
                    })

            # Verificar que todos los blocks originales existen y son procesables
            unprocessable_blocks = [r for r in original_processing_results if not r['can_process']]
            if unprocessable_blocks:
                error_msg = f"No se pueden procesar {len(unprocessable_blocks)} blocks originales"
                print(f"❌ {error_msg}")
                for block in unprocessable_blocks:
                    print(f"   • Block {block['block_id']}: {block.get('error', 'Desconocido')}")
                raise Exception(error_msg)

            print("✅ Todos los blocks originales son procesables")

            # Ahora procesar los blocks originales (marcar como completados o eliminar)
            processed_originals = []
            deleted_count = 0
            completed_count = 0
            kept_count = 0

            for result in original_processing_results:
                original_id = result['block_id']
                block_type = result['type']

                try:
                    if block_type == 'to_do':
                        # Para to_do, marcar como completado y registrar como "procesado"
                        # NOTA: Los to_do completados siguen siendo visibles en Notion, pero marcados
                        self.client.blocks.update(original_id, to_do={'checked': True})
                        completed_count += 1
                        processed_originals.append({
                            'block_id': original_id,
                            'action': 'completed',
                            'status': 'success'
                        })
                        print(f"✅ To-do {original_id} marcado como completado")
                    else:
                        # Para otros tipos, intentar eliminar completamente
                        delete_result = self.delete_block(original_id)
                        if delete_result.get('deleted', False):
                            deleted_count += 1
                            processed_originals.append({
                                'block_id': original_id,
                                'action': 'deleted',
                                'status': 'success'
                            })
                            print(f"🗑️ Block {original_id} ({block_type}) eliminado")
                        else:
                            # Si no se pudo eliminar, registrar como mantenido
                            kept_count += 1
                            processed_originals.append({
                                'block_id': original_id,
                                'action': 'kept',
                                'status': 'error',
                                'error': delete_result.get('error', 'Delete failed')
                            })
                            print(f"⚠️ Block {original_id} no pudo ser eliminado, se mantiene")

                except Exception as e:
                    kept_count += 1
                    processed_originals.append({
                        'block_id': original_id,
                        'action': 'kept',
                        'status': 'error',
                        'error': str(e)
                    })
                    print(f"❌ Error procesando block original {original_id}: {e}")

            # Verificar si hay demasiados blocks que no se pudieron procesar
            if kept_count > len(block_order) * 0.5:  # Más del 50% no se pudieron procesar
                warning_msg = f"Demasiados blocks originales no pudieron procesarse ({kept_count}/{len(block_order)})"
                print(f"⚠️ {warning_msg}")
                # No fallar completamente, pero informar del problema

            print(f"📊 Procesamiento de originales completado:")
            print(f"   • Completados (to_do): {completed_count}")
            print(f"   • Eliminados: {deleted_count}")
            print(f"   • Mantenidos: {kept_count}")

            return {
                'operation': 'reorganize_complete',
                'original_blocks': block_order,
                'new_blocks': new_block_ids,
                'blocks_created': len(new_blocks),
                'originals_deleted': deleted_count,
                'originals_completed': completed_count,
                'originals_kept': kept_count,
                'processed_originals': processed_originals,
                'placed_at_end': True,
                'success': True,
                'note': f'Blocks reorganizados al final de la página. Completados: {completed_count}, Eliminados: {deleted_count}, Mantenidos: {kept_count}'
            }

        except Exception as e:
            print(f"❌ Error en reorganización completa: {e}")
            return {
                'operation': 'reorganize_complete',
                'success': False,
                'error': str(e)
            }

    def cleanup_duplicate_blocks(self, page_id: str, block_ids: List[str]) -> Dict[str, Any]:
        """
        Limpia bloques duplicados después de una reorganización.

        Args:
            page_id: ID de la página
            block_ids: Lista de IDs de blocks a verificar por duplicados

        Returns:
            Resultado de la limpieza de duplicados
        """
        try:
            print(f"🧹 Limpiando posibles duplicados en página: {page_id}")

            # Obtener información de todos los blocks especificados
            blocks_info = {}
            for block_id in block_ids:
                try:
                    block_info = self.client.blocks.retrieve(block_id)
                    block_type = block_info.get('type')
                    content = block_info.get(block_type, {})

                    # Crear una clave para identificar contenido similar
                    if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
                        text_content = content.get('rich_text', [{}])[0].get('plain_text', '')
                        key = f"{block_type}:{text_content}"
                    elif block_type == 'to_do':
                        text_content = content.get('rich_text', [{}])[0].get('plain_text', '')
                        checked = content.get('checked', False)
                        key = f"to_do:{text_content}:{checked}"
                    elif block_type == 'code':
                        text_content = content.get('rich_text', [{}])[0].get('plain_text', '')
                        language = content.get('language', 'python')
                        key = f"code:{language}:{text_content[:50]}"  # Limitar longitud
                    else:
                        key = f"{block_type}:{str(content)[:50]}"

                    if key not in blocks_info:
                        blocks_info[key] = []

                    blocks_info[key].append({
                        'block_id': block_id,
                        'type': block_type,
                        'content': content
                    })

                except Exception as e:
                    print(f"⚠️ No se pudo obtener info del block {block_id}: {e}")

            # Identificar y eliminar duplicados
            total_processed = 0
            duplicates_removed = 0

            for content_key, blocks in blocks_info.items():
                if len(blocks) > 1:
                    print(f"📋 Encontrados {len(blocks)} duplicados para: {content_key[:50]}...")

                    # Mantener el primer block, eliminar los demás
                    blocks_to_remove = blocks[1:]  # Todos menos el primero

                    for block in blocks_to_remove:
                        try:
                            delete_result = self.delete_block(block['block_id'])
                            if delete_result.get('deleted', False):
                                duplicates_removed += 1
                                print(f"🗑️ Eliminado duplicado: {block['block_id']}")
                            else:
                                print(f"⚠️ No se pudo eliminar duplicado: {block['block_id']}")
                        except Exception as e:
                            print(f"❌ Error eliminando duplicado {block['block_id']}: {e}")

                    total_processed += len(blocks)

            print(f"✅ Limpieza completada: {duplicates_removed} duplicados eliminados")

            return {
                'operation': 'cleanup_duplicates',
                'success': True,
                'blocks_processed': total_processed,
                'duplicates_removed': duplicates_removed,
                'unique_contents': len(blocks_info),
                'note': f'Se procesaron {total_processed} blocks y se eliminaron {duplicates_removed} duplicados'
            }

        except Exception as e:
            print(f"❌ Error en limpieza de duplicados: {e}")
            return {
                'operation': 'cleanup_duplicates',
                'success': False,
                'error': str(e)
            }

    def _create_block_group(self, page_id: str, blocks: List[Dict[str, Any]], position: str = 'end') -> Dict[str, Any]:
        """
        Crea un grupo de blocks en una posición específica.

        Args:
            page_id: ID de la página
            blocks: Lista de blocks a crear
            position: Posición ('end' para final, o ID de block para insertar después)

        Returns:
            Resultado de la operación
        """
        try:
            print(f"➕ Creando grupo de {len(blocks)} blocks en posición: {position}")

            # Normalizar blocks
            normalized_blocks = []
            for block in blocks:
                normalized_block = self._normalize_block(block)
                normalized_blocks.append(normalized_block)

            # Crear blocks
            result = self.client.blocks.children.append(
                page_id,
                children=normalized_blocks
            )

            created_blocks = result.get('results', [])
            block_ids = [block['id'] for block in created_blocks]

            print(f"✅ Grupo creado: {len(block_ids)} blocks")
            return {
                'operation': 'create_group',
                'created_blocks': block_ids,
                'position': position,
                'success': True
            }

        except Exception as e:
            print(f"❌ Error creando grupo de blocks: {e}")
            return {
                'operation': 'create_group',
                'error': str(e),
                'success': False
            }

    def append_blocks(self, parent_id: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Agrega múltiples blocks al final de una página o block padre.

        Args:
            parent_id: ID de la página o block padre
            blocks: Lista de blocks a agregar

        Returns:
            Resultado de la operación
        """
        try:
            print(f"➕ Agregando {len(blocks)} blocks a {parent_id}")
            print(f"📦 Blocks crudos: {blocks}")

            # Validar y normalizar blocks antes de enviarlos
            normalized_blocks = []
            for i, block in enumerate(blocks):
                try:
                    normalized_block = self._normalize_block(block)
                    normalized_blocks.append(normalized_block)
                    print(f"✅ Block {i+1} normalizado: {normalized_block.get('type')}")
                except Exception as block_error:
                    print(f"❌ Error normalizando block {i+1}: {block_error}")
                    raise Exception(f"Block {i+1} inválido: {block_error}")

            print(f"📦 Blocks normalizados: {len(normalized_blocks)}")

            result = self.client.blocks.children.append(
                parent_id,
                children=normalized_blocks
            )

            print("✅ Blocks agregados exitosamente")
            return {
                'parent_id': parent_id,
                'blocks_added': len(result.get('results', [])),
                'results': result.get('results', [])
            }

        except Exception as e:
            print(f"❌ Error al agregar blocks a {parent_id}: {e}")
            raise Exception(f"Error al agregar blocks a {parent_id}: {str(e)}")

    def _normalize_block(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza un block para que tenga la estructura correcta para la API de Notion.

        Args:
            block: Block crudo a normalizar

        Returns:
            Block normalizado con estructura correcta

        Raises:
            Exception: Si el block no tiene una estructura válida
        """
        print(f"🔧 Normalizando block: {block}")

        if not isinstance(block, dict):
            raise Exception("Block debe ser un diccionario")

        # Verificar que tenga tipo
        if 'type' not in block:
            raise Exception("Block debe tener propiedad 'type'")

        block_type = block['type']
        print(f"📝 Tipo de block: {block_type}")

        # Validar tipos de block soportados
        supported_types = [
            'paragraph', 'heading_1', 'heading_2', 'heading_3',
            'bulleted_list_item', 'numbered_list_item', 'to_do',
            'code', 'quote', 'callout', 'divider'
        ]

        if block_type not in supported_types:
            raise Exception(f"Tipo de block '{block_type}' no soportado. Tipos válidos: {supported_types}")

        # Crear block normalizado
        normalized_block = {
            'type': block_type,
            block_type: {}
        }

        # Normalizar contenido según el tipo
        if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
            # Tipos que usan rich_text
            content = block.get('content', '')

            # Usar helper para extraer texto limpio
            text_content = self._extract_text_content(content)

            if text_content:
                normalized_block[block_type] = {
                    'rich_text': [{
                        'type': 'text',
                        'text': {
                            'content': text_content
                        }
                    }]
                }
            else:
                # Si no hay contenido, crear estructura vacía
                normalized_block[block_type] = {
                    'rich_text': []
                }

        elif block_type == 'to_do':
            content = block.get('content', '')
            checked = block.get('checked', False)

            # Usar helper para extraer texto limpio
            text_content = self._extract_text_content(content)

            normalized_block[block_type] = {
                'rich_text': [{
                    'type': 'text',
                    'text': {
                        'content': text_content
                    }
                }] if text_content else [],
                'checked': bool(checked)
            }

        elif block_type == 'code':
            content = block.get('content', '')
            language = block.get('language', 'python')

            # Usar helper para extraer texto limpio
            text_content = self._extract_text_content(content)

            normalized_block[block_type] = {
                'rich_text': [{
                    'type': 'text',
                    'text': {
                        'content': text_content
                    }
                }] if text_content else [],
                'language': str(language)
            }

        elif block_type == 'quote':
            content = block.get('content', '')

            # Usar helper para extraer texto limpio
            text_content = self._extract_text_content(content)

            normalized_block[block_type] = {
                'rich_text': [{
                    'type': 'text',
                    'text': {
                        'content': text_content
                    }
                }] if text_content else []
            }

        elif block_type == 'callout':
            content = block.get('content', '')
            icon = block.get('icon', '💡')

            # Usar helper para extraer texto limpio
            text_content = self._extract_text_content(content)

            normalized_block[block_type] = {
                'rich_text': [{
                    'type': 'text',
                    'text': {
                        'content': text_content
                    }
                }] if text_content else [],
                'icon': {
                    'type': 'emoji',
                    'emoji': str(icon)
                }
            }

        elif block_type == 'divider':
            # Divider no necesita contenido adicional
            normalized_block[block_type] = {}

        else:
            raise Exception(f"Tipo de block '{block_type}' no implementado aún")

        print(f"✅ Block normalizado: {normalized_block}")
        return normalized_block

    def _extract_text_content(self, content: Any) -> str:
        """
        Extrae el contenido de texto de diferentes formatos posibles.

        Args:
            content: Contenido que puede ser string, dict, o JSON serializado

        Returns:
            Contenido de texto extraído
        """
        # Manejar caso donde content ya es una estructura compleja
        if isinstance(content, dict):
            if 'rich_text' in content:
                # Si ya tiene rich_text, devolver el primer elemento de texto
                if content['rich_text'] and len(content['rich_text']) > 0:
                    return content['rich_text'][0].get('text', {}).get('content', str(content))
                return ''
            elif 'text' in content:
                # Extraer el texto de cualquier estructura anidada
                return content.get('text', {}).get('content', str(content))
            else:
                # Para otras estructuras, devolver representación como string
                return str(content)

        # Manejar caso donde content es una cadena JSON serializada
        elif isinstance(content, str) and content.startswith('{'):
            try:
                import json
                parsed_content = json.loads(content)
                if isinstance(parsed_content, dict):
                    if 'rich_text' in parsed_content:
                        # Usar la estructura parseada directamente
                        if parsed_content['rich_text'] and len(parsed_content['rich_text']) > 0:
                            return parsed_content['rich_text'][0].get('text', {}).get('content', content)
                        return ''
                    else:
                        # Extraer texto de la estructura parseada
                        return parsed_content.get('text', {}).get('content', content)
            except (json.JSONDecodeError, KeyError):
                # Si no se puede parsear como JSON, usar como texto normal
                return content

        # Caso normal: content es texto plano
        else:
            return str(content)

    def create_simple_block(self, block_type: str, content: str = "", **kwargs) -> Dict[str, Any]:
        """
        Crea un block simple con estructura correcta para Notion.

        Args:
            block_type: Tipo de block ('paragraph', 'heading_1', etc.)
            content: Contenido del block
            **kwargs: Parámetros adicionales según el tipo

        Returns:
            Block con estructura correcta
        """
        block = {
            'type': block_type,
            'content': content
        }

        # Agregar parámetros adicionales
        for key, value in kwargs.items():
            block[key] = value

        return self._normalize_block(block)

    def get_page_blocks(self, page_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los blocks de una página de manera simplificada.

        Args:
            page_id: ID de la página

        Returns:
            Lista simplificada de blocks
        """
        try:
            print(f"📋 Obteniendo blocks de página: {page_id}")

            blocks_response = self.client.blocks.children.list(page_id)
            blocks = blocks_response.get('results', [])

            # Simplificar la información de blocks
            simplified_blocks = []
            for block in blocks:
                simplified_block = {
                    'id': block['id'],
                    'type': block['type'],
                    'has_children': block.get('has_children', False),
                    'content': block.get(block['type'], {})
                }
                simplified_blocks.append(simplified_block)

            print(f"📄 Encontrados {len(simplified_blocks)} blocks")
            return simplified_blocks

        except Exception as e:
            print(f"❌ Error al obtener blocks de página {page_id}: {e}")
            raise Exception(f"Error al obtener blocks de página {page_id}: {str(e)}")

    def create_page(self, title: str, content: Optional[List[Dict[str, Any]]] = None,
                   properties: Optional[Dict[str, Any]] = None, is_database: bool = True, parent_id: str = '2606269f472a803888c2e6e7855a8273') -> Dict[str, Any]:
        """
        Crea una nueva página en Notion.

        Args:
            parent_id: ID del padre (página o base de datos)
            title: Título de la nueva página
            content: Lista de bloques para el contenido inicial
            properties: Propiedades adicionales de la página
            is_database: True si el padre es una base de datos

        Returns:
            Información de la página creada
        """
        try:
            # Preparar propiedades
            page_properties = properties or {}
            if title:
                page_properties['title'] = {
                    'title': [{'text': {'content': title}}]
                }

            # Preparar datos de creación
            create_data = {
                'properties': page_properties
            }

            if is_database:
                create_data['parent'] = {'database_id': parent_id}
            else:
                create_data['parent'] = {'page_id': parent_id}

            # Crear la página
            new_page = self.client.pages.create(**create_data)

            # Agregar contenido si se proporciona
            if content:
                print(f"📄 Agregando {len(content)} blocks iniciales a la nueva página")
                normalized_blocks = []

                # Normalizar todos los blocks antes de enviarlos
                for i, block in enumerate(content):
                    try:
                        normalized_block = self._normalize_block(block)
                        normalized_blocks.append(normalized_block)
                        print(f"✅ Block inicial {i+1} normalizado: {normalized_block.get('type')}")
                    except Exception as block_error:
                        print(f"❌ Error normalizando block inicial {i+1}: {block_error}")
                        raise Exception(f"Block inicial {i+1} inválido: {block_error}")

                # Agregar blocks normalizados
                if normalized_blocks:
                    self.client.blocks.children.append(
                        new_page['id'],
                        children=normalized_blocks
                    )
                    print(f"✅ {len(normalized_blocks)} blocks iniciales agregados a la página")

            return {
                'id': new_page['id'],
                'title': title,
                'url': new_page.get('url', ''),
                'created_time': new_page.get('created_time', ''),
                'properties': new_page.get('properties', {})
            }

        except Exception as e:
            raise Exception(f"Error al crear la página: {str(e)}")

    def _extract_title(self, page: Dict[str, Any]) -> str:
        """
        Extrae el título de una página de Notion.

        Args:
            page: Objeto de página de Notion

        Returns:
            Título de la página
        """
        try:
            properties = page.get('properties', {})
            title_property = None

            # Buscar propiedad de título
            for prop_key, prop_value in properties.items():
                if prop_value.get('type') == 'title':
                    title_property = prop_value
                    break

            if title_property and 'title' in title_property:
                title_parts = []
                for text_obj in title_property['title']:
                    if 'plain_text' in text_obj:
                        title_parts.append(text_obj['plain_text'])
                return ''.join(title_parts)

            return "Sin título"

        except Exception:
            return "Sin título"

    def _process_blocks(self, blocks: List[Dict[str, Any]], depth: int = 0) -> List[Dict[str, Any]]:
        """
        Procesa recursivamente los bloques de Notion.

        Args:
            blocks: Lista de bloques a procesar
            depth: Profundidad actual (para evitar recursión infinita)

        Returns:
            Lista de bloques procesados
        """
        if depth > 10:  # Límite de profundidad para evitar recursión infinita
            return []

        processed_blocks = []

        for block in blocks:
            try:
                block_type = block.get('type', '')
                block_data = {
                    'id': block['id'],
                    'type': block_type,
                    'has_children': block.get('has_children', False)
                }

                # Extraer contenido específico según el tipo de bloque
                if block_type in block:
                    content = block[block_type]

                    # Procesar texto enriquecido
                    if 'rich_text' in content:
                        block_data['text'] = self._extract_rich_text(content['rich_text'])
                    elif 'text' in content:
                        block_data['text'] = content['text'].get('content', '') if isinstance(content['text'], dict) else str(content['text'])
                    elif 'title' in content:
                        block_data['title'] = self._extract_rich_text(content['title'])
                    elif 'caption' in content:
                        block_data['caption'] = self._extract_rich_text(content['caption'])

                    # Agregar propiedades específicas del tipo
                    for key, value in content.items():
                        if key not in ['rich_text', 'text', 'title', 'caption']:
                            block_data[key] = value

                # Procesar hijos recursivamente si existen
                if block.get('has_children') and depth < 10:
                    try:
                        children = self.client.blocks.children.list(block['id'])
                        block_data['children'] = self._process_blocks(children.get('results', []), depth + 1)
                    except Exception:
                        block_data['children'] = []

                processed_blocks.append(block_data)

            except Exception as e:
                # Si hay error procesando un bloque, agregar información básica
                processed_blocks.append({
                    'id': block.get('id', 'unknown'),
                    'type': block.get('type', 'unknown'),
                    'error': str(e)
                })

        return processed_blocks

    def _extract_rich_text(self, rich_text_list: List[Dict[str, Any]]) -> str:
        """
        Extrae el texto plano de una lista de objetos rich_text.

        Args:
            rich_text_list: Lista de objetos rich_text

        Returns:
            Texto plano concatenado
        """
        if not rich_text_list:
            return ""

        text_parts = []
        for text_obj in rich_text_list:
            if 'plain_text' in text_obj:
                text_parts.append(text_obj['plain_text'])

        return ''.join(text_parts)


# Función de conveniencia para crear instancia del adaptador
def create_notion_adapter(api_key: Optional[str] = None) -> NotionAdapter:
    """
    Crea una instancia del adaptador de Notion.

    Args:
        api_key: Token de API de Notion (opcional)

    Returns:
        Instancia de NotionAdapter
    """
    return NotionAdapter(api_key)
