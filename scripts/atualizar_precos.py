"""Refresh MercadoVoz catalog from configured public retailer pages."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import time
import unicodedata
from pathlib import Path
from statistics import median
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "precos.json"
SOURCES_PATH = Path(__file__).with_name("fontes_precos.json")
USER_AGENT = "MercadoVozPriceUpdater/2.0 (+https://github.com/dtdias/mercadovoz-pwa)"
PRODUCT_RE = re.compile(
    r"<h2[^>]*>(?P<name>.*?)</h2>.*?"
    r"<span[^>]*class=[\"'][^\"']*text-price[^\"']*[\"'][^>]*>\s*"
    r"(?:R\$\s*)?(?P<price>[\d.]+(?:,\d{2})?)",
    re.I | re.S,
)
PACKAGE_RE = re.compile(
    r"(?<![A-Za-z])(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>kg|g|l|litros?|ml|mg|unidades?|unid|un|pacotes?|pct|caixas?|cx|rolos?)\b",
    re.I,
)
KNOWN_BRANDS = (
    "tio joão", "camil", "prato fino", "carrefour", "seletto", "namorado",
    "limpol", "ypê", "ype", "omo", "ariel", "brilhante", "coca-cola",
    "coca cola", "pepsi", "nestlé", "nestle", "parmalat", "barilla",
    "3 corações", "3 coracoes", "angeloni", "montana", "perdigão", "perdigao",
)
COUNT_UNITS = {"un", "unid", "unidades", "pct", "pacote", "pacotes", "cx", "caixa", "caixas", "rolos"}
UNIT_ALIASES = {
    "quilo": "kg", "quilos": "kg", "kg": "kg", "g": "g", "litro": "l", "litros": "l", "l": "l",
    "ml": "ml", "mg": "mg", "un": "un", "unid": "un", "unidades": "un", "pct": "pct",
    "pacote": "pct", "pacotes": "pct", "cx": "cx", "caixa": "cx", "caixas": "cx", "rolos": "rolos",
}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").lower().strip()


def slugify(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_text(value)).strip("_") or "item"


def parse_price(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        price = float(value)
        return round(price, 2) if math.isfinite(price) and 0.05 <= price <= 10000 else 0.0
    text = str(value or "").replace("R$", "").strip()
    text = re.sub(r"\.(?=\d{3}(?:,|$))", "", text).replace(",", ".")
    try:
        price = float(re.sub(r"[^\d.-]", "", text))
    except ValueError:
        return 0.0
    return round(price, 2) if math.isfinite(price) and 0.05 <= price <= 10000 else 0.0


def parse_count(value: object, default: int = 1) -> int:
    try:
        return max(1, int(float(str(value or default).replace(",", "."))))
    except ValueError:
        return default


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def canonical_unit(value: str) -> str:
    return UNIT_ALIASES.get(normalize_text(value), normalize_text(value))


def package_info(name: str, explicit: str = "") -> dict:
    text = str(explicit or name)
    matches = list(PACKAGE_RE.finditer(text))
    amount = 0.0
    unit = ""
    package_count = 1
    if matches:
        amount = float(matches[0].group("amount").replace(",", "."))
        unit = canonical_unit(matches[0].group("unit"))
        extra_matches = list(PACKAGE_RE.finditer(name)) if explicit else matches[1:]
        for match in extra_matches:
            if canonical_unit(match.group("unit")) in COUNT_UNITS:
                package_count = max(1, int(float(match.group("amount").replace(",", "."))))
    elif re.search(r"d[uú]zia|\bdz\b", normalize_text(text)):
        unit = "dz"
        amount = 1.0
    package = f"{amount:g}{unit}" if amount and unit else ""
    return {"amount": amount, "unit": unit, "package": package, "package_count": package_count}


def remove_package_text(name: str) -> str:
    text = re.sub(r"\([^)]*(?:kg|g|ml|l|un|pct|caixa|pacote|rolo|d[uú]zia)[^)]*\)", " ", name, flags=re.I)
    text = PACKAGE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text.replace(" - ", " ")).strip(" -")


def remove_brand_text(name: str, brand: str) -> str:
    if not brand:
        return name
    return re.sub(rf"\b{re.escape(brand)}\b", " ", name, flags=re.I).strip(" -/")


def extract_brand(name: str, explicit: str = "") -> str:
    if explicit:
        return str(explicit).strip()
    normalized = normalize_text(name)
    for brand in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(normalize_text(brand))}\b", normalized):
            return brand
    return ""


def price_stats(offers: list[dict]) -> dict:
    prices = sorted(price for offer in offers if isinstance(offer, dict) and (price := parse_price(offer.get("price"))) > 0)
    if not prices:
        return {"min": 0.0, "median": 0.0, "max": 0.0, "count": 0}
    return {"min": prices[0], "median": round(float(median(prices)), 2), "max": prices[-1], "count": len(prices)}


def normalize_offer(raw: dict, source: str, source_url: str, region: str, collected_at: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    price = parse_price(raw.get("price"))
    if not price:
        return None
    return {
        "source": str(raw.get("source") or source),
        "source_url": str(raw.get("source_url") or source_url),
        "region": str(raw.get("region") or region),
        "collected_at": str(raw.get("collected_at") or collected_at),
        "price": price,
    }


def normalize_product(raw: dict, category: str = "Outros", source: str = "Catálogo local", source_url: str = "", region: str = "") -> dict:
    if not isinstance(raw, dict):
        raise ValueError("product must be an object")
    if "offers" in raw and not isinstance(raw.get("offers"), list):
        raise ValueError("offers must be a list")
    legacy = not raw.get("name") and raw.get("un")
    name = str(raw.get("name") or (raw.get("un") if legacy else raw.get("nome")) or "Produto").strip()
    category = str(raw.get("category") or raw.get("categoria") or category or "Outros")
    package = package_info(name, str(raw.get("package") or raw.get("embalagem") or ""))
    brand = extract_brand(name, str(raw.get("brand") or ""))
    family = str(raw.get("family") or remove_brand_text(remove_package_text(name), brand)).strip()
    family_key = str(raw.get("family_key") or raw.get("familyKey") or slugify(family))
    brand_key = slugify(brand) if brand else "generic"
    package_count = max(parse_count(raw.get("package_count") or raw.get("packageCount") or 1), package["package_count"])
    package_key = package["package"] or slugify(str(raw.get("package") or raw.get("embalagem") or "un"))
    comparison_key = "|".join((slugify(category), family_key, package_key, str(package_count)))
    sku_key = "|".join((comparison_key, brand_key))
    collected_at = str(raw.get("collected_at") or dt.datetime.now(dt.timezone.utc).isoformat())
    raw_offers = raw.get("offers") if isinstance(raw.get("offers"), list) else []
    offers = []
    for offer in raw_offers:
        if not isinstance(offer, dict) or not parse_price(offer.get("price")):
            raise ValueError(f"invalid offer for product: {name}")
        normalized = normalize_offer(offer, str(raw.get("source") or source), str(raw.get("source_url") or source_url), str(raw.get("region") or region), collected_at)
        if normalized:
            offers.append(normalized)
    base_price = parse_price(raw.get("price") if raw.get("price") is not None else raw.get("preco"))
    stats = price_stats(offers) if offers else {"min": base_price, "median": base_price, "max": base_price, "count": 0}
    aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else str(raw.get("nome") or name).split("|")
    search_terms = raw.get("search_terms") if isinstance(raw.get("search_terms"), list) else []
    normalized_name = normalize_text(name)
    normalized_family = normalize_text(family)
    normalized_brand = normalize_text(brand)
    strong_aliases = []
    for alias in aliases:
        alias_text = str(alias).strip()
        normalized_alias = normalize_text(alias_text)
        is_broad = len(normalized_alias.split()) == 1 and normalized_alias not in {normalized_name, normalized_family, normalized_brand}
        (search_terms if is_broad else strong_aliases).append(alias_text)
    unit = str(raw.get("unit") or raw.get("unidade") or ("pct" if package["unit"] in {"kg", "g"} else "un"))
    product_id = str(raw.get("id") or f"sku_{slugify(sku_key)}")
    return {
        "id": product_id,
        "sku_key": sku_key,
        "comparison_key": comparison_key,
        "family_key": family_key,
        "family": family,
        "brand": brand,
        "name": name,
        "aliases": sorted({str(alias).strip() for alias in [*strong_aliases, name, family] if str(alias).strip()}),
        "search_terms": sorted({str(term).strip() for term in [*search_terms] if str(term).strip()}),
        "category": category,
        "unit": unit,
        "package": package_key,
        "package_amount": package["amount"],
        "package_unit": package["unit"],
        "package_count": package_count,
        "offers": offers,
        "price_stats": stats,
        "price": stats["median"],
        "source": offers[0]["source"] if offers else str(raw.get("source") or source),
        "source_url": offers[0]["source_url"] if offers else str(raw.get("source_url") or source_url),
        "collected_at": offers[0]["collected_at"] if offers else str(raw.get("collected_at") or ""),
    }


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if isinstance(payload.get("produtos"), list):
        products = [normalize_product(item) for item in payload["produtos"]]
        validate_catalog(products)
        return products
    products: list[dict] = []
    for category, items in (payload.get("categorias") or {}).items():
        if isinstance(items, list):
            products.extend(normalize_product(item, category) for item in items)
    validate_catalog(products)
    return products


def load_sources() -> list[dict]:
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [source for source in payload.get("sources", []) if source.get("enabled", True)]


def merge_offers(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for offer in [*existing, *incoming]:
        key = (normalize_text(offer.get("source")), normalize_text(offer.get("region")))
        merged[key] = offer
    return list(merged.values())


def merge_products(existing: list[dict], scraped: list[dict]) -> list[dict]:
    result: list[dict] = []
    index: dict[str, int] = {}
    id_index: dict[str, int] = {}
    identity_index: dict[tuple[str, str, str, int], int] = {}
    for product, is_scraped in [*((item, False) for item in existing), *((item, True) for item in scraped)]:
        key = product["sku_key"]
        identity = (normalize_text(product["name"]), product["category"], product["package"], product["package_count"])
        position = index.get(key, identity_index.get(identity, id_index.get(product["id"])))
        if position is not None:
            current = result[position]
            if is_scraped or product.get("offers"):
                current.update({field: product[field] for field in ("sku_key", "comparison_key", "family_key", "family", "brand", "category", "unit", "package", "package_amount", "package_unit", "package_count")})
            current["aliases"] = sorted(set(current.get("aliases", [])) | set(product.get("aliases", [])))
            current["search_terms"] = sorted(set(current.get("search_terms", [])) | set(product.get("search_terms", [])))
            current["offers"] = merge_offers(current.get("offers", []), product.get("offers", []))
            if is_scraped and (product.get("source") != "Catálogo local" or product.get("offers")):
                current["name"] = product["name"]
        else:
            result.append(dict(product))
            position = len(result) - 1
        index[key] = position
        id_index[product["id"]] = position
        identity_index[identity] = position
        current = result[position]
        offers = current.get("offers", [])
        if offers:
            current["price_stats"] = price_stats(offers)
            current["price"] = current["price_stats"]["median"]
            current["source"] = offers[0]["source"]
            current["source_url"] = offers[0]["source_url"]
            current["collected_at"] = offers[0]["collected_at"]
    return result


def fetch_page(url: str, timeout: int, retries: int = 2) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"})
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}
    for attempt in range(max(0, retries) + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status not in {200, 206}:
                    raise RuntimeError(f"HTTP {response.status}")
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            if error.code not in transient_statuses or attempt >= retries:
                raise
        except (URLError, TimeoutError):
            if attempt >= retries:
                raise
        time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(f"request failed after {retries} retries: {url}")


def scraped_product(name: str, prices: list[float], query: str, source: dict, source_url: str, brand: str = "") -> dict:
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat()
    offers = [{"price": price, "source": source["name"], "source_url": source_url, "region": source.get("region", ""), "collected_at": collected_at} for price in prices]
    return {"name": name, "brand": brand, "aliases": [], "search_terms": [query], "category": source.get("category", "Outros"), "offers": offers, "source": source["name"], "source_url": source_url, "region": source.get("region", ""), "collected_at": collected_at}


def parse_carrefour(html_page: str, query: str, source: dict, limit: int) -> list[dict]:
    products: list[dict] = []
    tokens = [token for token in normalize_text(query).split() if len(token) > 2]
    source_url = source["url"].format(query=quote(query))
    for match in PRODUCT_RE.finditer(html_page):
        name = strip_tags(match.group("name"))
        price = parse_price(match.group("price"))
        if not name or not price or tokens and not any(token in normalize_text(name) for token in tokens):
            continue
        products.append(scraped_product(name, [price], query, source, source_url))
        if len(products) >= limit:
            break
    return products


def iter_jsonld(value: object):
    if isinstance(value, dict):
        types = value.get("@type")
        if types == "Product" or isinstance(types, list) and "Product" in types:
            yield value
        for child in value.values():
            yield from iter_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_jsonld(child)


def parse_jsonld(html_page: str, query: str, source: dict, limit: int) -> list[dict]:
    products: list[dict] = []
    tokens = [token for token in normalize_text(query).split() if len(token) > 2]
    source_url = source["url"].format(query=quote(query))
    blocks = re.findall(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html_page, re.I | re.S)
    for block in blocks:
        try:
            payload = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        for product in iter_jsonld(payload):
            name = str(product.get("name") or "").strip()
            if not name or tokens and not any(token in normalize_text(name) for token in tokens):
                continue
            offers = product.get("offers") or {}
            if isinstance(offers, list):
                offer_rows = offers
            elif isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                offer_rows = offers["offers"]
            else:
                offer_rows = [offers] if isinstance(offers, dict) else []
            prices = [parse_price(row.get("price")) for row in offer_rows if isinstance(row, dict)]
            if not prices and isinstance(offers, dict):
                prices = [parse_price(offers.get("lowPrice") or offers.get("price"))]
            prices = [price for price in prices if price]
            if not prices:
                continue
            brand = product.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name", "")
            products.append(scraped_product(name, prices, query, source, str(product.get("@id") or source_url), str(brand or "")))
            if len(products) >= limit:
                return products
    return products


def parse_vtex_json(payload_text: str, query: str, source: dict, limit: int) -> list[dict]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    products: list[dict] = []
    tokens = [token for token in normalize_text(query).split() if len(token) > 2]
    source_url = source["url"].format(query=quote(query))
    for product in payload:
        if not isinstance(product, dict):
            continue
        name = str(product.get("productName") or product.get("productTitle") or "").strip()
        if not name or tokens and not any(token in normalize_text(name) for token in tokens):
            continue
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name", "")
        items = product.get("items") if isinstance(product.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("nameComplete") or item.get("name") or name).strip()
            prices = []
            for seller in item.get("sellers", []):
                if not isinstance(seller, dict):
                    continue
                offer = seller.get("commertialOffer") or {}
                if offer.get("IsAvailable", True):
                    price = parse_price(offer.get("Price"))
                    if price:
                        prices.append(price)
            if not item_name or not prices:
                continue
            product_url = str(item.get("link") or product.get("link") or source_url)
            products.append(scraped_product(item_name, [min(prices)], query, source, product_url, str(brand or "")))
            if len(products) >= limit:
                return products
    return products


PARSERS = {"carrefour": parse_carrefour, "jsonld": parse_jsonld, "vtex": parse_vtex_json}


def scrape_sources(sources: list[dict], max_queries: int, limit: int, timeout: int, delay: float, retries: int = 2) -> tuple[list[dict], list[dict]]:
    scraped: list[dict] = []
    reports: list[dict] = []
    for source in sources:
        parser = PARSERS.get(source.get("parser", "carrefour"))
        if not parser:
            reports.append({"id": source["id"], "nome": source["name"], "regiao": source.get("region", ""), "parser": source.get("parser"), "consultas": 0, "produtos": 0, "erros": ["parser não configurado"]})
            continue
        source_report = {"id": source["id"], "nome": source["name"], "regiao": source.get("region", ""), "parser": source.get("parser", "carrefour"), "consultas": 0, "produtos": 0, "erros": []}
        for query in source.get("queries", [])[:max_queries]:
            term = str(query.get("term", "")).strip()
            if not term:
                continue
            source_report["consultas"] += 1
            try:
                page = fetch_page(source["url"].format(query=quote(term)), timeout, retries)
                batch = parser(page, term, {**source, **query}, limit)
                scraped.extend(batch)
                source_report["produtos"] += len(batch)
            except Exception as error:
                source_report["erros"].append({"consulta": term, "erro": str(error)[:180]})
            time.sleep(delay)
        if source_report["produtos"] == 0:
            source_report["erros"].append({"consulta": "*", "erro": "nenhum produto válido retornado"})
        reports.append(source_report)
    return scraped, reports


def require_scrape_success(scraped: list[dict], reports: list[dict]) -> None:
    if scraped and any(report.get("produtos", 0) > 0 for report in reports):
        return
    details = "; ".join(f"{report.get('nome', report.get('id', 'fonte'))}: {len(report.get('erros', []))} erro(s)" for report in reports)
    raise RuntimeError(f"no valid prices collected; existing catalog preserved. {details}")


def validate_catalog(products: list[dict]) -> None:
    if not products:
        raise ValueError("catalog has no products")
    required = {"id", "sku_key", "comparison_key", "name", "aliases", "category", "package", "offers", "price_stats", "price"}
    seen_ids: set[str] = set()
    for product in products:
        missing = required - product.keys()
        if missing:
            raise ValueError(f"{product.get('name', 'product')}: missing {sorted(missing)}")
        if product["id"] in seen_ids:
            raise ValueError(f"duplicate product id: {product['id']}")
        seen_ids.add(product["id"])
        if not product["name"].strip() or not isinstance(product["aliases"], list) or not isinstance(product["offers"], list):
            raise ValueError(f"invalid product: {product['id']}")
        stats = product.get("price_stats")
        if not isinstance(stats, dict) or set(stats) != {"min", "median", "max", "count"}:
            raise ValueError(f"invalid price_stats: {product['id']}")
        for field in ("min", "median", "max"):
            value = stats[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"invalid price_stats values: {product['id']}")
        if not isinstance(stats["count"], int) or stats["count"] < 0:
            raise ValueError(f"invalid price_stats count: {product['id']}")
        offer_keys: set[tuple[str, str]] = set()
        for offer in product["offers"]:
            if not isinstance(offer, dict):
                raise ValueError(f"invalid offer: {product['id']}")
            price = parse_price(offer.get("price"))
            if price <= 0 or offer.get("price") != price:
                raise ValueError(f"invalid offer price: {product['id']}")
            offer_key = (normalize_text(offer.get("source")), normalize_text(offer.get("region")))
            if offer_key in offer_keys:
                raise ValueError(f"duplicate offer: {product['id']}")
            offer_keys.add(offer_key)
        if product["offers"]:
            expected_stats = price_stats(product["offers"])
        else:
            base_price = parse_price(product.get("price"))
            expected_stats = {"min":base_price, "median":base_price, "max":base_price, "count":0}
        if stats != expected_stats or product["price"] != stats["median"]:
            raise ValueError(f"median mismatch: {product['id']}")


def write_catalog(products: list[dict], reports: list[dict]) -> None:
    validate_catalog(products)
    payload = {"schema_version": 3, "atualizado_em": dt.date.today().isoformat(), "total_produtos": len(products), "fontes": reports, "produtos": products}
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
        sources = load_sources()
        configured_queries = os.getenv("PRICE_MAX_QUERIES")
        max_queries = int(configured_queries) if configured_queries is not None else max((len(source.get("queries", [])) for source in sources), default=0)
        scraped, reports = scrape_sources(sources, max_queries, int(os.getenv("PRICE_RESULTS_PER_QUERY", "8")), int(os.getenv("PRICE_TIMEOUT", "20")), float(os.getenv("PRICE_DELAY", "0.8")), int(os.getenv("PRICE_RETRIES", "2")))
        require_scrape_success(scraped, reports)
    products = merge_products(products, [normalize_product(item) for item in scraped])
    write_catalog(products, reports)
    print(f"Catalog updated: {len(products)} products ({len(scraped)} scraped)")
    for report in reports:
        print(f"{report['nome']}: {report['produtos']} products, {len(report['erros'])} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
