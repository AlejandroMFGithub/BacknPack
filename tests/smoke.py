import os, sys, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

tmp = tempfile.mkdtemp()
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tmp, "t.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})

def q(sql, *a):
    with app.app_context():
        return get_db().execute(sql, a).fetchall()

def bal(char, code):
    r = q("""SELECT amount FROM character_currencies cc JOIN currencies c ON c.id=cc.currency_id
             JOIN characters ch ON ch.id=cc.character_id WHERE ch.name LIKE ? AND c.code=?""", char + "%", code)
    return r[0][0] if r else 0

def inv(char, item):
    r = q("""SELECT SUM(quantity) FROM inventory_items ii JOIN items i ON i.id=ii.item_id
             JOIN characters ch ON ch.id=ii.character_id WHERE ch.name LIKE ? AND i.name=?""", char + "%", item)
    return r[0][0] or 0

def login(c, u):
    c.get("/logout")
    r = c.post("/login", data={"username": u, "password": u}, follow_redirects=True)
    assert r.status_code == 200, r.status_code
    if u == "ana":
        c.post("/play/1")  # Ana tiene dos personajes: juega con Lyra

def ok(r, *needles):
    assert r.status_code == 200, (r.status_code, r.request.path)
    body = r.get_data(as_text=True)
    for n in needles:
        assert n in body, (n, r.request.path)
    return body

def flashes(body):
    return re.findall(r'class="flash flash-(\w+)">([^<]*)<', body)

c = app.test_client()
lyra = q("SELECT id FROM characters WHERE name LIKE ?", "Lyra%")[0][0]
thor = q("SELECT id FROM characters WHERE name LIKE ?", "Thorgar%")[0][0]
cur = {r[0]: r[1] for r in q("SELECT code, id FROM currencies")}

# --- DM ve todo
login(c, "dm")
ok(c.get("/dm/"), "Lyra", "Thorgar", "Marca del licántropo")
ok(c.get(f"/characters/{lyra}"), "Amuleto de hueso", "Oculto al jugador", "Guardar bolsa")
for url in ["/dm/items", "/dm/currencies", "/shops/", "/shops/1", "/loot/", "/loot/1", "/trades/", "/characters/new", "/dm/items/1/edit"]:
    ok(c.get(url))

# DM da un objeto y una maldición
pocion = q("SELECT id FROM items WHERE name='Poción de curación'")[0][0]
c.post(f"/characters/{thor}/inventory/add", data={"item_id": pocion, "quantity": 3, "visible": "1"})
assert inv("Thorgar", "Poción de curación") == 3
c.post(f"/characters/{thor}/conditions/add", data={"name": "Envenenado", "kind": "condition", "visible": "1"})
c.post(f"/characters/{thor}/currencies", data={f"cur_{cur['po']}": 50})
assert bal("Thorgar", "po") == 50

# --- Jugador: no ve lo oculto, no accede a lo ajeno ni a DM
login(c, "ana")
body = ok(c.get(f"/characters/{lyra}"), "Bendición", "Daga")
assert "Amuleto de hueso" not in body and "licántropo" not in body
assert c.get(f"/characters/{thor}").status_code == 403
assert c.get("/dm/").status_code == 403
assert c.post(f"/characters/{lyra}/inventory/add", data={"item_id": pocion, "quantity": 1}).status_code == 403

# Comprar espada larga (15 po) con po
listing = {r[0]: r[1] for r in q("SELECT i.name, si.id FROM shop_items si JOIN items i ON i.id=si.item_id")}
r = c.post(f"/shops/1/buy/{listing['Espada larga']}", data={"character_id": lyra, "quantity": 1, "currency_id": cur["po"]}, follow_redirects=True)
print("compra po:", flashes(r.get_data(as_text=True)))
assert bal("Lyra", "po") == 10 and inv("Lyra", "Espada larga") == 1
# Flechas (1 po) pagadas con plata -> 10 pp
r = c.post(f"/shops/1/buy/{listing['Flechas (20)']}", data={"character_id": lyra, "quantity": 2, "currency_id": cur["pp"]}, follow_redirects=True)
print("compra pp:", flashes(r.get_data(as_text=True)))
assert bal("Lyra", "pp") == 10 and inv("Lyra", "Flechas (20)") == 3
# Sin fondos
r = c.post(f"/shops/1/buy/{listing['Cota de malla']}", data={"character_id": lyra, "quantity": 1, "currency_id": cur["po"]}, follow_redirects=True)
print("sin fondos:", flashes(r.get_data(as_text=True)))
assert inv("Lyra", "Cota de malla") == 0 and bal("Lyra", "po") == 10
# Mercado de las sombras: solo fichas
r = c.post(f"/shops/2/buy/{listing['Anillo de protección']}", data={"character_id": lyra, "quantity": 1, "currency_id": cur["po"]}, follow_redirects=True)
print("sin cambio:", flashes(r.get_data(as_text=True)))
assert inv("Lyra", "Anillo de protección") == 0
# (El jugador compra siempre con el personaje con el que juega: el character_id del formulario no cuenta)

# Botín
entries = {(r[1] or r[2]): r[0] for r in q("""SELECT le.id, i.name, c.code FROM loot_entries le
    LEFT JOIN items i ON i.id=le.item_id LEFT JOIN currencies c ON c.id=le.currency_id""")}
r = c.post(f"/loot/1/claim/{entries['pp']}", data={"character_id": lyra, "quantity": 15}, follow_redirects=True)
print("botín:", flashes(r.get_data(as_text=True)))
assert bal("Lyra", "pp") == 25
c.post(f"/loot/1/claim/{entries['Cimitarra']}", data={"character_id": lyra, "quantity": 1})
assert inv("Lyra", "Cimitarra") == 1
r = c.post(f"/loot/1/claim/{entries['Cimitarra']}", data={"character_id": lyra, "quantity": 5}, follow_redirects=True)
print("botín excesivo:", flashes(r.get_data(as_text=True)))
assert inv("Lyra", "Cimitarra") == 1

# Intercambio: Lyra da 2 dagas + 5 pp, pide 1 antorcha + 3 po
ok(c.get(f"/trades/new?from_id={lyra}&to_id={thor}"), "Antorcha")
daga = q("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE ii.character_id=? AND i.name='Daga'", lyra)[0][0]
antorcha = q("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE ii.character_id=? AND i.name='Antorcha'", thor)[0][0]
amuleto = q("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE i.name='Amuleto de hueso'")[0][0]
# objeto oculto no se puede ofrecer
r = c.post("/trades/new", data={"from_id": lyra, "to_id": thor, f"give_item_{amuleto}": 1}, follow_redirects=True)
print("oculto:", flashes(r.get_data(as_text=True)))
r = c.post("/trades/new", data={"from_id": lyra, "to_id": thor, f"give_item_{daga}": 2, f"give_cur_{cur['pp']}": 5,
                               f"take_item_{antorcha}": 1, f"take_cur_{cur['po']}": 3, "message": "trato"}, follow_redirects=True)
print("propuesta:", flashes(r.get_data(as_text=True)))
tid = q("SELECT id FROM trades ORDER BY id DESC")[0][0]
assert c.post(f"/trades/{tid}/accept").status_code == 403  # ana no puede aceptar su propia propuesta

login(c, "bruno")
ok(c.get("/trades/"), "trato", "Aceptar")
r = c.post(f"/trades/{tid}/accept", follow_redirects=True)
print("aceptar:", flashes(r.get_data(as_text=True)))
assert inv("Lyra", "Daga") == 0 and inv("Thorgar", "Daga") == 2
assert inv("Lyra", "Antorcha") == 1 and inv("Thorgar", "Antorcha") == 2
assert bal("Lyra", "pp") == 20 and bal("Thorgar", "pp") == 5
assert bal("Lyra", "po") == 13 and bal("Thorgar", "po") == 47

# Intercambio imposible -> rollback total
login(c, "ana")
c.post("/trades/new", data={"from_id": lyra, "to_id": thor, f"give_cur_{cur['pp']}": 20, f"take_cur_{cur['ppt']}": 5})
tid2 = q("SELECT id FROM trades ORDER BY id DESC")[0][0]
login(c, "bruno")
r = c.post(f"/trades/{tid2}/accept", follow_redirects=True)
print("aceptar sin fondos:", flashes(r.get_data(as_text=True)))
assert bal("Lyra", "pp") == 20 and bal("Thorgar", "pp") == 5 and bal("Thorgar", "ppt") == 1
assert q("SELECT status FROM trades WHERE id=?", tid2)[0][0] == "pending"
c.post(f"/trades/{tid2}/reject")
assert q("SELECT status FROM trades WHERE id=?", tid2)[0][0] == "rejected"

# Creación de personaje (en una de sus campañas)
login(c, "ana")
r = c.post("/characters/new", data={"name": "Mirela O'Hara", "race": "Tiflin", "speed": "30", "strength": "8",
                                    "campaign_id": 1}, follow_redirects=True)
ok(r, "Mirela O")
r = c.post("/characters/new", data={"name": "", "campaign_id": 1}, follow_redirects=True)
ok(r, "necesita un nombre")
c.post("/play/1")
# Tirar objeto
c.post(f"/characters/{lyra}/inventory/{q('SELECT ii.id FROM inventory_items ii JOIN items i ON i.id=ii.item_id WHERE ii.character_id=? AND i.name=?', lyra, 'Flechas (20)')[0][0]}/remove", data={"quantity": 1})
assert inv("Lyra", "Flechas (20)") == 2

login(c, "dm")
ok(c.get("/dm/"), "con Lyra Vientoalto completado")  # (el número del intercambio depende de la base de datos)
print("TODO OK")
