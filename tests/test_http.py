"""Pruebas del cliente HTTP: clasificación de 401/403 sin tocar la red."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import http  # noqa: E402

URL = "https://api-g.cinepolis.com/shared-services/locations/graphql"
CLOUDFLARE_PAGE = ('<!DOCTYPE html>\n<!--[if lt IE 7]> <html class="no-js ie6 oldie" lang="en-US"> <![endif]-->\n'
                   '<title>Attention Required! | Cloudflare</title>')


def test_403_with_html_page_is_an_edge_block_not_a_key_problem():
    err = http._forbidden_error(403, URL, CLOUDFLARE_PAGE)
    assert isinstance(err, http.Blocked)
    assert not isinstance(err, http.AuthError)
    assert err.status == 403
    assert "<!DOCTYPE" not in str(err)


def test_401_json_from_the_api_is_an_auth_error():
    err = http._forbidden_error(401, URL, '{"message":"Unauthorized access."}')
    assert isinstance(err, http.AuthError)
    assert err.status == 401
    assert "Unauthorized access" in str(err)


def test_403_json_from_the_api_is_an_auth_error():
    err = http._forbidden_error(403, URL, '{"message":"Forbidden"}')
    assert isinstance(err, http.AuthError)


def test_both_are_api_errors_so_generic_handlers_still_catch_them():
    assert issubclass(http.Blocked, http.ApiError)
    assert issubclass(http.AuthError, http.ApiError)


def test_without_egress_proxy_everything_goes_direct(monkeypatch):
    monkeypatch.setattr(http.config, "EGRESS_PROXY", "")
    assert http._proxy_for("https://api-g.cinepolis.com/v2/billboards/graphql") is None


def test_egress_proxy_applies_only_to_listed_hosts(monkeypatch):
    monkeypatch.setattr(http.config, "EGRESS_PROXY", "http://127.0.0.1:8118")
    monkeypatch.setattr(http.config, "EGRESS_PROXY_HOSTS", ("api-g.cinepolis.com",))
    assert http._proxy_for("https://api-g.cinepolis.com/v2/billboards/graphql") == "http://127.0.0.1:8118"
    assert http._proxy_for("https://api.cinemex.com/rest/v2.37.2/cinemas/") is None
    assert http._proxy_for("https://www.rappi.com.mx/tiendas/x") is None
