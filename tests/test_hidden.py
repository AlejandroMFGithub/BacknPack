"""Personajes ocultos al resto de jugadores. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "hid.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def one(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()[0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', htmllib.unescape(r.get_data(as_text=True)))
def found(q=""): return [r["label"] for r in c.get(f"/api/characters?q={q}").get_json()["results"]]
def hide(cid, value): return c.post(f"/characters/{cid}/hidden", data={"hide": value}, follow_redirects=True)

LYRA, THORGAR = 1, 2

# --- El jugador oculta a su personaje ---------------------------------------------------------
login("bruno"); assert "Lyra Vientoalto" in found()
login("ana")
r = hide(LYRA, "1")
print("ocultar:", flashes(r))
assert one("SELECT hidden_by FROM characters WHERE id = 1") == "player"
assert "Oculto a los jugadores" in htmllib.unescape(c.get("/characters/").get_data(as_text=True))
assert "Lyra Vientoalto" in found()                               # su dueña lo sigue viendo
login("bruno")
print("Bruno busca:", found())
assert "Lyra Vientoalto" not in found() and "Lyra Vientoalto" not in found("lyra")
assert c.get(f"/trades/new?to_id={LYRA}").status_code == 404
assert c.post("/trades/new", data={"to_id": LYRA, "give_cur_1": "1"}).status_code == 404
assert hide(LYRA, "0").status_code == 403                        # no es suyo
login("dm")
assert "Lyra Vientoalto 🙈" in found()                            # el DM ve a todos
login("ana"); hide(LYRA, "0")
assert one("SELECT hidden_by FROM characters WHERE id = 1") is None
login("bruno"); assert "Lyra Vientoalto" in found()
assert c.get(f"/trades/new?to_id={LYRA}").status_code == 200

# --- El DM oculta: el jugador no puede deshacerlo --------------------------------------------
login("dm")
r = hide(THORGAR, "1")
assert one("SELECT hidden_by FROM characters WHERE id = 2") == "dm"
b = htmllib.unescape(c.get("/dm/").get_data(as_text=True))
assert "Oculto por el DM" in b and "Mostrar Thorgar Puñohierro a los jugadores" in b
login("ana"); assert "Thorgar Puñohierro" not in found()
login("bruno")
b = htmllib.unescape(c.get("/characters/").get_data(as_text=True))
assert "Oculto por el DM" in b and "Mostrar Thorgar" not in b      # sin botón para mostrarlo
r = hide(THORGAR, "0")
print("jugador intenta mostrar:", flashes(r))
assert ("error", "El DM ha ocultado a este personaje: solo el DM puede volver a mostrarlo.") in flashes(r)
hide(THORGAR, "1")
assert one("SELECT hidden_by FROM characters WHERE id = 2") == "dm"  # ocultarlo de nuevo no le quita el candado
login("dm"); hide(THORGAR, "0")
assert one("SELECT hidden_by FROM characters WHERE id = 2") is None
login("ana"); assert "Thorgar Puñohierro" in found()

# El DM también puede mostrar uno que ocultó el jugador
login("ana"); hide(LYRA, "1")
login("dm"); r = hide(LYRA, "0")
assert one("SELECT hidden_by FROM characters WHERE id = 1") is None, flashes(r)
print("OCULTOS OK")
