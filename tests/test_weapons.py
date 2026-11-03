"""Ataques con armas e inventario en pestañas. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "wp.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def one(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()[0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', htmllib.unescape(r.get_data(as_text=True)))
def attacks(cid):
    """{arma: (clase de color, ataque, daño, daño a dos manos, sin competencia)} de la tarjeta de Ataques."""
    b = htmllib.unescape(c.get(f"/characters/{cid}").get_data(as_text=True))
    card = b[b.index('id="ataques"'):b.index('id="tiradas"')]
    out = {}
    for row in re.findall(r"<tr class=\"[^\"]*\">(.*?)</tr>", card, re.S):
        name = re.search(r"<td><b>([^<]+)</b>", row).group(1)
        att = re.search(r'attack-roll calc( mod-\w+)?"[^>]*>\s*<b class="calc-value">([^<]+)</b>', row)
        dmg = re.search(r'damage-roll[^>]*>\s*<b class="calc-value">([^<]+)</b>\s*([^<{]*)', row)
        two = re.search(r'two-hands">([^<]+)</span>', row)
        out[name] = ((att.group(1) or "").strip(), att.group(2).replace("−", "-"),
                     f"{dmg.group(1)} {dmg.group(2).strip()}".strip(), two.group(1) if two else None, "sin competencia" in row)
    return out
def item(name): return one("SELECT id FROM items WHERE name = ?", name)
def give(cid, name, equip=True):
    c.post(f"/characters/{cid}/inventory/add", data={"item_id": item(name), "quantity": 1, "visible": "1"})
    inv = one("SELECT MAX(id) FROM inventory_items WHERE character_id = ? AND item_id = ?", cid, item(name))
    if equip:
        c.post(f"/characters/{cid}/inventory/{inv}/equip")
    return inv

LYRA, THORGAR, SIGRID = 1, 2, 3
login("dm")
assert one("SELECT COUNT(*) FROM items WHERE weapon IS NOT NULL") >= 78

# --- 1. Datos de ejemplo --------------------------------------------------------------------------
a = attacks(THORGAR)
print("Thorgar:", a)
assert a["Hacha de batalla"] == ("", "+5", "1d8 + 3 cortante", "1d10 + 3 a dos manos", False)   # FUE 17 + 2
assert a["Golpe sin armas"] == ("", "+5", "4 contundente", None, False)                        # 1 + FUE
a = attacks(LYRA)
assert a["Arco corto"][1:3] == ("+5", "1d6 + 3 perforante")                                     # DES 17 + 2

# --- 2. Sutil, competencia por clase, armas mágicas ------------------------------------------------
give(THORGAR, "Estoque")
assert attacks(THORGAR)["Estoque"][1:3] == ("+5", "1d8 + 3 perforante")       # sutil: la mejor (FUE 17 > DES 10)
give(LYRA, "Estoque")
assert attacks(LYRA)["Estoque"][1:3] == ("+5", "1d8 + 3 perforante")          # sutil con DES 17
give(THORGAR, "Cimitarra de velocidad")
a = attacks(THORGAR)["Cimitarra de velocidad"]
print("cimitarra de velocidad:", a)
assert a == ("mod-up", "+7", "1d6 + 5 cortante", None, False)                  # +3 FUE +2 comp. +2 mágica, en verde
# Druida: armas de druida sí, marciales no
sword = give(SIGRID, "Espada larga")
give(SIGRID, "Cimitarra")
a = attacks(SIGRID)
print("Sigrid:", a)
assert a["Espada larga"][1] == "+0" and a["Espada larga"][4] is True          # FUE 10, sin competencia
assert a["Cimitarra"][1] == "+2" and a["Cimitarra"][4] is False                # cimitarra: arma de druida
# Fijar la competencia a mano (y volver a la de su clase)
c.post(f"/characters/3/inventory/{sword}/proficient", data={"value": "1"})
assert attacks(SIGRID)["Espada larga"][1:] == ("+2", "1d8 cortante", "1d10 a dos manos", False)
b = htmllib.unescape(c.get("/characters/3").get_data(as_text=True))
assert "(fijado a mano)" in b
c.post(f"/characters/3/inventory/{sword}/proficient", data={"value": "auto"})
assert attacks(SIGRID)["Espada larga"][4] is True
# Bardo: competente con la espada larga por nombre, no con el resto de marciales
c.post("/characters/new", data={"name": "Bardolino", "level": 1, "campaign_id": 1,
       "class_id": one("SELECT id FROM classes WHERE code = 'bard'"), "dexterity": 14})
bard = one("SELECT id FROM characters WHERE name = 'Bardolino'")
give(bard, "Espada larga"); give(bard, "Gran hacha"); give(bard, "Ballesta de mano")
a = attacks(bard)
print("bardo:", {k: v[4] for k, v in a.items()})
assert (a["Espada larga"][4], a["Ballesta de mano"][4], a["Gran hacha"][4]) == (False, False, True)
# Un efecto de «ataques con arma» (p. ej. estilo de combate o Bendición fija)
c.post("/characters/2/conditions/add", data={"name": "Estilo: Arquería mental", "kind": "buff",
       "eff_t": ["weapon_attack", "weapon_damage"], "eff_op": ["add", "add"], "eff_v": ["1", "2"], "eff_cap": ["none", "none"]})
a = attacks(THORGAR)["Hacha de batalla"]
assert a == ("mod-up", "+6", "1d8 + 5 cortante", "1d10 + 5 a dos manos", False)

# --- 3. El DM crea un arma propia en el catálogo ----------------------------------------------------
r = c.post("/dm/items", data={"name": "Kopesh de bronce", "category": "Arma", "w_form": "1", "w_enabled": "1",
           "w_dice": "1d8", "w_type": "cortante", "w_cat": "martial", "w_props": ["finesse"], "w_bonus": "1"},
           follow_redirects=True)
w = one("SELECT weapon FROM items WHERE name = 'Kopesh de bronce'")
assert w == '{"dice":"1d8","type":"cortante","cat":"martial","ranged":false,"props":["finesse"],"two":null,"range":null,"bonus":1,"base":null,"mastery":null,"extra":[]}', w
r = c.post("/dm/items", data={"name": "Arma rota", "w_form": "1", "w_enabled": "1", "w_dice": "un montón"}, follow_redirects=True)
assert ("error", "«unmontón» no es un dado válido (p. ej. 1d8 o 2d6).") in flashes(r), flashes(r)
r = c.post("/dm/items", data={"name": "Piedra rara", "w_form": "1", "w_dice": "1d4"}, follow_redirects=True)   # sin marcar: no es arma
assert one("SELECT weapon FROM items WHERE name = 'Piedra rara'") is None
b = htmllib.unescape(c.get(f"/dm/items/{item('Kopesh de bronce')}/edit").get_data(as_text=True))
assert 'name="w_enabled" value="1" class="js-weapon-toggle" checked' in b and 'value="1d8"' in b
give(THORGAR, "Kopesh de bronce")
assert attacks(THORGAR)["Kopesh de bronce"][1:3] == ("+7", "1d8 + 6 cortante")   # 3 + 2 + 1 mágica + 1 efecto / 3 + 1 + 2

# --- 4. Inventario en pestañas ---------------------------------------------------------------------
b = htmllib.unescape(c.get("/characters/1").get_data(as_text=True))
inv = b[b.index('id="inventario"'):]
tabs = dict(re.findall(r'data-tab="(\w+)"[^>]*>[^<]*<span>(\d+)</span>', inv))
print("pestañas de Lyra:", tabs)
assert tabs["all"] == str(one("SELECT COUNT(*) FROM inventory_items WHERE character_id = 1")) and tabs["weapons"] == "4"
groups = {name: group for group, name in re.findall(r'data-group="(\w+)">\s*<div class="inv-main">\s*<b[^>]*>([^<]+)</b>', inv)}
assert groups["Arco corto"] == "weapons" and groups["Armadura de cuero"] == "armor"
assert groups["Poción de curación"] == "consumables" and groups["Varita de proyectiles mágicos"] == "magic"
assert "⚔ <b>+5</b> al ataque" in inv                                                # línea de ataque en el arma
print("ARMAS OK")
