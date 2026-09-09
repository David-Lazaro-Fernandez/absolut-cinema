"""Dulcería a domicilio: precios de Cinemex y Cinépolis en Rappi y DiDi Food (CDMX).

Uso: python3 -m scraper.delivery [--platform rappi|didi] [--chain cinemex|cinepolis] [--limit N] [--days 7] [--dry-run]

Por qué: Cinemex tiene apagada la venta de dulcería en línea (ver project.md > "Dulcería"), pero vende a domicilio en
Rappi, DiDi Food y Uber Eats. Uber Eats prohíbe la extracción en sus términos, así que solo se usan Rappi (sin
cláusula anti-scraping; robots.txt sin bloqueo a /restaurantes/) y DiDi Food (robots.txt `Allow: /`). Ambas sirven
el HTML con los precios del lado del servidor, sin login ni ubicación. Ojo: es el catálogo "para llevar" (Mega
Palomitas 230 g, latas 355 ml), no el tablero de sala, y el 2026-09-09 el precio era el mismo en todas las tiendas.

Descubrimiento de tiendas:
  - Rappi: listado por marca `/{ciudad}/restaurantes/delivery/{brandId}-{slug}` (Cinemex 51760, Cinépolis Tradicional 96681).
  - DiDi Food: la categoría "pasaboca" (botanas) de la ciudad, paginada; ahí están los cines.
Cada tienda se vuelve a leer a los `--days` días. Una petición cada `config.DELIVERY_PAUSE` segundos. Todo lo
configurable (hosts, ciudad, marcas, categoría) vive en `scraper/config.py`.
"""
import argparse
import html as htmllib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from . import config, store
from .http import ApiError, request_text


def log(msg):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(config.LOG_DIR / "delivery.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url, stats=None):
    body = request_text(url, pause=config.DELIVERY_PAUSE)
    if stats is not None:
        stats["calls"] = stats.get("calls", 0) + 1
    return body


def chain_of(text):
    t = text.lower()
    return "cinemex" if "cinemex" in t else "cinepolis" if "cinepolis" in t or "cinépolis" in t else None


# --- Rappi ------------------------------------------------------------------------------------------------
def rappi_discover(chain, stats=None):
    brand_id, slug = config.RAPPI_BRANDS[chain]
    h = fetch(f"{config.RAPPI_BASE_URL}/{config.RAPPI_CITY}/restaurantes/delivery/{brand_id}-{slug}", stats)
    found = sorted(set(re.findall(r'/restaurantes/(\d+)-([a-z0-9-]+)', h)))
    return [(sid, s) for sid, s in found if chain_of(s) == chain]


def rappi_store(store_id, slug, stats=None):
    """(meta, productos) de una tienda de Rappi a partir de __NEXT_DATA__."""
    h = fetch(f"{config.RAPPI_BASE_URL}/restaurantes/{store_id}-{slug}", stats)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', h, re.S)
    if not m:
        raise ApiError(f"Rappi {store_id}: la página no trae __NEXT_DATA__ (¿cambió el sitio?)")
    fb = json.loads(m.group(1))["props"]["pageProps"].get("fallback") or {}
    key = next((k for k in fb if k.startswith('@"restaurant/')), None)
    if not key:
        raise ApiError(f"Rappi {store_id}: sin tienda en el estado de la página")
    r = fb[key]
    lat = lng = None
    mm = re.search(r'lng:(-?[\d.]+),lat:(-?[\d.]+)', key)
    if mm:
        lng, lat = float(mm.group(1)), float(mm.group(2))
    meta = {"store_name": r.get("name"), "status": r.get("status"), "available": 1 if r.get("isCurrentlyAvailable") else 0,
            "address": r.get("address") or "", "schedule": r.get("schedule") or "", "lat": lat, "lng": lng}
    prods = []
    for cor in r.get("corridors") or []:
        for p in cor.get("products") or []:
            price = p.get("price")
            if price is None:
                continue
            prods.append({"category": cor.get("name") or "", "product_id": str(p.get("id") or ""), "product_name": (p.get("name") or "").strip(),
                          "price_cents": int(round(float(price) * 100)), "description": (p.get("description") or "").strip()[:300],
                          "in_stock": 1 if p.get("inStock", True) else 0})
    return meta, prods


# --- DiDi Food --------------------------------------------------------------------------------------------
def didi_discover(stats=None, max_pages=config.DIDI_MAX_PAGES):
    """Tiendas de cines en la categoría de botanas de la ciudad: [(store_id, slug, chain)]."""
    found = {}
    for page in range(1, max_pages + 1):
        h = fetch(f"{config.DIDI_BASE_URL}/mx/food/{config.DIDI_CITY}/categoria/{config.DIDI_CATEGORY}/?page={page}", stats)
        links = re.findall(r'href="/mx/food/%s/([a-z0-9-]+)/(\d{10,})/"' % re.escape(config.DIDI_CITY), h)
        if not links:
            break
        for slug, sid in links:
            c = chain_of(slug)
            if c:
                found[sid] = (sid, slug, c)
    return sorted(found.values())


def didi_store(store_id, slug, stats=None):
    """(meta, productos) de una tienda de DiDi Food: HTML estático, se parsea por bloque de producto."""
    h = fetch(f"{config.DIDI_BASE_URL}/mx/food/{config.DIDI_CITY}/{slug}/{store_id}/", stats)
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    name = htmllib.unescape(title.group(1).split("|")[0].strip()) if title else slug
    addr = re.search(r'itemprop="streetAddress"[^>]*>([^<]*)<', h) or re.search(r'"streetAddress":"([^"]*)"', h)
    meta = {"store_name": name, "status": "", "available": 1, "address": htmllib.unescape(addr.group(1)) if addr else "",
            "schedule": "", "lat": None, "lng": None}
    prods, category = [], ""
    # Recorrer en orden de aparición: <h3> abre categoría; cada <h4> es un producto y su precio y descripción
    # están en el HTML que sigue a ese <h4>, antes del siguiente encabezado. Se corta por posición, no
    # buscando el nombre, porque un nombre puede estar contenido en otro ("Hot Dog" en "Combo Hot Dog").
    heads = list(re.finditer(r"<(h3|h4)[^>]*>(.*?)</\1>", h, re.S))
    for i, m in enumerate(heads):
        tag, body = m.group(1), m.group(2)
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", body)).strip()
        if tag == "h3":
            category = text
            continue
        seg = h[m.end():heads[i + 1].start() if i + 1 < len(heads) else m.end() + 1500]
        pm = re.search(r"MX\$\s?([\d,]+(?:\.\d+)?)", seg)
        if not pm:
            continue
        dm = re.search(r"<p[^>]*>(.*?)</p>", seg, re.S)
        prods.append({"category": category, "product_id": "", "product_name": text,
                      "price_cents": int(round(float(pm.group(1).replace(",", "")) * 100)),
                      "description": htmllib.unescape(re.sub(r"<[^>]+>", "", dm.group(1))).strip()[:300] if dm else "", "in_stock": 1})
    return meta, prods


# --- pasada -----------------------------------------------------------------------------------------------
def run(conn, platforms=("rappi", "didi"), chains=("cinemex", "cinepolis"), days=config.DELIVERY_REFRESH_DAYS, limit=None, dry_run=False):
    stats = {"calls": 0}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    recent = {(r[0], r[1]) for r in conn.execute("SELECT DISTINCT platform, store_id FROM delivery_price WHERE sampled_at >= ?", (since,))}
    todo = []
    if "rappi" in platforms:
        for chain in chains:
            for sid, slug in rappi_discover(chain, stats):
                todo.append(("rappi", chain, sid, slug))
    if "didi" in platforms:
        for sid, slug, chain in didi_discover(stats):
            if chain in chains:
                todo.append(("didi", chain, sid, slug))
    total = len(todo)
    todo = [t for t in todo if (t[0], t[2]) not in recent]
    if limit:
        todo = todo[:limit]
    log(f"delivery: {total} tiendas descubiertas, {len(todo)} pendientes{' (dry-run)' if dry_run else ''} calls={stats['calls']}")
    if dry_run or not todo:
        return True
    ok = fail = 0
    for platform, chain, sid, slug in todo:
        try:
            meta, prods = (rappi_store if platform == "rappi" else didi_store)(sid, slug, stats)
        except (ApiError, KeyError, json.JSONDecodeError) as e:
            fail += 1; log(f"delivery FAIL {platform} {sid} {slug}: {e}"[:300]); continue
        if not prods:
            log(f"delivery skip {platform} {sid} {slug}: sin productos ({meta.get('status')})"); continue
        ts = utc_now()
        conn.executemany("""INSERT INTO delivery_price (platform, chain, store_id, store_slug, store_name, address, lat, lng, status, available,
                                sampled_at, category, product_id, product_name, price_cents, description, in_stock)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         [(platform, chain, sid, slug, meta["store_name"], meta["address"], meta["lat"], meta["lng"], meta["status"],
                           meta["available"], ts, p["category"], p["product_id"], p["product_name"], p["price_cents"], p["description"],
                           p["in_stock"]) for p in prods])
        conn.commit(); ok += 1
    log(f"delivery ok={ok} fail={fail} calls={stats['calls']}")
    return fail == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=["rappi", "didi"], action="append")
    ap.add_argument("--chain", choices=["cinemex", "cinepolis"], action="append")
    ap.add_argument("--days", type=int, default=config.DELIVERY_REFRESH_DAYS)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    conn = store.connect()
    t0 = time.time()
    ok = run(conn, platforms=tuple(a.platform or ("rappi", "didi")), chains=tuple(a.chain or ("cinemex", "cinepolis")),
             days=a.days, limit=a.limit, dry_run=a.dry_run)
    conn.close()
    log(f"done in {time.time() - t0:.0f}s ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
