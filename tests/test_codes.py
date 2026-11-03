"""Códigos de campaña y pertenencia. TEST_DB opcional (Postgres)."""
import os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db
from app.models.campaign import CODE_ALPHABET

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "k.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return q(sql, *a)[0][0]
def login(u): c.get("/logout"); c.post("/login", data={"username": u, "password": u})
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))
costa, helada = (one("SELECT id FROM campaigns WHERE name LIKE ?", n + "%") for n in ("La Costa", "Las Tierras"))
code = lambda cid: one("SELECT join_code FROM campaigns WHERE id = ?", cid)

# Cada campaña tiene un código de 8 caracteres sin letras confusas, distinto en cada una
for cid in (costa, helada):
    assert len(code(cid)) == 8 and all(ch in CODE_ALPHABET for ch in code(cid)), code(cid)
assert code(costa) != code(helada)
print("códigos:", code(costa), code(helada))
# Miembros: quien tiene personajes en una campaña
assert {r[0] for r in q("SELECT u.username FROM campaign_members m JOIN users u ON u.id = m.user_id WHERE campaign_id = ?", helada)} == {"ana"}

# --- Bruno solo está en la Costa
login("bruno")
b = c.get("/characters/new").get_data(as_text=True)
assert "La Costa de la Espada" in b and "Las Tierras Heladas" not in b
assert "Unirme a una campaña con un código" in b
r = c.post("/characters/new", data={"name": "Intruso", "campaign_id": helada}, follow_redirects=True)
print("sin ser miembro:", flashes(r))
assert not q("SELECT 1 FROM characters WHERE name = 'Intruso'")
# Código erróneo
r = c.post("/campaigns/join", data={"code": "AAAA-BBBB"}, follow_redirects=True)
print("código malo:", flashes(r))
# Código bueno escrito en minúsculas, con espacios y guion
messy = f" {code(helada)[:4].lower()} - {code(helada)[4:].lower()} "
r = c.post("/campaigns/join", data={"code": messy})
assert r.headers["Location"].endswith(f"/characters/new?campaign_id={helada}"), r.headers["Location"]
b = c.get(r.headers["Location"]).get_data(as_text=True)
print("unido:", flashes(c.get("/").__class__ and type("R", (), {"get_data": lambda self, **k: b})()))
assert re.search(rf'<option value="{helada}"\s+selected', b), "la campaña recién unida viene preseleccionada"
r = c.post("/characters/new", data={"name": "Bjorn", "campaign_id": helada}, follow_redirects=True)
assert one("SELECT campaign_id FROM characters WHERE name = 'Bjorn'") == helada
r = c.post("/campaigns/join", data={"code": code(helada)}, follow_redirects=True)
print("otra vez:", flashes(r))

# --- DM: ve el código y los jugadores; genera uno nuevo
login("dm")
b = c.get("/campaigns").get_data(as_text=True)
shown = f"{code(costa)[:4]}-{code(costa)[4:]}"
assert shown in b and f'data-copy="{shown}"' in b and "2 jugadores: ana, bruno" in b
old = code(costa)
c.post(f"/campaigns/{costa}/code")
assert code(costa) != old
# Cerrar una campaña impide entrar con código
c.post(f"/campaigns/{helada}/toggle/is_open")

# --- Carla, jugadora nueva
c.get("/logout"); c.post("/register", data={"username": "carla", "password": "x"})
b = c.get("/characters/new").get_data(as_text=True)
assert "Aún no estás en ninguna campaña" in b and '<details class="card join-box" open' in b
r = c.post("/campaigns/join", data={"code": old}, follow_redirects=True)
print("código antiguo:", flashes(r))
assert not q("SELECT 1 FROM campaign_members m JOIN users u ON u.id = m.user_id WHERE u.username = 'carla'")
r = c.post("/campaigns/join", data={"code": code(helada)}, follow_redirects=True)
print("campaña cerrada:", flashes(r))
r = c.post("/campaigns/join", data={"code": code(costa)}, follow_redirects=True)
print("código nuevo:", flashes(r))
c.post("/characters/new", data={"name": "Carla la Roja", "campaign_id": costa})
assert one("SELECT campaign_id FROM characters WHERE name = 'Carla la Roja'") == costa
# Archivada: tampoco
login("dm"); c.post(f"/campaigns/{costa}/toggle/archived")
c.get("/logout"); c.post("/register", data={"username": "dani", "password": "x"})
r = c.post("/campaigns/join", data={"code": code(costa)}, follow_redirects=True)
print("archivada:", flashes(r))
assert not q("SELECT 1 FROM campaign_members m JOIN users u ON u.id = m.user_id WHERE u.username = 'dani'")

# --- El DM crea un personaje para un jugador: ese jugador pasa a estar en la campaña
login("dm"); c.post(f"/campaigns/{costa}/toggle/archived")
dani = one("SELECT id FROM users WHERE username = 'dani'")
c.post("/characters/new", data={"name": "PNJ de Dani", "campaign_id": helada, "user_id": dani})
assert q("SELECT 1 FROM campaign_members WHERE campaign_id = ? AND user_id = ?", helada, dani)
print("CÓDIGOS OK")
