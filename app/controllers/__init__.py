"""Capa Controlador: recibe peticiones, llama a los modelos y elige la vista."""
from . import api, auth, characters, dm, loot, main, shops, trades
from .helpers import is_dm


def register_controllers(app):
    for module in (auth, main, characters, dm, shops, loot, trades, api):
        app.register_blueprint(module.bp)

    @app.context_processor
    def inject_helpers():
        return {"is_dm": is_dm}
