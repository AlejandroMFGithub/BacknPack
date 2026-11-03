"""Catálogo del SRD 5.1: objetos con efectos, conjuros y migración sin duplicados. TEST_DB opcional."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "srd.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def rows(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return rows(sql, *a)[0][0]
def page(url): return htmllib.unescape(c.get(url).get_data(as_text=True))
def item(name): return one("SELECT id FROM items WHERE name = ?", name)
def stat(b, label):
    m = re.search(r'<span class="combat-label">' + label + r'</span>\s*<b[^>]*>([^<]+)</b>', b)
    return m.group(1).strip()
def score(b, short):
    return int(re.search(r'<div class="label">' + short + r'</div>\s*<div class="score calc-value">(\d+)</div>', b).group(1))

# --- 1. Todo está, sin duplicados ----------------------------------------------------------------
n_items, n_spells = one("SELECT COUNT(*) FROM items"), one("SELECT COUNT(*) FROM spells")
print("objetos:", n_items, "| conjuros:", n_spells)
assert n_items >= 611 and n_spells >= 319
assert not rows("SELECT search_name FROM items GROUP BY search_name HAVING COUNT(*) > 1")
assert not rows("SELECT search_name FROM spells GROUP BY search_name HAVING COUNT(*) > 1")
for name in ("Espada larga", "Armadura de placas", "Bolsa de contención", "Anillo de protección", "Cota de malla +3",
             "Cinturón de fuerza de gigante de las tormentas", "Poción de curación suprema", "Pergamino de conjuro (nivel 9)",
             "Vara inamovible", "Bastón del mago", "Caballo de guerra", "Herramientas de ladrón"):
    assert rows("SELECT 1 FROM items WHERE name = ?", name), name
for name in ("Bola de fuego", "Deseo", "Palabra de poder: matar", "Revivificar", "Salpicadura ácida", "Golpe atronador"):
    assert rows("SELECT 1 FROM spells WHERE name = ?", name), name
assert one("SELECT classes FROM spells WHERE name = 'Curar heridas'") == " artificer bard cleric druid paladin ranger "

# --- 2. El catálogo: precio, categorías nuevas, resumen y créditos ------------------------------------
c.post("/login", data={"username": "dm", "password": "dm"})
b = page("/dm/items?q=espada+larga")
assert '<td data-label="Precio">15 po</td>' in b and "1d8 cortante · versátil (1d10)" in b
assert "System Reference Document 5.1" in b and "CC-BY-4.0" in b
b = page("/dm/items?category=Anillo&q=proteccion")
assert "Anillo de protección" in b and "⚙ CA +1 · Todas las salvaciones +1" in b
b = page("/dm/items?q=cinturon+tormentas")
assert "Tu FUE es 29 mientras lo llevas." in b and "⚙ FUE mín. 29" in b
assert "Varita de bolas de fuego" in page("/dm/items?category=Varita")
# Precio editable (en po)
c.post(f"/dm/items/{item('Bolsa de contención')}/edit", data={"name": "Bolsa de contención", "category": "Objeto maravilloso",
       "rarity": "Poco común", "weight": "7.5", "cost": "500", "description": "Bolsa de contención"})
assert one("SELECT cost_cp FROM items WHERE name = 'Bolsa de contención'") == 50000
assert 'value="500"' in page(f"/dm/items/{item('Bolsa de contención')}/edit")
r = c.post("/dm/items", data={"name": "Precio raro", "cost": "mucho"}, follow_redirects=True)
assert "El precio debe ser un número (en piezas de oro)." in htmllib.unescape(r.get_data(as_text=True))

# --- 3. Los objetos aplican sus efectos al equiparlos ----------------------------------------------------
def give_and_equip(cid, name):
    c.post(f"/characters/{cid}/inventory/add", data={"item_id": item(name), "quantity": 1, "visible": "1"})
    inv = one("SELECT id FROM inventory_items WHERE character_id = ? AND item_id = ?", cid, item(name))
    c.post(f"/characters/{cid}/inventory/{inv}/equip")
    return inv

THORGAR, SIGRID = 2, 3
assert score(page("/characters/2"), "FUE") == 17
belt = give_and_equip(THORGAR, "Cinturón de fuerza de gigante de fuego")
b = page("/characters/2")
assert score(b, "FUE") == 25 and "máx. 187.5 kg" in b
# Cambiar la cota de malla normal por una +1: CA 16 + escudo 2 → 17 + 2
mail = one("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = 2 AND i.name = 'Cota de malla'")
c.post(f"/characters/2/inventory/{mail}/equip")
give_and_equip(THORGAR, "Cota de malla +1")
assert stat(page("/characters/2"), "Clase de armadura") == "19"
# Túnica del archimago en la druida: CA 15 + DES y +2 a la CD de conjuros
before = page("/characters/3/spells")
dc_before = int(stat(before, "CD de salvación"))
give_and_equip(SIGRID, "Túnica del archimago")
b = page("/characters/3")
dex = (one("SELECT dexterity FROM characters WHERE id = 3") - 10) // 2
assert stat(b, "Clase de armadura") == str(15 + dex)
assert int(stat(page("/characters/3/spells"), "CD de salvación")) == dc_before + 2
# Una varita equipada concede su conjuro (y un bastón, muchos)
give_and_equip(SIGRID, "Varita de bolas de fuego")
b = page("/characters/3/spells")
assert re.search(r'id="objetos".*Bola de fuego', b, re.S)
give_and_equip(SIGRID, "Bastón del mago")
b = page("/characters/3/spells")
print("conjuros de objetos de Sigrid:", b[b.index('id="objetos"'):].count('class="spell-row'))
assert b[b.index('id="objetos"'):].count('class="spell-row') >= 20

# --- 4. Conjuros del SRD en el buscador, por lista de clase ----------------------------------------------
labels = [r["label"] for r in c.get("/api/spells?cls=wizard&level=9").get_json()["results"]]
print("mago nivel 9:", labels)
assert {"Deseo", "Detener el tiempo", "Palabra de poder: matar"} <= set(labels)
assert c.get("/api/spells?q=bola").get_json()["results"][0]["label"] == "Bola de fuego"
print("SRD OK")
