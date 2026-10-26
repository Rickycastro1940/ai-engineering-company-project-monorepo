"""Public-site snapshot: Brasaland menu and location HTML only."""

from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest

from data.pipelines.public_site_snapshot import (
    PublicSiteParser,
    PublicSiteSnapshot,
    assert_allowed_url,
)

MENU_HTML = """
<html><head><title>Menu — Brasaland</title>
<meta name="description" content="Six grilled dishes." />
</head><body>
<article class="card menu-row">
  <img src="images/menu-grilled-sirloin.jpg" alt="sirloin" />
  <p class="menu-kind">Main · grilled</p>
  <h3>Grilled Sirloin</h3>
  <p class="menu-also">Lomo a la Brasa</p>
  <p class="menu-copy">Beef sirloin over the brasa, with a marinade.</p>
  <p class="menu-allergens">Contains soy.</p>
</article>
<article class="card">
  <h3>Not a dish</h3>
</article>
</body></html>
"""

LOCATIONS_HTML = """
<html><head><title>Locations — Brasaland</title></head><body>
<p class="lede">Colombia and Florida.</p>
<table>
<tr><td>bogota-norte</td><td data-i18n="loc.country.co">Colombia</td><td>COP</td></tr>
<tr><td>miami-downtown</td><td>United States</td><td>USD</td></tr>
</table>
</body></html>
"""


def test_parser_reads_menu_dishes_and_skips_other_cards():
    records = PublicSiteParser.parse(MENU_HTML, "https://www.brasalandrestaurant.com/menu.html")
    pages = [row for row in records if row.record_type == "page"]
    dishes = [row for row in records if row.record_type == "menu_dish"]
    assert pages[0].title == "Menu — Brasaland"
    assert pages[0].summary == "Six grilled dishes."
    assert len(dishes) == 1
    assert dishes[0].name == "Grilled Sirloin"
    assert dishes[0].also_known_as == "Lomo a la Brasa"
    assert dishes[0].allergens == "Contains soy."
    assert dishes[0].image_url.endswith("/images/menu-grilled-sirloin.jpg")


def test_parser_reads_location_currency():
    records = PublicSiteParser.parse(LOCATIONS_HTML, "https://www.brasalandrestaurant.com/locations.html")
    locations = [row for row in records if row.record_type == "location"]
    assert [(row.location_id, row.currency) for row in locations] == [
        ("bogota-norte", "COP"),
        ("miami-downtown", "USD"),
    ]
    assert records[0].summary == "Colombia and Florida."


def test_refuses_hosts_outside_brasaland():
    with pytest.raises(ValueError):
        assert_allowed_url("https://quotes.toscrape.com/")


def test_pipeline_retries_then_writes_jsonl_and_sqlite(tmp_path):
    menu_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("menu.html"):
            menu_calls["n"] += 1
            if menu_calls["n"] == 1:
                return httpx.Response(503, text="busy")
            return httpx.Response(200, text=MENU_HTML)
        return httpx.Response(200, text=LOCATIONS_HTML)

    snapshot = PublicSiteSnapshot(
        base_url="http://127.0.0.1:9",
        paths=("/menu.html", "/locations.html"),
        delay=0,
        jsonl_path=tmp_path / "snapshot.jsonl",
        sqlite_path=tmp_path / "snapshot.sqlite3",
    )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await snapshot.run(client)

    records = asyncio.run(run())
    assert menu_calls["n"] == 2
    kinds = {row.record_type for row in records}
    assert kinds == {"page", "menu_dish", "location"}

    lines = (tmp_path / "snapshot.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["name"] == "Grilled Sirloin" for line in lines if '"menu_dish"' in line)

    with sqlite3.connect(tmp_path / "snapshot.sqlite3") as connection:
        dish = connection.execute("SELECT name, kind FROM menu_dishes").fetchone()
        currencies = connection.execute("SELECT currency FROM locations ORDER BY location_id").fetchall()
    assert dish == ("Grilled Sirloin", "Main · grilled")
    assert currencies == [("COP",), ("USD",)]
