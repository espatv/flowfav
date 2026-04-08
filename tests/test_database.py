import unittest
import os
import sys
import shutil
from unittest.mock import patch, Mock

# Mock the xbmc module and other kodi dependencies
sys.modules['xbmc'] = Mock()
sys.modules['xbmcaddon'] = Mock()
sys.modules['xbmcgui'] = Mock()
sys.modules['xbmcvfs'] = Mock()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../plugin.program.flowfavmanager')))

from resources.lib.database import FavouritesEngine, FavouriteEntry, PATHS

class TestFavouritesEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FavouritesEngine()
        self.test_dir = '/tmp/test_flowfav_db'
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)

        PATHS['favourites'] = os.path.join(self.test_dir, 'favourites.xml')
        PATHS['backup'] = os.path.join(self.test_dir, 'favourites.xml.bak')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_load_empty(self):
        self.assertFalse(self.engine.load())
        self.assertEqual(len(self.engine.entries), 0)

    def test_save_and_load(self):
        entry1 = FavouriteEntry(name="Test1", thumb="icon1.png", url="plugin://test1")
        entry2 = FavouriteEntry(name="Test2", thumb="icon2.png", url="plugin://test2")
        self.engine.entries = [entry1, entry2]

        # Test Save
        self.assertTrue(self.engine.save())
        self.assertTrue(os.path.exists(PATHS['favourites']))
        self.assertFalse(os.path.exists(PATHS['favourites'] + ".tmp"))

        # Test Load
        new_engine = FavouritesEngine()
        self.assertTrue(new_engine.load())
        self.assertEqual(len(new_engine.entries), 2)
        self.assertEqual(new_engine.entries[0].name, "Test1")
        self.assertEqual(new_engine.entries[1].name, "Test2")

    def test_save_creates_backup(self):
        # Initial save
        entry1 = FavouriteEntry(name="Test1", thumb="", url="url1")
        self.engine.entries = [entry1]
        self.engine.save()
        self.assertFalse(os.path.exists(PATHS['backup'])) # Backup not created on first save

        # Modify and save again
        entry2 = FavouriteEntry(name="Test2", thumb="", url="url2")
        self.engine.entries = [entry2]
        self.assertTrue(self.engine.save())
        self.assertTrue(os.path.exists(PATHS['backup'])) # Backup created

    def test_atomic_save_failure_cleanup(self):
        entry1 = FavouriteEntry(name="Test1", thumb="", url="url1")
        self.engine.entries = [entry1]

        with patch('resources.lib.database.shutil.move', side_effect=Exception("Disk Full")):
            result = self.engine.save()
            self.assertFalse(result)
            self.assertFalse(os.path.exists(PATHS['favourites'] + ".tmp")) # Ensure tmp file is cleaned up

if __name__ == '__main__':
    unittest.main()
