"""The loader's Settings constants (loader/settings.c, payload/settings.h) against firmware 2.3."""

import re
import struct
import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "build/fw/osos.img"
sys.path.insert(0, str(ROOT / "tools/re"))


def defines(*paths):
    out = {}
    for p in paths:
        for name, value in re.findall(r"#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)u?\b", (ROOT / p).read_text()):
            out[name] = int(value, 0)
    return out


@pytest.mark.firmware
class SettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from resources import Bundle
        cls.d = IMAGE.read_bytes()
        cls.b = Bundle(str(IMAGE))
        cls.k = defines("loader/settings.c", "payload/settings.h", "payload/holdmenu.h", "payload/letters.h")

    def word(self, addr):
        return struct.unpack_from("<I", self.d, addr)[0]

    def test_bundle_layout(self):
        k = self.k
        self.assertEqual(k["BUNDLE"], 0x181d20)
        self.assertEqual(self.b.data, k["BUNDLE_DATA"])

    def test_settings_entry_and_clicker(self):
        k = self.k
        e = k["SETTINGS_ENTRY"]
        size = 4 + k["SETTINGS_ITEMS"] * 4 * k["MENU_ITEM_WORDS"]
        self.assertEqual([self.word(e + 4 * i) for i in range(3)], [k["SETTINGS_ID"], k["SETTINGS_OFFSET"], size])
        menu = k["BUNDLE"] + k["BUNDLE_DATA"] + k["SETTINGS_OFFSET"]
        self.assertEqual(self.word(menu), k["SETTINGS_ITEMS"])
        clicker = menu + 4 + 40 * k["CLICKER"]
        self.assertEqual(self.word(clicker + 24), k["CLICKER_ITEM"])
        self.assertEqual(self.b.strs[self.word(clicker + 32)], "Clicker")

    def test_values_are_on_and_off(self):
        self.assertEqual(self.b.strs[self.k["SETTING_ON"]], "On")
        self.assertEqual(self.b.strs[self.k["SETTING_OFF"]], "Off")

    def test_our_ids_are_free(self):
        used = {r & 0xffff for entries in self.b.types.values() for r, _, _ in entries}
        for name in ("FROGGER_ITEM_HIDDEN", "FROGGER_STR_HIDDEN", "FROGGER_ITEM_LETTERS", "FROGGER_STR_LETTERS",
                     "FROGGER_ITEM_RESUME", "FROGGER_STR_RESUME"):
            self.assertNotIn(self.k[name], used, name)
        for name in ("FROGGER_ITEM_FLASH", "FROGGER_STR_FLASH", "FROGGER_STR_AUTO", "FROGGER_ITEM_VOLUME", "FROGGER_STR_VOLUME",
                     "FROGGER_STR_QUIET", "FROGGER_STR_MEDIUM", "FROGGER_STR_LOUD", "FROGGER_STR_SPEAKER",
                     "FROGGER_STR_PHONES", "FROGGER_STR_BOTH"):
            self.assertNotIn(self.k[name], used, name)
        for i in range(self.k["FEATURES"]):          # the feature switches: item and label ids
            self.assertNotIn(self.k["FROGGER_ITEM_FEATURE"] + i, used, "feature item %d" % i)
            self.assertNotIn(self.k["FROGGER_STR_FEATURE"] + i, used, "feature label %d" % i)
        for fourcc, names in (("Str ", ("HM_STR_TITLE", "HM_STR_QUEUE", "HM_STR_PLAYLIST", "HM_STR_ADD_TO", "HM_STR_NEXT",
                                        "HM_STR_ALBUM", "HM_STR_ARTIST", "HM_STR_HIDE", "HM_STR_UPNEXT", "HM_STR_REMOVE",
                                        "HM_STR_CLEAR", "HM_STR_SHOW", "HM_STR_AFTER", "HM_STR_QS_SHUFFLE", "HM_STR_QS_REPEAT",
                                        "HM_STR_QS_TIMER", "HM_STR_QS_SLEEP", "HM_STR_QS_CLICKER", "LETTER_STR", "LETTER_STR2")),):
            ids = {r & 0xffff for r, _, _ in self.b.types[fourcc]}
            for name in names:
                self.assertNotIn(self.k[name], ids, name)

    def test_popup_entry(self):
        # Menu 0x25ba, the popup's list (loader/patches.c points it at the payload's hm_popup)
        k = self.k
        e = k["HM_POPUP_ENTRY"]
        self.assertEqual([self.word(e + 4 * i) for i in range(3)], [k["HM_POPUP_ID"], k["HM_POPUP_OFFSET"], k["HM_POPUP_SIZE"]])
        menu = k["BUNDLE"] + k["BUNDLE_DATA"] + k["HM_POPUP_OFFSET"]
        self.assertEqual(self.word(menu), 2)
        self.assertEqual([self.word(menu + 4 + 40 * i + 20) & 0xffff for i in range(2)], [0x25d4, 0x25d5])

    def test_main_entry(self):
        # Menu 0x2512, the main menu (loader/patches.c points it at the payload's hm_main)
        k = self.k
        e = k["HM_MAIN_ENTRY"]
        self.assertEqual([self.word(e + 4 * i) for i in range(3)], [k["HM_MAIN_ID"], k["HM_MAIN_OFFSET"], 4 + 40 * k["HM_MAIN_ITEMS"]])
        menu = k["BUNDLE"] + k["BUNDLE_DATA"] + k["HM_MAIN_OFFSET"]
        self.assertEqual(self.word(menu), k["HM_MAIN_ITEMS"])
        item = lambda i, w: self.word(menu + 4 + 40 * i + 4 * w)
        self.assertEqual(item(k["HM_MAIN_AFTER"], 8), 0x25be)                  # Music
        self.assertEqual(item(k["HM_MAIN_LIKE"], 8), k["HM_MAIN_LABEL"])       # Settings
        self.assertEqual(item(k["HM_MAIN_LIKE"], 1), 0x22)                     # a plain row, with the arrow
        self.assertEqual(item(k["HM_MAIN_LIKE"], 6), 0x2579)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
