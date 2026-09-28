"""El índice de lugares de la landing (`scripts/export_places.py`): qué tipo es cada elemento de OpenStreetMap y que una
estación con nodo, andenes y edificio quede como un solo lugar. Sin red: elementos de Overpass escritos a mano."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import export_places as ep  # noqa: E402


def test_each_osm_element_gets_its_kind():
    assert ep.kind_of({"place": "borough"}) == "Alcaldía"
    assert ep.kind_of({"place": "neighbourhood"}) == "Colonia"
    assert ep.kind_of({"public_transport": "station", "station": "subway"}) == "Metro"
    assert ep.kind_of({"public_transport": "station", "network": "Metrobús"}) == "Metrobús"
    assert ep.kind_of({"public_transport": "station", "network": "Cablebús Línea 2"}) == "Cablebús"
    assert ep.kind_of({"public_transport": "station", "station": "subway", "network": "Metrorrey"}) == "Metrorrey"
    assert ep.kind_of({"public_transport": "station", "network": "Mi Macro Periférico"}) == "Mi Macro"
    assert ep.kind_of({"place": "city"}) == "Ciudad"
    assert ep.kind_of({"public_transport": "station"}) == "Estación"
    assert ep.kind_of({"shop": "mall"}) == "Plaza comercial"
    assert ep.kind_of({"amenity": "cafe"}) is None


def test_one_place_per_name_kind_and_spot():
    station = {"public_transport": "station", "station": "subway", "name": "Coyoacán"}
    elements = [
        {"type": "node", "lat": 19.3612, "lon": -99.1709, "tags": station},
        {"type": "way", "center": {"lat": 19.3614, "lon": -99.1711}, "tags": station},        # el edificio, a metros
        {"type": "node", "lat": 19.3500, "lon": -99.1620, "tags": {"place": "neighbourhood", "name": "Coyoacán"}},
        {"type": "node", "lat": 19.4000, "lon": -99.1000, "tags": station},                     # otra, a kilómetros
        {"type": "node", "lat": 19.4, "lon": -99.1, "tags": {"place": "neighbourhood"}},        # sin nombre: fuera
    ]
    got = ep.places(elements)
    kinds = [ep.KINDS[k] for _, k, _, _ in got]
    assert sorted(kinds) == ["Colonia", "Metro", "Metro"]
    assert all(name == "Coyoacán" for name, _, _, _ in got)
