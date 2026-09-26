"""Las APIs reales de ambas cadenas siguen entregando lo que la captura necesita: una captura en vivo del alcance chico
de `scripts/capture_fixtures.py` debe cumplir las mismas reglas que lo grabado. Toca la red, así que solo corre con
`AC_LIVE=1` (`make test-live`); en CI se omite, porque el WAF de Cinépolis bloquea las IPs de nube (ver project.md >
Consideraciones). Cinépolis necesita la salida por WARP (`AC_EGRESS_PROXY`) fuera de la Mac."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import capture_fixtures as fixtures  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("AC_LIVE") != "1", reason="toca las APIs reales; AC_LIVE=1 para correrla")


@pytest.mark.parametrize("chain", sorted(fixtures.SCOPES))
def test_the_live_api_still_gives_what_the_capture_needs(chain):
    got = fixtures.result(chain, fixtures.capture(chain))
    assert fixtures.problems(chain, got) == []
