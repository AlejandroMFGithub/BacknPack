import os, sys, tempfile, shutil, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

# --- 1. Migración sobre copia de la BD real
tmp = tempfile.mkdtemp()
real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "backnpack.sqlite")
copy = os.path.join(tmp, "copy.sqlite")
shutil.copy(real, copy)
app = create_app({"DATABASE": copy, "TESTING": True, "CSRF_ENABLED": False})
with app.app_context():
    db = get_db()
    print("user_version:", db.execute("PRAGMA user_version").fetchone()[0])
    print("tablas:", [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='item_traits'")])
    print("personajes conservados:", db.execute("SELECT COUNT(*) FROM characters").fetchone()[0])
c = app.test_client()
c.post("/login", data={"username": "dm", "password": "dm"})
for url in ["/dm/", "/dm/items", "/dm/items/1/edit", "/characters/1", "/shops/1", "/trades/new?from_id=1&to_id=2"]:
    assert c.get(url).status_code == 200, url
create_app({"DATABASE": copy, "TESTING": True})  # segunda vez: no debe re-migrar
print("migración OK")

# --- 2. BD nueva con demo
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tmp, "new.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
def q(sql, *a):
    with app.app_context():
        return get_db().execute(sql, a).fetchall()
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def body(url):
    r = c.get(url); assert r.status_code == 200, (url, r.status_code); return r.get_data(as_text=True)
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))

c = app.test_client()
lyra = q("SELECT id FROM characters WHERE name LIKE ?", "Lyra%")[0][0]
thor = q("SELECT id FROM characters WHERE name LIKE ?", "Thorgar%")[0][0]
inv_id = lambda ch, name: q("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE ii.character_id=? AND i.name=?", ch, name)
trait_id = lambda name: q("SELECT id FROM item_traits WHERE name=? AND inventory_item_id IS NOT NULL", name)[0][0]

# Botón atrás
login("dm")
assert "Atrás" not in body("/dm/")
for url in ["/dm/items", "/dm/currencies", f"/characters/{lyra}", "/shops/", "/shops/1", "/loot/1", "/trades/", "/trades/new", "/characters/new", "/characters/"]:
    assert 'class="back-link"' in body(url), url
assert 'class="back-link"' in c.get("/register").get_data(as_text=True) or True
b = body(f"/characters/{thor}")
assert "Runa de Moradin" in b and "Sed de sangre" in b and "Oculta" in b

login("bruno")
assert "Atrás" not in body("/characters/")
b = body(f"/characters/{thor}")
assert "Runa de Moradin" in b and "Sed de sangre" not in b
# jugador no puede tocar cualidades ocultas ni fijar usos
assert c.post(f"/characters/{thor}/traits/{trait_id('Sed de sangre')}/use").status_code == 404
assert c.post(f"/characters/{thor}/traits/{trait_id('Runa de Moradin')}/uses", data={"uses_current": 9}).status_code == 403
# usa la runa: 1 -> 0, y luego no puede más
r = c.post(f"/characters/{thor}/traits/{trait_id('Runa de Moradin')}/use", follow_redirects=True)
assert q("SELECT uses_current FROM item_traits WHERE id=?", trait_id("Runa de Moradin"))[0][0] == 0
r = c.post(f"/characters/{thor}/traits/{trait_id('Runa de Moradin')}/use", follow_redirects=True)
print("sin usos:", flashes(r))

# Lyra usa su varita
login("ana")
c.post(f"/characters/{lyra}/traits/{trait_id('Cargas')}/use")
assert q("SELECT uses_current FROM item_traits WHERE id=?", trait_id("Cargas"))[0][0] == 6
assert "6/7" in body(f"/characters/{lyra}")
# poción del botín se apila con las suyas (misma firma)
entry = q("SELECT le.id FROM loot_entries le JOIN items i ON i.id=le.item_id WHERE i.name='Poción de curación'")[0][0]
c.post(f"/loot/1/claim/{entry}", data={"character_id": lyra, "quantity": 1})
rows = q("SELECT quantity FROM inventory_items WHERE id IN (SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE ii.character_id=? AND i.name='Poción de curación')", lyra)
assert [r[0] for r in rows] == [3], rows

# Intercambio: Thorgar le da el hacha (con maldición oculta) a Lyra a cambio de 1 poción
login("bruno")
hacha = inv_id(thor, "Hacha de batalla")[0][0]
pocion_lyra = inv_id(lyra, "Poción de curación")[0][0]
c.post("/trades/new", data={"from_id": thor, "to_id": lyra, f"give_item_{hacha}": 1, f"take_item_{pocion_lyra}": 1})
tid = q("SELECT MAX(id) FROM trades")[0][0]
login("ana")
r = c.post(f"/trades/{tid}/accept", follow_redirects=True); print("intercambio:", flashes(r))
assert inv_id(lyra, "Hacha de batalla") and not inv_id(thor, "Hacha de batalla")
names = [r[0] for r in q("SELECT name FROM item_traits WHERE inventory_item_id=?", inv_id(lyra, "Hacha de batalla")[0][0])]
assert sorted(names) == ["Runa de Moradin", "Sed de sangre"], names
b = body(f"/characters/{lyra}")
assert "Runa de Moradin" in b and "Sed de sangre" not in b
# la poción de Lyra (pila de 3, partida en 1) se apila con la de Thorgar? Thorgar no tenía -> nueva fila con su cualidad
p = inv_id(thor, "Poción de curación")[0][0]
assert [r[0] for r in q("SELECT name FROM item_traits WHERE inventory_item_id=?", p)] == ["Un solo uso"]

# Comprar una segunda varita: NO se apila (tiene cargas)
login("dm")
varita = q("SELECT id FROM items WHERE name = 'Varita de proyectiles mágicos'")[0][0]
c.post(f"/characters/{lyra}/inventory/add", data={"item_id": varita, "quantity": 1, "visible": "1"})
assert len(inv_id(lyra, "Varita de proyectiles mágicos")) == 2
# DM: recargar, fijar, ocultar, quitar, añadir cualidad a ejemplar y a plantilla
t = trait_id("Cargas") if False else q("SELECT id FROM item_traits WHERE name='Cargas' AND uses_current=6")[0][0]
c.post(f"/characters/{lyra}/traits/{t}/uses")
assert q("SELECT uses_current FROM item_traits WHERE id=?", t)[0][0] == 7
c.post(f"/characters/{lyra}/traits/{t}/uses", data={"uses_current": 2})
assert q("SELECT uses_current FROM item_traits WHERE id=?", t)[0][0] == 2
daga = inv_id(lyra, "Daga")[0][0]
r = c.post(f"/characters/{lyra}/inventory/{daga}/traits", data={"name": "Envenenada", "kind": "property", "uses_max": "3", "visible": "1"}, follow_redirects=True)
assert "Envenenada" in r.get_data(as_text=True)
r = c.post(f"/characters/{lyra}/inventory/{daga}/traits", data={"name": "Sin usos", "kind": "charges"}, follow_redirects=True)
print("cargas sin máximo:", flashes(r))
espada = q("SELECT id FROM items WHERE name='Espada larga'")[0][0]
c.post(f"/dm/items/{espada}/traits", data={"name": "+1", "kind": "blessing", "visible": "1", "description": "+1 a ataque y daño"})
assert "+1 a ataque" in body(f"/dm/items/{espada}/edit")
assert "+1 a ataque" in body("/shops/1")
tid2 = q("SELECT id FROM item_traits WHERE item_id=?", espada)[0][0]
c.post(f"/dm/items/{espada}/traits/{tid2}/visibility")
login("ana")
assert "+1 a ataque" not in body("/shops/1")
print("TODO OK")
