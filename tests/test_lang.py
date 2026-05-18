"""Tests for language support."""
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class TestLanguage:
    def test_lang_en_returns_english(self, game):
        state = game.start(seed="lang_en1", lang="en")
        # Neow event — card names should be English
        player = state.get("player", {})
        deck = player.get("deck", [])
        assert any("Strike" in str(c.get("name", "")) for c in deck), \
            f"Expected English card names, got: {[c['name'] for c in deck[:3]]}"

    def test_lang_zh_returns_chinese(self, game):
        state = game.start(seed="lang_zh1", lang="zh")
        player = state.get("player", {})
        deck = player.get("deck", [])
        # Check for Chinese characters (unicode > 0x4e00)
        names = [c.get("name", "") for c in deck]
        has_chinese = any(any(ord(ch) > 0x4e00 for ch in name) for name in names)
        assert has_chinese, f"Expected Chinese card names, got: {names[:3]}"

    def test_default_lang_is_english(self, game):
        """Without lang param, should default to English."""
        state = game.send({"cmd": "start_run", "character": "Ironclad", "seed": "lang_def1"})
        player = state.get("player", {})
        deck = player.get("deck", [])
        names = [c.get("name", "") for c in deck]
        # Should be English (no Chinese characters)
        has_chinese = any(any(ord(ch) > 0x4e00 for ch in name) for name in names)
        assert not has_chinese, f"Expected English by default, got: {names[:3]}"


def test_zhs_relics_include_current_engine_winged_boots_text():
    relics = json.loads((ROOT / "localization_zhs" / "relics.json").read_text(encoding="utf-8"))

    assert "WINGED_BOOTS.title" in relics
    assert "Winged Boots" not in relics["WINGED_BOOTS.title"]
    assert any("\u4e00" <= ch <= "\u9fff" for ch in relics["WINGED_BOOTS.description"])
