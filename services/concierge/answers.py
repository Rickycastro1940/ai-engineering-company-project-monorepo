"""Grounded concierge replies from the existing menu catalogue and location roster.

Prices are the list prices on ``GET /menus`` (COP and USD). Locations are the
14 restaurants on ``GET /locations``. Nothing here invents a dish or a site.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_ORDER_WORDS = (
    "order",
    "i'd like",
    "i would like",
    "i want",
    "add",
    "get me",
    "take",
    "quiero",
    "pidame",
    "pídeme",
    "para llevar",
    "me llevo",
    "agrega",
)
_ALLERGEN_WORDS = (
    "allergen",
    "allergy",
    "allergic",
    "soy",
    "gluten",
    "dairy",
    "nut",
    "peanut",
    "sulfite",
    "egg",
    "alergeno",
    "alérgeno",
    "alergia",
)
_MENU_WORDS = (
    "menu",
    "menú",
    "price",
    "prices",
    "cost",
    "how much",
    "cuanto",
    "cuánto",
    "precio",
    "carta",
)
_CONFIRM_WORDS = ("confirm", "place it", "place the order", "yes place", "confirmar", "confirmo")
_CANCEL_WORDS = ("cancel", "never mind", "nevermind", "cancela", "cancelar")
_QTY_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "un": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
}
_QTY_BEFORE = re.compile(
    r"(?:(\d+)|a|an|one|two|three|four|five|six|un|una|dos|tres|cuatro)\s+$",
    re.IGNORECASE,
)
_CROSS = "Zero cross-contamination risk is never guaranteed."
_GREETING = re.compile(r"^(hi|hello|hey|hola|buenas|good morning|good afternoon)\b[.! ]*$", re.I)


def fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def money_cop(amount: int | float) -> str:
    return f"{int(round(amount)):,} COP"


def money_usd(amount: float) -> str:
    return f"{amount:,.2f} USD"


def both_prices(price_cop: int | float, price_usd: float, lead: str | None) -> str:
    cop = money_cop(price_cop)
    usd = money_usd(price_usd)
    if lead == "USD":
        return f"{usd} (listed at {cop})"
    if lead == "COP":
        return f"{cop} (listed at {usd})"
    return f"{cop} and {usd}"


def menu_items() -> list[Any]:
    from menus import list_menu_items

    return list(list_menu_items())


def locations() -> list[Any]:
    from locations import location_roster

    return list(location_roster())


def _aliases(item: Any) -> list[str]:
    names = [fold(item.name), fold(item.name_es), item.id.replace("-", " ")]
    if item.id == "grilled-sirloin":
        names.append("sirloin")
    elif item.id == "bbq-ribs":
        names.extend(["ribs", "costillas"])
    elif item.id == "grilled-chicken":
        names.extend(["chicken", "pollo"])
    elif item.id == "tropical-salad":
        names.extend(["salad", "ensalada"])
    elif item.id == "corn-arepa":
        names.append("arepa")
    elif item.id == "house-sauce":
        names.extend(["house sauce", "salsa"])
    unique: list[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    unique.sort(key=len, reverse=True)
    return unique


def _find_items(folded: str) -> list[tuple[int, Any, str]]:
    found: list[tuple[int, Any, str]] = []
    for item in menu_items():
        best: tuple[int, str] | None = None
        for alias in _aliases(item):
            index = folded.find(alias)
            if index < 0:
                continue
            if best is None or len(alias) > len(best[1]):
                best = (index, alias)
        if best is not None:
            found.append((best[0], item, best[1]))
    found.sort(key=lambda row: row[0])
    return found


def _quantity_before(folded: str, index: int) -> int:
    window = folded[max(0, index - 24) : index]
    match = _QTY_BEFORE.search(window)
    if not match:
        return 1
    digits = match.group(1)
    if digits:
        qty = int(digits)
        return qty if qty > 0 else 1
    word = match.group(0).split()[0].lower()
    return _QTY_WORDS.get(word, 1)


def _match_locations(folded: str) -> list[Any]:
    hits: list[tuple[int, Any]] = []
    for location in locations():
        aliases = [fold(location.name), fold(location.city), location.id.replace("-", " ")]
        best = 0
        for alias in aliases:
            if alias and alias in folded:
                best = max(best, len(alias))
        if best:
            hits.append((best, location))
    if not hits:
        return []
    longest = max(score for score, _location in hits)
    chosen: dict[str, Any] = {}
    for score, location in hits:
        if score == longest:
            chosen[location.id] = location
    return list(chosen.values())


def _lead_currency(folded: str, location: Any | None) -> str | None:
    if location is not None:
        return location.currency
    if "florida" in folded or "usd" in folded or "miami" in folded:
        return "USD"
    if "colombia" in folded or "cop" in folded:
        return "COP"
    return None


def _contains_any(folded: str, words: tuple[str, ...]) -> bool:
    return any(fold(word) in folded for word in words)


def _allergen_sentence(item: Any) -> str:
    if item.allergens:
        listed = ", ".join(item.allergens)
        return f"{item.name} declares {listed}."
    return (
        f"{item.name} has no declared allergens on the chain menu "
        "(gluten-free, dairy-free, nut-free)."
    )


def _fresh_order() -> dict[str, Any]:
    return {
        "status": "draft",
        "location_id": None,
        "location_name": None,
        "currency": None,
        "lines": [],
        "total_cop": 0,
        "total_usd": 0.0,
    }


def _ensure_order(session: dict[str, Any]) -> dict[str, Any]:
    order = session.get("order")
    if not isinstance(order, dict) or order.get("status") == "placed":
        order = _fresh_order()
        session["order"] = order
    return order


def _reprice(order: dict[str, Any]) -> None:
    order["total_cop"] = int(sum(line["line_cop"] for line in order["lines"]))
    order["total_usd"] = round(sum(line["line_usd"] for line in order["lines"]), 2)


def _add_lines(order: dict[str, Any], folded: str, found: list[tuple[int, Any, str]]) -> list[Any]:
    added = []
    for index, item, _alias in found:
        qty = _quantity_before(folded, index)
        line_cop = int(item.price_cop) * qty
        line_usd = round(float(item.price_usd) * qty, 2)
        existing = next((line for line in order["lines"] if line["item_id"] == item.id), None)
        if existing is None:
            order["lines"].append(
                {
                    "item_id": item.id,
                    "name": item.name,
                    "quantity": qty,
                    "unit_price_cop": int(item.price_cop),
                    "unit_price_usd": float(item.price_usd),
                    "line_cop": line_cop,
                    "line_usd": line_usd,
                    "allergens": list(item.allergens),
                }
            )
        else:
            existing["quantity"] += qty
            existing["line_cop"] = existing["unit_price_cop"] * existing["quantity"]
            existing["line_usd"] = round(existing["unit_price_usd"] * existing["quantity"], 2)
        added.append(item)
    _reprice(order)
    return added


def _apply_location(order: dict[str, Any], location: Any) -> None:
    order["location_id"] = location.id
    order["location_name"] = location.name
    order["currency"] = location.currency


def _line_text(order: dict[str, Any]) -> str:
    lead = order.get("currency")
    parts = []
    for line in order["lines"]:
        parts.append(
            f"{line['quantity']} {line['name']} — "
            f"{both_prices(line['line_cop'], line['line_usd'], lead)}"
        )
    return "; ".join(parts)


def _order_reply(session: dict[str, Any], folded: str) -> str:
    order = _ensure_order(session)
    if order["status"] == "cancelled":
        order = _fresh_order()
        session["order"] = order
    found = _find_items(folded)
    sites = _match_locations(folded)
    if len(sites) > 1:
        names = " and ".join(site.name for site in sites)
        return (
            f"That matches more than one kitchen: {names}. "
            "Which location should I use for this order?"
        )
    if len(sites) == 1:
        _apply_location(order, sites[0])
    added: list[Any] = []
    if found:
        added = _add_lines(order, folded, found)
    elif not order["lines"] and not sites:
        names = ", ".join(item.name for item in menu_items())
        return f"Which dish should I add? The menu is the same in all 14 kitchens: {names}."
    if not order["lines"]:
        names = ", ".join(item.name for item in menu_items())
        where = order["location_name"] or "that kitchen"
        return f"I can take an order at {where} once you name a dish. The menu is: {names}."
    notes = []
    for item in added:
        if item.allergens:
            notes.append(_allergen_sentence(item))
    note = (" " + " ".join(notes) + f" {_CROSS}") if notes else ""
    summary = _line_text(order)
    if not order["location_id"]:
        return (
            f"Added {summary}. Which of the 14 locations should I send this to? "
            f"Colombia kitchens charge COP and Florida kitchens charge USD.{note}"
        )
    pay = both_prices(order["total_cop"], order["total_usd"], order["currency"])
    return (
        f"Draft for {order['location_name']}: {summary}. "
        f"Pay {pay}. Say confirm to place this guest order.{note}"
    )


def _confirm(session: dict[str, Any]) -> str:
    order = session.get("order") or _fresh_order()
    if not order.get("lines"):
        return "There is nothing to place yet. Tell me a dish and a location."
    if not order.get("location_id"):
        return "Tell me which location should receive this order before I place it."
    order["status"] = "placed"
    session["order"] = order
    pay = both_prices(order["total_cop"], order["total_usd"], order["currency"])
    return (
        f"Placed at {order['location_name']}. Pay {pay}. "
        "This is a guest order for the kitchen, not a point-of-sale ticket."
    )


def _cancel(session: dict[str, Any]) -> str:
    session["order"] = _fresh_order()
    session["order"]["status"] = "cancelled"
    return "I cancelled that draft. The menu is still the same in every kitchen."


def _allergen_reply(folded: str, lead: str | None) -> str:
    found = _find_items(folded)
    if not found:
        if "gluten" in folded:
            safe = [item.name for item in menu_items() if item.gluten_free and "gluten" not in item.allergens]
            listed = ", ".join(safe)
            return (
                f"Gluten-free dishes on the chain menu: {listed}. "
                f"Brasaland BBQ Ribs are not certified gluten-free. {_CROSS}"
            )
        names = ", ".join(item.name for item in menu_items())
        return f"Which dish should I check? The menu is: {names}. {_CROSS}"
    parts = []
    for _index, item, _alias in found:
        price = both_prices(item.price_cop, item.price_usd, lead)
        parts.append(f"{_allergen_sentence(item)} Listed at {price}.")
    parts.append(
        "The kitchen uses clean utensils and a surface separate from the general prep area. "
        + _CROSS
    )
    return " ".join(parts)


def _menu_reply(folded: str, lead: str | None, location: Any | None) -> str:
    found = _find_items(folded)
    items = [item for _index, item, _alias in found] or menu_items()
    if location is not None:
        where = f"At {location.name} the bill is in {location.currency}."
    elif lead == "USD":
        where = "Florida kitchens charge USD. The same plates are listed in COP in Colombia."
    elif lead == "COP":
        where = "Colombia kitchens charge COP. The same plates are listed in USD in Florida."
    else:
        where = "Every kitchen serves the same menu. Colombia lists COP and Florida lists USD."
    lines = [
        f"{item.name}: {both_prices(item.price_cop, item.price_usd, lead)}"
        for item in items
    ]
    return where + " " + "; ".join(lines) + "."


def _welcome() -> str:
    return (
        "Welcome to Brasaland. I can read the menu in COP and USD, check allergens, "
        "or take an order for one of the 14 kitchens. The plates are the same in Medellín and Miami."
    )


def reply(session: dict[str, Any], text: str) -> str:
    """Update ``session['order']`` when the guest is ordering, and return the full answer."""
    raw = (text or "").strip()
    folded = fold(raw)
    if not folded:
        return "Tell me a dish, an allergen question, or the location for an order."
    if _GREETING.match(raw):
        return _welcome()
    sites = _match_locations(folded)
    location = sites[0] if len(sites) == 1 else None
    lead = _lead_currency(folded, location)
    order_intent = _contains_any(folded, _ORDER_WORDS)
    confirming = _contains_any(folded, _CONFIRM_WORDS) and not order_intent
    cancelling = _contains_any(folded, _CANCEL_WORDS) and not order_intent
    current = session.get("order") or {}
    if confirming and current.get("lines"):
        return _confirm(session)
    if cancelling and current:
        return _cancel(session)
    if order_intent or (_find_items(folded) and _match_locations(folded) and not _contains_any(folded, _ALLERGEN_WORDS)):
        if order_intent or (location and _find_items(folded) and not _contains_any(folded, _MENU_WORDS)):
            return _order_reply(session, folded)
    if _contains_any(folded, _ALLERGEN_WORDS):
        return _allergen_reply(folded, lead)
    if _contains_any(folded, _MENU_WORDS) or _find_items(folded) or location is not None or "florida" in folded:
        if len(sites) > 1 and not _find_items(folded):
            names = " and ".join(site.name for site in sites)
            return (
                f"That matches more than one kitchen: {names}. "
                "Prices are the same list in each market. Which location do you mean?"
            )
        return _menu_reply(folded, lead, location)
    return _welcome()


def stream_chunks(text: str, words_per_chunk: int = 4) -> list[str]:
    """Split a finished answer into token deltas. The joined chunks equal ``text``."""
    words = text.split(" ")
    if not words:
        return []
    chunks: list[str] = []
    for index in range(0, len(words), words_per_chunk):
        piece = " ".join(words[index : index + words_per_chunk])
        if index + words_per_chunk < len(words):
            piece += " "
        chunks.append(piece)
    return chunks
