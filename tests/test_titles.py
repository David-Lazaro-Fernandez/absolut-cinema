"""Pruebas de la llave de título entre cadenas: los pares reales que deben unirse y los que nunca."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper import titles  # noqa: E402
from scraper.normalize import norm_title  # noqa: E402
from scraper.titles import title_key  # noqa: E402


def key(title):
    return title_key(norm_title(title))


def test_same_movie_across_chains():
    # Pares vistos en la cartelera del 2026-09-25 (Cinemex, Cinépolis).
    for a, b in [("Avengers Endgame: Bonus", "Avengers: Endgame Bonus Infinity Vision"),
                 ("Rápido y Furioso (25° Aniversario)", "Reestreno Rápido Y Furioso"),
                 ("One Piece: La Pelicula 2000", "One Piece: La Película"),              # por title_pairs.csv
                 ("Transformers: La película", "The Transformers: La Película 40 Aniversario"),
                 ("BTS WORLD TOUR 'ARIRANG' IN SÃO PAULO: LIVE VIEWING", "BTS WORLD TOUR 'ARIRANG' IN SÃO PAULO: EN VIVO"),
                 ("Coraline y la Puerta Secreta (Re-estreno 2026)", "Coraline y la Puerta Secreta"),
                 ("Queen: Budapest", "Queen Budapest")]:
        assert key(a) == key(b), (a, b)


def test_never_merge():
    for a, b in [("BTS WORLD TOUR 'ARIRANG' IN BUENOS AIRES: EN VIVO", "BTS WORLD TOUR 'ARIRANG' IN SÃO PAULO: EN VIVO"),
                 ("Puella Magi Madoka Mágica: La Película Parte 1", "Puella Magi Madoka Magica: Walpurgisnacht Rising"),
                 ("El Final", "El Final De La Calle Oak"),
                 ("Blade Runner 2049", "Blade Runner"),
                 ("Terminator 2: El Juicio Final", "Terminator: El Juicio Final"),
                 ("Duna", "Duna: Parte Tres")]:
        assert key(a) != key(b), (a, b)


def test_empty_title():
    assert title_key("") == "" and title_key(None) == ""


def test_a_rejection_only_splits_what_the_rules_merged():
    merged = frozenset(("reestreno rapido y furioso", "rapido y furioso 25 aniversario"))   # las reglas los unen
    unrelated = frozenset(("el descenso re estrenos 2026", "el desaire"))                    # nunca se unieron
    assert titles._exempt({merged, unrelated}) == set(merged)
    assert title_key("el descenso re estrenos 2026") == "el descenso"      # el rechazo no le quita sus reglas


def test_candidates_need_matching_numbers_and_skip_paired_titles():
    info = {"title": "x", "duration_min": 100, "distributor": "d", "shows": 1}
    out = titles.candidates({"la pelicula parte 1": info, "queen budapest": info},
                            {"la pelicula parte 3": info, "queen budapest": info})
    assert out == []      # "parte 1" frente a "parte 3" no se propone; Queen ya tiene pareja
