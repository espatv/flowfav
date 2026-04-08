# -*- coding: utf-8 -*-
import os
import sys
import shutil
import json
import re
import xbmc
import xbmcaddon
import xbmcvfs
import xml.etree.ElementTree as ET

# Definición de translatePath para compatibilidad
translatePath = xbmcvfs.translatePath if hasattr(xbmcvfs, 'translatePath') else xbmc.translatePath

# Constantes necesarias para la base de datos (extraídas de default.py)
ADDON = xbmcaddon.Addon()
PATHS = {
    'favourites': translatePath('special://userdata/favourites.xml'),
    'backup': translatePath('special://userdata/favourites.xml.bak'),
    'addon_path': ADDON.getAddonInfo('path'),
    'profiles': translatePath('special://profile/addon_data/plugin.program.flowfavmanager/profiles')
}

# Logger simple para uso interno
DEBUG_MODE = True
def log_debug(msg):
    if DEBUG_MODE:
        xbmc.log('[Flow FavManager Lib] ' + str(msg), xbmc.LOGINFO)

# --- CLASES DE DATOS ---

class FavouriteEntry:
    """Representa un elemento favorito individual."""
    def __init__(self, name, thumb, url):
        self.name = name
        self.thumb = thumb
        self.url = url

    @classmethod
    def from_xml_element(cls, element):
        return cls(
            name=element.get('name', ''),
            thumb=element.get('thumb', ''),
            url=element.text or ''
        )

    def to_xml_string(self):
        from xml.sax.saxutils import escape
        return '    <favourite name="{}" thumb="{}">{}</favourite>'.format(
            escape(self.name, {"'": "&apos;", '"': "&quot;"}),
            escape(self.thumb, {"'": "&apos;", '"': "&quot;"}),
            escape(self.url)
        )

class FavouritesEngine:
    """Gestiona la carga, guardado y backup de favoritos."""
    def __init__(self):
        self._entries = []

    @property
    def entries(self):
        return self._entries

    @entries.setter
    def entries(self, value):
        self._entries = value

    def load(self):
        self._entries = []
        if not os.path.exists(PATHS['favourites']):
            return False

        try:
            tree = ET.parse(PATHS['favourites'])
            root = tree.getroot()
            if root.tag == 'favourites':
                for child in root:
                    if child.tag == 'favourite':
                        self._entries.append(FavouriteEntry.from_xml_element(child))
            return True
        except Exception as e:
            log_debug("Load Error: " + str(e))
            return False

    def load_original(self):
        """Recarga favoritos desde disco y devuelve la lista."""
        self.load()
        return self._entries

    def save(self, xml_content=None):
        """Guarda los favoritos en disco. Si xml_content es None, serializa self.entries."""

        # Generar XML si no se proporciona
        if xml_content is None:
            try:
                lines = ['<favourites>']
                for entry in self._entries:
                    lines.append(entry.to_xml_string())
                lines.append('</favourites>')
                xml_content = "\n".join(lines)
            except Exception as e:
                log_debug("Serialization Error: " + str(e))
                return False

        # 1. Crear backup automático
        try:
            if os.path.exists(PATHS['favourites']):
                shutil.copy(PATHS['favourites'], PATHS['backup'])
        except Exception as e:
            log_debug("Backup Error: " + str(e))

        # 2. Guardar nuevo contenido atómicamente
        tmp_path = PATHS['favourites'] + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(tmp_path, PATHS['favourites'])
            return True
        except Exception as e:
            log_debug("Save Error: " + str(e))
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def generate_xml(self, entries):
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<favourites>\n'
        for entry in entries:
            xml += entry.to_xml_string() + '\n'
        xml += '</favourites>\n'
        return xml

    def enrich_missing_icons(self):
        """Intenta buscar iconos para favoritos que no tienen."""
        count = 0
        for entry in self._entries:
            if not entry.thumb:
                match = re.search(r'^plugin://([^/]+)/', entry.url)
                if match:
                    addon_id = match.group(1)
                    try:
                        addon = xbmcaddon.Addon(addon_id)
                        icon = addon.getAddonInfo('icon')
                        if icon:
                            entry.thumb = icon
                            entry.auto_icon = True
                            count += 1
                    except:
                        pass
        return count

# --- FUNCIONES DE PERFILES (Migradas) ---

def get_profiles():
    """Devuelve una lista de perfiles disponibles (archivos .json)."""
    profiles = []
    if not os.path.exists(PATHS['profiles']): return []

    for f in os.listdir(PATHS['profiles']):
        if f.endswith('.json'):
            path = os.path.join(PATHS['profiles'], f)
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    mod_time = os.path.getmtime(path)
                    import datetime
                    date_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')

                    profiles.append({
                        'filename': f,
                        'name': data.get('name', f.replace('.json', '')),
                        'date': date_str,
                        'entries': data.get('entries', [])
                    })
            except: pass
    return sorted(profiles, key=lambda x: x['name'])

def save_profile(name, entries):
    """Guarda la lista de entradas como un perfil."""
    filename = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip() + ".json"
    path = os.path.join(PATHS['profiles'], filename)

    # Serializar objetos FavouriteEntry a diccionarios
    data = {
        'name': name,
        'entries': [{'name': e.name, 'thumb': e.thumb, 'url': e.url} for e in entries]
    }

    # Asegurar que el directorio existe
    if not os.path.exists(PATHS['profiles']):
        os.makedirs(PATHS['profiles'])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return True

def load_profile(filename):
    """Carga entradas desde un perfil."""
    path = os.path.join(PATHS['profiles'], filename)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return [FavouriteEntry(e['name'], e['thumb'], e['url']) for e in data.get('entries', [])]

def delete_profile(filename):
    """Elimina un archivo de perfil."""
    path = os.path.join(PATHS['profiles'], filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
