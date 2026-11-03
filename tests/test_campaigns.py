"""Campañas: separación de mundos, elección de personaje y herramientas del DM. TEST_DB opcional."""
import os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db
from app.models import RuleError, Trade

tmp = tempfile.mkdtemp()
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tmp, "c.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return q(sql, *a)[0][0]
def login(u): c.get("/logout"); return c.post("/login", data={"username": u, "password": u})
def html(url, code=200):
    r = c.get(url); assert r.status_code == code, (url, r.status_code); return r.get_data(as_text=True)
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))

lyra, thor, sigrid = (one("SELECT id FROM characters WHERE name LIKE ?", n + "%") for n in ("Lyra", "Thorgar", "Sigrid"))
costa, helada = (one("SELECT id FROM campaigns WHERE name LIKE ?", n + "%") for n in ("La Costa", "Las Tierras"))
trampero = one("SELECT id FROM shops WHERE name LIKE ?", "Puesto%")
cueva = one("SELECT id FROM loot_pools WHERE name LIKE ?", "Cueva%")

# --- Jugador con dos personajes: debe elegir al entrar
r = login("ana")
assert r.headers["Location"].endswith("/"), r.headers["Location"]
assert c.get("/").headers["Location"].endswith("/play")
assert "/play" in c.get("/shops/").headers["Location"], "sin personaje elegido no hay tiendas"
b = html("/play")
assert "La Costa de la Espada" in b and "Las Tierras Heladas" in b and "Sigrid Escarcha" in b
r = c.post(f"/play/{lyra}", follow_redirects=True)
print("elegir:", flashes(r))
assert c.get("/").headers["Location"].endswith(f"/characters/{lyra}")

# Lyra ve solo lo de la Costa
b = html("/shops/")
assert "Forja de Brunhilda" in b and "Puesto del trampero" not in b
html(f"/shops/{trampero}", 404); html(f"/loot/{cueva}", 404)
listing = one("SELECT id FROM shop_items WHERE shop_id = ?", trampero)
assert c.post(f"/shops/{trampero}/buy/{listing}", data={"quantity": 1, "currency_id": 1}).status_code == 404
entry = one("SELECT id FROM loot_entries WHERE pool_id = ?", cueva)
assert c.post(f"/loot/{cueva}/claim/{entry}", data={"quantity": 1}).status_code == 404
names = [r["label"] for r in c.get("/api/characters").get_json()["results"]]
print("buscador (Lyra):", names)
assert "Thorgar Puñohierro" in names and "Sigrid Escarcha" not in names
b = html("/shops/1")
assert "Jugando como" not in b and f'name="character_id" value="{lyra}"' in b

# Cambiar a Sigrid: solo lo de las Tierras Heladas
c.post(f"/play/{sigrid}")
b = html("/shops/")
assert "Puesto del trampero" in b and "Forja" not in b
html("/shops/1", 404); html("/loot/1", 404)
assert "Thorgar" not in str(c.get("/api/characters?q=thor").get_json())
html(f"/trades/new?to_id={thor}", 404)
assert c.post("/trades/new", data={"to_id": thor, "give_cur_1": 1}).status_code == 404
html(f"/trades/new?to_id={lyra}", 404)            # ni siquiera con su otro personaje
b = html("/trades/")
assert "Las Tierras Heladas" in b

# Regla del modelo: nunca entre campañas distintas
with app.app_context():
    try:
        Trade.create(lyra, sigrid, {}, {1: 1}, {}, {})
        raise SystemExit("debía impedir el intercambio entre campañas")
    except RuleError as e:
        print("modelo:", e)

# --- Jugador con un solo personaje: se elige solo
login("bruno")
assert c.get("/").headers["Location"].endswith(f"/characters/{thor}")
assert "Thorgar" in html("/shops/1")                # la tienda de su campaña
assert c.get("/campaigns").status_code == 403 and c.post(f"/campaigns/{costa}/activate").status_code == 403

# --- DM
login("dm")
b = html("/dm/")
assert "La Costa de la Espada" in b and "Lyra" in b and "Sigrid" not in b
b = html("/campaigns")
assert "Las Tierras Heladas" in b and "1 personaje" in b
r = c.post("/campaigns", data={"name": "Strahd", "description": "Barovia", "is_open": "1"}, follow_redirects=True)
print("crear:", flashes(r))
strahd = one("SELECT id FROM campaigns WHERE name = 'Strahd'")
b = html("/dm/")
assert "Strahd" in b and "Lyra" not in b
# La última campaña se recuerda entre sesiones
c.get("/logout"); login("dm")
assert "Strahd" in html("/dm/")
c.post(f"/campaigns/{costa}/activate")
# Abrir algo de otra campaña cambia a esa campaña
r = c.get(f"/shops/{trampero}", follow_redirects=True)
print("cambio automático:", flashes(r))
assert "Las Tierras Heladas" in html("/dm/")
c.post(f"/campaigns/{costa}/activate")
# Tienda y botín nuevos van a la campaña activa
c.post("/shops/new", data={"name": "Tienda costera"})
assert one("SELECT campaign_id FROM shops WHERE name = 'Tienda costera'") == costa

# Mover a Thorgar de campaña cancela sus intercambios pendientes
login("ana"); c.post(f"/play/{lyra}")
c.post("/trades/new", data={"to_id": thor, f"give_cur_{one('SELECT id FROM currencies WHERE code = ?', 'po')}": 1})
pending = one("SELECT id FROM trades WHERE status = 'pending'")
login("dm")
r = c.post(f"/characters/{thor}/edit", data={"name": "Thorgar Puñohierro", "campaign_id": helada}, follow_redirects=True)
print("mover:", flashes(r))
assert one("SELECT campaign_id FROM characters WHERE id = ?", thor) == helada
assert one("SELECT status FROM trades WHERE id = ?", pending) == "cancelled"

# Eliminar con personajes: no; archivar: sí, y bloquea a los jugadores
r = c.post(f"/campaigns/{helada}/delete", follow_redirects=True)
print("eliminar con personajes:", flashes(r))
assert q("SELECT 1 FROM campaigns WHERE id = ?", helada)
c.post(f"/campaigns/{helada}/toggle/archived")
login("ana")
r = c.post(f"/play/{sigrid}", follow_redirects=True)
print("archivada:", flashes(r))
assert "archivada" in r.get_data(as_text=True)
# Cerrada a nuevos personajes: el jugador no puede crear ahí
login("dm"); c.post(f"/campaigns/{strahd}/toggle/is_open")
login("ana")
assert "Strahd" not in html("/characters/new")
r = c.post("/characters/new", data={"name": "Ireena", "campaign_id": strahd}, follow_redirects=True)
print("cerrada:", flashes(r))
assert not q("SELECT 1 FROM characters WHERE name = 'Ireena'")
r = c.post("/characters/new", data={"name": "Nadia", "campaign_id": costa}, follow_redirects=True)
nadia = one("SELECT id FROM characters WHERE name = 'Nadia'")
assert one("SELECT campaign_id FROM characters WHERE id = ?", nadia) == costa
assert c.get("/").headers["Location"].endswith(f"/characters/{nadia}"), "el personaje nuevo pasa a ser el activo"
# El DM sí puede crear en una campaña cerrada
login("dm")
c.post("/characters/new", data={"name": "Rahadin", "campaign_id": strahd, "user_id": 1})
assert one("SELECT campaign_id FROM characters WHERE name = 'Rahadin'") == strahd
# Eliminar campaña vacía
c.post("/campaigns", data={"name": "Vacía"})
vacia = one("SELECT id FROM campaigns WHERE name = 'Vacía'")
c.post(f"/campaigns/{vacia}/delete")
assert not q("SELECT 1 FROM campaigns WHERE id = ?", vacia)
print("CAMPAÑAS OK")
