import functools

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
    return Character.all() if is_dm() else Character.for_user(g.user["id"])


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
