"""Guest menu card stays aligned with the chain catalogue."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.api.menus import _ITEMS  # pylint: disable=wrong-import-position

SITE = REPO_ROOT / "uis" / "website-classic"
MENU_HTML = (SITE / "menu.html").read_text(encoding="utf-8")
ALLERGENS_HTML = (SITE / "allergens.html").read_text(encoding="utf-8")
LANG_JS = (SITE / "lang.js").read_text(encoding="utf-8")


def _cop(amount: int) -> str:
    return f"COP ${amount:,}".replace(",", ".")


def _usd(amount: float) -> str:
    whole = int(amount)
    if amount == whole:
        return f"USD ${whole}"
    return f"USD ${amount}"


def _lang_keys(source: str, language: str) -> set[str]:
    match = re.search(rf"{language}: \{{(.*?)\n        \}}", source, flags=re.S)
    assert match, language
    return set(re.findall(r'"([^"]+)":', match.group(1)))


def test_public_card_lists_every_catalogue_item_in_cop_and_usd() -> None:
    assert len(_ITEMS) == 14
    categories = {item.category for item in _ITEMS}
    assert categories == {"main", "side", "sauce"}
    for item in _ITEMS:
        assert item.name in MENU_HTML
        assert item.name in ALLERGENS_HTML
        assert _cop(item.price_cop) in MENU_HTML
        assert _usd(item.price_usd) in MENU_HTML
        assert item.available_in == ["Colombia", "Florida"]
    assert "Grilled Picanha" in MENU_HTML
    assert "Chimichurri" in MENU_HTML
    assert "Vinagrete" in MENU_HTML
    assert "Six dishes" not in MENU_HTML


def test_menu_copy_exists_in_english_and_spanish() -> None:
    english = _lang_keys(LANG_JS, "en")
    spanish = _lang_keys(LANG_JS, "es")
    used = set(re.findall(r'data-i18n="([^"]+)"', MENU_HTML))
    used |= set(re.findall(r'data-i18n-alt="([^"]+)"', MENU_HTML))
    missing_en = sorted(key for key in used if key not in english)
    missing_es = sorted(key for key in used if key not in spanish)
    assert missing_en == []
    assert missing_es == []
    assert "menu.picanha.copy" in spanish
    assert "Picanha a la brasa" in LANG_JS
    assert "Yuca frita" in LANG_JS
