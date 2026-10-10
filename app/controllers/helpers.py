import functools
from urllib.parse import urlparse

from flask import abort, g, redirect, request, url_for

from ..models import Character


def is_dm():
    return g.get("user") is not None and g.user["role"] == "dm"


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def dm_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_dm():
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def get_character_or_404(character_id):
    """Devuelve el personaje si el usuario actual puede manejarlo (dueño o DM)."""
    character = Character.get(character_id) if character_id else None
    if character is None:
        abort(404)
    if not is_dm() and character["user_id"] != g.user["id"]:
        abort(403)
    return character


def my_characters():
    """Personajes propios del jugador (pocos). El DM usa el buscador en su lugar."""
    return Character.for_user(g.user["id"])


def acting_character():
    """Personaje con el que se compra o se recoge botín: ?as=<id>, o el primero del jugador.
    El DM lo elige con el buscador (devuelve None hasta que elija)."""
    character_id = request.args.get("as", type=int)
    if character_id:
        return get_character_or_404(character_id)
    if is_dm():
        return None
    own = my_characters()
    return own[0] if own else None


class ListArgs:
    """Parámetros de una lista: ?q=…&sort=…&page=…&<filtros>…"""

    def __init__(self, sorts, default_sort, filters=()):
        args = request.args
        self.q = args.get("q", "").strip()
        self.sort = args.get("sort") if args.get("sort") in sorts else default_sort
        self.page = max(1, args.get("page", 1, type=int))
        self.filters = {name: args.get(name, "").strip() for name in filters}
        self.sort_options = [(key, label) for key, (label, _) in sorts.items()]

    def __getattr__(self, name):  # args.category -> valor del filtro
        try:
            return self.__dict__["filters"][name]
        except KeyError:
            raise AttributeError(name) from None


def redirect_back(default_url):
    """Tras una acción, vuelve a la página de origen conservando búsqueda, filtros y orden.
    Solo acepta páginas de este mismo sitio (nunca redirige fuera)."""
    ref = request.referrer
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc == request.host and parsed.path.startswith("/"):
            return redirect(parsed.path + (f"?{parsed.query}" if parsed.query else ""))
    return redirect(default_url)


def form_int(name, default=None):
    try:
        return int(request.form.get(name, ""))
    except ValueError:
        return default


def collect_quantities(prefix):
    """Lee campos 'prefix<id>' con cantidad > 0 -> {id: cantidad}."""
    result = {}
    for key, value in request.form.items():
        if key.startswith(prefix):
            try:
                ref_id, qty = int(key[len(prefix):]), int(value or 0)
            except ValueError:
                continue
            if qty > 0:
                result[ref_id] = qty
    return result
