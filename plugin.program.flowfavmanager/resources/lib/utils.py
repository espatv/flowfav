# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import os
import datetime

ADDON = xbmcaddon.Addon()
DEBUG_MODE = True

translatePath = xbmcvfs.translatePath if hasattr(xbmcvfs, 'translatePath') else xbmc.translatePath

# Safe path extraction to support unit testing with mocks
addon_path = ADDON.getAddonInfo('path')
if not isinstance(addon_path, str):
    addon_path = ''

PATHS = {
    'favourites': translatePath('special://userdata/favourites.xml'),
    'backup': translatePath('special://userdata/favourites.xml.bak'),
    'addon_path': addon_path,
    'templates': os.path.join(addon_path, 'resources', 'templates.json') if addon_path else '',
    'profiles': translatePath('special://profile/addon_data/plugin.program.flowfavmanager/profiles')
}

PROPS = {
    'result': 'flow_xml_output',
    'reorder_method': 'flow_action_mode',
    'font_size': 'flow_ui_font',
    'thumb_size': 'flow_ui_thumb'
}

AUDIT_FILE = translatePath('special://profile/addon_data/plugin.program.flowfavmanager/audit.log')

def get_string(string_id):
    s = ADDON.getLocalizedString(string_id)
    if not s:
        xbmc.log(f"[Flow FavManager] MISSING ID: {string_id}", xbmc.LOGWARNING)
        return str(string_id)
    return s

def log_debug(msg):
    if DEBUG_MODE:
        xbmc.log('[Flow FavManager Lib] ' + str(msg), xbmc.LOGINFO)

def log_audit(action, details):
    """Registra eventos de seguridad y acciones importantes."""
    if ADDON.getSetting('enable_audit_log') != 'true': return

    try:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {action}: {details}\n"
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception as e:
        log_debug(f"Error escribiendo audit log: {e}")

def get_window_prop(prop_name):
    return xbmcgui.Window(xbmcgui.getCurrentWindowId()).getProperty(prop_name)

def set_window_prop(prop_name, value):
    xbmcgui.Window(xbmcgui.getCurrentWindowId()).setProperty(prop_name, value)

def clear_window_prop(prop_name):
    xbmcgui.Window(xbmcgui.getCurrentWindowId()).clearProperty(prop_name)

def load_templates():
    """Carga las plantillas personalizables desde JSON."""
    try:
        with open(PATHS['templates'], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_debug("Error cargando templates: " + str(e))
        return {"secciones_kodi": [], "comandos_sistema": []}

def save_templates(data):
    """Guarda las plantillas en JSON."""
    try:
        with open(PATHS['templates'], 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        log_debug("Error guardando templates: " + str(e))
        return False
