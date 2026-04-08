# -*- coding: utf-8 -*-
import sys
import os
import shutil
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
import xbmcaddon
import xml.etree.ElementTree as ET
import datetime
import re
import json
# Importar módulo de base de datos extraído
from resources.lib.database import (
    FavouriteEntry,
    FavouritesEngine,
    get_profiles,
    save_profile,
    load_profile,
    delete_profile
)
from resources.lib.utils import (
    get_string, log_debug, log_audit,
    get_window_prop, set_window_prop, clear_window_prop,
    load_templates, save_templates,
    ADDON, PATHS, translatePath, AUDIT_FILE
)

PLUGIN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else -1
# Usar base_url fija para evitar acumulaciones en la ruta al navegar
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""
if not BASE_URL.endswith('/'): BASE_URL += '/'
PLUGIN_URL = BASE_URL # Alias para compatibilidad con código existente

if not os.path.exists(PATHS['profiles']):
    try:
        os.makedirs(PATHS['profiles'])
    except: pass

# --- SISTEMA DE SEGURIDAD ---
SECURITY_FILE = translatePath('special://profile/addon_data/plugin.program.flowfavmanager/security.json')
RESET_FILE = translatePath('special://profile/addon_data/plugin.program.flowfavmanager/reset_pass.txt')
SESSION_UNLOCKED_PROP = 'FlowFavManager_Unlocked'

def load_security_config():
    """Carga la configuración de seguridad."""
    try:
        if os.path.exists(SECURITY_FILE):
            with open(SECURITY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'enabled': False, 'pin': '', 'question': '', 'answer': ''}

def save_security_config(config):
    """Guarda la configuración de seguridad."""
    try:
        # Asegurar que exista el directorio
        dir_path = os.path.dirname(SECURITY_FILE)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(SECURITY_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        log_debug("Error guardando seguridad: " + str(e))
        return False

def check_reset_file():
    """Comprueba si existe el archivo de reseteo de emergencia."""
    if os.path.exists(RESET_FILE):
        try:
            os.remove(RESET_FILE)
            # Desactivar seguridad
            config = load_security_config()
            config['enabled'] = False
            config['pin'] = ''
            save_security_config(config)
            xbmcgui.Dialog().ok(get_string(30226),
                get_string(30227))
            log_audit("AUTH_RESET_FILE", "Seguridad reseteada mediante archivo de emergencia")
            return True
        except:
            pass
    return False

def is_session_unlocked():
    """Comprueba si ya hemos desbloqueado en esta sesión de Kodi."""
    # Usamos Window(10000) = Home, que persiste durante toda la sesión
    return xbmcgui.Window(10000).getProperty(SESSION_UNLOCKED_PROP) == 'true'

def set_session_unlocked():
    """Marca la sesión como desbloqueada."""
    xbmcgui.Window(10000).setProperty(SESSION_UNLOCKED_PROP, 'true')

def check_security_gate():
    """
    Comprueba si hay protección activa y pide el PIN.
    Devuelve True si puede continuar, False si debe bloquearse.
    """
    # 1. Comprobar archivo de reseteo de emergencia
    if check_reset_file():
        return True # Seguridad reseteada, dejar pasar

    # 2. Cargar config
    config = load_security_config()

    # 3. Si no está activado, dejar pasar
    if not config.get('enabled', False):
        return True

    # 4. Si ya desbloqueamos esta sesión, dejar pasar
    if is_session_unlocked():
        return True

    # 5. Pedir PIN
    pin_correcto = config.get('pin', '')
    intentos = 3

    while intentos > 0:
        kb = xbmc.Keyboard('', get_string(30048).format(intentos))
        kb.setHiddenInput(True) # Ocultar caracteres
        kb.doModal()

        if not kb.isConfirmed():
            return False # Canceló, bloquear

        if kb.getText() == pin_correcto:
            set_session_unlocked()
            return True # PIN correcto

        intentos -= 1
        if intentos > 0:
            xbmcgui.Dialog().notification(get_string(30047), get_string(30048).format(intentos), xbmcgui.NOTIFICATION_WARNING)
            log_audit("AUTH_FAIL_PIN", f"PIN incorrecto. Intentos restantes: {intentos}")

    # 6. Agotados los intentos, ofrecer recuperación
    recovery_opts = [get_string(30050), get_string(30051)]
    sel = xbmcgui.Dialog().select(get_string(30049), recovery_opts)

    if sel == 0: # Pregunta de seguridad
        question = config.get('question', get_string(30052))
        answer_correct = config.get('answer', '').lower().strip()

        if not answer_correct:
            xbmcgui.Dialog().ok(get_string(30044), get_string(30053))
            return False

        kb = xbmc.Keyboard('', question)
        kb.doModal()

        if kb.isConfirmed() and kb.getText().lower().strip() == answer_correct:
            xbmcgui.Dialog().ok(get_string(30054), get_string(30055))
            config['enabled'] = False
            save_security_config(config)
            set_session_unlocked()
            return True
        else:
            xbmcgui.Dialog().ok(get_string(30056), get_string(30057) + os.path.dirname(SECURITY_FILE))
            log_audit("AUTH_FAIL_QUESTION", "Respuesta a pregunta de seguridad incorrecta")
            return False

            return False

    return False # Canceló

def build_list_item(entry):
    """Crea un ListItem optimizado y resuelve la URL de destino."""
    import urllib.parse

    li = xbmcgui.ListItem(label=entry.name)
    li.setArt({'thumb': entry.thumb, 'icon': entry.thumb})

    url = entry.url if entry.url else ""
    target_url = ""
    is_folder = False

    # 1. Rutas directas de Plugin (plugin://...)
    if url.lower().startswith('plugin://'):
        target_url = url
        is_folder = True

    # 2. Comandos RunAddon("id") -> Convertir a ruta navegable plugin://id/
    elif url.startswith('RunAddon('):
        match = re.search(r'RunAddon\("?([^")\s]+)"?\)', url)
        if match:
            addon_id = match.group(1)
            target_url = "plugin://{}/".format(addon_id)
            is_folder = True
        else:
            target_url = BASE_URL + 'execute?cmd=' + urllib.parse.quote(url)
            is_folder = False

    # 3. URLs script:// -> Convertir a RunAddon y ejecutar
    elif url.lower().startswith('script://'):
        match = re.match(r'^script://([^/]+)/?', url, re.IGNORECASE)
        if match:
            addon_id = match.group(1)
            cmd = f'RunAddon("{addon_id}")'
            target_url = BASE_URL + 'execute?cmd=' + urllib.parse.quote(cmd)
            is_folder = False
        else:
            target_url = BASE_URL + 'execute?cmd=' + urllib.parse.quote(url)
            is_folder = False

    # 4. Otros comandos (ActivateWindow, etc.) -> Puente de ejecución
    else:
        target_url = BASE_URL + 'execute?cmd=' + urllib.parse.quote(url)
        is_folder = False

        # Excepción visual: Notificaciones (separadores)
        if 'Notification' in url:
             li.setProperty('IsPlayable', 'false')

    # FIX: Recursividad. Si apunta a este mismo addon, forzar Container.Update
    if 'plugin.program.flowfavs' in target_url and is_folder:
        cmd = f'Container.Update({target_url})'
        target_url = BASE_URL + 'execute?cmd=' + urllib.parse.quote(cmd)
        is_folder = False

    # Mejoras para Widgets (Metadata básica)
    li.setInfo('video', {'title': entry.name, 'plot': url})

    return li, target_url, is_folder

def run_security_menu():
    """Menú para gestionar la seguridad del addon."""
    while True:
        config = load_security_config()
        is_enabled = config.get('enabled', False)
        has_pin = bool(config.get('pin', ''))
        has_question = bool(config.get('answer', ''))

        status = f"[COLOR lime]{get_string(30059)}[/COLOR]" if is_enabled else f"[COLOR gray]{get_string(30060)}[/COLOR]"

        opts = [
            get_string(30061).format(status),
            get_string(30062) if has_pin else get_string(30063),
            get_string(30064),
            get_string(30065) if not is_enabled else get_string(30066),
            f"[COLOR gray]{get_string(30067)}[/COLOR]"
        ]

        sel = xbmcgui.Dialog().select(get_string(30058), opts)

        if sel == -1 or sel == 4: return # Volver

        if sel == 0: # Info
            info_msg = get_string(30069)
            if is_enabled:
                info_msg += f"{get_string(30061).format(get_string(30059))}\n"
                info_msg += get_string(30070).format(get_string(30071) if has_question else get_string(30072)) + "\n\n"
                info_msg += get_string(30073)
                info_msg += os.path.dirname(SECURITY_FILE)
            else:
                info_msg += get_string(30061).format(get_string(30060))
            xbmcgui.Dialog().textviewer(get_string(30068), info_msg)

        elif sel == 1: # Cambiar/Establecer PIN
            kb = xbmc.Keyboard('', get_string(30074))
            kb.setHiddenInput(True)
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                new_pin = kb.getText()
                # Confirmar
                kb2 = xbmc.Keyboard('', get_string(30075))
                kb2.setHiddenInput(True)
                kb2.doModal()
                if kb2.isConfirmed() and kb2.getText() == new_pin:
                    config['pin'] = new_pin
                    save_security_config(config)
                    xbmcgui.Dialog().notification(get_string(30076), get_string(30077), xbmcgui.NOTIFICATION_INFO)
                else:
                    xbmcgui.Dialog().notification(get_string(30044), get_string(30078), xbmcgui.NOTIFICATION_ERROR)

        elif sel == 2: # Pregunta de seguridad
            questions = [
                get_string(30221),
                get_string(30222),
                get_string(30223),
                get_string(30224),
                get_string(30225),
                get_string(30080)
            ]
            q_sel = xbmcgui.Dialog().select(get_string(30079), questions)
            if q_sel < 0: continue

            if q_sel == len(questions) - 1: # Personalizada
                kb = xbmc.Keyboard('', get_string(30081))
                kb.doModal()
                if not kb.isConfirmed() or not kb.getText(): continue
                selected_question = kb.getText()
            else:
                selected_question = questions[q_sel]

            # Pedir respuesta
            kb = xbmc.Keyboard('', get_string(30082))
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                config['question'] = selected_question
                config['answer'] = kb.getText()
                save_security_config(config)
                xbmcgui.Dialog().notification(get_string(30083), get_string(30084), xbmcgui.NOTIFICATION_INFO)

        elif sel == 3: # Activar/Desactivar
            if not is_enabled:
                # Activar
                if not has_pin:
                    xbmcgui.Dialog().ok(get_string(30085), get_string(30086))
                    continue
                if not has_question:
                    if not xbmcgui.Dialog().yesno(get_string(30087), get_string(30088)):
                        continue
                config['enabled'] = True
                save_security_config(config)
                xbmcgui.Dialog().notification(get_string(30089), get_string(30090), xbmcgui.NOTIFICATION_INFO)
            else:
                # Desactivar
                config['enabled'] = False
                save_security_config(config)
                xbmcgui.Dialog().notification(get_string(30091), get_string(30092), xbmcgui.NOTIFICATION_INFO)

# --- Estructuras de Datos ---

# --- Estructuras de Datos ---
# (Las clases FavouriteEntry y FavouritesEngine se han movido a resources/lib/database.py)


from resources.lib.gui.editor import FavouritesEditor

# --- Controlador de Interfaz ---

def run_simple_editor():
    engine = FavouritesEngine()
    engine.load()
    entries = engine.entries

    while True:
        if not entries:
            xbmcgui.Dialog().ok(get_string(30368), get_string(30369))
            break

        # 1. Mostrar Lista
        names = ["{}. {}".format(i+1, e.name) for i, e in enumerate(entries)]
        idx = xbmcgui.Dialog().select(get_string(30384), names)
        if idx == -1: break # Cancelar/Atrás pulsado

        selected_entry = entries[idx]

        # 2. Mostrar Acciones (sin emojis para compatibilidad)
        actions = [
            get_string(30390), # Subir 1
            get_string(30391), # Bajar 1
            get_string(30408), # Subir 5
            get_string(30409), # Bajar 5
            get_string(30410), # Al Inicio
            get_string(30411), # Al Final
            get_string(30392), # Mover a Posición...
            get_string(30112), # Renombrar (Correct ID)
            get_string(30119)  # Eliminar (Correct ID)
        ]

        action = xbmcgui.Dialog().select(get_string(30385).format(selected_entry.name), actions)
        if action == -1: continue

        # 3. Ejecutar Acción
        changed = False
        new_idx = idx

        if action == 0: # Subir 1
            new_idx = max(0, idx - 1)
        elif action == 1: # Bajar 1
            new_idx = min(len(entries)-1, idx + 1)
        elif action == 2: # Subir 5
            new_idx = max(0, idx - 5)
        elif action == 3: # Bajar 5
            new_idx = min(len(entries)-1, idx + 5)
        elif action == 4: # Al Inicio
            new_idx = 0
        elif action == 5: # Al Final
            new_idx = len(entries) - 1
        elif action == 6: # Ir a posición
            kb = xbmc.Keyboard("", get_string(30393).format(len(entries)))
            kb.doModal()
            if kb.isConfirmed() and kb.getText().isdigit():
                pos = int(kb.getText())
                new_idx = max(0, min(len(entries)-1, pos - 1))
            else:
                continue

        # Ejecutar Movimiento
        if action <= 6 and new_idx != idx:
            entries.pop(idx)
            entries.insert(new_idx, selected_entry)
            changed = True

        elif action == 7: # Renombrar
            kb = xbmc.Keyboard(selected_entry.name, get_string(30160))
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                selected_entry.name = kb.getText()
                changed = True

        elif action == 8: # Eliminar
            if xbmcgui.Dialog().yesno(get_string(30167), get_string(30168).format(selected_entry.name)):
                entries.pop(idx)
                changed = True

        if changed:
            engine.save(engine.generate_xml(entries))
            xbmcgui.Dialog().notification(get_string(30243), get_string(30244), xbmcgui.NOTIFICATION_INFO, 1000)

def run_backup_menu():
    """Menú de backup/restaurar accesible desde el menú principal."""
    options = [
        get_string(30245),
        get_string(30246)
    ]
    choice = xbmcgui.Dialog().select(get_string(30216), options)

    if choice == 0:  # Crear backup
        engine = FavouritesEngine()
        engine.load()
        if not engine.entries:
            xbmcgui.Dialog().ok(get_string(30247), get_string(30248))
            return

        import datetime
        default_name = 'favoritos_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        kb = xbmc.Keyboard(default_name, get_string(30217))
        kb.doModal()
        if not kb.isConfirmed() or not kb.getText(): return

        folder = xbmcgui.Dialog().browse(0, get_string(30196), 'files')
        if not folder: return

        path = os.path.join(translatePath(folder), kb.getText() + '.xml')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(engine.generate_xml(engine.entries))
            xbmcgui.Dialog().notification(get_string(30249), kb.getText(), xbmcgui.NOTIFICATION_INFO, 3000)
        except Exception as e:
            xbmcgui.Dialog().ok(get_string(30044), str(e))

    elif choice == 1:  # Restaurar backup
        file_path = xbmcgui.Dialog().browse(1, get_string(30250), 'files', '.xml')
        if not file_path: return

        full_path = translatePath(file_path)
        if not os.path.exists(full_path):
            xbmcgui.Dialog().ok(get_string(30044), get_string(30251))
            return

        try:
            tree = ET.parse(full_path)
            root = tree.getroot()
            if root.tag != 'favourites':
                xbmcgui.Dialog().ok(get_string(30044), get_string(30252))
                return

            loaded_entries = []
            for child in root:
                if child.tag == 'favourite':
                    loaded_entries.append(FavouriteEntry.from_xml_element(child))

            if not loaded_entries:
                xbmcgui.Dialog().ok(get_string(30044), get_string(30253))
                return

            if xbmcgui.Dialog().yesno(get_string(30108), get_string(30254).format(len(loaded_entries))):
                engine = FavouritesEngine()
                engine.save(engine.generate_xml(loaded_entries))
                xbmcgui.Dialog().notification(get_string(30255), get_string(30256).format(len(loaded_entries)), xbmcgui.NOTIFICATION_INFO, 3000)
        except Exception as e:
            xbmcgui.Dialog().ok(get_string(30044), get_string(30257) + "\n" + str(e))

def run_templates_editor():
    """Editor para personalizar las plantillas de elementos predefinidos."""
    while True:
        templates = load_templates()

        # Construir menú dinámico con todas las categorías
        category_keys = list(templates.keys())
        category_names = []

        # Mapeo de traducciones para categorías fijas
        MAP_CATEGORIES = {
            "secciones_kodi": 30452,
            "comandos_sistema": 30453
        }

        for key in category_keys:
            if key in MAP_CATEGORIES:
                display_name = get_string(MAP_CATEGORIES[key])
            else:
                # Formato legible: secciones_kodi -> Secciones Kodi
                display_name = key.replace('_', ' ').title()

            item_count = len(templates[key])
            items_label = get_string(30203).format(item_count)
            category_names.append("{} ({})".format(display_name, items_label))

        # Añadir opciones de gestión
        opts = category_names + [
            '[COLOR lime]+ ' + get_string(30286) + '[/COLOR]',
            '[COLOR orange]' + get_string(30287) + '[/COLOR]',
            '[COLOR cyan]' + get_string(30288) + '[/COLOR]',
            '[COLOR cyan]' + get_string(30289) + '[/COLOR]',
            '[COLOR gray]« ' + get_string(30430) + '[/COLOR]'
        ]

        sel = xbmcgui.Dialog().select(get_string(30285), opts)

        if sel == -1 or sel == len(opts) - 1: return # Volver

        # Importar Plantillas
        if sel == len(opts) - 2:
            file_path = xbmcgui.Dialog().browse(1, get_string(30250).replace('xml','json'), 'files', '.json')
            if file_path:
                full_path = translatePath(file_path)
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        imported = json.load(f)

                    # Validar estructura básica
                    if not isinstance(imported, dict):
                        raise ValueError(get_string(30394))

                    # Preguntar si reemplazar o fusionar
                    merge_opts = [get_string(30317), get_string(30318), '« ' + get_string(30430)]
                    merge_sel = xbmcgui.Dialog().select(get_string(30316), merge_opts)

                    if merge_sel == 0: # Reemplazar
                        save_templates(imported)
                        xbmcgui.Dialog().notification(get_string(30267), get_string(30313), xbmcgui.NOTIFICATION_INFO)
                    elif merge_sel == 1: # Fusionar
                        current = load_templates()
                        for key, items in imported.items():
                            if key in current:
                                # Añadir items que no existan
                                existing_names = [i['name'] for i in current[key]]
                                for item in items:
                                    if item['name'] not in existing_names:
                                        current[key].append(item)
                            else:
                                current[key] = items
                        save_templates(current)
                        xbmcgui.Dialog().notification(get_string(30314), get_string(30315), xbmcgui.NOTIFICATION_INFO)
                except Exception as e:
                    xbmcgui.Dialog().ok(get_string(30044), get_string(30264) + ":\n" + str(e))
            continue

        # Exportar Plantillas
        if sel == len(opts) - 3:
            folder = xbmcgui.Dialog().browse(0, get_string(30218), 'files')
            if folder:
                default_name = 'plantillas_favoritos_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                kb = xbmc.Keyboard(default_name, get_string(30319))
                kb.doModal()
                if kb.isConfirmed() and kb.getText():
                    file_path = os.path.join(translatePath(folder), kb.getText() + '.json')
                    try:
                        current = load_templates()
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(current, f, ensure_ascii=False, indent=4)
                        xbmcgui.Dialog().notification(get_string(30270), kb.getText(), xbmcgui.NOTIFICATION_INFO)
                    except Exception as e:
                        xbmcgui.Dialog().ok(get_string(30044), get_string(30271) + ":\n" + str(e))
            continue

        # Restablecer
        if sel == len(opts) - 4:
            if xbmcgui.Dialog().yesno(get_string(30167), get_string(30310)):
                default_templates = {
                    "secciones_kodi": [

                        {"name": get_string(30400), "path": "ActivateWindow(Videos,MovieTitles)", "icon": "DefaultMovies.png"},
                        {"name": get_string(30417), "path": "ActivateWindow(Videos,TVShowTitles)", "icon": "DefaultTVShows.png"},
                        {"name": get_string(30418), "path": "ActivateWindow(Home)", "icon": "DefaultHome.png"},
                        {"name": get_string(30401), "path": "ActivateWindow(TVChannels)", "icon": "DefaultLiveTV.png"},
                        {"name": get_string(30402), "path": "ActivateWindow(TVGuide)", "icon": "DefaultEPG.png"},
                        {"name": get_string(30419), "path": "ActivateWindow(Radio)", "icon": "DefaultRadio.png"},
                        {"name": get_string(30403), "path": "ActivateWindow(Music)", "icon": "DefaultMusic.png"},
                        {"name": get_string(30420), "path": "ActivateWindow(Videos,MusicVideoTitles)", "icon": "DefaultMusicVideos.png"},
                        {"name": get_string(30421), "path": "ActivateWindow(Weather)", "icon": "DefaultWeather.png"},
                        {"name": get_string(30404), "path": "ActivateWindow(Pictures)", "icon": "DefaultPicture.png"},
                        {"name": get_string(30422), "path": "ActivateWindow(Settings)", "icon": "DefaultIconSettings.png"},
                        {"name": get_string(30423), "path": "ActivateWindow(FileManager)", "icon": "DefaultFile.png"},
                        {"name": get_string(30424), "path": "ActivateWindow(SystemInfo)", "icon": "DefaultIconInfo.png"},
                        {"name": get_string(30425), "path": "ActivateWindow(EventLog)", "icon": "DefaultIconInfo.png"},
                        {"name": get_string(30426), "path": "ActivateWindow(AddonBrowser)", "icon": "DefaultAddon.png"}
                    ],
                    "comandos_sistema": [
                        {"name": get_string(30405), "path": "ActivateWindow(ShutdownMenu)", "icon": "DefaultIconPower.png"},
                        {"name": get_string(30406), "path": "UpdateLibrary(video)", "icon": "DefaultIconSync.png"},
                        {"name": get_string(30407), "path": "CleanLibrary(video)", "icon": "DefaultAddon.png"},
                        {"name": get_string(30427), "path": "ReloadSkin()", "icon": "DefaultIconRepeat.png"},
                        {"name": get_string(30428), "path": "ActivateWindow(SkinSettings)", "icon": "DefaultAddon.png"},
                        {"name": get_string(30423), "path": "ActivateWindow(FileManager)", "icon": "DefaultFile.png"}
                    ]
                }
                save_templates(default_templates)
                xbmcgui.Dialog().notification(get_string(30311), get_string(30312), xbmcgui.NOTIFICATION_INFO)
            continue

        if sel == len(opts) - 5: # Añadir nueva categoría
            kb = xbmc.Keyboard('', get_string(30290))
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                new_cat_name = kb.getText().strip()
                # Convertir a clave válida: "Mis Addons" -> "mis_addons"
                new_cat_key = new_cat_name.lower().replace(' ', '_')

                if new_cat_key in templates:
                    xbmcgui.Dialog().notification(get_string(30044), get_string(30292), xbmcgui.NOTIFICATION_WARNING)
                else:
                    templates[new_cat_key] = []
                    save_templates(templates)
                    xbmcgui.Dialog().notification(get_string(30293), new_cat_name, xbmcgui.NOTIFICATION_INFO)
            continue

        # Editar categoría seleccionada
        category = category_keys[sel]

        # Mapeo de traducciones para categorías
        MAP_CATEGORIES = {
            "secciones_kodi": 30452,
            "comandos_sistema": 30453
        }
        category_display = get_string(MAP_CATEGORIES[category]) if category in MAP_CATEGORIES else category.replace('_', ' ').title()

        while True:
            templates = load_templates()
            items = templates.get(category, [])

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

            # Construir lista con nombres traducidos
            names = [get_string(MAP_ITEMS[i['name']]) if i['name'] in MAP_ITEMS else i['name'] for i in items]
            names.append('[COLOR lime]+ ' + get_string(30294) + '[/COLOR]')
            names.append('[COLOR red]- ' + get_string(30295) + '[/COLOR]')
            names.append('[COLOR gray]« ' + get_string(30430) + '[/COLOR]')

            item_sel = xbmcgui.Dialog().select(category_display, names)

            if item_sel == -1 or item_sel == len(names) - 1: break # Volver

            if item_sel == len(names) - 2: # Eliminar categoría
                if xbmcgui.Dialog().yesno(get_string(30167), get_string(30296).format(category_display)):
                    del templates[category]
                    save_templates(templates)
                    xbmcgui.Dialog().notification(get_string(30297), category_display, xbmcgui.NOTIFICATION_INFO)
                    break
                continue

            if item_sel == len(names) - 3: # Añadir nuevo
                # Nombre
                kb = xbmc.Keyboard('', get_string(30298))
                kb.doModal()
                if not kb.isConfirmed() or not kb.getText(): continue
                new_name = kb.getText()

                # Comando/Ruta
                kb = xbmc.Keyboard('', get_string(30299))
                kb.doModal()
                if not kb.isConfirmed() or not kb.getText(): continue
                new_path = kb.getText()

                # Icono - Elegir método
                icon_opts = [get_string(30301), get_string(30302)]
                icon_sel = xbmcgui.Dialog().select(get_string(30300), icon_opts)

                if icon_sel == 0: # Escribir
                    kb = xbmc.Keyboard('DefaultAddon.png', get_string(30303))
                    kb.doModal()
                    new_icon = kb.getText() if kb.isConfirmed() and kb.getText() else 'DefaultAddon.png'
                elif icon_sel == 1: # Explorar
                    browse_result = xbmcgui.Dialog().browse(1, get_string(30185), 'pictures')
                    new_icon = browse_result if browse_result else 'DefaultAddon.png'
                else:
                    new_icon = 'DefaultAddon.png'

                # Guardar
                items.append({"name": new_name, "path": new_path, "icon": new_icon})
                templates[category] = items
                save_templates(templates)
                xbmcgui.Dialog().notification(get_string(30293), new_name, xbmcgui.NOTIFICATION_INFO)

            else: # Editar existente
                selected_item = items[item_sel]

                actions = [get_string(30304), get_string(30305), get_string(30306), get_string(30119), '« ' + get_string(30430)]
                action = xbmcgui.Dialog().select(selected_item['name'], actions)

                if action == 0: # Nombre
                    kb = xbmc.Keyboard(selected_item['name'], get_string(30307))
                    kb.doModal()
                    if kb.isConfirmed() and kb.getText():
                        items[item_sel]['name'] = kb.getText()
                        templates[category] = items
                        save_templates(templates)

                elif action == 1: # Comando
                    kb = xbmc.Keyboard(selected_item['path'], get_string(30308))
                    kb.doModal()
                    if kb.isConfirmed() and kb.getText():
                        items[item_sel]['path'] = kb.getText()
                        templates[category] = items
                        save_templates(templates)

                elif action == 2: # Icono
                    icon_opts = [get_string(30301), get_string(30302)]
                    icon_sel = xbmcgui.Dialog().select(get_string(30300), icon_opts)

                    new_icon = None
                    if icon_sel == 0: # Escribir
                        kb = xbmc.Keyboard(selected_item['icon'], get_string(30309))
                        kb.doModal()
                        if kb.isConfirmed() and kb.getText():
                            new_icon = kb.getText()
                    elif icon_sel == 1: # Explorar
                        browse_result = xbmcgui.Dialog().browse(1, get_string(30185), 'pictures')
                        if browse_result:
                            new_icon = browse_result

                    if new_icon:
                        items[item_sel]['icon'] = new_icon
                        templates[category] = items
                        save_templates(templates)

                elif action == 3: # Eliminar
                    if xbmcgui.Dialog().yesno(get_string(30167), get_string(30168).format(selected_item['name'])):
                        items.pop(item_sel)
                        templates[category] = items
                        save_templates(templates)
                        xbmcgui.Dialog().notification(get_string(30297), selected_item['name'], xbmcgui.NOTIFICATION_INFO)

def run_health_check():
    """Ejecuta el escaneo de salud de favoritos para limpiar enlaces rotos."""
    from resources.lib.health import check_broken_links
    engine = FavouritesEngine()
    if not engine.load():
        xbmcgui.Dialog().notification("Flow FavManager", "No se pudo cargar favourites.xml", xbmcgui.NOTIFICATION_ERROR)
        return

    valid, broken = check_broken_links(engine.entries)

    if not broken:
        xbmcgui.Dialog().notification("Health Check", "No se encontraron enlaces rotos.", xbmcgui.NOTIFICATION_INFO)
        return

    msg = f"Se encontraron {len(broken)} enlaces rotos (addons no instalados).\n¿Desea eliminarlos?"
    if xbmcgui.Dialog().yesno("Health Check", msg):
        engine.entries = valid
        if engine.save():
            xbmcgui.Dialog().notification("Health Check", "Enlaces rotos eliminados.", xbmcgui.NOTIFICATION_INFO)
        else:
            xbmcgui.Dialog().notification("Error", "No se pudieron guardar los cambios.", xbmcgui.NOTIFICATION_ERROR)

def show_about_dialog():
    msg = ("[B]Flow FavManager[/B]\n"
           "[COLOR gray]-----------------------------------------------[/COLOR]\n"
           + get_string(30341) + "\n"
           "https://github.com/fullstackcurso/")
    xbmcgui.Dialog().ok(get_string(30340), msg)

def run_profiles_menu():
    """Menú para gestionar perfiles de favoritos."""
    while True:
        profiles = get_profiles()

        # Opciones
        display_list = [get_string(30258),
                        get_string(30259),
                        get_string(30260)]

        for p in profiles:
            items_label = get_string(30203).format(len(p['entries']))
            display_list.append(f"{p['name']} | [I]{p['date']}[/I] | {items_label}")

        sel = xbmcgui.Dialog().select(get_string(30261), display_list)
        if sel == -1: break

        if sel == 0: # Crear Nuevo
            kb = xbmc.Keyboard('', get_string(30035))
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                name = kb.getText()
                # Cargar favoritos actuales del sistema
                eng = FavouritesEngine()
                eng.load()
                if save_profile(name, eng.entries):
                    xbmcgui.Dialog().notification(get_string(30262), get_string(30263).format(name), xbmcgui.NOTIFICATION_INFO)
                    log_audit("PROFILE_CREATED", f"Perfil '{name}' creado con {len(eng.entries)} items")
                    # Refrescar contenedor si venimos desde Explorar
                    xbmc.executebuiltin('Container.Refresh')
                    break # Salir del menú tras crear
            continue

        elif sel == 1: # Importar XML
            path = xbmcgui.Dialog().browse(1, get_string(30250), 'files', '.xml')
            if path:
                try:
                    log_debug(f"Importando XML desde: {path}")
                    tree = ET.parse(path)
                    root = tree.getroot()
                    entries = []

                    for child in root:
                        if child.tag == 'favourite':
                            try:
                                entry = FavouriteEntry.from_xml_element(child)
                                entries.append(entry)
                            except Exception as inner:
                                log_debug(f"Error parseando elemento: {inner}")

                    log_debug(f"Encontrados {len(entries)} favoritos")

                    if not entries:
                        xbmcgui.Dialog().notification(get_string(30044), get_string(30264), xbmcgui.NOTIFICATION_ERROR)
                        continue

                    kb = xbmc.Keyboard(get_string(30265), get_string(30266))
                    kb.doModal()
                    if kb.isConfirmed():
                        p_name = kb.getText() or get_string(30265)
                        save_profile(p_name, entries)
                        xbmcgui.Dialog().notification(get_string(30267), get_string(30268).format(len(entries)), xbmcgui.NOTIFICATION_INFO)
                        log_audit("PROFILE_IMPORTED", f"Perfil '{p_name}' importado desde XML ({len(entries)} items)")
                        xbmc.executebuiltin('Container.Refresh')
                        break # Salir y refrescar
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    log_debug("ERROR IMPORT: " + tb)
                    xbmcgui.Dialog().textviewer(get_string(30269), str(e) + "\n\n" + tb)
            continue

        elif sel == 2: # Exportar Actuales
            dest = xbmcgui.Dialog().browse(3, get_string(30196), 'files')
            if dest:
                try:
                    eng = FavouritesEngine()
                    eng.load() # Cargar actuales

                    file_name = f"favourites_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xml"
                    path = os.path.join(dest, file_name)

                    root = ET.Element('favourites')
                    for e in eng.entries:
                        item = ET.SubElement(root, 'favourite')
                        item.set('name', e.name)
                        item.set('thumb', e.thumb)
                        item.text = e.url

                    tree = ET.ElementTree(root)
                    tree.write(path, encoding='utf-8', xml_declaration=True)
                    xbmcgui.Dialog().notification(get_string(30270), file_name, xbmcgui.NOTIFICATION_INFO)
                except Exception as e:
                    xbmcgui.Dialog().ok(get_string(30271), str(e))
            continue

        # Acciones sobre perfil existente
        prof = profiles[sel - 3]
        opts = [get_string(30272), get_string(30112), get_string(30273), get_string(30119), '« ' + get_string(30430)]
        act = xbmcgui.Dialog().select(f"{get_string(30274)}: {prof['name']}", opts)

        if act == 0: # Cargar
            if xbmcgui.Dialog().yesno(get_string(30275), get_string(30276).format(prof['name'])):
                eng = FavouritesEngine()
                eng.entries = load_profile(prof['filename'])
                eng.save()
                xbmcgui.Dialog().notification(get_string(30277), get_string(30278), xbmcgui.NOTIFICATION_INFO)
                log_audit("PROFILE_LOADED", f"Perfil '{prof['name']}' cargado como favoritos activos")
                break

        elif act == 1: # Renombrar
            kb = xbmc.Keyboard(prof['name'], get_string(30279))
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                new_name = kb.getText()
                if new_name != prof['name']:
                    # Cargar, guardar con nuevo nombre, borrar viejo
                    entries = load_profile(prof['filename'])
                    save_profile(new_name, entries)
                    delete_profile(prof['filename'])
                    xbmcgui.Dialog().notification(get_string(30280), get_string(30281).format(new_name), xbmcgui.NOTIFICATION_INFO)
                    log_audit("PROFILE_RENAMED", f"Perfil renombrado de '{prof['name']}' a '{new_name}'")

        elif act == 2: # Exportar
            # Seleccionar carpeta destino
            dest = xbmcgui.Dialog().browse(3, get_string(30388), 'files')
            if dest:
                try:
                    safe_name = "".join([c for c in prof['name'] if c.isalnum() or c in (' ', '-', '_')]).strip()
                    file_name = f"{safe_name}.xml"
                    path = os.path.join(dest, file_name)

                    entries = load_profile(prof['filename'])

                    root = ET.Element('favourites')
                    for e in entries:
                        item = ET.SubElement(root, 'favourite')
                        item.set('name', e.name)
                        item.set('thumb', e.thumb)
                        item.text = e.url

                    # Guardar
                    tree = ET.ElementTree(root)
                    tree.write(path, encoding='utf-8', xml_declaration=True)

                    xbmcgui.Dialog().notification(get_string(30270), get_string(30282).format(file_name), xbmcgui.NOTIFICATION_INFO)
                except Exception as e:
                    xbmcgui.Dialog().ok(get_string(30271), str(e))

        elif act == 3: # Eliminar
            if xbmcgui.Dialog().yesno(get_string(30283), get_string(30284).format(prof['name'])):
                delete_profile(prof['filename'])
                log_audit("PROFILE_DELETED", f"Perfil '{prof['name']}' eliminado")

def router(param):
    try:
        if '/health' in param:
            run_health_check()
            return

        if '/profiles' in param:
            run_profiles_menu()

        elif '/dialog' in param:
            # Always use the new single editor.xml
            xml = 'editor.xml'

            # Decide layout property based on settings
            # view_mode: 0 = Lista (default), 1 = Cuadrícula
            view_setting = ADDON.getSetting('view_mode') or '0'
            thumb_size = ADDON.getSetting('icon_scale') or '0'
            font_size = ADDON.getSetting('text_scale') or '1'

            if view_setting == '1':  # Cuadrícula
                if thumb_size == '0':
                    prop_mode = '1' # Grid Small
                else:
                    prop_mode = '0' # Grid Large
            else: # Lista
                # Si Font > Pequeño (0) O Thumb > Pequeño (0), usar Lista Grande
                # font_size: 0=Pequeño, 1=Mediano, 2=Grande
                if thumb_size == '1' or font_size != '0':
                    prop_mode = '3' # List Large
                else:
                    prop_mode = '2' # List Compact

            gui = FavouritesEditor(xml, PATHS['addon_path'], 'Default', '1080i')
            gui.setProperty('view_mode', prop_mode)
            gui.setProperty('addonIcon', os.path.join(PATHS['addon_path'], 'icon.png'))
            gui.doModal()
            del gui

        elif '/simple_editor' in param:
            run_simple_editor()

        elif '/backup_menu' in param:
            run_backup_menu()

        elif '/save_reload' in param:
            # Ask to clear cache
            if xbmcgui.Dialog().yesno(get_string(30351), get_string(30377)):
                # Clear Texture Cache logic
                try:
                    db_path = translatePath('special://profile/Database/Textures13.db')
                    thumbs_path = translatePath('special://profile/Thumbnails/')

                    # 1. Try to delete Database (Might fail on Windows, we ignore it)
                    try:
                        if os.path.exists(db_path):
                            os.remove(db_path)
                    except Exception:
                        pass # File locked, continue to delete images

                    # 2. Delete Thumbnails folder contents (This forces reload)
                    if os.path.exists(thumbs_path):
                        try:
                            shutil.rmtree(thumbs_path)
                            xbmc.sleep(200)
                            os.mkdir(thumbs_path)
                        except Exception:
                            pass # Some files might be locked, ignore

                    xbmcgui.Dialog().notification(get_string(30351), get_string(30352), xbmcgui.NOTIFICATION_INFO, 2000)
                    xbmc.sleep(1000)
                except Exception as e:
                    log_debug("Cache warning: " + str(e))

            # Always reload profile to apply changes/restart skin
            xbmc.executebuiltin('LoadProfile(%s)' % xbmc.getInfoLabel('System.ProfileName'))

        elif '/settings' in param:
            # Submenú de Configuración
            while True:
                audit_enabled = ADDON.getSetting('enable_audit_log') == 'true'

                opts = [
                    get_string(30326), # Advanced Editor (correct ID)
                    get_string(30285), # Templates Editor (correct ID)
                    get_string(30058), # Security and Password (correct ID)
                    get_string(30395) if audit_enabled else get_string(30396),
                    '« ' + get_string(30430)  # Back
                ]
                sel = xbmcgui.Dialog().select(get_string(30422), opts)

                if sel == 0:
                    ADDON.openSettings()
                elif sel == 1:
                    run_templates_editor()
                elif sel == 2:
                    run_security_menu()
                elif sel == 3:
                    # Submenú Log de Auditoría
                    while True:
                        audit_on = ADDON.getSetting('enable_audit_log') == 'true'
                        status_str = get_string(30413) if audit_on else get_string(30414)
                        color_str = 'lime' if audit_on else 'gray'

                        log_opts = [
                            get_string(30412).format(color=color_str, status=status_str),
                            get_string(30415) if audit_on else get_string(30416),
                            get_string(30397), # View Audit Log
                            get_string(30378), # Delete Log
                            "[COLOR gray]« " + get_string(30430) + "[/COLOR]"
                        ]
                        log_sel = xbmcgui.Dialog().select(get_string(30386), log_opts)

                        if log_sel == 1:  # Toggle
                            new_val = 'false' if audit_on else 'true'
                            ADDON.setSetting('enable_audit_log', new_val)
                            xbmcgui.Dialog().notification(get_string(30353), get_string(30354) if new_val == 'true' else get_string(30355), xbmcgui.NOTIFICATION_INFO)
                        elif log_sel == 2:  # Ver Log
                            if os.path.exists(AUDIT_FILE):
                                try:
                                    with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                    if content.strip():
                                        xbmcgui.Dialog().textviewer(get_string(30386), content)
                                    else:
                                        xbmcgui.Dialog().ok(get_string(30370), get_string(30371))
                                except Exception as e:
                                    xbmcgui.Dialog().ok(get_string(30044), get_string(30374) + f"\n{e}")
                            else:
                                xbmcgui.Dialog().ok(get_string(30372), get_string(30373))
                        elif log_sel == 3:  # Borrar
                            if os.path.exists(AUDIT_FILE):
                                if xbmcgui.Dialog().yesno(get_string(30378), get_string(30379)):
                                    try:
                                        os.remove(AUDIT_FILE)
                                        xbmcgui.Dialog().notification(get_string(30353), get_string(30356), xbmcgui.NOTIFICATION_INFO)
                                    except:
                                        pass
                            else:
                                xbmcgui.Dialog().notification(get_string(30357), get_string(30358), xbmcgui.NOTIFICATION_INFO)
                        else:
                            break
                else:
                    break  # Volver

        elif '/templates_editor' in param:
            run_templates_editor()

        elif '/about' in param:
            show_about_dialog()

        elif '/open_favourites' in param:
            # Detectar versión para compatibilidad (Kodi 21+ usa FavouritesBrowser)
            version = xbmc.getInfoLabel('System.BuildVersion')
            major = 19
            try:
                if version: major = int(version.split('.')[0])
            except: pass

            if major >= 21:
                xbmc.executebuiltin('ActivateWindow(FavouritesBrowser)')
            else:
                xbmc.executebuiltin('ActivateWindow(Favourites)')

        elif '/execute' in param:
            # Puente para ejecutar comandos de Kodi (ActivateWindow, RunAddon, etc)
            import urllib.parse
            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)
            cmd = args.get('cmd', [''])[0]

            if cmd:
                log_debug("Ejecutando comando: " + cmd)
                xbmc.executebuiltin(cmd)
            return

        elif '/explore_profile' in param:
            # Listar contenido de un perfil específico
            import urllib.parse

            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)
            filename = args.get('file', [''])[0]

            if not filename and len(sys.argv) > 2:
                args = urllib.parse.parse_qs(sys.argv[2].lstrip('?'))
                filename = args.get('file', [''])[0]

            if not filename:
                log_debug("Explore Profile: No filename found in URL: " + str(param))
                xbmcplugin.endOfDirectory(PLUGIN_ID, False)
                return

            try:
                entries = load_profile(filename)

                if not entries:
                    li = xbmcgui.ListItem(label=get_string(30398))
                    xbmcplugin.addDirectoryItem(PLUGIN_ID, "", li, False)

                for entry in entries:
                    li, target_url, is_folder = build_list_item(entry)
                    xbmcplugin.addDirectoryItem(PLUGIN_ID, target_url, li, is_folder)

                xbmcplugin.endOfDirectory(PLUGIN_ID)

            except Exception as e:
                log_debug("Error explorando perfil: " + str(e))
                xbmcgui.Dialog().notification(get_string(30044), get_string(30359), xbmcgui.NOTIFICATION_ERROR)
                xbmcplugin.endOfDirectory(PLUGIN_ID, False)

        elif '/search_profiles' in param:
            # Buscar en todos los perfiles
            import urllib.parse
            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)
            query = args.get('q', [''])[0]

            if not query:
                # Pedir término de búsqueda
                kb = xbmc.Keyboard('', get_string(30320))
                kb.doModal()
                if not kb.isConfirmed() or not kb.getText():
                    xbmcplugin.endOfDirectory(PLUGIN_ID, False)
                    return
                query = kb.getText()

            # Buscar en todos los perfiles
            profiles = get_profiles()
            results = []
            query_lower = query.lower()

            for p in profiles:
                for entry_data in p.get('entries', []):
                    entry_name = entry_data.get('name', '')
                    # Limpiar tags de color para buscar
                    clean_name = re.sub(r'\[COLOR[^\]]*\]|\[/COLOR\]|\[B\]|\[/B\]|\[I\]|\[/I\]', '', entry_name)
                    if query_lower in clean_name.lower():
                        results.append({
                            'name': entry_name,
                            'thumb': entry_data.get('thumb', ''),
                            'url': entry_data.get('url', ''),
                            'profile': p['name']
                        })

            xbmcplugin.setContent(PLUGIN_ID, 'files')

            if not results:
                li = xbmcgui.ListItem(label=f"[COLOR gray]{get_string(30321).format(query)}[/COLOR]")
                li.setInfo('video', {'plot': get_string(30322)})
                xbmcplugin.addDirectoryItem(PLUGIN_ID, '', li, False)
            else:
                # Mostrar resultados
                for r in results:
                    # Crear objeto temporal para usar build_list_item
                    temp_entry = FavouriteEntry(r['name'], r['thumb'], r['url'])

                    li, target_url, is_folder = build_list_item(temp_entry)

                    # Personalizar etiqueta para búsqueda (añadir nombre de perfil)
                    display_name = f"{r['name']} [COLOR gray]({r['profile']})[/COLOR]"
                    li.setLabel(display_name)
                    li.setInfo('video', {'plot': f"{get_string(30323)} {r['profile']}\nURL: {r['url'][:80]}..."})

                    xbmcplugin.addDirectoryItem(PLUGIN_ID, target_url, li, is_folder)

            xbmcplugin.endOfDirectory(PLUGIN_ID)

        elif '/delete_profile' in param:
            # Acción para borrar perfil desde menú contextual
            import urllib.parse
            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)
            filename = args.get('file', [''])[0]

            if filename and xbmcgui.Dialog().yesno(get_string(30380), get_string(30381)):
                if delete_profile(filename):
                    xbmcgui.Dialog().notification(get_string(30360), get_string(30361), xbmcgui.NOTIFICATION_INFO)
                    xbmc.executebuiltin('Container.Refresh') # Recargar lista visualmente
                else:
                    xbmcgui.Dialog().notification(get_string(30044), get_string(30362), xbmcgui.NOTIFICATION_ERROR)
            return

        elif '/rename_profile' in param:
            # Acción para renombrar perfil desde menú contextual
            import urllib.parse
            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)
            filename = args.get('file', [''])[0]
            current_name = args.get('name', [''])[0]

            if filename:
                kb = xbmc.Keyboard(current_name, get_string(30382))
                kb.doModal()
                if kb.isConfirmed() and kb.getText():
                    new_name = kb.getText()
                    try:
                        # Cargar, guardar con nuevo nombre y borrar viejo
                        entries = load_profile(filename)
                        if save_profile(new_name, entries):
                            delete_profile(filename)
                            xbmcgui.Dialog().notification(get_string(30363), get_string(30364), xbmcgui.NOTIFICATION_INFO)
                            xbmc.executebuiltin('Container.Refresh')
                    except Exception as e:
                         xbmcgui.Dialog().notification(get_string(30044), str(e), xbmcgui.NOTIFICATION_ERROR)
            return

        elif '/widget' in param:
            # Ruta optimizada para Widgets
            import urllib.parse
            parsed = urllib.parse.urlparse(param)
            args = urllib.parse.parse_qs(parsed.query)

            # Obtener nombre de perfil (o archivo)
            profile_val = args.get('profile', [''])[0] or args.get('file', [''])[0]

            entries = []
            if not profile_val:
                # Si no se especifica, intentar cargar el último usado o el default
                # (Por ahora, listamos carpetas de perfiles si no hay params)
                profiles = get_profiles()
                for p in profiles:
                    url = BASE_URL + 'widget?profile=' + urllib.parse.quote(p['filename'])
                    li = xbmcgui.ListItem(label=p['name'])
                    li.setArt({'thumb': 'DefaultFolder.png', 'icon': 'DefaultFolder.png'})
                    xbmcplugin.addDirectoryItem(PLUGIN_ID, url, li, True)
                xbmcplugin.endOfDirectory(PLUGIN_ID)
                return
            else:
                # Cargar perfil específico
                # Soporta nombre de archivo "profile_xyz.json" o nombre "Mis Favoritos"

                # Intentar cargar directo (asumiendo filename)
                entries = load_profile(profile_val)

                # Si falla o vacío, buscar por nombre
                if not entries and not profile_val.endswith('.json'):
                    profiles = get_profiles()
                    for p in profiles:
                        if p['name'] == profile_val:
                            entries = load_profile(p['filename'])
                            break

            xbmcplugin.setContent(PLUGIN_ID, 'files')

            if not entries:
                # Mostrar item vacío
                li = xbmcgui.ListItem(label=get_string(30399))
                xbmcplugin.addDirectoryItem(PLUGIN_ID, "", li, False)
            else:
                for entry in entries:
                    li, target_url, is_folder = build_list_item(entry)
                    xbmcplugin.addDirectoryItem(PLUGIN_ID, target_url, li, is_folder)

            xbmcplugin.endOfDirectory(PLUGIN_ID)

        elif '/explore' in param:
            # Listar carpetas de perfiles
            profiles = get_profiles()

            xbmcplugin.setContent(PLUGIN_ID, 'files')

            # --- GESTOR DE PERFILES (Botón Superior) ---
            li = xbmcgui.ListItem(label="[COLOR violet][B]" + get_string(30342) + "[/B][/COLOR]")
            li.setArt({'icon': 'DefaultAddonService.png', 'thumb': 'DefaultAddonService.png'})
            li.setInfo('video', {'plot': get_string(30343)})
            url_manager = BASE_URL + 'profiles'
            xbmcplugin.addDirectoryItem(PLUGIN_ID, url_manager, li, False)
            # ------------------------------------------

            # --- BUSCAR EN TODOS LOS PERFILES ---
            li = xbmcgui.ListItem(label="[COLOR cyan][B]" + get_string(30320) + "[/B][/COLOR]")
            li.setArt({'icon': 'DefaultAddonsSearch.png', 'thumb': 'DefaultAddonsSearch.png'})
            li.setInfo('video', {'plot': get_string(30322)})
            url_search = BASE_URL + 'search_profiles'
            xbmcplugin.addDirectoryItem(PLUGIN_ID, url_search, li, True)
            # ------------------------------------

            # --- VISTA WIDGETS LIMPIA ---
            li = xbmcgui.ListItem(label="[COLOR yellow][B]" + get_string(30344) + "[/B][/COLOR]")
            li.setArt({'icon': 'DefaultPlaylist.png', 'thumb': 'DefaultPlaylist.png'})
            li.setInfo('video', {'plot': get_string(30345)})
            url_widget = BASE_URL + 'widget'
            xbmcplugin.addDirectoryItem(PLUGIN_ID, url_widget, li, True)
            # ----------------------------

            for p in profiles:
                # Crear URL para entrar en el perfil
                import urllib.parse
                url = BASE_URL + 'explore_profile?file=' + urllib.parse.quote(p['filename'])

                li = xbmcgui.ListItem(label=p['name'])
                li.setArt({'icon': 'DefaultUser.png'})
                li.setInfo('video', {'plot': f"{len(p['entries'])} elementos.\nModificado: {p['date']}"})

                # --- MENÚ CONTEXTUAL ---
                # Definir comandos para el click derecho
                cmd_delete = f"RunPlugin({BASE_URL}delete_profile?file={urllib.parse.quote(p['filename'])})"
                cmd_rename = f"RunPlugin({BASE_URL}rename_profile?file={urllib.parse.quote(p['filename'])}&name={urllib.parse.quote(p['name'])})"

                li.addContextMenuItems([
                    (get_string(30279), cmd_rename),
                    (get_string(30283), cmd_delete)
                ])

                xbmcplugin.addDirectoryItem(PLUGIN_ID, url, li, True)

            xbmcplugin.endOfDirectory(PLUGIN_ID)

        elif '/toggle_ee' in param:
            # Easter Egg Toggle
            current = ADDON.getSetting('easter_egg') == 'true'
            ADDON.setSetting('easter_egg', 'false' if current else 'true')
            xbmc.executebuiltin('Container.Refresh')
            return

        elif '/exit_only' in param:
             xbmc.executebuiltin('Action(Back)')

        elif '/spanish_alert' in param:
            msg = ("Este addon está desarrollado por hispanohablantes.\n\n"
                   "En caso de experimentar algún fallo, se recomienda descargar la versión en español desde:\n"
                   "https://github.com/fullstackcurso/Flow-FavManager/releases\n\n"
                   "Dicha versión es la más probada y pulida por el momento.")

            # Diálogo con botones personalizados
            # Yes -> Ocultar botón (True)
            # No -> Mantener (False)
            ocultar = xbmcgui.Dialog().yesno(
                "Atención - Comunidad Hispana",    # Título
                msg,                               # Mensaje
                nolabel="Mantener",                # Botón Izquierda
                yeslabel="Ocultar botón"           # Botón Derecha
            )

            if ocultar:
                ADDON.setSetting('spanish_alert_dismissed', 'true')
                xbmc.executebuiltin('Container.Refresh')
            return

        else:
            # Main Menu construction
            xbmcplugin.setContent(PLUGIN_ID, 'files')

            def add_item(label, route, icon_name, desc, color='white', is_folder=False, context_items=None):
                # Construir URL limpia
                full_url = BASE_URL + route.lstrip('/')

                # Texto limpio para el título (InfoTag)
                clean_label = label

                li = xbmcgui.ListItem(label='[COLOR {}][B]{}[/B][/COLOR]'.format(color, label))
                li.setArt({
                    'thumb': icon_name,
                    'icon': icon_name
                })
                # Usamos 'video' y 'plot' para que salga la descripción en la mayoría de skins
                li.setInfo('video', {
                    'title': clean_label,
                    'plot': desc,
                    'plotoutline': desc
                })

                if context_items:
                    li.addContextMenuItems(context_items)

                xbmcplugin.addDirectoryItem(PLUGIN_ID, full_url, li, is_folder)

            add_item(get_string(30324), 'explore',
                     'DefaultUser.png',
                     get_string(30325), 'white', is_folder=True)

            add_item(get_string(30326), 'dialog',
                     'DefaultPlaylist.png',
                     get_string(30327), 'cyan')

            add_item(get_string(30328), 'simple_editor',
                     'DefaultFile.png',
                     get_string(30329), 'violet')

            add_item(get_string(30216), 'backup_menu',
                     'DefaultHardDisk.png',
                     get_string(30457), 'orange')

            add_item("Health Check", 'health',
                     'DefaultIconWarning.png',
                     "Escanea tus favoritos en busca de enlaces rotos.", 'red')

            add_item(get_string(30330), 'save_reload',
                     'DefaultAddonsUpdates.png',
                     get_string(30331), 'lime')

            add_item(get_string(30332), 'settings',
                     'DefaultProgram.png',
                     get_string(30333), 'silver')

            add_item(get_string(30334), 'open_favourites',
                     'DefaultFavourites.png',
                     get_string(30335), 'gold')

            # --- EASTER EGG LOGIC ---
            is_ee = ADDON.getSetting('easter_egg') == 'true'
            lbl_about = get_string(30429) + ADDON.getAddonInfo('version') if is_ee else get_string(30338)
            desc_about = get_string(30341) if is_ee else get_string(30339)
            color_about = "blue" if is_ee else "cornflowerblue"

            # Context Menu para activarlo
            ctx_ee = [(get_string(30451), f'RunPlugin({BASE_URL}toggle_ee)')]

            add_item(lbl_about, 'about',
                     'DefaultIconInfo.png',
                     desc_about, color_about, context_items=ctx_ee)
            # ------------------------

            add_item(get_string(30336), 'exit_only',
                     'DefaultFolderBack.png',
                     get_string(30337), 'red')

            # --- SPANISH ALERT ---
            # Se muestra solo si es idioma español y no está oculto
            lang = xbmc.getLanguage(xbmc.ISO_639_1)
            is_hidden = ADDON.getSetting('spanish_alert_dismissed') == 'true'

            if lang.startswith('es') and not is_hidden:
                add_item("¡ATENCIÓN: Español Detectado! (Leer)", 'spanish_alert',
                         'DefaultIconInfo.png',
                         "Información importante sobre la versión en español.", 'yellow')
            # ---------------------

            xbmcplugin.endOfDirectory(PLUGIN_ID)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log_debug("CRASH: " + tb)
        xbmcgui.Dialog().textviewer(get_string(30387), str(e) + "\n\n" + tb)

if __name__ == '__main__':
    # Chequeo de seguridad antes de arrancar
    if not check_security_gate():
        # Bloquear acceso - No mostrar nada
        if PLUGIN_ID >= 0:
            xbmcplugin.endOfDirectory(PLUGIN_ID, succeeded=False)
    else:
        # Pasar sys.argv[0] (ruta) y sys.argv[2] (parámetros) para que el router tenga todo
        full_url = sys.argv[0]
        if len(sys.argv) > 2:
            full_url += sys.argv[2]
        router(full_url)
