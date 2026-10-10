from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..models import Character, Currency, Inventory, ItemTrait, RuleError, Trade
from ..models.item_trait import KINDS as TRAIT_KINDS
from ..models.trade import STATUS
from .helpers import collect_quantities, get_character_or_404, is_dm, login_required, my_characters

bp = Blueprint("trades", __name__, url_prefix="/trades")


@bp.route("/")
@login_required
def index():
    trades = Trade.all() if is_dm() else Trade.for_user(g.user["id"])
    return render_template(
        "trades/index.html",
        trades=trades,
        lines=Trade.lines_for([t["id"] for t in trades]),
        status=STATUS,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    from_id = request.values.get("from_id", type=int)
    to_id = request.values.get("to_id", type=int)
    from_char = get_character_or_404(from_id) if from_id else None
    to_char = (Character.get(to_id) or abort(404)) if to_id else None

    if request.method == "POST" and from_char and to_char:
        try:
            Trade.create(
                from_char["id"], to_char["id"],
                give_items=collect_quantities("give_item_"),
                give_currency=collect_quantities("give_cur_"),
                take_items=collect_quantities("take_item_"),
                take_currency=collect_quantities("take_cur_"),
                message=request.form.get("message"),
            )
        except RuleError as e:
            flash(str(e), "error")
        else:
            flash(f"Propuesta enviada a {to_char['name']}.", "ok")
            return redirect(url_for("trades.index"))

    ctx = {}
    if from_char and to_char:
        from_inventory = Inventory.for_character(from_char["id"])
        to_inventory = Inventory.for_character(to_char["id"])
        ctx = {
            "from_inventory": from_inventory,
            "from_balances": Currency.balances(from_char["id"]),
            "to_inventory": to_inventory,
            "currencies": Currency.all(),
            "traits": ItemTrait.for_inventory(
                [r["id"] for r in from_inventory + to_inventory], include_hidden=False,
            ),
            "trait_kinds": TRAIT_KINDS,
        }
    return render_template(
        "trades/new.html",
        mine=my_characters(),
        targets=[c for c in Character.all() if not from_char or c["id"] != from_char["id"]],
        from_char=from_char,
        to_char=to_char,
        **ctx,
    )


def _resolve(trade_id, action):
    trade = Trade.get(trade_id) or abort(404)
    me = g.user["id"]
    allowed = {
        "accept": trade["to_user_id"] == me,
        "reject": trade["to_user_id"] == me,
        "cancel": trade["from_user_id"] == me,
    }[action]
    if not (allowed or is_dm()):
        abort(403)
    try:
        if action == "accept":
            Trade.accept(trade_id)
            flash("¡Intercambio completado!", "ok")
        else:
            Trade.close(trade_id, "rejected" if action == "reject" else "cancelled")
            flash("Intercambio cerrado.", "ok")
    except RuleError as e:
        flash(str(e), "error")
    return redirect(url_for("trades.index"))


@bp.route("/<int:trade_id>/<any(accept, reject, cancel):action>", methods=["POST"])
@login_required
def resolve(trade_id, action):
    return _resolve(trade_id, action)
