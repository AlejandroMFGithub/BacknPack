"""Consultas de listas: búsqueda, filtros, orden y paginación comunes a todos los modelos.

Cada modelo declara sus órdenes posibles en un dict SORTS = {clave: (etiqueta, SQL)}.
Solo se usan claves de esa lista blanca, nunca SQL que venga del usuario.
"""
from ..db import get_db

PER_PAGE = 50


class Page:
    """Una página de resultados."""

    def __init__(self, rows, total, page, per_page):
        self.rows = rows
        self.total = total
        self.per_page = per_page
        self.pages = max(1, -(-total // per_page))
        self.page = min(max(1, page), self.pages)

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __bool__(self):
        return bool(self.rows)


def sort_sql(sorts, key, default):
    return sorts.get(key, sorts[default])[1]


def paginate(select_sql, where, params, order_sql, page=1, per_page=PER_PAGE, order_params=()):
    """Ejecuta `select_sql` + filtros + orden y devuelve una Page."""
    db = get_db()
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.execute(f"SELECT COUNT(*) FROM ({select_sql}{where_sql}) AS sub", tuple(params)).fetchone()[0]
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    rows = db.execute(
        f"{select_sql}{where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        (*params, *order_params, per_page, (page - 1) * per_page),
    ).fetchall()
    return Page(rows, total, page, per_page)
