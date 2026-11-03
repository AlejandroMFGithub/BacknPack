"""Modo producción contra PostgreSQL. Uso: TEST_DB=uri1 TEST_DB2=uri2 python test_prod.py"""
import os, re, sys, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

DB, DB2 = os.environ["TEST_DB"], os.environ["TEST_DB2"]

def token(c, url):
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

def post(c, url, data, page=None):
    return c.post(url, data={**data, "csrf_token": token(c, page or url)}, follow_redirects=True)

os.environ["RENDER"] = "true"
# 1. Sin secreto no arranca
try:
    create_app({"DATABASE": DB}); raise SystemExit("debía fallar sin BACKNPACK_SECRET")
except RuntimeError as e:
    print("sin secreto:", e)
os.environ["BACKNPACK_SECRET"] = "x" * 40
# 2. BD vacía sin DM_PASSWORD no arranca
try:
    create_app({"DATABASE": DB}); raise SystemExit("debía fallar sin DM_PASSWORD")
except RuntimeError as e:
    print("sin DM_PASSWORD:", e)
os.environ["DM_PASSWORD"] = "dragon-rojo-42"
app = create_app({"DATABASE": DB})
assert app.config["SESSION_COOKIE_SECURE"]
with app.app_context():
    users = [tuple(r) for r in get_db().execute("SELECT username, role FROM users").fetchall()]
    print("usuarios iniciales:", users)
    assert users == [("dm", "dm")]
    assert get_db().execute("SELECT COUNT(*) FROM items").fetchone()[0] > 5
c = app.test_client()
# CSRF
assert c.post("/login", data={"username": "dm", "password": "dragon-rojo-42"}).status_code == 400
r = post(c, "/login", {"username": "dm", "password": "dm"})
assert "incorrectos" in r.get_data(as_text=True)
r = post(c, "/login", {"username": "dm", "password": "dragon-rojo-42"})
assert "Campañas" in r.get_data(as_text=True) and "Salir" in r.get_data(as_text=True)   # sin campañas aún: a crearlas
# Cambio de contraseña
r = post(c, "/account", {"current": "mal", "new": "nuevaclave1", "repeat": "nuevaclave1"})
assert "no es correcta" in r.get_data(as_text=True)
r = post(c, "/account", {"current": "dragon-rojo-42", "new": "nuevaclave1", "repeat": "nuevaclave1"})
assert "Contraseña cambiada" in r.get_data(as_text=True)
c.get("/logout")
# Registro cerrado sin INVITE_CODE
assert "registro está cerrado" in c.get("/register").get_data(as_text=True)
assert "Crea una cuenta" not in c.get("/login").get_data(as_text=True)
post(c, "/register", {"username": "intruso", "password": "x"}, page="/login")
with app.app_context():
    assert get_db().execute("SELECT COUNT(*) FROM users WHERE username = 'intruso'").fetchone()[0] == 0
# Con código de invitación
app.config["INVITE_CODE"] = "mesa-del-jueves"
r = post(c, "/register", {"username": "intruso", "password": "x", "invite": "otro"})
assert "no es correcto" in r.get_data(as_text=True)
r = post(c, "/register", {"username": "carla", "password": "x", "invite": "mesa-del-jueves"})
assert "Bienvenido" in r.get_data(as_text=True)
r = post(c, "/characters/new", {"name": "Nyx O'Malley", "speed": "30"}, page="/characters/new")
assert "campaña" in r.get_data(as_text=True).lower()                         # sin campaña no puede crear personaje
print("producción OK")

# 3. Copia de la SQLite real a otra BD Postgres, excluyendo cuentas demo
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "real.sqlite")
shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "backnpack.sqlite"), src)
os.environ["DM_PASSWORD"] = "clave-copiada-99"
app2 = create_app({"DATABASE": DB2})
res = app2.test_cli_runner().invoke(args=["copy-to-postgres", "--source", src, "--exclude-users", "ana,bruno", "--yes"])
print(res.output)
assert res.exit_code == 0, res.exception
with app2.app_context():
    db = get_db()
    print("usuarios:", [r[0] for r in db.execute("SELECT username FROM users ORDER BY id").fetchall()])
    print("personajes:", [r[0] for r in db.execute("SELECT name FROM characters ORDER BY id").fetchall()])
    assert db.execute("SELECT COUNT(*) FROM users WHERE username IN ('ana','bruno')").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM characters WHERE name = 'Mahara Oshi'").fetchone()[0] == 1
    campaign = db.execute("SELECT id FROM campaigns ORDER BY id").fetchone()[0]
    assert db.execute("SELECT COUNT(*) FROM items WHERE name = 'Bola de cristal de telepatía'").fetchone()[0] == 1
c = app2.test_client()
r = post(c, "/login", {"username": "dm", "password": "clave-copiada-99"})
assert "Panel del DM" in r.get_data(as_text=True)
for url in ["/dm/", "/dm/items", "/shops/", "/loot/", "/trades/", "/characters/"]:
    assert c.get(url).status_code == 200, url
# las secuencias siguen bien tras copiar ids
r = post(c, "/characters/new", {"name": "Tras la copia", "user_id": "1", "campaign_id": campaign}, page="/characters/new")
assert "Personaje creado" in r.get_data(as_text=True)
r = post(c, "/dm/items", {"name": "Objeto nuevo", "category": "Tesoro"}, page="/dm/items")
assert "añadido" in r.get_data(as_text=True)
print("copia OK")
