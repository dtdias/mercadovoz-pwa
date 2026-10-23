"""Refresh MercadoVoz catalog from configured public retailer search pages.

The updater keeps the last valid catalog when a source fails. It uses only
public pages, bounded requests, and no login, CAPTCHA bypass, or proxy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "precos.json"
SOURCES_PATH = Path(__file__).with_name("fontes_precos.json")
USER_AGENT = "MercadoVozPriceUpdater/1.0 (+https://github.com/dtdias/mercadovoz-pwa)"
PRICE_RE = re.compile(r"R\$\s*([\d.]+(?:,\d{2})?)", re.I)
PRODUCT_RE = re.compile(
    r"<h2[^>]*>(?P<name>.*?)</h2>.*?"
    r"<span[^>]*class=[\"'][^\"']*text-price[^\"']*[\"'][^>]*>\s*"
    r"(?:R\$\s*)?(?P<price>[\d.]+(?:,\d{2})?)",
    re.I | re.S,
)


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").lower().strip()


def slugify(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_text(value)).strip("_") or "item"


def parse_price(value: object) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value or "").replace("R$", "").strip()
    text = re.sub(r"\.(?=\d{3}(?:,|$))", "", text).replace(",", ".")
    try:
        price = float(re.sub(r"[^\d.-]", "", text))
    except ValueError:
        return 0.0
    return round(price, 2) if 0.05 <= price <= 10000 else 0.0


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def package_from_name(name: str) -> str:
    match = re.search(
        r"(?:\(|\s)(\d+(?:[.,]\d+)?)\s*(kg|g|l|ml|mg|un|unid|unidades?|litros?|latas?|caixas?|pacotes?|rolos?)\b",
        name,
        re.I,
    )
    return f"{match.group(1)}{match.group(2).lower()}" if match else ""


def normalize_product(raw: dict, category: str = "Outros", source: str = "Catálogo local") -> dict:
    legacy = not raw.get("name") and raw.get("un") and raw.get("marca") is not None
    name = str(raw.get("name") or (raw.get("un") if legacy else raw.get("nome")) or "Produto").strip()
    aliases = raw.get("aliases")
    if not isinstance(aliases, list):
        aliases = str(raw.get("nome") or name).split("|")
    package = str(raw.get("package") or raw.get("embalagem") or package_from_name(name))
    category = str(raw.get("category") or raw.get("categoria") or category or "Outros")
    return {
        "id": str(raw.get("id") or f"product_{slugify(category)}_{slugify(name)}"),
        "name": name,
        "aliases": sorted({str(alias).strip() for alias in [*aliases, name] if str(alias).strip()}),
        "category": category,
        "unit": str(raw.get("unit") or (raw.get("preco") if legacy else raw.get("preco")) or "un"),
        "package": package,
        "price": parse_price(raw.get("price", raw.get("marca", 0))),
        "source": str(raw.get("source") or raw.get("fonte") or source),
        "source_url": str(raw.get("source_url") or raw.get("sourceUrl") or ""),
        "collected_at": str(raw.get("collected_at") or ""),
    }


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if isinstance(payload.get("produtos"), list):
        return [normalize_product(item) for item in payload["produtos"]]
    products: list[dict] = []
    for category, items in (payload.get("categorias") or {}).items():
        if isinstance(items, list):
            products.extend(normalize_product(item, category) for item in items)
    return products


def load_sources() -> list[dict]:
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [source for source in payload.get("sources", []) if source.get("enabled", True)]


def product_key(product: dict) -> tuple[str, str, str]:
    return normalize_text(product["name"]), normalize_text(product["category"]), normalize_text(product.get("package", ""))


def merge_products(existing: list[dict], scraped: list[dict]) -> list[dict]:
    result = list(existing)
    index = {product_key(product): position for position, product in enumerate(result)}
    for product in scraped:
        key = product_key(product)
        if key in index:
            current = result[index[key]]
            current["aliases"] = sorted(set(current.get("aliases", [])) | set(product.get("aliases", [])))
            if product.get("price", 0) > 0:
                current.update({key: product[key] for key in ("price", "source", "source_url", "collected_at")})
        else:
            index[key] = len(result)
            result.append(product)
    return result


def fetch_page(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")


def parse_carrefour(html_page: str, query: str, source: dict, limit: int) -> list[dict]:
    products: list[dict] = []
    query_tokens = [token for token in normalize_text(query).split() if len(token) > 2]
    for match in PRODUCT_RE.finditer(html_page):
        name = strip_tags(match.group("name"))
        price = parse_price(match.group("price"))
        normalized_name = normalize_text(name)
        if not name or not price or query_tokens and not any(token in normalized_name for token in query_tokens):
            continue
        package = package_from_name(name)
        products.append(
            normalize_product(
                {
                    "id": f"{source['id']}_{slugify(name)}",
                    "name": name,
                    "aliases": [query],
                    "category": source.get("category", "Outros"),
                    "unit": "kg" if "kg" in package else "L" if re.search(r"\d+l", package, re.I) else "un",
                    "package": package,
                    "price": price,
                    "source": source["name"],
                    "source_url": source["url"].format(query=quote(query)),
                    "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
                source.get("category", "Outros"),
                source["name"],
            )
        )
        if len(products) >= limit:
            break
    return products


def scrape_sources(sources: list[dict], max_queries: int, limit: int, timeout: int, delay: float) -> tuple[list[dict], list[dict]]:
    scraped: list[dict] = []
    reports: list[dict] = []
    for source in sources:
        queries = source.get("queries", [])[:max_queries]
        source_report = {"id": source["id"], "nome": source["name"], "regiao": source.get("region", ""), "consultas": 0, "produtos": 0, "erros": []}
        for query in queries:
            term = query.get("term", "").strip()
            if not term:
                continue
            source_report["consultas"] += 1
            try:
                url = source["url"].format(query=quote(term))
                page = fetch_page(url, timeout)
                batch = parse_carrefour(page, term, {**source, **query}, limit)
                scraped.extend(batch)
                source_report["produtos"] += len(batch)
            except Exception as error:  # Keep last good catalog on one failed source/query.
                source_report["erros"].append({"consulta": term, "erro": str(error)[:180]})
            time.sleep(delay)
        reports.append(source_report)
    return scraped, reports


def validate_catalog(products: list[dict]) -> None:
    if not products:
        raise ValueError("catalog has no products")
    required = {"id", "name", "aliases", "category", "unit", "price"}
    seen_ids: set[str] = set()
    for product in products:
        missing = required - product.keys()
        if missing:
            raise ValueError(f"{product.get('name', 'product')}: missing {sorted(missing)}")
        if product["id"] in seen_ids:
            raise ValueError(f"duplicate product id: {product['id']}")
        seen_ids.add(product["id"])
        if not product["name"].strip() or not isinstance(product["aliases"], list) or product["price"] < 0:
            raise ValueError(f"invalid product: {product['id']}")


def write_catalog(products: list[dict], reports: list[dict]) -> None:
    validate_catalog(products)
    payload = {
        "schema_version": 2,
        "atualizado_em": dt.date.today().isoformat(),
        "total_produtos": len(products),
        "fontes": reports,
        "produtos": products,
    }
    temporary = CATALOG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(CATALOG_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Atualiza catálogo MercadoVoz por scraping público controlado.")
    parser.add_argument("--no-scrape", action="store_true", help="normaliza catálogo atual sem consultar fontes")
    parser.add_argument("--check", action="store_true", help="valida catálogo atual e não escreve")
    args = parser.parse_args()
    products = load_catalog()
    if args.check:
        validate_catalog(products)
        print(f"Catalog OK: {len(products)} products")
        return 0
    reports: list[dict] = []
    scraped: list[dict] = []
    if not args.no_scrape:
        scraped, reports = scrape_sources(
            load_sources(),
            max_queries=int(os.getenv("PRICE_MAX_QUERIES", "24")),
            limit=int(os.getenv("PRICE_RESULTS_PER_QUERY", "8")),
            timeout=int(os.getenv("PRICE_TIMEOUT", "20")),
            delay=float(os.getenv("PRICE_DELAY", "0.8")),
        )
    products = merge_products(products, scraped)
    write_catalog(products, reports)
    print(f"Catalog updated: {len(products)} products ({len(scraped)} scraped)")
    if reports:
        for report in reports:
            print(f"{report['nome']}: {report['produtos']} products, {len(report['erros'])} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
