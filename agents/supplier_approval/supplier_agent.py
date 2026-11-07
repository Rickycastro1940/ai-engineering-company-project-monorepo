"""Supplier Agent — turn an incoming application into directory fields.

Procurement (Lucía Fernández) collects the same fields as the public supplier
form and `GET /suppliers`: name, country, categories, emergency surcharge, status.
Colombia maps to COP; the United States maps to Florida and USD.
"""

from __future__ import annotations

import re

FOOD_CATEGORIES = ("proteins", "vegetables_and_fruit", "sauces", "beverages")
KNOWN_CATEGORIES = FOOD_CATEGORIES + ("packaging", "cleaning")

_STATUS = {
    "active": "active",
    "preferred": "preferred",
    "inactive": "inactive",
    "suspend": "inactive",
    "suspended": "inactive",
}


def _add(found: list[str], category: str) -> None:
    if category not in found:
        found.append(category)


def categories_from_text(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    if "beverages_and_packaging" in lowered:
        _add(found, "beverages")
        _add(found, "packaging")
    if "imported_sauces_and_condiments" in lowered or re.search(r"\bsauces?\b", lowered):
        _add(found, "sauces")
    if "vegetables_and_fruit" in lowered or re.search(r"\b(vegetables|produce|fruit)\b", lowered):
        _add(found, "vegetables_and_fruit")
    if re.search(r"\b(proteins?|beef|chicken|poultry|meat)\b", lowered):
        _add(found, "proteins")
    if re.search(r"\bbeverages?\b", lowered):
        _add(found, "beverages")
    if re.search(r"\bpackaging\b", lowered):
        _add(found, "packaging")
    if re.search(r"\bcleaning\b", lowered):
        _add(found, "cleaning")
    return found


def normalize_categories(values: list[str]) -> list[str]:
    found: list[str] = []
    for value in values:
        token = (value or "").strip().lower()
        if token == "beverages_and_packaging":
            _add(found, "beverages")
            _add(found, "packaging")
        elif token in {"imported_sauces_and_condiments", "sauce", "sauces", "condiments"}:
            _add(found, "sauces")
        elif token in {"vegetables_and_fruit", "vegetables", "produce", "fruit"}:
            _add(found, "vegetables_and_fruit")
        elif token in {"protein", "proteins", "beef", "chicken", "poultry", "meat"}:
            _add(found, "proteins")
        elif token in {"beverage", "beverages"}:
            _add(found, "beverages")
        elif token == "packaging":
            _add(found, "packaging")
        elif token == "cleaning":
            _add(found, "cleaning")
    return found


def _country_from_text(text: str) -> str | None:
    labeled = re.search(
        r"country\s*[:\-]\s*(colombia|united states|usa|u\.s\.a\.|florida)\b",
        text,
        re.IGNORECASE,
    )
    token = labeled.group(1) if labeled else ""
    if not token:
        if re.search(r"\b(united states|u\.s\.a\.|usa|florida)\b", text, re.IGNORECASE):
            token = "united states"
        elif re.search(r"\bcolombia\b", text, re.IGNORECASE):
            token = "colombia"
    token = token.lower()
    if token == "colombia":
        return "Colombia"
    if token in {"united states", "usa", "u.s.a.", "florida"}:
        return "United States"
    return None


def _name_from_text(text: str) -> str | None:
    match = re.search(
        r"(?:legal(?:\s+or\s+trade)?\s+name|trade\s+name|applicant|name)\s*[:\-]\s*([^\n]+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    name = match.group(1).strip(" \t-")
    if len(name) < 2 or name.lower() in {"country", "and country"}:
        return None
    return name[:120]


def _surcharge_from_text(text: str) -> float | None:
    patterns = (
        r"emergency[^\n]{0,80}?(\d+(?:\.\d+)?)\s*%",
        r"surcharge[^\n]{0,40}?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:emergency\s+)?surcharge",
        r"emergency_surcharge_pct\s*[:=]\s*(\d+(?:\.\d+)?)",
        r"surcharge\s*[:=]\s*(\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _status_from_text(text: str) -> str | None:
    match = re.search(
        r"\bstatus\s*[:\-]\s*(active|preferred|inactive|suspend|suspended)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _STATUS[match.group(1).lower()]


def _normalize_status(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _STATUS.get(str(value).strip().lower())


def parse_application(payload: dict) -> dict:
    raw_text = str(payload.get("raw_text") or "")
    health_notes = str(payload.get("health_notes") or "")
    combined = "\n".join(part for part in (raw_text, health_notes) if part).strip()

    name = (payload.get("name") or "").strip() or _name_from_text(combined)
    country = _explicit_country(payload.get("country")) or _country_from_text(combined)
    if payload.get("product_categories"):
        categories = normalize_categories(list(payload["product_categories"]))
    else:
        categories = categories_from_text(combined)
    if payload.get("emergency_surcharge_pct") is not None:
        surcharge = float(payload["emergency_surcharge_pct"])
    else:
        surcharge = _surcharge_from_text(combined)
    status = _normalize_status(payload.get("status"))
    if status is None:
        status = _status_from_text(combined)

    market = None
    currency = None
    if country == "Colombia":
        market, currency = "Colombia", "COP"
    elif country == "United States":
        market, currency = "Florida", "USD"

    gaps: list[str] = []
    if not name or len(name) < 2:
        gaps.append("Legal or trade name is missing.")
    if country not in {"Colombia", "United States"}:
        gaps.append("Country must be Colombia or the United States.")
    if not categories:
        gaps.append("At least one product category is required.")

    return {
        "name": name or None,
        "country": country,
        "market": market,
        "currency": currency,
        "categories": categories,
        "emergency_surcharge_pct": surcharge,
        "status": status,
        "raw_text": raw_text,
        "health_notes": health_notes,
        "review_text": combined,
        "complete": not gaps,
        "gaps": gaps,
    }


def _explicit_country(value: object) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    if token == "colombia":
        return "Colombia"
    if token in {"united states", "usa", "u.s.a.", "florida"}:
        return "United States"
    if token:
        return "invalid"
    return None


def run(state: dict) -> dict:
    parsed = parse_application(state["input"])
    state["parsed"] = parsed
    state["trace"].append("supplier")
    return state
