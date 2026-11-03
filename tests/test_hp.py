"""PG actuales y temporales con los botones − / +. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "hp.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def hp(cid):
    with app.app_context():
        r = get_db().execute("SELECT hp_current, hp_temp FROM characters WHERE id = ?", (cid,)).fetchone()
        return r["hp_current"], r["hp_temp"]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def press(cid, op, amount=1, json=True):
    headers = {"Accept": "application/json"} if json else {}
    return c.post(f"/characters/{cid}/hp", data={"op": op, "amount": amount}, headers=headers)

LYRA, THORGAR = 1, 2
login("bruno")
assert hp(THORGAR) == (34, 5)
b = htmllib.unescape(c.get("/characters/2").get_data(as_text=True))
assert 'class="js-hp-current" aria-live="polite">34<' in b and 'class="js-hp-temp" aria-live="polite">5<' in b

# Daño: primero los temporales
r = press(THORGAR, "damage", 3)
assert r.get_json() == {"hp_current": 34, "hp_temp": 2, "hp_max": 34}
r = press(THORGAR, "damage", 10)
assert r.get_json() == {"hp_current": 26, "hp_temp": 0, "hp_max": 34}         # 2 temporales + 8 actuales
press(THORGAR, "damage", 500)
assert hp(THORGAR) == (0, 0)                                                     # nunca por debajo de 0
# Curar: hasta el máximo
press(THORGAR, "heal", 30); press(THORGAR, "heal", 10)
assert hp(THORGAR) == (34, 0)
# Temporales
press(THORGAR, "temp_add", 8); press(THORGAR, "temp_sub", 3)
assert hp(THORGAR) == (34, 5)
press(THORGAR, "temp_sub", 50)
assert hp(THORGAR) == (34, 0)
# Sin JS: redirige a la ficha
r = press(THORGAR, "damage", 4, json=False)
assert r.status_code == 302 and r.headers["Location"].endswith("/characters/2#pg") and hp(THORGAR) == (30, 0)
# Cantidad vacía o rara: 1
c.post("/characters/2/hp", data={"op": "damage", "amount": ""}, headers={"Accept": "application/json"})
assert hp(THORGAR) == (29, 0)
r = press(THORGAR, "explode")
assert r.status_code == 400 and r.get_json()["error"] == "Operación de PG no válida."
# No es suyo
assert press(LYRA, "damage").status_code == 403

# El máximo con efectos: un efecto de +10 PG máximos deja curar por encima de los 28 de la ficha
login("ana")
c.post("/characters/1/conditions/add", data={"name": "Ayuda", "kind": "buff",
       "eff_t": ["hp_max"], "eff_op": ["add"], "eff_v": ["10"], "eff_cap": ["none"]})
r = press(LYRA, "heal", 100)
assert r.get_json() == {"hp_current": 38, "hp_temp": 0, "hp_max": 38}
# Si el efecto se va, curar no le baja los PG que ya tiene
with app.app_context():
    aid = get_db().execute("SELECT id FROM conditions WHERE name = 'Ayuda'").fetchone()[0]
c.post(f"/characters/1/conditions/{aid}/toggle")
press(LYRA, "heal", 1)
assert hp(LYRA) == (38, 0)

# El formulario de edición también guarda los temporales; las listas los muestran
login("dm")
c.post("/characters/2/edit", data={"name": "Thorgar Puñohierro", "hp_max": 34, "hp_current": 20, "hp_temp": 7, "class_id": ""})
assert hp(THORGAR) == (20, 7)
b = htmllib.unescape(c.get("/dm/").get_data(as_text=True))
assert '20/34 <span class="hp-temp-text" title="PG temporales">+7</span>' in b
print("PG OK")
