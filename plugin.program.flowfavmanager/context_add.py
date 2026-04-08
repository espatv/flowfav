# -*- coding: utf-8 -*-
"""
Script para el menú contextual global.
Permite añadir cualquier elemento de Kodi a un perfil de Flow FavManager.
"""
import sys
import xbmc
import xbmcgui
import xbmcaddon

# Importar funciones de la base de datos
from resources.lib.database import (
    FavouriteEntry,
    get_profiles,
    load_profile,
    save_profile
)

ADDON = xbmcaddon.Addon()

def get_string(string_id):
    return ADDON.getLocalizedString(string_id)

def log(msg):
    xbmc.log('[Flow FavManager Context] ' + str(msg), xbmc.LOGINFO)

def get_selected_item_info():
    """Obtiene la información del elemento seleccionado en Kodi."""
    # Usar InfoLabels para obtener datos del ListItem actual
    name = xbmc.getInfoLabel('ListItem.Label')
    thumb = xbmc.getInfoLabel('ListItem.Thumb') or xbmc.getInfoLabel('ListItem.Icon')

    # La URL puede venir de diferentes fuentes
    url = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    if not url:
        url = xbmc.getInfoLabel('ListItem.Path')
    if not url:
        url = xbmc.getInfoLabel('ListItem.FolderPath')

    return name, thumb, url

def normalize_url(url):
    """Convierte URLs capturadas a formato válido para favoritos de Kodi."""
    import re

    if not url:
        return url

    # script://addon.id/ → RunAddon("addon.id")
    match = re.match(r'^script://([^/]+)/?', url)
    if match:
        addon_id = match.group(1)
        return f'RunAddon("{addon_id}")'

    # Si ya es un formato válido, dejarlo igual
    # plugin://, RunAddon, RunScript, ActivateWindow, etc.
    return url

def main():
    # 1. Obtener información del elemento seleccionado
    name, thumb, url = get_selected_item_info()

    # Normalizar URL a formato válido de Kodi
    url = normalize_url(url)

    if not name or not url:
        xbmcgui.Dialog().notification(
            get_string(30030), # "Flow FavManager"
            get_string(30031), # "No se pudo obtener la información del elemento"
            xbmcgui.NOTIFICATION_WARNING
        )
        return

    log(f"Capturado: {name} | {url[:50]}...")

    # 2. Obtener lista de perfiles
    profiles = get_profiles()

    if not profiles:
        # No hay perfiles, ofrecer crear uno
        if xbmcgui.Dialog().yesno(
            get_string(30032), # "Sin Perfiles"
            get_string(30033)  # "No tienes ningún perfil creado.\n¿Quieres crear uno ahora?"
        ):
            kb = xbmc.Keyboard(get_string(30034), get_string(30035)) # "Mis Favoritos", "Nombre del nuevo perfil"
            kb.doModal()
            if kb.isConfirmed() and kb.getText():
                profile_name = kb.getText()
                new_entry = FavouriteEntry(name, thumb, url)
                if save_profile(profile_name, [new_entry]):
                    xbmcgui.Dialog().notification(
                        get_string(30036), # "Perfil Creado"
                        get_string(30037).format(name, profile_name), # "'{name}' añadido a '{profile_name}'"
                        xbmcgui.NOTIFICATION_INFO
                    )
        return

    # 3. Mostrar selector de perfiles
    profile_names = [p['name'] for p in profiles]
    profile_names.append(get_string(30038)) # "[COLOR lime]+ Crear Nuevo Perfil[/COLOR]"

    sel = xbmcgui.Dialog().select(
        get_string(30039).format(name[:30]), # "Añadir '{name[:30]}...' a:"
        profile_names
    )

    if sel < 0:
        return  # Cancelado

    # 4. Crear nuevo perfil o añadir a existente
    if sel == len(profiles):
        # Crear nuevo perfil
        kb = xbmc.Keyboard('', get_string(30035)) # Reuse "Nombre del nuevo perfil"
        kb.doModal()
        if not kb.isConfirmed() or not kb.getText():
            return

        profile_name = kb.getText()
        new_entry = FavouriteEntry(name, thumb, url)

        if save_profile(profile_name, [new_entry]):
            xbmcgui.Dialog().notification(
                get_string(30036), # Reuse "Perfil Creado"
                get_string(30037).format(name, profile_name), # Reuse "'{name}' añadido a '{profile_name}'"
                xbmcgui.NOTIFICATION_INFO
            )
    else:
        # Añadir a perfil existente
        selected_profile = profiles[sel]

        try:
            # Cargar entradas existentes
            existing_entries = load_profile(selected_profile['filename'])

            # Verificar si ya existe (por URL)
            for entry in existing_entries:
                if entry.url == url:
                    xbmcgui.Dialog().notification(
                        get_string(30040), # "Ya Existe"
                        get_string(30041).format(name, selected_profile['name']), # "'{name}' ya está en '{name}'"
                        xbmcgui.NOTIFICATION_INFO
                    )
                    return

            # Añadir nuevo elemento
            new_entry = FavouriteEntry(name, thumb, url)
            existing_entries.append(new_entry)

            # Guardar perfil actualizado (usando el nombre original)
            if save_profile(selected_profile['name'], existing_entries):
                xbmcgui.Dialog().notification(
                    get_string(30042), # "Añadido"
                    get_string(30043).format(name[:20], selected_profile['name']), # "'{name}' -> '{name}'"
                    xbmcgui.NOTIFICATION_INFO,
                    3000
                )
                log(f"Éxito: {name} añadido a {selected_profile['name']}")
            else:
                xbmcgui.Dialog().notification(
                    get_string(30044), # "Error"
                    get_string(30045), # "Fallo al guardar el perfil"
                    xbmcgui.NOTIFICATION_ERROR
                )
        except Exception as e:
            log(f"Error: {e}")
            xbmcgui.Dialog().notification(
                get_string(30044), # Reuse "Error"
                get_string(30046), # "No se pudo añadir al perfil"
                xbmcgui.NOTIFICATION_ERROR
            )

if __name__ == '__main__':
    main()
