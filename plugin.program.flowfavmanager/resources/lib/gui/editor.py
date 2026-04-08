# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import os
import re
import datetime

from resources.lib.utils import (
    get_string, log_debug, log_audit,
    get_window_prop, set_window_prop, clear_window_prop,
    load_templates, save_templates,
    ADDON, PATHS, PROPS
)
from resources.lib.database import FavouritesEngine, FavouriteEntry, save_profile

class FavouritesEditor(xbmcgui.WindowXMLDialog):
    """Lógica principal de la ventana del editor."""

    # IDs de controles del XML - mapeados a modos de vista
    PANEL_IDS = {
        '0': 101,  # Cuadrícula Grande
        '1': 102,  # Cuadrícula Pequeña
        '2': 103,  # Lista Compacta
        '3': 104   # Lista Grande
    }
    ID_BTN_CLOSE = 301
    ID_BTN_RESTORE = 302

    # Constantes de Comportamiento
    MOVE_SWAP = '0'
    MOVE_INSERT_BEFORE = '1'
    MOVE_INSERT_AFTER = '2'
    MOVE_ARROWS = '3'

    def __init__(self, *args, **kwargs):
        super(FavouritesEditor, self).__init__(*args, **kwargs)
        self.engine = FavouritesEngine()
        self.entries = []
        self.list_items = []
        self.drag_origin_index = None
        self.unsaved_changes = False
        self._context_menu_lock = False
        self.panel = None
        self.panel_id = 101  # Default

        # Estado de comportamiento (por defecto: Swap)
        self.move_behavior = self.MOVE_SWAP

        # Multiselección
        self.multiselect_active = False
        self.pending_move = False
        self.selected_indices = set()

    def onInit(self):
        # Determinar qué ID de panel usar según la propiedad view_mode
        view_mode = self.getProperty('view_mode') or '0'
        self.panel_id = self.PANEL_IDS.get(view_mode, 101)

        try:
            self.panel = self.getControl(self.panel_id)
        except Exception as e:
            log_debug("Error control panel: " + str(e))
            # Fallback al panel por defecto
            self.panel = self.getControl(101)

        # Aplicar configuración de UI y comportamiento
        # Recuperar comportamiento si se guardó en memoria
        saved_behavior = xbmcgui.Window(10000).getProperty('FlowFavManager_Behavior')
        if saved_behavior:
            self.move_behavior = saved_behavior

        self._update_behavior_label()

        self.setProperty(PROPS['reorder_method'], self.move_behavior)
        self.setProperty(PROPS['font_size'], ADDON.getSetting('text_scale') or '1')
        self.setProperty(PROPS['thumb_size'], ADDON.getSetting('icon_scale') or '0')

        # Establecer icono del addon para uso en XML
        icon_path = os.path.join(PATHS['addon_path'], 'icon.png')
        self.setProperty('addonIcon', icon_path)

        self.apply_color_settings()

        self.reload_data()

        # Forzar foco inicial y seleccionar primer elemento
        try:
            self.setFocusId(self.panel_id)
            self.panel.selectItem(0)
        except: pass

    def apply_color_settings(self):
        # Default colors (Oscuro/Cyan/Verde)
        bg_color = 'F0101010'
        bg_top = 'FF202020'
        select_color = 'FF12A0C7' # Cyan
        multiselect_color = 'FF00FF00' # Green

        # Colorblind Mode (Alto Contraste)
        is_colorblind = ADDON.getSetting('colorblindMode') == 'true'

        if is_colorblind:
            bg_color = 'FF000000' # Negro Puro
            bg_top = 'FF404040'   # Gris Oscuro
            select_color = 'FFFFFF00' # Amarillo intenso
            multiselect_color = 'FFFF0000' # Rojo intenso

        else:
            # Custom Colors
            try:
                idx_bg = int(ADDON.getSetting('colorBackground') or '0')
                idx_sel = int(ADDON.getSetting('colorSelection') or '0')
                idx_multi = int(ADDON.getSetting('colorMultiselect') or '0')
            except:
                idx_bg, idx_sel, idx_multi = 0, 0, 0

            # Map Backgrounds
            if idx_bg == 1: # Claro (Gris Medio)
                bg_color = 'FF505050'
                bg_top = 'FF707070'
            elif idx_bg == 2: # Gris Neutro
                bg_color = 'FF303030'
                bg_top = 'FF404040'
            elif idx_bg == 3: # Azul Profundo
                bg_color = 'FF050520'
                bg_top = 'FF101040'

            # Map Selection
            sel_colors = [
                'FF12A0C7', # Cyan
                'FF20E020', # Verde
                'FFE0E020', # Amarillo
                'FFE02020', # Rojo
                'FFE08020', # Naranja
                'FFE020E0'  # Violeta
            ]
            if 0 <= idx_sel < len(sel_colors):
                select_color = sel_colors[idx_sel]

            # Map Multiselect
            multi_colors = [
                'FF20E020', # Verde
                'FFE020E0', # Magenta
                'FFE0E020', # Amarillo
                'FFFFFFFF'  # Blanco
            ]
            if 0 <= idx_multi < len(multi_colors):
                multiselect_color = multi_colors[idx_multi]

        # Calculate Faded Selection (base color with 60 alpha)
        # 'FF...' -> '60...'
        select_color_faded = '60' + select_color[2:]

        # --- FONTS ---
        idx_font = ADDON.getSetting('text_scale') or '1'
        font_name = 'font13' # Default (Medium)

        if idx_font == '0': font_name = 'font12' # Small
        elif idx_font == '2': font_name = 'font30' # Large

        # Set Properties -> Skin Strings (Fix for white background when dialogs open)
        # Using Skin.String ensures values are accessible even when the editor loses focus (e.g. keyboard open)
        xbmc.executebuiltin('Skin.SetString(FavEdit_color_bg, %s)' % bg_color)
        xbmc.executebuiltin('Skin.SetString(FavEdit_color_bg_top, %s)' % bg_top)
        xbmc.executebuiltin('Skin.SetString(FavEdit_color_selection, %s)' % select_color)
        xbmc.executebuiltin('Skin.SetString(FavEdit_color_selection_faded, %s)' % select_color_faded)
        xbmc.executebuiltin('Skin.SetString(FavEdit_color_multiselect, %s)' % multiselect_color)
        xbmc.executebuiltin('Skin.SetString(FavEdit_font_name, %s)' % font_name)

    def reload_data(self):
        self.engine.load()
        self.entries = self.engine.entries
        # Guardar copia del estado original para poder restablecer
        self.original_entries = [FavouriteEntry(e.name, e.thumb, e.url) for e in self.entries]

        # Enriquecimiento automático de iconos
        changes = self.engine.enrich_missing_icons()
        if changes > 0:
            # Si hemos recuperado iconos, marcamos como cambios pendientes para que se puedan guardar
            self.unsaved_changes = True
            self.has_pending_auto_icons = True
            # Mostrar notificación discreta
            xbmcgui.Dialog().notification(get_string(30176), get_string(30454).format(changes), xbmcgui.NOTIFICATION_INFO)
        else:
            self.unsaved_changes = False
            self.has_pending_auto_icons = False

        self.refresh_view()

    def reset_to_original(self):
        if xbmcgui.Dialog().yesno(get_string(30167), get_string(30215)):
            self.entries = self.engine.load_original()
            self.unsaved_changes = True
            self.refresh_view()
            xbmcgui.Dialog().notification(get_string(30348), get_string(30441), xbmcgui.NOTIFICATION_INFO, 1000)

    def refresh_view(self):
        self.panel.reset()
        self.list_items = []
        for i, entry in enumerate(self.entries):
            li = xbmcgui.ListItem(label=entry.name)
            li.setArt({'thumb': entry.thumb})
            li.setProperty('index', str(i))

            # Estado visual de seleccion
            if i in self.selected_indices:
                li.setProperty('multiselected', '1')

            self.list_items.append(li)
        if self.unsaved_changes:
            self.setProperty('UnsavedChanges', 'true')
        else:
            self.setProperty('UnsavedChanges', '')

        self.panel.addItems(self.list_items)

        # Restaurar estado del radiobutton
        try:
             self.getControl(308).setSelected(self.multiselect_active)
        except: pass

    def onClick(self, controlId):
        if controlId in self.PANEL_IDS.values():
            self.handle_panel_click()
        elif controlId == 301 or controlId == 3001: # Guardar y Salir
            self.handle_close()
        elif controlId == 302: # Backup/Restaurar (Ahora incluye Guardar Perfil)
            self.handle_restore_menu()
        elif controlId == 303: # Ayuda
            self.show_help()
        elif controlId == 304: # Salir sin guardar
            self.handle_exit_no_save()
        elif controlId == 305: # Añadir... (Menú Add)
            self.handle_add_menu()
        elif controlId == 308: # Entrar Multiselección
            self.toggle_multiselect()

        # Acciones Multiselección
        elif controlId == 350: # Cancelar
            self.cancel_multiselect()
        elif controlId == 351: # Mover Aquí
            self.mass_move_here()
        elif controlId == 352: # Color
            self.mass_color()
        elif controlId == 353: # Eliminar
            self.mass_delete()

        # Botón Comportamiento
        elif controlId == 315:
            self.cycle_move_behavior()

        # Iconos de barra lateral
        elif controlId == 309: # Ordenar
            self.sort_entries()
        elif controlId == 310: # Restablecer
            self.reset_to_original()
        elif controlId == 312: # Auto-Agrupar
            self.auto_group_by_addon()

    def auto_group_by_addon(self):
        """Reordena todos los favoritos agrupándolos por Addon ID/Tipo."""
        if not xbmcgui.Dialog().yesno(get_string(30167), get_string(30135)):
            return

        def get_sort_key(entry):
            # 1. Determinar Grupo (Addon Name o 'ZZ_Sistema')
            # Usamos 'zz' para que sistema salga al final, o '00' para el principio.
            # Usuario pidió "agrupa por tipo de acción o addon".

            group_name = "ZZ_Otros" # Default a final

            # Detectar Plugin
            match = re.search(r'^plugin://([^/]+)/', entry.url)
            if match:
                addon_id = match.group(1)
                try:
                    addon = xbmcaddon.Addon(addon_id)
                    name = addon.getAddonInfo('name')
                    # Limpiar tags de color del nombre del addon si los tiene
                    group_name = self._strip_tags(name).upper()
                except:
                    group_name = addon_id.upper()

            elif 'ActivateWindow' in entry.url:
                group_name = "AAA_VENTANAS KODI" # Para que salgan antes? O al final?
            elif 'RunScript' in entry.url:
                group_name = "AAA_SCRIPTS"
            elif 'StartAndroidActivity' in entry.url:
                group_name = "APPS ANDROID"

            # 2. Retornar tupla para ordenación (Grupo, NombreItem)
            # Strip tags del nombre del item para orden limpio
            item_name = self._strip_tags(entry.name).upper()

            return (group_name, item_name)

        # Ordenar in-place
        self.entries.sort(key=get_sort_key)

        self.unsaved_changes = True
        self.refresh_view()
        self.unsaved_changes = True
        self.refresh_view()
        xbmcgui.Dialog().notification(get_string(30101), get_string(30102), xbmcgui.NOTIFICATION_INFO)

    def show_help(self):
        method = self.move_behavior
        msg = ""

        if method == self.MOVE_SWAP:
            msg = get_string(30104)
        elif method == self.MOVE_INSERT_BEFORE:
            msg = get_string(30105)
        elif method == self.MOVE_INSERT_AFTER:
             msg = get_string(30106)
        elif method == self.MOVE_ARROWS:
             msg = get_string(30107)

        msg += get_string(30108)
        msg += get_string(30109)
        msg += get_string(30110)
        msg += get_string(30111)

        xbmcgui.Dialog().ok(get_string(30103), msg)

    def onAction(self, action):
        action_id = action.getId()

        # Fix Navegación ROBUSTA:
        SIDEBAR_IDS = [9000, 301, 3001, 302, 303, 304, 305, 308, 309, 310, 312, 315, 350, 351, 352, 353]

        # 1. Si pulso IZQUIERDA en sidebar -> Volver al Panel
        if action_id == 1 and self.getFocusId() in SIDEBAR_IDS: # ACTION_MOVE_LEFT
            try:
                self.setFocusId(self.panel_id)
                return
            except: pass


        # Menú Contextual: 117 (ContextMenu), 101 (MouseRightClick)
        if action_id in [117, 101]:
            self.open_context_menu()
        # Atrás/Escape: 92, 10
        elif action_id in [92, 10]:
            self.handle_close()
        # Eliminar: 18 (normalmente tecla X)
        elif action_id == 18:
            self.delete_selected_item()
        # --- Lógica de Movimiento con Flechas ---
        # Solo si el modo ARROWS está activo, hay item seleccionado, Y el foco está en el panel
        elif self.move_behavior == self.MOVE_ARROWS and self.drag_origin_index is not None and self.getFocusId() == self.panel_id:
            if action_id == 3: # UP
                self.move_with_arrows(-1)
            elif action_id == 4: # DOWN
                self.move_with_arrows(1)
            else:
                super(FavouritesEditor, self).onAction(action)
        else:
            super(FavouritesEditor, self).onAction(action)


    def handle_panel_click(self):
        selected_idx = self.panel.getSelectedPosition()
        if selected_idx < 0: return

        # Lógica Multiselección
        if self.multiselect_active:
            # Si estamos esperando destino para mover
            if self.pending_move:
                self.execute_mass_move(selected_idx)
                return

            # Toggle selección
            item = self.panel.getListItem(selected_idx)

            if selected_idx in self.selected_indices:
                self.selected_indices.remove(selected_idx)
                item.setProperty('multiselected', '')
            else:
                self.selected_indices.add(selected_idx)
                item.setProperty('multiselected', '1')

            # NO recargar la vista completa para no perder el scroll
            # Simplemente actualizar el estado visual del item actual
            return

        # Lógica Normal (Arrastrar/Intercambiar)
        # Si estamos en modo ARROWS, siempre tratamos el clic como una "nueva selección"
        # para evitar el swap accidental. Solo permitimos deseleccionar si es el mismo.
        is_arrow_mode = (self.move_behavior == self.MOVE_ARROWS)

        if self.drag_origin_index is None:
            # Iniciar selección
            self.drag_origin_index = selected_idx
            # Actualizar visualmente SIN recargar lista para evitar scroll
            item = self.panel.getListItem(selected_idx)
            item.setProperty('selected', '1')
            self.list_items[selected_idx].setProperty('selected', '1') # Mantener sincro memoria

        else:
            # Finalizar selección o deseleccionar
            if self.drag_origin_index == selected_idx:
                # Deseleccionar (funciona igual en todos los modos)
                # Actualizar visualmente SIN recargar
                item = self.panel.getListItem(selected_idx)
                item.setProperty('selected', '')
                self.list_items[selected_idx].setProperty('selected', '') # Sincro memoria

                self.drag_origin_index = None

            else:
                if is_arrow_mode:
                    # En modo flechas: Cambiar selección

                    # 1. Quitar visualmente del anterior
                    prev_item = self.panel.getListItem(self.drag_origin_index)
                    prev_item.setProperty('selected', '')
                    self.list_items[self.drag_origin_index].setProperty('selected', '')

                    # 2. Poner visualmente al nuevo
                    self.drag_origin_index = selected_idx
                    cursor_item = self.panel.getListItem(selected_idx)
                    cursor_item.setProperty('selected', '1')
                    self.list_items[selected_idx].setProperty('selected', '1')

                else:
                    # Modos normales (Swap/Insert): Ejecutar acción (esto SÍ mueve cosas, requiere refresh)
                    self.execute_reorder(self.drag_origin_index, selected_idx)

    def refresh_view_keep_selection(self, select_idx):
        # Reconstruir items con propiedades actualizadas
        self.list_items = []
        for i, entry in enumerate(self.entries):
            li = xbmcgui.ListItem(label=entry.name)
            li.setArt({'thumb': entry.thumb})
            li.setProperty('index', str(i))

            # Estado multiselección
            if i in self.selected_indices:
                li.setProperty('multiselected', '1')

            # Estado drag normal
            if i == self.drag_origin_index:
                li.setProperty('selected', '1')

            self.list_items.append(li)

        self.panel.reset()
        self.panel.addItems(self.list_items)
        if select_idx >= 0 and select_idx < len(self.list_items):
            self.panel.selectItem(select_idx)

    def execute_reorder(self, idx_a, idx_b):
        # Nueva lógica de movimiento
        # Modos: 0=Swap, 1=Insert Before, 2=Insert After
        mode = self.move_behavior

        # En modo flechas, el clic secundario actúa como SWAP
        if mode == self.MOVE_ARROWS:
            mode = self.MOVE_SWAP

        if mode == self.MOVE_SWAP:
            # SWAP Simple: Intercambio directo SIN refresh (evita scroll)
            self._swap_items(idx_a, idx_b)

            # Swap visual in-place
            item_a = self.panel.getListItem(idx_a)
            item_b = self.panel.getListItem(idx_b)

            lbl_a, lbl_b = item_a.getLabel(), item_b.getLabel()
            art_a, art_b = item_a.getArt('thumb'), item_b.getArt('thumb')

            item_a.setLabel(lbl_b)
            item_a.setArt({'thumb': art_b})
            item_b.setLabel(lbl_a)
            item_b.setArt({'thumb': art_a})

            # Quitar selección del origen, poner en destino
            # IMPORTANTE: Limpiar primero
            item_a.setProperty('selected', '')
            item_b.setProperty('selected', '')

            # En modo SWAP normal, el foco final va a 'idx_b' (el destino del segundo clic)
            # Como hemos intercambiado contenidos:
            # - En idx_b ahora está lo que había en idx_a (el primer seleccionado)
            # Para mantener la lógica visual de "he movido A a la posición de B",
            # seleccionamos B.
            item_b.setProperty('selected', '1') # Seleccionar el destino

            # Sincronizar lista interna 'list_items' SIN mover objetos
            li_a = self.list_items[idx_a]
            li_b = self.list_items[idx_b]

            # Intercambiar contenidos en memoria
            li_a.setLabel(lbl_b)
            li_a.setArt({'thumb': art_b})

            li_b.setLabel(lbl_a)
            li_b.setArt({'thumb': art_a})

            # Limpiar selección en ambos (swap acaba accion)
            li_a.setProperty('selected', '')
            li_b.setProperty('selected', '')

            # Quitar selección visual final (opcional, pero limpio)
            item_b.setProperty('selected', '')

            final_focus = idx_b
            self.drag_origin_index = None
            self.unsaved_changes = True
            self.setProperty('UnsavedChanges', 'true') # Actualizar UI (asterisco botón)

            # Solo mover el foco de Kodi
            try:
                self.panel.selectItem(final_focus)
            except: pass

        else:
            # MOVER (Insert Before/After): Requiere refresh porque cambia estructura
            target = idx_b
            if mode == self.MOVE_INSERT_AFTER:
                target += 1

            final_focus = self._move_item_to(idx_a, target)

            self.drag_origin_index = None
            self.unsaved_changes = True
            self.refresh_view()
            self.panel.selectItem(final_focus)

    def _swap_items(self, i1, i2):
        """Intercambia dos elementos de la lista en su lugar."""
        self.entries[i1], self.entries[i2] = self.entries[i2], self.entries[i1]

    def _move_item_to(self, src_idx, dest_idx):
        """Mueve un elemento de src a dest, ajustando índices."""
        # Validar limites
        dest_idx = max(0, min(dest_idx, len(self.entries)))

        item = self.entries.pop(src_idx)

        # Si el destino está después del origen, el índice de destino 'real'
        # se ha desplazado -1 al hacer el pop.
        if dest_idx > src_idx:
            dest_idx -= 1

        self.entries.insert(dest_idx, item)
        return dest_idx

    def open_context_menu(self):
        if self._context_menu_lock: return
        self._context_menu_lock = True

        idx = self.panel.getSelectedPosition()
        if idx < 0:
            self._context_menu_lock = False
            return

        # Título del menú con el nombre del item
        # Título del menú con el nombre del item
        entry_name = self._strip_tags(self.entries[idx].name)
        header = "[B][COLOR yellow]{}[/COLOR][/B]".format(entry_name)

        opts = [header, get_string(30112), get_string(30113), get_string(30114), get_string(30115), get_string(30116), get_string(30117), get_string(30118), get_string(30119), '« ' + get_string(30430)]

        selection = xbmcgui.Dialog().contextmenu(opts)

        if selection == 0: return # Click en el título, no hacer nada
        elif selection == 1: self.rename_entry(idx)
        elif selection == 2: self.edit_entry_path(idx)
        elif selection == 3: self.change_icon_selected(idx)
        elif selection == 4: self.style_entry_color(idx)
        elif selection == 5: self.style_entry_format(idx)
        elif selection == 6: self.quick_move_entry(idx)
        elif selection == 7: self.duplicate_entry(idx)
        elif selection == 8: self.delete_selected_item()

        xbmc.sleep(200)
        self._context_menu_lock = False

    def _strip_tags(self, text):
        # Función auxiliar para limpiar texto
        text = re.sub(r'\[COLOR [^\]]+\]', '', text)
        text = re.sub(r'\[/COLOR\]', '', text)
        text = re.sub(r'\[/?(B|I|UPPERCASE|LOWERCASE)\]', '', text)
        return text.strip()

    def duplicate_entry(self, idx):
        """Duplica el elemento seleccionado y lo inserta justo después."""
        import time
        original = self.entries[idx]

        # Crear copia con nombre modificado
        new_name = original.name + get_string(30455)

        # Hacer el URL único para que Kodi no lo ignore
        # Kodi usa el URL como identificador único
        unique_id = str(int(time.time() * 1000))[-6:]  # Últimos 6 dígitos del timestamp
        original_url = original.url

        if 'Notification(' in original_url:
            # Para separadores: modificar el mensaje
            # Notification("Sección", "texto") -> Notification("Sección", "texto #123456")
            new_url = original_url.replace(')', ' #{})'.format(unique_id), 1)
        elif original_url.endswith('/'):
            # Para plugin:// URLs: añadir parámetro
            new_url = original_url + '?_dup=' + unique_id
        elif '?' in original_url:
            # Ya tiene parámetros
            new_url = original_url + '&_dup=' + unique_id
        else:
            # Para otros comandos: añadir un comentario invisible al final
            # Esto funciona para la mayoría de comandos de Kodi
            new_url = original_url + ' '  # Espacio trailing hace la URL única

        copy = FavouriteEntry(new_name, original.thumb, new_url)

        # Insertar después del original
        self.entries.insert(idx + 1, copy)

        self.unsaved_changes = True
        self.refresh_view()

        # Seleccionar la copia
        self.panel.selectItem(idx + 1)
        xbmcgui.Dialog().notification(get_string(30121), self._strip_tags(original.name), xbmcgui.NOTIFICATION_INFO, 2000)

    def quick_move_entry(self, idx):
        """Muestra submenú para mover rápidamente el elemento."""
        total = len(self.entries)

        opts = [
            get_string(30123), # Move 1 up
            get_string(30124), # Move 5 up
            get_string(30125), # Move 10 up
            get_string(30126), # To the top
            get_string(30127), # Move 1 down
            get_string(30128), # Move 5 down
            get_string(30129), # Move 10 down
            get_string(30130), # To the bottom
            get_string(30120)  # Cancel
        ]

        sel = xbmcgui.Dialog().select(get_string(30122), opts)
        if sel < 0 or sel == 8: return

        entry = self.entries.pop(idx)
        new_idx = idx

        if sel == 0:   # 1 arriba
            new_idx = max(0, idx - 1)
        elif sel == 1: # 5 arriba
            new_idx = max(0, idx - 5)
        elif sel == 2: # 10 arriba
            new_idx = max(0, idx - 10)
        elif sel == 3: # Al principio
            new_idx = 0
        elif sel == 4: # 1 abajo
            new_idx = min(total - 1, idx + 1)
        elif sel == 5: # 5 abajo
            new_idx = min(total - 1, idx + 5)
        elif sel == 6: # 10 abajo
            new_idx = min(total - 1, idx + 10)
        elif sel == 7: # Al final
            new_idx = total - 1

        self.entries.insert(new_idx, entry)
        self.unsaved_changes = True
        self.refresh_view()
        self.panel.selectItem(new_idx)

    def sort_entries(self):
        """Muestra opciones de ordenación."""
        opts = [
            get_string(30132), # Sort A → Z (correct ID)
            get_string(30133), # Sort Z → A (correct ID)
            get_string(30134), # Reverse order (correct ID)
            get_string(30135), # Group by TYPE/ADDON (correct ID)
            get_string(30120)  # Cancel (correct ID)
        ]

        sel = xbmcgui.Dialog().select(get_string(30131), opts)
        if sel < 0 or sel == 4: return

        if sel == 3: # Agrupar por Addon
            self.auto_group_by_addon()
            return

        if sel == 0: # A-Z
            self.entries.sort(key=lambda e: self._strip_tags(e.name).lower())
            msg = get_string(30136)
        elif sel == 1: # Z-A
            self.entries.sort(key=lambda e: self._strip_tags(e.name).lower(), reverse=True)
            msg = get_string(30137)
        elif sel == 2: # Invertir
            self.entries.reverse()
            msg = get_string(30138)

        self.unsaved_changes = True
        self.refresh_view()
        xbmcgui.Dialog().notification(get_string(30139), msg, xbmcgui.NOTIFICATION_INFO)

    def quick_save_profile(self):
        """Guarda el estado actual como un nuevo perfil."""
        default_name = "Backup " + datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
        kb = xbmc.Keyboard(default_name, get_string(30035))
        kb.doModal()
        if kb.isConfirmed() and kb.getText():
            profile_name = kb.getText()
            if save_profile(profile_name, self.entries):
                xbmcgui.Dialog().notification(get_string(30036), get_string(30141).format(profile_name), xbmcgui.NOTIFICATION_INFO)

    def style_entry_color(self, idx):
        entry = self.entries[idx]
        colors = [
            (get_string(30143), None), (get_string(30144), 'white'), (get_string(30145), 'yellow'),
            (get_string(30146), 'orange'), (get_string(30147), 'red'), (get_string(30148), 'pink'),
            (get_string(30149), 'violet'), (get_string(30150), 'blue'), (get_string(30151), 'cyan'),
            (get_string(30152), 'green'), (get_string(30153), 'lime')
        ]

        sel = xbmcgui.Dialog().select(get_string(30142), [c[0] for c in colors])
        if sel < 0: return

        clean = self._strip_tags(entry.name)
        color_code = colors[sel][1]

        if color_code:
            entry.name = '[COLOR {}]{}[/COLOR]'.format(color_code, clean)
        else:
            entry.name = clean

        self.unsaved_changes = True
        self.refresh_view_keep_selection(idx)

    def style_entry_format(self, idx):
        entry = self.entries[idx]
        formats = [
            (get_string(30155), ''), (get_string(30156), 'B'), (get_string(30157), 'I'),
            (get_string(30158), 'BI'), (get_string(30159), 'UPPERCASE')
        ]

        sel = xbmcgui.Dialog().select(get_string(30154), [f[0] for f in formats])
        if sel < 0: return

        # Preservar color si existe
        color_match = re.search(r'\[COLOR ([^\]]+)\]', entry.name)
        color_tag = color_match.group(1) if color_match else None

        clean = self._strip_tags(entry.name)
        fmt_tag = formats[sel][1]

        if 'B' in fmt_tag: clean = '[B]{}[/B]'.format(clean)
        if 'I' in fmt_tag: clean = '[I]{}[/I]'.format(clean)
        if 'UPPERCASE' in fmt_tag: clean = '[UPPERCASE]{}[/UPPERCASE]'.format(clean)

        if color_tag:
            clean = '[COLOR {}]{}[/COLOR]'.format(color_tag, clean)

        entry.name = clean
        self.unsaved_changes = True
        self.refresh_view_keep_selection(idx)

    def rename_entry(self, idx):
        entry = self.entries[idx]
        kb = xbmc.Keyboard(self._strip_tags(entry.name), get_string(30160))
        kb.doModal()
        if (kb.isConfirmed()):
            new_name = kb.getText()
            if new_name:
                # Mantener color/formato si lo tenía? Mejor reconstruirlo simple o intentar preservar.
                # Simplificación: el usuario renombra el texto base.
                # Si queremos mantener tags, es complejo. Asumimos renombrado total.
                entry.name = new_name
                self.unsaved_changes = True
                self.refresh_view_keep_selection(idx)

    def edit_entry_path(self, idx):
        entry = self.entries[idx]
        kb = xbmc.Keyboard(entry.url, get_string(30161))
        kb.doModal()
        if (kb.isConfirmed()):
            new_path = kb.getText().strip()
            if new_path:
                entry.url = new_path
                self.unsaved_changes = True
                self.refresh_view_keep_selection(idx)
                xbmcgui.Dialog().notification(get_string(30219), get_string(30220), xbmcgui.NOTIFICATION_INFO, 1000)

    def delete_selected_item(self):
        idx = self.panel.getSelectedPosition()
        if idx < 0: return

        entry = self.entries[idx]

        # Detectar si es un separador (por el comando usado al crearlo)
        is_separator = 'Notification("Sección"' in entry.url

        if is_separator:
            # Preguntar qué borrar
            opts = [get_string(30164), get_string(30165), get_string(30120)]
            sel = xbmcgui.Dialog().select(get_string(30166).format(self._strip_tags(entry.name)), opts)

            if sel == -1 or sel == 2: return # Cancelar

            if sel == 0: # Solo separador
                self.entries.pop(idx)

            elif sel == 1: # Separador + Contenido
                # Borramos el separador
                self.entries.pop(idx)
                # Borramos lo siguiente mientras NO sea otro separador
                while idx < len(self.entries):
                    next_url = self.entries[idx].url
                    if 'Notification("Sección"' in next_url:
                        break # Hemos llegado al siguiente separador

                    # Borrar item
                    self.entries.pop(idx)

        else:
            # Borrado normal de un item
            if not xbmcgui.Dialog().yesno(get_string(30167), get_string(30168).format(self._strip_tags(entry.name))):
                return
            self.entries.pop(idx)

        self.unsaved_changes = True

        # Ajustar selección
        new_idx = min(idx, len(self.entries) - 1)
        self.refresh_view()
        if new_idx >= 0:
            self.panel.selectItem(new_idx)

    def handle_close(self):
        # Si no hay cambios, salir directamente
        if not self.unsaved_changes:
            self.close()
            return

        # Si hay cambios, mostrar menú de opciones
        opts = [
            get_string(30170),
            get_string(30171),
            get_string(30172)
        ]

        sel = xbmcgui.Dialog().select(get_string(30169), opts)

        if sel == 0: # Guardar y Salir
            if self._perform_save():
                self.close()

        elif sel == 1: # Guardar y Actualizar
            if self._perform_save():
                self.unsaved_changes = False
                self.close()
                # Recargar perfil para ver cambios SIN pregunta de caché
                xbmc.executebuiltin('LoadProfile(%s)' % xbmc.getInfoLabel('System.ProfileName'))

        elif sel == 2: # Salir sin Guardar
            self.close()

        # Si sel == -1 (Cancelar), no hacemos nada

    def _perform_save(self):
        """Lógica interna de guardado, devuelve True si se guardó ok."""
        # Comprobar si hay cambios automáticos de iconos pendientes
        if getattr(self, 'has_pending_auto_icons', False):
            # Preguntar SOLO si hay iconos automáticos
            q_msg = get_string(30173)
            yes = xbmcgui.Dialog().yesno(get_string(30176), q_msg, yeslabel=get_string(30174), nolabel=get_string(30175))

            if not yes:
                # El usuario NO quiere los iconos automáticos. Revertirlos antes de guardar.
                reverted_count = 0
                for entry in self.entries:
                    if getattr(entry, 'auto_icon', False):
                        entry.thumb = '' # Volver a dejar vacío
                        entry.auto_icon = False
                        reverted_count += 1

                xbmcgui.Dialog().notification(get_string(30176), get_string(30177).format(reverted_count), xbmcgui.NOTIFICATION_INFO)

        # Generar y guardar XML
        xml_out = self.engine.generate_xml(self.entries)
        if self.engine.save(xml_out):
            xbmcgui.Dialog().notification(get_string(30030), get_string(30178), xbmcgui.NOTIFICATION_INFO, 2000)
            log_audit("FAVOURITES_SAVED", f"Lista guardada con {len(self.entries)} items")
            return True
        else:
            xbmcgui.Dialog().notification(get_string(30044), get_string(30179), xbmcgui.NOTIFICATION_ERROR, 3000)
            log_audit("ERROR_SAVING", "Fallo al guardar favourites.xml")
            return False

    def handle_exit_no_save(self):
        # Salir directamente, descartando cambios sin preguntar
        self.close()

    def add_custom_item(self):
        # Cargar plantillas para construir menú dinámico
        templates = load_templates()

        # Menú base
        menu_items = [get_string(30235)]
        menu_actions = ['manual']

        # Mapeo de traducciones para categorías
        MAP_CATEGORIES = {
            "secciones_kodi": 30452,
            "comandos_sistema": 30453
        }

        # Añadir categorías dinámicas desde plantillas
        for cat_key in templates.keys():
            cat_display = get_string(MAP_CATEGORIES[cat_key]) if cat_key in MAP_CATEGORIES else cat_key.replace('_', ' ').title()
            menu_items.append(cat_display)
            menu_actions.append(('template', cat_key))

        # Addons instalados (siempre disponible)
        menu_items.append(get_string(30236))
        menu_actions.append('addons')

        sel = xbmcgui.Dialog().select(get_string(30182), menu_items)
        if sel < 0: return # Cancelado

        name = ""
        path = ""
        thumb = "DefaultAddon.png"

        action = menu_actions[sel]

        if action == 'manual': # MANUAL
            # 1. Nombre
            kb = xbmc.Keyboard('', get_string(30237))
            kb.doModal()
            if not kb.isConfirmed() or not kb.getText(): return
            name = kb.getText()

            # 2. Ruta
            kb = xbmc.Keyboard('', get_string(30105))
            kb.doModal()
            if not kb.isConfirmed(): return
            path = kb.getText().strip()

            # 3. Icono
            browse_icon = xbmcgui.Dialog().browse(1, get_string(30188), 'pictures')
            thumb = browse_icon if browse_icon else 'DefaultAddon.png'

        elif action == 'addons': # ADDONS INSTALADOS
            addons = self.get_installed_addons(None)
            if not addons:
                xbmcgui.Dialog().notification(get_string(30044), get_string(30238), xbmcgui.NOTIFICATION_WARNING)
                return

            addons.sort(key=lambda x: x['name'].lower())

            s = xbmcgui.Dialog().select(get_string(30239), [a['name'] for a in addons])
            if s < 0: return

            sel_addon = addons[s]
            name = sel_addon['name']
            thumb = sel_addon['thumbnail']
            addon_id = sel_addon['addonid']
            addon_type = sel_addon.get('type', 'unknown')
            # SIEMPRE usar RunAddon para máxima compatibilidad
            # Evita problemas con plugin:// que a veces falla
            path = 'RunAddon("{}")'.format(addon_id)

        elif isinstance(action, tuple) and action[0] == 'template':
            # Categoría desde plantillas
            cat_key = action[1]
            items = templates.get(cat_key, [])
            if not items:
                xbmcgui.Dialog().notification(get_string(30087), get_string(30240), xbmcgui.NOTIFICATION_WARNING)
                return

            cat_display = cat_key.replace('_', ' ').title()

            # Mapeo de traducciones para items fijos
            MAP_ITEMS = {
                "Movies": 30400, "TV (PVR)": 30401, "Live TV (PVR)": 30401,
                "TV Guide (EPG)": 30402, "Music": 30403, "Pictures": 30404,
                "Power / Restart Menu": 30405, "Update Library (Video)": 30406,
                "Clean Library (Video)": 30407, "TV Shows": 30417, "Home": 30418,
                "Radio": 30419, "Music Videos": 30420, "Weather": 30421,
                "Settings": 30422, "File Manager": 30423, "System Info": 30424,
                "Event Log": 30425, "Addons (Browser)": 30426,
                "Reload Skin": 30427, "Skin Settings": 30428
            }

            display_names = [get_string(MAP_ITEMS[i['name']]) if i['name'] in MAP_ITEMS else i['name'] for i in items]

            s = xbmcgui.Dialog().select(get_string(30241) + cat_display, display_names)
            if s < 0: return
            name = get_string(MAP_ITEMS[items[s]['name']]) if items[s]['name'] in MAP_ITEMS else items[s]['name']
            path = items[s]['path']
            thumb = items[s]['icon']

        # Validar ruta vacía
        if not path:
             path = 'Notification("{}", "{}", 3000)'.format(get_string(30450), get_string(30449))

        # Crear entrada
        entry = FavouriteEntry(name, thumb, path)
        self.entries.append(entry)

        self.unsaved_changes = True
        self.refresh_view()

        xbmc.sleep(100)
        self.setFocus(self.panel)
        new_idx = len(self.entries) - 1
        self.panel.selectItem(new_idx)
        xbmcgui.Dialog().notification(get_string(30242), name, xbmcgui.NOTIFICATION_INFO, 2000)

    def get_installed_addons(self, type_filter):
        # Tipos que nos interesan
        types_to_check = ["xbmc.python.pluginsource", "xbmc.python.script"]
        all_addons = []

        for t in types_to_check:
            query = {
                "jsonrpc": "2.0",
                "method": "Addons.GetAddons",
                "params": {
                    "properties": ["name", "thumbnail"],
                    "enabled": True,
                    "type": t
                },
                "id": 1
            }
            try:
                json_str = xbmc.executeJSONRPC(json.dumps(query))
                result = json.loads(json_str)
                if 'result' in result and 'addons' in result['result']:
                    # Añadir tipo para luego saber qué comando usar
                    for a in result['result']['addons']:
                        a['type'] = t
                        all_addons.append(a)
            except:
                pass

        return all_addons

    def add_separator(self):
        kb = xbmc.Keyboard('', get_string(30193))
        kb.doModal()
        if not kb.isConfirmed() or not kb.getText(): return
        name = kb.getText()

        # Selección de color
        colors = [
            (get_string(30194), 'gold'), (get_string(30144), 'white'), (get_string(30145), 'yellow'),
            (get_string(30146), 'orange'), (get_string(30147), 'red'), (get_string(30148), 'pink'),
            (get_string(30149), 'violet'), (get_string(30150), 'blue'), (get_string(30151), 'cyan'),
            (get_string(30152), 'green'), (get_string(30153), 'lime'), (get_string(30195), 'gray')
        ]
        sel = xbmcgui.Dialog().select(get_string(30196), [c[0] for c in colors])
        color_code = colors[sel][1] if sel >= 0 else 'gold'

        # Formato: Texto primero, luego raya (tamaño ajustado)
        display_name = "[COLOR {}][B]{}[/B] ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬[/COLOR]".format(color_code, name.upper())

        # Acción dummy
        action = 'Notification("{}", "{}", 1000)'.format(get_string(30449), name)

        # Usamos icono de carpeta por defecto
        entry = FavouriteEntry(display_name, 'DefaultFolder.png', action)
        self.entries.append(entry)

        self.unsaved_changes = True
        self.refresh_view()
        self.panel.selectItem(len(self.entries)-1)

    def toggle_multiselect(self):
        self.multiselect_active = True
        self.selected_indices.clear()
        self.setProperty('multiselect_active', '1') # Activa grouplist B
        self.refresh_view_keep_selection(self.panel.getSelectedPosition())
        # Poner foco en la lista para empezar a seleccionar
        self.setFocus(self.panel)

    def cancel_multiselect(self):
        self.multiselect_active = False
        self.pending_move = False
        self.selected_indices.clear()
        self.clearProperty('multiselect_active') # Vuelve a grouplist A
        self.refresh_view_keep_selection(self.panel.getSelectedPosition())

    def mass_move_here(self):
        if not self.selected_indices:
            xbmcgui.Dialog().notification(get_string(30044), get_string(30197), xbmcgui.NOTIFICATION_WARNING)
            return

        self.pending_move = True
        self.setFocus(self.panel)
        xbmcgui.Dialog().notification(get_string(30167), get_string(30168), xbmcgui.NOTIFICATION_INFO, 3000)

    def execute_mass_move(self, target_idx):
        # Lógica especial para el primer elemento
        insert_after = True
        if target_idx == 0:
            # Preguntar si quiere ponerlo al principio absoluto o debajo del primero
            ret = xbmcgui.Dialog().select(get_string(30167), [get_string(30200), get_string(30201)])
            if ret < 0: return # Cancelado
            if ret == 0: insert_after = False

        # Usamos la lógica de mover
        items_to_move = []
        indices = sorted(list(self.selected_indices))

        # Extraer items
        for i in indices:
            items_to_move.append(self.entries[i])

        # Borrar originales
        for i in reversed(indices):
            self.entries.pop(i)

        # Recalcular destino
        # Calculamos la posición corregida tras los borrados
        deleted_before = sum(1 for x in indices if x < target_idx)

        if insert_after:
            # Insertar DESPUÉS (+1)
            insert_pos = max(0, target_idx - deleted_before + 1)
        else:
            # Insertar ANTES (pos tal cual)
            insert_pos = max(0, target_idx - deleted_before)

        # Insertar
        for item in reversed(items_to_move):
            self.entries.insert(insert_pos, item)

        self.cancel_multiselect()
        self.unsaved_changes = True
        self.refresh_view_keep_selection(insert_pos)
        xbmcgui.Dialog().notification(get_string(30202), get_string(30203).format(len(items_to_move)), xbmcgui.NOTIFICATION_INFO)

    def mass_delete(self):
        if not self.selected_indices: return
        if not xbmcgui.Dialog().yesno(get_string(30167), get_string(30204).format(len(self.selected_indices))):
            return

        indices = sorted(list(self.selected_indices), reverse=True)
        for i in indices:
            self.entries.pop(i)

        self.cancel_multiselect()
        self.unsaved_changes = True
        self.refresh_view()

    def mass_color(self):
        if not self.selected_indices: return

        colors = [
            (get_string(30143), None), (get_string(30144), 'white'), (get_string(30145), 'yellow'),
            (get_string(30146), 'orange'), (get_string(30147), 'red'), (get_string(30148), 'pink'),
            (get_string(30149), 'violet'), (get_string(30150), 'blue'), (get_string(30151), 'cyan'),
            (get_string(30152), 'green'), (get_string(30153), 'lime')
        ]
        sel = xbmcgui.Dialog().select(get_string(30205).format(len(self.selected_indices)), [c[0] for c in colors])
        if sel < 0: return
        color_code = colors[sel][1]

        for i in self.selected_indices:
            entry = self.entries[i]
            clean = self._strip_tags(entry.name)
            if color_code:
                entry.name = '[COLOR {}]{}[/COLOR]'.format(color_code, clean)
            else:
                entry.name = clean

        self.cancel_multiselect()
        self.unsaved_changes = True
        self.refresh_view()

    def change_icon_selected(self, idx=None):
        if idx is None:
            idx = self.panel.getSelectedPosition()

        if idx < 0:
            xbmcgui.Dialog().notification(get_string(30044), get_string(30197), xbmcgui.NOTIFICATION_WARNING, 2000)
            return

        browse_icon = xbmcgui.Dialog().browse(1, get_string(30206), 'pictures')
        if browse_icon:
            self.entries[idx].thumb = browse_icon
            self.unsaved_changes = True
            self.refresh_view_keep_selection(idx)
            xbmcgui.Dialog().notification(get_string(30030), get_string(30208), xbmcgui.NOTIFICATION_INFO, 1500)

    def handle_add_menu(self):
        opts = [get_string(30209), get_string(30210)]
        sel = xbmcgui.Dialog().select(get_string(30211), opts)
        if sel == 0: self.add_custom_item()
        elif sel == 1: self.add_separator()

    def handle_restore_menu(self):
        opts = [get_string(30212), get_string(30213), get_string(30214), get_string(30215)]
        sel = xbmcgui.Dialog().select(get_string(30216), opts)

        if sel == 0: self.quick_save_profile()
        elif sel == 1: self.do_backup_create()
        elif sel == 2: self.do_backup_restore()
        elif sel == 3:
            self.reload_data()
            self.unsaved_changes = False

    def do_backup_create(self):
        default_name = 'favoritos_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        kb = xbmc.Keyboard(default_name, get_string(30383))
        kb.doModal()
        if not kb.isConfirmed() or not kb.getText(): return

        folder = xbmcgui.Dialog().browse(0, get_string(30388), 'files')
        if not folder: return

        path = os.path.join(translatePath(folder), kb.getText() + '.xml')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.engine.generate_xml(self.entries))
            xbmcgui.Dialog().notification(get_string(30347), kb.getText(), xbmcgui.NOTIFICATION_INFO, 3000)
        except Exception as e:
            xbmcgui.Dialog().ok(get_string(30044), str(e))

    def do_backup_restore(self):
        file_path = xbmcgui.Dialog().browse(1, get_string(30389), 'files', '.xml')
        if not file_path: return

        full_path = translatePath(file_path)
        if not os.path.exists(full_path):
            xbmcgui.Dialog().ok(get_string(30044), get_string(30365))
            return

        try:
            tree = ET.parse(full_path)
            root = tree.getroot()
            if root.tag != 'favourites':
                xbmcgui.Dialog().ok(get_string(30044), get_string(30366))
                return

            # Cargar entradas desde backup
            loaded_entries = []
            for child in root:
                if child.tag == 'favourite':
                    loaded_entries.append(FavouriteEntry.from_xml_element(child))

            self.entries = loaded_entries
            self.unsaved_changes = True
            self.refresh_view()
            xbmcgui.Dialog().notification(get_string(30348), get_string(30349), xbmcgui.NOTIFICATION_INFO, 3000)
        except Exception as e:
            xbmcgui.Dialog().ok(get_string(30044), get_string(30367) + "\n" + str(e))

    # --- Helper Methods for Behavior ---
    def _update_behavior_label(self):
        """Actualiza la etiqueta del botón de comportamiento."""
        labels = {
            self.MOVE_SWAP: get_string(30431),
            self.MOVE_INSERT_BEFORE: get_string(30432),
            self.MOVE_INSERT_AFTER: get_string(30433),
            self.MOVE_ARROWS: get_string(30434)
        }
        lbl = labels.get(self.move_behavior, "?")
        self.setProperty('flow_action_label', f"[B]{lbl}[/B]")
        # Guardar globalmente para persistencia en sesión
        xbmcgui.Window(10000).setProperty('FlowFavManager_Behavior', self.move_behavior)
        # Propiedad para lógica interna de la UI
        self.setProperty(PROPS['reorder_method'], self.move_behavior)

    def cycle_move_behavior(self):
        """Rota entre los modos de comportamiento."""
        modes = [self.MOVE_SWAP, self.MOVE_INSERT_BEFORE, self.MOVE_INSERT_AFTER, self.MOVE_ARROWS]
        try:
            current_idx = modes.index(self.move_behavior)
        except:
            current_idx = 0

        next_idx = (current_idx + 1) % len(modes)
        self.move_behavior = modes[next_idx]
        self._update_behavior_label()

        # Notificar al usuario (feedback visual)
        labels = {
            self.MOVE_SWAP: get_string(30431),
            self.MOVE_INSERT_BEFORE: get_string(30432),
            self.MOVE_INSERT_AFTER: get_string(30433),
            self.MOVE_ARROWS: get_string(30434)
        }
        xbmcgui.Dialog().notification(get_string(30350), labels[self.move_behavior], xbmcgui.NOTIFICATION_INFO, 2000)

    def move_with_arrows(self, direction):
        """Mueve el item seleccionado una posición arriba (-1) o abajo (+1)."""
        idx = self.drag_origin_index
        total = len(self.entries)
        new_idx = idx + direction

        # Lógica de Carrusel (Wrap-around infinite loop)
        if new_idx < 0:
            new_idx = total - 1  # De arriba salta al final
        elif new_idx >= total:
            new_idx = 0          # De abajo salta al principio

        # Si la lista tiene 1 elemento, no hacer nada
        if new_idx == idx: return

        # 1. SWAP en DATOS (internamente)
        self._swap_items(idx, new_idx)

        # 2. SWAP VISUAL (In-Place) para evitar saltos de scroll
        # Obtenemos los dos items de la interfaz
        item_a = self.panel.getListItem(idx)
        item_b = self.panel.getListItem(new_idx)

        # Intercambiamos sus etiquetas y arte
        lbl_a = item_a.getLabel()
        art_a = item_a.getArt('thumb')

        lbl_b = item_b.getLabel()
        art_b = item_b.getArt('thumb')

        item_a.setLabel(lbl_b)
        item_a.setArt({'thumb': art_b})

        item_b.setLabel(lbl_a)
        item_b.setArt({'thumb': art_a})

        # 3. Actualizar Selección (el foco visual viaja con el item)
        # IMPORTANTE: Limpiar explícitamente primero para evitar fantasmas
        item_a.setProperty('selected', '')
        item_b.setProperty('selected', '') # Limpiar por si acaso

        # Asignar al nuevo
        item_b.setProperty('selected', '1')

        # Sincronizar lista interna 'list_items' SIN mover objetos, solo datos
        li_a = self.list_items[idx]
        li_b = self.list_items[new_idx]

        # Intercambiar contenidos en memoria
        # Nota: getArt devuelve string o dict, manejar con cuidado pero setArt acepta ambos
        li_a.setLabel(lbl_b)
        li_a.setArt({'thumb': art_b})

        li_b.setLabel(lbl_a)
        li_b.setArt({'thumb': art_a})

        # Actualizar propiedades en la lista espejo
        li_a.setProperty('selected', '')
        li_b.setProperty('selected', '1')

        # Los índices no cambian porque los objetos no se han movido
        # (li_a sigue siendo el objeto en pos 'idx', li_b en 'new_idx')

        # 4. Actualizar estado
        self.drag_origin_index = new_idx
        self.unsaved_changes = True
        self.setProperty('UnsavedChanges', 'true') # Actualizar UI (asterisco botón)

        # 5. Mover el foco de Kodi
        # Al ser un movimiento adyacente y no haber reset, el scroll visual debería ser mínimo o nulo
        try:
            self.panel.selectItem(new_idx)
        except: pass

# --- Punto de Entrada Principal ---

# --- Editor Rápido (sin gráficos) ---
