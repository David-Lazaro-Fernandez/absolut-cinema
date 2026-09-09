"""Parsers de Rappi y DiDi Food sobre HTML guardado (sin red)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import delivery  # noqa: E402

DIDI_HTML = """<html><title>Cinemex (Prueba) | DiDi Food México</title><body>
<h3 class="x">Combos</h3>
<div><h4>Combo Hot Dog</h4><span>MX$245.00</span><p>Palomitas, 2 latas y 2 hot dog.</p></div>
<h3>Snacks</h3>
<div><h4>Hot Dog</h4><span>MX$58.00</span><p>Hot dog 135 g.</p></div>
<div><h4>Nachos con queso</h4><span>MX$65.00</span><p>110 g.</p></div>
<div><h4>Sin precio</h4><p>agotado</p></div>
</body></html>"""


def test_didi_prices_follow_each_heading(monkeypatch):
    monkeypatch.setattr(delivery, "fetch", lambda url, stats=None: DIDI_HTML)
    meta, prods = delivery.didi_store("1", "cinemex-prueba")
    assert meta["store_name"] == "Cinemex (Prueba)"
    assert [(p["category"], p["product_name"], p["price_cents"]) for p in prods] == [
        ("Combos", "Combo Hot Dog", 24500), ("Snacks", "Hot Dog", 5800), ("Snacks", "Nachos con queso", 6500)]
    assert prods[1]["description"] == "Hot dog 135 g."
