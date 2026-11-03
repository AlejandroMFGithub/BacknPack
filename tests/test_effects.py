"""Estadísticas modificadas por equipo, cualidades y estados. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "e.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return q(sql, *a)[0][0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))
def page(cid): return htmllib.unescape(c.get(f"/characters/{cid}").get_data(as_text=True))

def box(b, label):
    """(clase de color, valor mostrado, líneas del desglose) de una casilla de combate."""
    m = re.search(r'<div class="combat-box calc( mod-\w+)?"[^>]*>\s*<span class="combat-label">' + re.escape(label)
                  + r'</span>(.*?)<span class="calc-pop" role="tooltip">(.*?)</span>\s*</div>', b, re.S)
    assert m, label
    value = re.sub(r"<[^>]+>", " ", m.group(2)).split()
    lines = re.findall(r'<span class="calc-line[^"]*"><span>([^<]*)</span><b>([^<]*)</b>', m.group(3))
    return (m.group(1) or "").strip(), " ".join(value), lines

def ability(b, label):
    m = re.search(r'<div class="ability calc( mod-\w+)?"[^>]*>\s*<div class="label">' + label
                  + r'</div>\s*<div class="score calc-value">(\d+)</div>\s*<div class="mod calc-value">([^<]+)</div>(.*?)</div>', b, re.S)
    assert m, label
    return (m.group(1) or "").strip(), int(m.group(2)), m.group(3), m.group(4)

def check(b, name):
    m = re.search(r'<li class="[^"]*calc( mod-\w+)?"[^>]*>.*?<span class="check-name">' + re.escape(name)
                  + r'(?: <span[^>]*>\w+</span>)?</span><b class="check-total calc-value">([^<]+)</b>', b)
    assert m, name
    return (m.group(1) or "").strip(), m.group(2)

LYRA, THORGAR = 1, 2

# --- 1. Datos de ejemplo: armadura, escudo, maldición oculta y estados ---------------------------
login("bruno")
b = page(THORGAR)
cls, value, lines = box(b, "Clase de armadura")
print("Thorgar CA:", cls, value, lines)
assert value == "18" and cls == "mod-up"                        # 10 sin armadura → 16 cota → +2 escudo
assert lines[1] == ("Armadura: 16 · Cota de malla", "16") and lines[2] == ("+2 · Escudo", "18")
cls, score, mod, pop = ability(b, "SAB")
print("Thorgar SAB:", cls, score, mod)
assert (cls, score, mod) == ("mod-down", 10, "+0")              # 12 − 2 de la maldición oculta
assert "??? (efecto oculto)" in pop and "Sed de sangre" not in b # el jugador no sabe de dónde viene
assert check(b, "Perspicacia") == ("mod-down", "+0")            # hereda el rojo de SAB
assert check(b, "Percepción") == ("mod-down", "+2")             # SAB +0 + competencia +2 (antes +3)
assert box(b, "Percepción pasiva")[:2] == ("mod-down", "12")
assert box(b, "Velocidad")[:2] == ("", "25 ft 5 casillas")    # sin cambios: sin color
assert check(b, "Atletismo") == ("", "+5")

login("dm")
b = page(THORGAR)
assert "Sed de sangre (Hacha de batalla) (oculto)" in ability(b, "SAB")[3]

# Lyra: cuero (11 + DES) = 14; velocidad 35 + 10 (Paso largo) − 5 (maldición oculta) = 40, ámbar
login("ana")
b = page(LYRA)
cls, value, lines = box(b, "Clase de armadura")
print("Lyra CA:", cls, value, lines)
assert (cls, value) == ("mod-up", "14") and lines[1] == ("Armadura: 11 + DES · Armadura de cuero", "14")
cls, value, lines = box(b, "Velocidad")
print("Lyra velocidad:", cls, value, lines)
assert (cls, value) == ("mod-mixed", "40 ft 8 casillas")
assert lines[1:3] == [("−5 · ??? (efecto oculto)", "30 ft"), ("+10 · Paso largo", "40 ft")]
assert "Marca del licántropo" not in b
assert "⚙ CA 11 + DES" in b                                    # efecto visible en el objeto

# Desequipar la armadura: vuelve a la CA de la ficha, sin color
inv = one("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = 1 AND i.name = 'Armadura de cuero'")
c.post(f"/characters/{LYRA}/inventory/{inv}/equip")
assert box(page(LYRA), "Clase de armadura")[:2] == ("", "13")
c.post(f"/characters/{LYRA}/inventory/{inv}/equip")
assert box(page(LYRA), "Clase de armadura")[1] == "14"

# --- 2. El DM crea un objeto con efectos desde el catálogo -----------------------------------
login("dm")
r = c.post("/dm/items", data={"name": "Guanteletes de prueba", "category": "Objeto maravilloso",
                              "rarity": "Poco común", "attunement": "1",
                              "eff_t": ["strength", "", "skill:stealth"], "eff_op": ["floor", "add", "add"],
                              "eff_v": ["19", "", "-1"], "eff_cap": ["none", "none", "none"]}, follow_redirects=True)
eff = one("SELECT effects FROM items WHERE name = 'Guanteletes de prueba'")
print("guardado:", eff, flashes(r))
assert eff == '[{"t":"strength","op":"floor","v":19},{"t":"skill:stealth","op":"add","v":-1}]'  # fila vacía descartada
gid = one("SELECT id FROM items WHERE name = 'Guanteletes de prueba'")
b = htmllib.unescape(c.get(f"/dm/items/{gid}/edit").get_data(as_text=True))
assert b.count('<div class="eff-row">') == 4   # 2 guardados + plantilla del objeto + plantilla de cualidad
assert '<option value="floor" selected>' in b and 'value="19"' in b
assert "⚙ FUE mín. 19 · Sigilo −1" in htmllib.unescape(c.get("/dm/items?q=guanteletes+prueba").get_data(as_text=True))

# Errores de validación
r = c.post("/dm/items", data={"name": "Mal", "eff_t": ["speed"], "eff_op": ["armor"], "eff_v": ["3"], "eff_cap": ["none"]},
           follow_redirects=True)
assert ("error", "La operación «armadura» solo vale para la CA.") in flashes(r), flashes(r)
r = c.post("/dm/items", data={"name": "Mal", "eff_t": ["speed"], "eff_op": ["add"], "eff_v": ["mucho"], "eff_cap": ["none"]},
           follow_redirects=True)
assert ("error", "El valor del efecto sobre Velocidad no es un número.") in flashes(r)
assert one("SELECT COUNT(*) FROM items WHERE name = 'Mal'") == 0

# Dárselo a Lyra: no cuenta hasta que lo equipa
c.post(f"/characters/{LYRA}/inventory/add", data={"item_id": gid, "quantity": 1, "visible": "1"})
b = page(LYRA)
assert ability(b, "FUE")[:2] == ("", 11) and "(al equiparlo)" in b
gl = one("SELECT id FROM inventory_items WHERE character_id = 1 AND item_id = ?", gid)
c.post(f"/characters/{LYRA}/inventory/{gl}/equip")
b = page(LYRA)
cls, score, mod, pop = ability(b, "FUE")
print("Lyra FUE:", cls, score, mod)
assert (cls, score, mod) == ("mod-up", 19, "+4")
assert check(b, "Atletismo") == ("mod-up", "+4") and check(b, "Fuerza") == ("mod-up", "+6")
assert check(b, "Sigilo") == ("mod-down", "+6")                 # +3 DES + 4 pericia − 1
_, value, lines = box(b, "Carga")
assert "máx. 142.5 kg" in value, value                           # 19 × 7,5

# --- 3. Estados: los del reglamento traen su efecto; también se pueden poner a mano -----------
r = c.post(f"/characters/{LYRA}/conditions/add", data={"name": "Agarrado", "kind": "condition", "visible": "1"},
           follow_redirects=True)
assert one("SELECT effects FROM conditions WHERE name = 'Agarrado'") == '[{"t":"speed","op":"set","v":0}]'
b = page(LYRA)
cls, value, lines = box(b, "Velocidad")
print("agarrada:", cls, value, lines[-1])
assert value == "0 ft 0 casillas" and cls == "mod-mixed" and lines[-2] == ("= 0 · Agarrado", "0 ft")
c.post(f"/characters/{LYRA}/conditions/add", data={"name": "Escudo arcano", "kind": "buff", "visible": "1",
       "eff_t": ["armor_class", "saves"], "eff_op": ["add", "add"], "eff_v": ["5", "1"], "eff_cap": ["none", "none"]})
b = page(LYRA)
assert box(b, "Clase de armadura")[1] == "19"
assert check(b, "Constitución") == ("mod-up", "+2")              # +1 CON +1 a todas las salvaciones
assert "⚙ CA +5 · Todas las salvaciones +1" in b

# --- 4. Cualidad con efecto en un ejemplar: viaja con el objeto ------------------------------
dagger = one("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = 1 AND i.name = 'Daga'")
c.post(f"/characters/{LYRA}/inventory/{dagger}/traits", data={"name": "Filo veloz", "kind": "blessing", "visible": "1",
       "eff_t": ["initiative"], "eff_op": ["add"], "eff_v": ["2"], "eff_cap": ["none"]})
assert box(page(LYRA), "Iniciativa")[:2] == ("", "+3")           # la daga no está equipada
dagger_new = one("SELECT inventory_item_id FROM item_traits WHERE name = 'Filo veloz'")
c.post(f"/characters/{LYRA}/inventory/{dagger_new}/equip")
b = page(LYRA)
cls, value, lines = box(b, "Iniciativa")
print("iniciativa:", cls, value, lines)
assert (cls, value) == ("mod-up", "+5") and ("+2 · Filo veloz (Daga)", "+5") in lines

# --- 5. Lista de personajes y panel del DM con la CA real ------------------------------------
b = htmllib.unescape(c.get("/dm/").get_data(as_text=True))
assert '<td data-label="CA"><span class="mod-up-text">18</span></td>' in b
assert '<td data-label="Iniciativa"><span class="mod-up-text">+5</span></td>' in b
login("bruno")
b = htmllib.unescape(c.get("/characters/").get_data(as_text=True))
assert 'CA <b class="mod-up-text">18</b>' in b

print("EFECTOS OK")
