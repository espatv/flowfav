# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
from resources.lib.utils import log_debug

def check_broken_links(entries):
    """
    Escanea las entradas de favoritos y detecta enlaces rotos.
    Devuelve dos listas: una con las entradas válidas y otra con las rotas.
    """
    valid_entries = []
    broken_entries = []

    for entry in entries:
        if not entry.url:
            broken_entries.append(entry)
            continue

        # Comprobar URLs de addons (plugin://) o comandos de ejecución (RunAddon)
        is_broken = False

        # 1. Chequeo de plugin://
        if entry.url.startswith('plugin://'):
            addon_id = entry.url.split('/')[2]
            try:
                # Intentamos instanciar el addon, si falla es que no está instalado
                xbmcaddon.Addon(id=addon_id)
            except Exception:
                is_broken = True

        # 2. Chequeo de script://
        elif entry.url.startswith('script://'):
            addon_id = entry.url.split('/')[2]
            try:
                xbmcaddon.Addon(id=addon_id)
            except Exception:
                is_broken = True

        # 3. Chequeo de RunAddon() o RunScript()
        elif 'RunAddon(' in entry.url or 'RunScript(' in entry.url:
            # Extraer el ID del addon de RunAddon(id) o RunScript(id, ...)
            import re
            match = re.search(r'(?:RunAddon|RunScript)\((["\']?)([^,"\'\)]+)\1', entry.url)
            if match:
                addon_id = match.group(2).strip()
                try:
                    xbmcaddon.Addon(id=addon_id)
                except Exception:
                    is_broken = True

        if is_broken:
            log_debug(f"Enlace roto detectado: {entry.name} - {entry.url}")
            broken_entries.append(entry)
        else:
            valid_entries.append(entry)

    return valid_entries, broken_entries
