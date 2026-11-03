"""El jugador elimina sus personajes. TEST_DB opcional (Postgres)."""
import io, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "d.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return q(sql, *a)[0][0]
def login(u): c.get("/logout"); c.post("/login", data={"username": u, "password": u})
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))
lyra, thor, sigrid = (one("SELECT id FROM characters WHERE name LIKE ?", n + "%") for n in ("Lyra", "Thorgar", "Sigrid"))

login("ana"); c.post(f"/play/{lyra}")
b = c.get("/characters/").get_data(as_text=True)
assert b.count('class="btn-icon btn-icon-danger"') == 2 and "Eliminar a Sigrid Escarcha" in b
# Un intercambio pendiente y una imagen: se van con el personaje
po = one("SELECT id FROM currencies WHERE code = 'po'")
c.post("/trades/new", data={"to_id": thor, f"give_cur_{po}": 1})
buf = io.BytesIO(); Image.new("RGB", (64, 64), "red").save(buf, "PNG"); buf.seek(0)
c.post(f"/characters/{lyra}/avatar", data={"image": (buf, "a.png")}, content_type="multipart/form-data")
assert q("SELECT 1 FROM trades WHERE from_character_id = ?", lyra) and q("SELECT 1 FROM character_avatars WHERE character_id = ?", lyra)

# Borrar uno que no es el activo: sigue jugando con Lyra
r = c.post(f"/characters/{sigrid}/delete", follow_redirects=True)
print("borrar Sigrid:", flashes(r))
assert not q("SELECT 1 FROM characters WHERE id = ?", sigrid)
assert c.get("/").headers["Location"].endswith(f"/characters/{lyra}")
# No puede borrar el de otro jugador
assert c.post(f"/characters/{thor}/delete").status_code == 403
assert q("SELECT 1 FROM characters WHERE id = ?", thor)
# Borrar el activo: se limpia todo y vuelve a crear/elegir
r = c.post(f"/characters/{lyra}/delete", follow_redirects=True)
print("borrar Lyra:", flashes(r))
for table, col in [("characters", "id"), ("inventory_items", "character_id"), ("character_currencies", "character_id"),
                   ("character_avatars", "character_id"), ("trades", "from_character_id"), ("conditions", "character_id")]:
    assert not q(f"SELECT 1 FROM {table} WHERE {col} = ?", lyra), table
assert c.get("/").headers["Location"].endswith("/characters/new"), "sin personajes: a crear uno"
assert "/play" in c.get("/shops/").headers["Location"]
# El DM también puede
login("dm")
r = c.post(f"/characters/{thor}/delete", follow_redirects=True)
print("DM:", flashes(r))
assert not q("SELECT 1 FROM characters WHERE id = ?", thor)
print("BORRADO OK")
