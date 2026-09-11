"""Armado de filtros opcionales para las consultas del explorador. Puro, sin base de datos (tests/test_archive_sql.py)."""


def where(clauses, prefix="WHERE"):
    """`clauses` es una lista de (condición con %s, valor). Se omiten las de valor None o lista vacía; una lista se
    pasa como tupla para `= ANY(%s)`. Devuelve (fragmento SQL, parámetros); el fragmento es "" si no queda nada."""
    parts, params = [], []
    for cond, value in clauses:
        if value is None or value == "" or (isinstance(value, (list, tuple, set)) and not value):
            continue
        parts.append(cond)
        if isinstance(value, (list, tuple, set)):
            params.append(list(value))
        else:
            params.append(value)
    if not parts:
        return "", []
    return f" {prefix} " + " AND ".join(parts), params


def like(term):
    """Patrón ILIKE para 'contiene', o None si el texto viene vacío."""
    term = (term or "").strip()
    return f"%{term}%" if term else None
