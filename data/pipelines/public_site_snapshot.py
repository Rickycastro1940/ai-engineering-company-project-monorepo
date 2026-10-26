"""Snapshot Brasaland's own public site into JSON Lines and SQLite.

Department: Technology (Nicolás Park — a pipeline into downstream systems) and
Marketing (Camila Ospina — the guest menu, locations, and Brasa Points copy).

Targets the static pages on brasalandrestaurant.com. Those pages are server-rendered
HTML. This job does not open a browser, does not log in, and does not call any
other host. Parsed rows are the guest-facing menu and location list, for a
content check or a later knowledge load. They are not sales, stock, or supplier
invoices.

Depends on httpx and pydantic, which the monorepo API stack already installs.
HTML is read with the standard library.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("brasaland.public_site_snapshot")

ALLOWED_HOSTS = frozenset(
    {
        "brasalandrestaurant.com",
        "www.brasalandrestaurant.com",
        "127.0.0.1",
        "localhost",
    }
)
DEFAULT_PATHS = ("/", "/menu.html", "/locations.html", "/loyalty.html", "/allergens.html")
USER_AGENT = "BrasalandDigital/1.0 (public-site snapshot; +https://www.brasalandrestaurant.com)"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

Record = Union["PublicPage", "MenuDish", "PublicLocation"]


class PublicPage(BaseModel):
    record_type: str = "page"
    url: str
    title: str = Field(..., min_length=1)
    summary: Optional[str] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MenuDish(BaseModel):
    record_type: str = "menu_dish"
    url: str
    name: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    also_known_as: Optional[str] = None
    description: str = Field(..., min_length=1)
    allergens: Optional[str] = None
    image_url: Optional[str] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublicLocation(BaseModel):
    record_type: str = "location"
    url: str
    location_id: str = Field(..., min_length=1)
    country: str = Field(..., min_length=1)
    currency: str = Field(..., pattern="^(COP|USD)$")
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def assert_allowed_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError(
            f"Refusing {url}. This pipeline only reads Brasaland's public site "
            f"or a local test server ({', '.join(sorted(ALLOWED_HOSTS))})."
        )
    return url


class AsyncFetcher:
    def __init__(self, concurrency_limit: int = 2, delay_between_requests: float = 0.5):
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.delay = delay_between_requests
        self.headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}

    async def fetch(self, client: httpx.AsyncClient, url: str) -> str:
        assert_allowed_url(url)
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with self.semaphore:
                    logger.info("Fetching %s", url)
                    response = await client.get(url, headers=self.headers, follow_redirects=True)
                    if response.status_code in RETRY_STATUS:
                        response.raise_for_status()
                    response.raise_for_status()
                    if self.delay > 0:
                        await asyncio.sleep(self.delay)
                    return response.text
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if status is not None and status not in RETRY_STATUS:
                    raise
                await asyncio.sleep(min(10, 2 ** attempt))
        assert last_error is not None
        raise last_error


class PublicSiteParser:
    @staticmethod
    def parse(html: str, page_url: str) -> List[Record]:
        scraped_at = datetime.now(timezone.utc)
        records: List[Record] = [
            PublicPage(
                url=page_url,
                title=_page_title(html),
                summary=_page_summary(html),
                scraped_at=scraped_at,
            )
        ]
        if page_url.rstrip("/").endswith("menu.html") or "/menu.html" in page_url:
            records.extend(_menu_dishes(html, page_url, scraped_at))
        if page_url.rstrip("/").endswith("locations.html") or "/locations.html" in page_url:
            records.extend(_locations(html, page_url, scraped_at))
        return records


class SnapshotExporter:
    def __init__(self, jsonl_path: Path, sqlite_path: Path):
        self.jsonl_path = jsonl_path
        self.sqlite_path = sqlite_path

    def save(self, items: Sequence[Record]) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(item.model_dump_json() + "\n")
        _write_sqlite(self.sqlite_path, items)
        logger.info("Wrote %s records to %s and %s", len(items), self.jsonl_path, self.sqlite_path)


class PublicSiteSnapshot:
    def __init__(
        self,
        base_url: str = "https://www.brasalandrestaurant.com",
        paths: Sequence[str] = DEFAULT_PATHS,
        concurrency: int = 2,
        delay: float = 0.5,
        jsonl_path: Path = Path("data/raw/public_site_snapshot.jsonl"),
        sqlite_path: Path = Path("data/raw/public_site_snapshot.sqlite3"),
    ):
        self.base_url = base_url.rstrip("/")
        self.urls = [assert_allowed_url(urljoin(self.base_url + "/", path.lstrip("/"))) for path in paths]
        self.fetcher = AsyncFetcher(concurrency_limit=concurrency, delay_between_requests=delay)
        self.parser = PublicSiteParser()
        self.exporter = SnapshotExporter(jsonl_path, sqlite_path)

    async def _process_url(self, client: httpx.AsyncClient, url: str) -> List[Record]:
        try:
            html = await self.fetcher.fetch(client, url)
            return self.parser.parse(html, url)
        except Exception as exc:
            logger.error("Failed processing %s: %s", url, exc)
            return []

    async def run(self, client: Optional[httpx.AsyncClient] = None) -> List[Record]:
        if client is None:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as owned:
                return await self._gather(owned)
        return await self._gather(client)

    async def _gather(self, client: httpx.AsyncClient) -> List[Record]:
        batches = await asyncio.gather(*(self._process_url(client, url) for url in self.urls))
        items = [record for batch in batches for record in batch]
        self.exporter.save(items)
        logger.info("Pipeline finished. %s records from %s pages.", len(items), len(self.urls))
        return items


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _page_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
    title = _strip_tags(match.group(1)) if match else ""
    if not title:
        raise ValueError("Public page is missing a title")
    return title


def _page_summary(html: str) -> Optional[str]:
    meta = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.I | re.S,
    )
    if meta is None:
        meta = re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
            html,
            flags=re.I | re.S,
        )
    if meta:
        return _strip_tags(meta.group(1)) or None
    lede = re.search(r'<p[^>]*class="[^"]*\blede\b[^"]*"[^>]*>(.*?)</p>', html, flags=re.I | re.S)
    if lede:
        return _strip_tags(lede.group(1)) or None
    return None


def _class_text(fragment: str, class_name: str) -> Optional[str]:
    match = re.search(
        rf'<(?:p|h3|h2)[^>]*class="[^"]*\b{class_name}\b[^"]*"[^>]*>(.*?)</(?:p|h3|h2)>',
        fragment,
        flags=re.I | re.S,
    )
    if match is None:
        return None
    text = _strip_tags(match.group(1))
    return text or None


def _menu_dishes(html: str, page_url: str, scraped_at: datetime) -> List[MenuDish]:
    dishes: List[MenuDish] = []
    for attrs, body in re.findall(r"<article\b([^>]*)>(.*?)</article>", html, flags=re.I | re.S):
        if "menu-row" not in attrs:
            continue
        heading = re.search(r"<h3[^>]*>(.*?)</h3>", body, flags=re.I | re.S)
        name = _strip_tags(heading.group(1)) if heading else ""
        kind = _class_text(body, "menu-kind") or ""
        description = _class_text(body, "menu-copy") or ""
        if not name or not kind or not description:
            continue
        image = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', body, flags=re.I)
        dishes.append(
            MenuDish(
                url=page_url,
                name=name,
                kind=kind,
                also_known_as=_class_text(body, "menu-also"),
                description=description,
                allergens=_class_text(body, "menu-allergens"),
                image_url=urljoin(page_url, image.group(1)) if image else None,
                scraped_at=scraped_at,
            )
        )
    return dishes


def _locations(html: str, page_url: str, scraped_at: datetime) -> List[PublicLocation]:
    rows: List[PublicLocation] = []
    for location_id, country, currency in re.findall(
        r"<tr>\s*<td>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td>([^<]+)</td>\s*</tr>",
        html,
        flags=re.I,
    ):
        rows.append(
            PublicLocation(
                url=page_url,
                location_id=unescape(location_id).strip(),
                country=unescape(country).strip(),
                currency=unescape(currency).strip(),
                scraped_at=scraped_at,
            )
        )
    return rows


def _write_sqlite(path: Path, items: Iterable[Record]) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS pages;
            DROP TABLE IF EXISTS menu_dishes;
            DROP TABLE IF EXISTS locations;
            CREATE TABLE pages (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT,
                scraped_at TEXT NOT NULL
            );
            CREATE TABLE menu_dishes (
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                kind TEXT NOT NULL,
                also_known_as TEXT,
                description TEXT NOT NULL,
                allergens TEXT,
                image_url TEXT,
                scraped_at TEXT NOT NULL
            );
            CREATE TABLE locations (
                location_id TEXT NOT NULL,
                url TEXT NOT NULL,
                country TEXT NOT NULL,
                currency TEXT NOT NULL,
                scraped_at TEXT NOT NULL
            );
            """
        )
        for item in items:
            if isinstance(item, PublicPage):
                connection.execute(
                    "INSERT INTO pages (url, title, summary, scraped_at) VALUES (?, ?, ?, ?)",
                    (item.url, item.title, item.summary, item.scraped_at.isoformat()),
                )
            elif isinstance(item, MenuDish):
                connection.execute(
                    """
                    INSERT INTO menu_dishes
                    (name, url, kind, also_known_as, description, allergens, image_url, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.name,
                        item.url,
                        item.kind,
                        item.also_known_as,
                        item.description,
                        item.allergens,
                        item.image_url,
                        item.scraped_at.isoformat(),
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO locations (location_id, url, country, currency, scraped_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (item.location_id, item.url, item.country, item.currency, item.scraped_at.isoformat()),
                )


def main(argv: Optional[Sequence[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Snapshot Brasaland's public menu and location pages.")
    parser.add_argument("--base-url", default="https://www.brasalandrestaurant.com")
    parser.add_argument("--jsonl", type=Path, default=Path("data/raw/public_site_snapshot.jsonl"))
    parser.add_argument("--sqlite", type=Path, default=Path("data/raw/public_site_snapshot.sqlite3"))
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args(argv)
    snapshot = PublicSiteSnapshot(
        base_url=args.base_url,
        delay=args.delay,
        jsonl_path=args.jsonl,
        sqlite_path=args.sqlite,
    )
    asyncio.run(snapshot.run())


if __name__ == "__main__":
    main()
