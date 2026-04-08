import unittest
import os
import sys
from unittest.mock import patch, Mock

sys.modules['xbmc'] = Mock()
sys.modules['xbmcaddon'] = Mock()
sys.modules['xbmcgui'] = Mock()
sys.modules['xbmcvfs'] = Mock()

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../plugin.program.flowfavmanager')))

from resources.lib.health import check_broken_links
from resources.lib.database import FavouriteEntry

class TestHealthCheck(unittest.TestCase):
    @patch('resources.lib.health.xbmcaddon.Addon')
    def test_check_broken_links(self, mock_addon):
        # Configurar el mock para que falle si el ID es 'addon.roto' y pase si es 'addon.valido'
        def side_effect(id):
            if 'roto' in id:
                raise Exception("Addon no instalado")
            return Mock()
        mock_addon.side_effect = side_effect

        entries = [
            FavouriteEntry(name="Valido 1", thumb="", url="plugin://addon.valido/ruta"),
            FavouriteEntry(name="Roto 1", thumb="", url="plugin://addon.roto/ruta"),
            FavouriteEntry(name="Valido 2", thumb="", url="RunAddon(addon.valido)"),
            FavouriteEntry(name="Roto 2", thumb="", url="RunScript(addon.roto)"),
            FavouriteEntry(name="Vacio", thumb="", url="")
        ]

        valid, broken = check_broken_links(entries)

        self.assertEqual(len(valid), 2)
        self.assertEqual(valid[0].name, "Valido 1")
        self.assertEqual(valid[1].name, "Valido 2")

        self.assertEqual(len(broken), 3)
        self.assertEqual(broken[0].name, "Roto 1")
        self.assertEqual(broken[1].name, "Roto 2")
        self.assertEqual(broken[2].name, "Vacio")

if __name__ == '__main__':
    unittest.main()
