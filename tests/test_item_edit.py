"""Editar objetos desde donde aparecen (este ejemplar o todos) y el menú de armas. TEST_DB opcional."""
import html as htmllib, json, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "ie.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def rows(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return rows(sql, *a)[0][0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', htmllib.unescape(r.get_data(as_text=True)))
def page(url): return htmllib.unescape(c.get(url).get_data(as_text=True))
def item_of(table, ref): return rows(f"SELECT i.* FROM {table} t JOIN items i ON i.id = t.item_id WHERE t.id = ?", ref)[0]
def form_for(item, **changes):
    """Los datos del formulario tal como los enviaría la página (con el bloque de arma)."""
    data = {"name": item["name"], "category": item["category"], "rarity": item["rarity"], "weight": item["weight"],
            "properties": item["properties"] or "", "description": item["description"] or "", "w_form": "1",
            "cost": "" if item["cost_cp"] is None else item["cost_cp"] / 100}
    weapon = json.loads(item["weapon"]) if item["weapon"] else None
    if weapon:
        data.update({"w_enabled": "1", "w_dice": weapon["dice"] or "", "w_type": weapon["type"], "w_cat": weapon["cat"] or "",
                     "w_props": weapon["props"], "w_two": weapon["two"] or "", "w_bonus": weapon["bonus"],
                     "w_base": weapon["base"] or "", "w_mastery": weapon.get("mastery") or "",
                     "w_range_normal": weapon["range"][0] if weapon["range"] else "",
                     "w_range_long": weapon["range"][1] if weapon["range"] else ""})
        if weapon["ranged"]:
            data["w_ranged"] = "1"
    data.update(changes)
    return data

THORGAR = 2
axe_row = one("""SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id
                 WHERE ii.character_id = 2 AND i.name = 'Hacha de batalla'""")
axe = item_of("inventory_items", axe_row)
n_items = one("SELECT COUNT(*) FROM items")

# --- 0. Los datos de arma del SRD traen maestría ---------------------------------------------------
assert json.loads(axe["weapon"])["mastery"] == "topple"
flame = json.loads(one("SELECT weapon FROM items WHERE name = 'Lengua de fuego'"))
assert flame["extra"] == [{"dice": "2d6", "type": "fuego", "note": "con la hoja encendida"}]

# --- 1. Solo el DM ---------------------------------------------------------------------------------
login("bruno")
assert c.get(f"/dm/edit-item/inventory/{axe_row}").status_code == 403
assert "✎ Editar objeto" not in page("/characters/2")
login("dm")
b = page("/characters/2")
assert f"/dm/edit-item/inventory/{axe_row}" in b
b = page(f"/dm/edit-item/inventory/{axe_row}")
assert "desde el inventario de Thorgar Puñohierro" in b and 'name="scope" value="all"' in b
assert "Cualidades de plantilla" not in b                       # en un objeto del catálogo no se tocan desde aquí

# --- 2. Solo este ejemplar: se crea una versión única y solo esa fila la usa ----------------------------
r = c.post(f"/dm/edit-item/inventory/{axe_row}", data=form_for(axe, name="Hacha de Thorgar", w_bonus="1", scope="copy"),
           follow_redirects=True)
print("ejemplar:", flashes(r))
mine = item_of("inventory_items", axe_row)
assert (mine["name"], mine["unique_copy"], mine["parent_id"]) == ("Hacha de Thorgar", 1, axe["id"])
assert one("SELECT name FROM items WHERE id = ?", axe["id"]) == "Hacha de batalla"   # el catálogo no cambia
assert one("SELECT COUNT(*) FROM items") == n_items + 1
assert sorted(r_[0] for r_ in rows("SELECT name FROM item_traits WHERE inventory_item_id = ?", axe_row)) == \
    ["Runa de Moradin", "Sed de sangre"]                            # sus cualidades de ejemplar siguen ahí
assert "maestría: Derribar" in mine["properties"] and "+1 al ataque y al daño" in mine["properties"]
b = page("/characters/2")
assert "Hacha de Thorgar" in b and "✦ Único" in b
a = re.search(r"<td><b>Hacha de Thorgar</b>.*?</tr>", b, re.S).group(0)
assert '<b class="calc-value">+6</b>' in a                         # +3 FUE +2 comp. +1 mágica
assert "✦ Derribar" in a and "<b>13</b>" in a                      # maestría y su CD: 8 + 3 + 2
# Otra vez «solo este ejemplar»: ya es único y solo lo usa él → se edita tal cual
c.post(f"/dm/edit-item/inventory/{axe_row}", data=form_for(mine, description="Forjada en Karak", scope="copy"))
assert one("SELECT COUNT(*) FROM items") == n_items + 1 and item_of("inventory_items", axe_row)["description"] == "Forjada en Karak"
# Un ejemplar único no cambia el catálogo
r = c.post(f"/dm/edit-item/inventory/{axe_row}", data=form_for(mine, scope="all"), follow_redirects=True)
assert ("error", "Este ejemplar ya es una versión única: sus cambios no afectan al catálogo.") in flashes(r)
b = page(f"/dm/edit-item/inventory/{axe_row}")
assert 'name="scope" value="all"' not in b and "Basado en «" in b and "Volver a la versión del catálogo" in b

# Catálogo: las versiones únicas van aparte y no salen en el buscador
assert "Hacha de Thorgar" not in page("/dm/items?q=hacha")
b = page("/dm/items?kind=unique")
assert "Hacha de Thorgar" in b and "Basado en «Hacha de batalla» · en 1 sitio(s)" in b
assert "Hacha de Thorgar" not in [x["label"] for x in c.get("/api/items?q=hacha").get_json()["results"]]

# --- 3. Una unidad de una pila (Thorgar tiene 3 antorchas) -------------------------------------------
torch_row = one("""SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id
                   WHERE ii.character_id = 2 AND i.name = 'Antorcha'""")
torch = item_of("inventory_items", torch_row)
b = page(f"/dm/edit-item/inventory/{torch_row}")
assert "Hay ×3 en esta pila" in b
c.post(f"/dm/edit-item/inventory/{torch_row}", data=form_for(torch, name="Antorcha eterna", scope="copy", units="one"))
names = {r_["name"]: r_["quantity"] for r_ in rows(
    "SELECT i.name, ii.quantity FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = 2")}
print("antorchas:", {k: v for k, v in names.items() if "Antorcha" in k})
assert names["Antorcha"] == 2 and names["Antorcha eterna"] == 1

# --- 4. Desde una tienda: todos (catálogo) o solo esa oferta -------------------------------------------
listing = {r_["name"]: r_["id"] for r_ in rows("SELECT i.name, si.id FROM shop_items si JOIN items i ON i.id = si.item_id WHERE si.shop_id = 1")}
sword = item_of("shop_items", listing["Espada larga"])
c.post(f"/dm/edit-item/shop/{listing['Espada larga']}", data=form_for(sword, description="Acero de Aguasprofundas", scope="all"))
assert one("SELECT description FROM items WHERE id = ?", sword["id"]) == "Acero de Aguasprofundas"   # catálogo
assert item_of("shop_items", listing["Espada larga"])["id"] == sword["id"]                           # sin copia
mail = item_of("shop_items", listing["Cota de malla"])
c.post(f"/dm/edit-item/shop/{listing['Cota de malla']}", data=form_for(mail, name="Cota de malla bendita", scope="copy",
       eff_t=["armor_class", "saves"], eff_op=["armor", "add"], eff_v=["17", "1"], eff_cap=["0", "none"]))
blessed = item_of("shop_items", listing["Cota de malla"])
assert blessed["unique_copy"] == 1 and one("SELECT name FROM items WHERE id = ?", mail["id"]) == "Cota de malla"
assert "Cota de malla bendita" in page("/shops/1") and "✦ Único" in page("/shops/1")
# Al comprarla, el comprador se lleva esa versión
gp = one("SELECT id FROM currencies WHERE code = 'po'")
c.post("/characters/2/currencies", data={f"cur_{gp}": 500})
c.post(f"/shops/1/buy/{listing['Cota de malla']}", data={"character_id": THORGAR, "quantity": 1, "currency_id": gp})
bought = rows("""SELECT i.name, i.unique_copy FROM inventory_items ii JOIN items i ON i.id = ii.item_id
                 WHERE ii.character_id = 2 AND i.name LIKE ?""", "Cota de malla%")
assert ("Cota de malla bendita", 1) in [tuple(r_) for r_ in bought], [tuple(r_) for r_ in bought]

# --- 5. Desde un botín ---------------------------------------------------------------------------------
entry = one("SELECT id FROM loot_entries WHERE item_id IS NOT NULL ORDER BY id LIMIT 1")
loot_item = item_of("loot_entries", entry)
assert f"/dm/edit-item/loot/{entry}" in page("/loot/1")
c.post(f"/dm/edit-item/loot/{entry}", data=form_for(loot_item, name=loot_item["name"] + " oxidada", scope="copy"))
assert item_of("loot_entries", entry)["unique_copy"] == 1

# --- 6. Volver a la versión del catálogo ----------------------------------------------------------------
fork_id = item_of("inventory_items", axe_row)["id"]
r = c.post(f"/dm/edit-item/inventory/{axe_row}/revert", follow_redirects=True)
assert ("ok", "Vuelve a ser «Hacha de batalla» del catálogo.") in flashes(r)
assert item_of("inventory_items", axe_row)["id"] == axe["id"] and not rows("SELECT 1 FROM items WHERE id = ?", fork_id)

# --- 7. El menú de armas: maestría, daño adicional y propiedades generadas -----------------------------------
r = c.post("/dm/items", data={"name": "Espada flamígera", "category": "Arma", "rarity": "Raro", "w_form": "1", "w_enabled": "1",
           "w_dice": "1d8", "w_type": "cortante", "w_cat": "martial", "w_props": ["versatile"], "w_two": "1d10",
           "w_bonus": "1", "w_mastery": "sap", "properties": "esto se sustituye",
           "w_extra_dice": ["2d6", "", "1d4"], "w_extra_type": ["fuego", "", "frío"], "w_extra_note": ["encendida", "", ""]},
           follow_redirects=True)
fl = rows("SELECT * FROM items WHERE name = 'Espada flamígera'")[0]
w = json.loads(fl["weapon"])
print("flamígera:", fl["properties"])
assert w["mastery"] == "sap" and w["extra"] == [{"dice": "2d6", "type": "fuego", "note": "encendida"},
                                                {"dice": "1d4", "type": "frío", "note": ""}]
assert fl["properties"] == "1d8 cortante · versátil (1d10) · +1 al ataque y al daño · maestría: Debilitar · +2d6 fuego (encendida) · +1d4 frío"
b = page(f"/dm/items/{fl['id']}/edit")
assert '<option value="sap" data-desc=' in b and 'selected>Debilitar</option>' in b and b.count('class="wx-row"') == 3  # 2 + plantilla
r = c.post("/dm/items", data={"name": "Mala", "w_form": "1", "w_enabled": "1", "w_dice": "1d8",
           "w_extra_dice": ["mucho"], "w_extra_type": [""], "w_extra_note": [""]}, follow_redirects=True)
assert ("error", "«mucho» no es un dado válido (p. ej. 1d8 o 2d6).") in flashes(r)
c.post("/characters/2/inventory/add", data={"item_id": fl["id"], "quantity": 1, "visible": "1"})
inv = one("SELECT id FROM inventory_items WHERE character_id = 2 AND item_id = ?", fl["id"])
c.post(f"/characters/2/inventory/{inv}/equip")
a = re.search(r"<td><b>Espada flamígera</b>.*?</tr>", page("/characters/2"), re.S).group(0)
assert "✦ Debilitar" in a and "+2d6 fuego" in a and "(encendida)" in a and "+1d4 frío" in a
print("EDICIÓN DE OBJETOS OK")
