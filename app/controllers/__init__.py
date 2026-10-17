"""Capa Controlador: recibe peticiones, llama a los modelos y elige la vista."""
from ..models import Campaign
from . import api, auth, campaigns, characters, dm, library, loot, main, notifications, shops, spells, trades
from .helpers import is_dm


def register_controllers(app):
    # auth primero: carga g.user antes de que campaigns fije g.character / g.campaign
    for module in (auth, campaigns, main, characters, spells, dm, library, shops, loot, trades, api, notifications):
        app.register_blueprint(module.bp)

    @app.context_processor
    def inject_helpers():
        return {"is_dm": is_dm, "dm_campaigns": lambda: Campaign.all(include_archived=False),
                "trade_alerts": notifications.trade_alerts}
