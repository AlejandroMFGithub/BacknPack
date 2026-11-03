"""Avisos de intercambios. TEST_DB opcional (Postgres)."""
import os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "n.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def one(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()[0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def page(url="/characters/"): return c.get(url).get_data(as_text=True)
def bell_count(b):
    m = re.search(r'<span class="bell-count"\s*(hidden)?\s*>(\d+)</span>', b)
    return None if m is None else (0 if m.group(1) else int(m.group(2)))
lyra, thor = 1, 2
po = one("SELECT id FROM currencies WHERE code = 'po'")

# Sin nada pendiente: campana sin contador, sin aviso
login("bruno")
b = page()
assert bell_count(b) == 0 and 'class="toast"' not in b and "No tienes intercambios pendientes" in b

# Lyra propone a Thorgar
login("ana")
c.post("/trades/new", data={"to_id": thor, f"give_cur_{po}": 3, "message": "¿Me das una antorcha?"})
b = page()
assert bell_count(b) == 0 and "Esperando respuesta (1)" in b and "Propuesta a <b>Thorgar" in b

login("bruno")
b = page()
print("contador de Bruno:", bell_count(b))
assert bell_count(b) == 1
assert re.search(r'class="toast" role="status" data-trade-ids="\d+"', b) and "<b>Lyra Vientoalto</b> te propone un intercambio" in b
assert "Te proponen (1)" in b and "Te da: 3× po" in b and "«¿Me das una antorcha?»" in b and ">Aceptar</button>" in b
assert re.search(r'Intercambios <span class="nav-badge" data-trade-badge\s*>1</span>', b)
st = c.get("/notifications/state").get_json()
print("estado:", {k: v for k, v in st.items() if k != "panel"})
assert st["incoming"] == 1 and len(st["unseen"]) == 1 and st["unseen"][0]["from"] == "Lyra Vientoalto"

# Cerrar el aviso: queda como visto, el contador sigue (hay que responder)
assert c.post("/notifications/seen").status_code == 204
b = page()
assert 'class="toast"' not in b and bell_count(b) == 1 and c.get("/notifications/state").get_json()["unseen"] == []

# Una propuesta nueva vuelve a avisar, solo de esa
login("ana"); c.post("/trades/new", data={"to_id": thor, f"give_cur_{po}": 1})
login("bruno")
b = page()
assert bell_count(b) == 2 and 'data-trade-ids="' in b and "(y" not in b.split('class="toast"')[1][:400]
# Abrir la lista de intercambios las marca como vistas y resalta las recibidas
b = page("/trades/")
assert "Te lo proponen a ti" in b and 'class="toast"' not in b
assert 'class="toast"' not in page()

# Responder desde la campana
first = one("SELECT MIN(id) FROM trades WHERE status = 'pending'")
c.post(f"/trades/{first}/reject")
b = page()
assert bell_count(b) == 1

# «¿Con quién juegas?» muestra los pendientes de cada personaje
login("bruno"); c.post("/trades/new", data={"to_id": lyra, f"give_cur_{po}": 1})
login("ana")
b = page("/play")
assert "🔔 1 intercambio pendiente" in b

# DM: contador de la campaña en el menú, sin campana ni avisos
login("dm")
b = page("/dm/")
assert "bell-btn" not in b and 'class="toast"' not in b
assert re.search(r'Intercambios <span class="nav-badge" data-trade-badge\s*>2</span>', b)
assert c.get("/notifications/state").get_json()["dm_pending"] == 2

# Con CSRF activado, marcar como visto exige el token (lo manda el JavaScript en una cabecera)
login("bruno")
app.config["CSRF_ENABLED"] = True
assert c.post("/notifications/seen").status_code == 400
token = re.search(r'name="csrf-token" content="([^"]+)"', page()).group(1)
assert c.post("/notifications/seen", headers={"X-CSRF-Token": token}).status_code == 204
print("AVISOS OK")
