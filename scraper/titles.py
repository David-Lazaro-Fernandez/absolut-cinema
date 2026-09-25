"""Llave de título común a ambas cadenas: qué nombres de Cinemex y de Cinépolis son la misma película.

Las cadenas escriben distinto el mismo título ("Rápido y Furioso (25° Aniversario)" y "Reestreno Rápido Y Furioso") y
Cinépolis a veces reparte uno en variantes de formato ("Avengers: Endgame Bonus" y "… Infinity Vision"). `title_key`
parte del `title_norm` de `normalize.norm_title` y:

1. Quita solo decoraciones con palabra clave que las delata (reestreno, aniversario, transmisión en vivo, formato).
   No quita años ni números sueltos: "Blade Runner 2049" no es "Blade Runner" y "Parte 1" no es "Parte 3".
2. Aplica `title_pairs.csv`: `same` une dos nombres que las reglas no alcanzan; `different` deja de proponer el par
   y, si las reglas los habían unido, los separa (cada uno conserva su `title_norm` como llave).

Los candidatos para la tabla los propone `scripts/title_pairs.py`; nada se une solo por parecido. Solo stdlib.
"""
import csv
import difflib
import re
from functools import lru_cache
from pathlib import Path

PAIRS_PATH = Path(__file__).resolve().parent / "title_pairs.csv"

# Cada regla, con el caso que la justifica (vistos en la cartelera del 2026-09-25).
_DECORATIONS = [
    re.compile(r"\bre ?estrenos?( \d{4})?\b"),   # "Coraline … (Re-estreno 2026)", "Reestreno Rápido Y Furioso"
    re.compile(r"\b\d{1,3} aniversario\b"),      # "Rápido y Furioso (25° Aniversario)", "Transformers … 40 Aniversario"
    re.compile(r"^evento especial "),            # "Evento Especial: Puella Magi Madoka Magica"
    re.compile(r" (en vivo|live viewing)$"),     # BTS: "En Vivo" en Cinépolis, "Live Viewing" en Cinemex
    re.compile(r" (infinity vision|4k)$"),       # "Avengers: Endgame Bonus Infinity Vision", "Akira 4k"
    re.compile(r"^the "),                        # "The Transformers: La Película …" frente a "Transformers: La película"
]


def _load_pairs():
    same, different = {}, set()
    if not PAIRS_PATH.exists():
        return same, different
    with open(PAIRS_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            a, b = r["title_norm_a"].strip(), r["title_norm_b"].strip()
            if r["decision"] == "different":
                different.add(frozenset((a, b)))
            elif r["decision"] == "same":
                same[b] = a
    return same, different


_SAME, _DIFFERENT = _load_pairs()


def _rules(title_norm):
    key = title_norm
    for rule in _DECORATIONS:
        key = rule.sub("", key).strip()
    return re.sub(r"\s+", " ", key) or title_norm


def _by_rules(title_norm):
    return _rules(_SAME.get(title_norm, title_norm))


def _exempt(different):
    """Nombres que las reglas unían con otro que la tabla marca como distinto: se quedan fuera de las reglas."""
    return {t for pair in different if len(pair) == 2 and len({_by_rules(t) for t in pair}) == 1 for t in pair}


_EXEMPT = _exempt(_DIFFERENT)


@lru_cache(maxsize=4096)
def title_key(title_norm):
    """Título canónico de un `title_norm`: igual para la misma película en ambas cadenas. Vacío si no hay título."""
    if not title_norm:
        return ""
    if title_norm in _EXEMPT:
        return title_norm
    return _by_rules(title_norm)


# Candidatos: parecido de texto sobre la llave, como propuesta para revisar, nunca como unión automática. Solo se
# comparan títulos que aún no tienen pareja en la otra cadena, y sus números deben coincidir ("Parte 1" no es
# "Parte 3", "Terminator 2" no es "Terminator"). El parecido solo no distingue sedes ni secuelas sin número (dos
# conciertos de BTS se parecen más de 80 %), por eso la decisión es siempre de una persona.
CANDIDATE_MIN_RATIO = 0.6
_DIGITS = re.compile(r"\d+")


def reviewed(a, b):
    """True si el par ya tiene una decisión en `title_pairs.csv`."""
    return _SAME.get(a) == b or _SAME.get(b) == a or frozenset((a, b)) in _DIFFERENT


def candidates(cinemex, cinepolis):
    """Pares por revisar entre títulos sin pareja. `cinemex` y `cinepolis`: {title_norm: {title, duration_min,
    distributor, shows}}. Devuelve dicts {a, b, ratio, title_a, title_b, duration_a, duration_b, distributor_a,
    distributor_b, shows_a, shows_b}, del más parecido al menos. Excluye los pares que ya unen las reglas y los ya
    decididos en la tabla."""
    keys_b = {title_key(b) for b in cinepolis}
    lonely_a = [a for a in cinemex if title_key(a) not in keys_b]
    keys_a = {title_key(a) for a in cinemex}
    lonely_b = [b for b in cinepolis if title_key(b) not in keys_a]
    out = []
    for a in lonely_a:
        for b in lonely_b:
            ka, kb = title_key(a), title_key(b)
            if set(_DIGITS.findall(ka)) != set(_DIGITS.findall(kb)) or reviewed(a, b):
                continue
            ratio = difflib.SequenceMatcher(None, ka, kb).ratio()
            if ratio >= CANDIDATE_MIN_RATIO:
                ia, ib = cinemex[a], cinepolis[b]
                out.append({"a": a, "b": b, "ratio": round(ratio, 2), "title_a": ia["title"], "title_b": ib["title"],
                            "duration_a": ia["duration_min"], "duration_b": ib["duration_min"],
                            "distributor_a": ia["distributor"], "distributor_b": ib["distributor"],
                            "shows_a": ia["shows"], "shows_b": ib["shows"]})
    return sorted(out, key=lambda c: (-c["ratio"], c["a"], c["b"]))
