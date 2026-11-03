"""Clases, subclases y conjuros. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db
from app.models import class_data as cd

# --- 1. Tablas oficiales (funciones puras) ---------------------------------------------------------
assert cd.spell_slots("full", 1) == {1: 2} and cd.spell_slots("full", 5) == {1: 4, 2: 3, 3: 2}
assert cd.spell_slots("full", 20) == {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1}
assert cd.spell_slots("half", 1) == {} and cd.spell_slots("half", 2) == {1: 2} and cd.spell_slots("half", 3) == {1: 3}
assert cd.spell_slots("half", 5) == {1: 4, 2: 2} and cd.spell_slots("half", 20) == {1: 4, 2: 3, 3: 3, 4: 3, 5: 2}
assert cd.spell_slots("half_up", 1) == {1: 2}                        # artífice
assert cd.spell_slots("third", 2) == {} and cd.spell_slots("third", 3) == {1: 2} and cd.spell_slots("third", 7) == {1: 4, 2: 2}
assert cd.spell_slots("third", 19) == {1: 4, 2: 3, 3: 3, 4: 1}
assert cd.pact_slots(1) == (1, 1) and cd.pact_slots(5) == (2, 3) and cd.pact_slots(11) == (3, 5) and cd.pact_slots(17) == (4, 5)
assert cd.spell_slots("none", 10) == {}
assert cd.cantrips_known("wizard", 1) == 3 and cd.cantrips_known("wizard", 10) == 5 and cd.cantrips_known(None, 5) is None
assert cd.spells_known("bard", 1) == 4 and cd.spells_known("ranger", 3) == 3 and cd.spells_known("eldritch_knight", 3) == 3
assert cd.prepared_max("prepared", 3, 2) == 5 and cd.prepared_max("prepared_half", 1, 3) == 2 and cd.prepared_max("known", 3, 3) is None
assert cd.default_hp(10, 1, 2) == 12 and cd.default_hp(10, 3, 2) == 12 + 2 * 8 and cd.default_hp(6, 1, -3) == 3

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "mg.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def row(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()
def one(sql, *a): return row(sql, *a)[0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', htmllib.unescape(r.get_data(as_text=True)))
def page(url): return htmllib.unescape(c.get(url).get_data(as_text=True))
def box(b, label):
    m = re.search(r'<span class="combat-label">' + label + r'</span>\s*<b[^>]*>(.*?)</b>', b, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).split() if m else None
def pips(b, label):
    m = re.search(r'<span class="slot-label">' + re.escape(label) + r'.*?</span>\s*<span class="slot-pips">(.*?)</span>', b, re.S)
    return (m.group(1).count('class="pip "'), m.group(1).count('class="pip spent"')) if m else None
def class_id(code): return one("SELECT id FROM classes WHERE code = ?", code)
def sub_id(name): return one("SELECT id FROM subclasses WHERE name = ?", name)
def spell_id(name): return one("SELECT id FROM spells WHERE name = ?", name)
def entry(cid, name): return one("SELECT cs.id FROM character_spells cs JOIN spells s ON s.id = cs.spell_id WHERE cs.character_id = ? AND s.name = ?", cid, name)

LYRA, THORGAR, SIGRID = 1, 2, 3
assert one("SELECT COUNT(*) FROM classes WHERE official = 1") == 13 and one("SELECT COUNT(*) FROM spells") >= 70

# --- 2. Datos de ejemplo: la clase llega con sus valores -------------------------------------------
lyra = row("SELECT * FROM characters WHERE id = 1")
assert (lyra["class_name"], lyra["subclass_name"], lyra["hit_die"], lyra["caster"], lyra["spell_ability"], lyra["spell_prep"]) \
    == ("Explorador", "Cazador", 10, "half", "wisdom", "known")
login("ana")
b = page("/characters/1")
assert "Explorador (Cazador) nivel 3" in b and "DG 3d10" in b and "✨ Conjuros" in b
b = page("/characters/1/spells")
print("Lyra:", box(b, "CD de salvación"), box(b, "Ataque de conjuro"), box(b, "Conocidos"), pips(b, "Nivel 1"))
assert box(b, "CD de salvación") == ["12"] and box(b, "Ataque de conjuro") == ["+4"]   # SAB 15: 8 + 2 + 2
assert box(b, "Conocidos") == ["3", "/", "3"]                                          # explorador 3: 3 conocidos
assert pips(b, "Nivel 1") == (2, 1)                                                    # 3 espacios, 1 gastado
assert "Marca del cazador" in b and 'id="objetos"' in b and "Varita de proyectiles mágicos" in b  # la varita equipada

# Lanzar: gasta espacios hasta que no queden; los descansos los recuperan
cure = entry(LYRA, "Curar heridas")
r = c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "1"}, follow_redirects=True)
assert ("ok", "Lanza «Curar heridas» (gasta un espacio de nivel 1).") in flashes(r), flashes(r)
c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "1"})
r = c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "1"}, follow_redirects=True)
assert ("error", "No le quedan espacios de nivel 1.") in flashes(r)
b = page("/characters/1/spells")
assert pips(b, "Nivel 1") == (0, 3) and "Lanza «Curar heridas» con un espacio de nivel 1" in page("/characters/1")
c.post("/characters/1/rest", data={"kind": "long"})
assert pips(page("/characters/1/spells"), "Nivel 1") == (3, 0)
c.post("/characters/1/slots/1/use"); c.post("/characters/1/slots/1/use"); c.post("/characters/1/slots/1/restore")
assert pips(page("/characters/1/spells"), "Nivel 1") == (2, 1)
r = c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "2"}, follow_redirects=True)
assert ("error", "«Curar heridas» necesita un espacio de nivel 1 o superior.") in flashes(r)  # no tiene de nivel 2

# Ajustar espacios a mano (homebrew, dotes…)
c.post("/characters/1/slots", data={"max_1": "", "max_2": "2"})
b = page("/characters/1/spells")
assert pips(b, "Nivel 2") == (2, 0)
r = c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "2"}, follow_redirects=True)  # subir de nivel
assert ("ok", "Lanza «Curar heridas» (gasta un espacio de nivel 2).") in flashes(r)
c.post("/characters/1/slots", data={"max_2": ""})
assert pips(page("/characters/1/spells"), "Nivel 2") is None

# Añadir y quitar de la lista (el jugador también)
r = c.post("/characters/1/spells/add", data={"spell_id": spell_id("Paso sin rastro"), "source": "class"}, follow_redirects=True)
assert ("ok", "«Paso sin rastro» añadido a su lista.") in flashes(r)
r = c.post("/characters/1/spells/add", data={"spell_id": spell_id("Paso sin rastro")}, follow_redirects=True)
assert ("error", "Ya tiene «Paso sin rastro» en su lista.") in flashes(r)
b = page("/characters/1/spells")
assert box(b, "Conocidos") == ["4", "/", "3"] and "más conjuros conocidos de los que le corresponden" in b
c.post(f"/characters/1/spells/{entry(LYRA, 'Paso sin rastro')}/remove")
assert box(page("/characters/1/spells"), "Conocidos") == ["3", "/", "3"]
# Trucos y rituales no gastan
c.post("/characters/1/spells/add", data={"spell_id": spell_id("Guía"), "source": "race"})
c.post("/characters/1/spells/add", data={"spell_id": spell_id("Hablar con los animales")})
r = c.post(f"/characters/1/spells/{entry(LYRA, 'Guía')}/cast", follow_redirects=True)
assert ("ok", "Lanza «Guía».") in flashes(r)
c.post(f"/characters/1/spells/{entry(LYRA, 'Hablar con los animales')}/cast", data={"ritual": "1"})
assert pips(page("/characters/1/spells"), "Nivel 1") == (2, 1)
assert "Lanza «Hablar con los animales» como ritual" in page("/characters/1")

# Un efecto sobre la CD de conjuros (p. ej. una vara +1)
c.post("/characters/1/conditions/add", data={"name": "Foco arcano", "kind": "buff",
       "eff_t": ["spell_dc", "spell_attack"], "eff_op": ["add", "add"], "eff_v": ["1", "1"], "eff_cap": ["none", "none"]})
b = page("/characters/1/spells")
assert box(b, "CD de salvación") == ["13"] and box(b, "Ataque de conjuro") == ["+5"]
assert re.search(r'combat-box calc mod-up"[^>]*>\s*<span class="combat-label">CD de salvación', b)

# Desequipar la varita: su conjuro desaparece
wand = one("SELECT ii.id FROM inventory_items ii JOIN items i ON i.id = ii.item_id WHERE ii.character_id = 1 AND i.name = 'Varita de proyectiles mágicos'")
c.post(f"/characters/1/inventory/{wand}/equip")
assert 'id="objetos"' not in page("/characters/1/spells")

# --- 3. Druida que prepara conjuros -------------------------------------------------------------------
login("dm")
b = page("/characters/3/spells")
print("Sigrid:", box(b, "Preparados"), pips(b, "Nivel 1"))
assert box(b, "Preparados") == ["4", "/", "5"] and "trucos 2 / 2" in b                  # SAB 16 (+3) + nivel 2
wave = entry(SIGRID, "Onda atronadora")
assert re.search(r'class="spell-row is-unprepared".{0,400}Onda atronadora', b, re.S)
r = c.post(f"/characters/3/spells/{wave}/cast", data={"slot": "1"}, follow_redirects=True)  # sin preparar no se lanza
assert ("error", "«Onda atronadora» no está preparado: prepáralo antes de lanzarlo.") in flashes(r)
assert pips(page("/characters/3/spells"), "Nivel 1") == (3, 0)
c.post(f"/characters/3/spells/{wave}/prepare")
assert box(page("/characters/3/spells"), "Preparados")[0] == "5"
c.post(f"/characters/3/spells/{entry(SIGRID, 'Enmarañar')}/always")                    # siempre preparado: no cuenta
assert box(page("/characters/3/spells"), "Preparados")[0] == "4"

# --- 4. Thorgar (guerrero) no tiene magia: sin pestaña para el jugador ---------------------------------
login("bruno")
assert "sheet-tabs" not in page("/characters/2")
assert c.get("/characters/1/spells").status_code == 403                                  # no es suyo
assert c.post(f"/characters/1/spells/{cure}/cast", data={"slot": "1"}).status_code == 403
assert c.get("/library/spells").status_code == 403 and c.get("/library/classes").status_code == 403
assert c.get("/api/spells?q=bola").get_json()["results"][0]["label"] == "Bola de fuego"   # el buscador sí

# Al hacerse caballero arcano: un tercio de lanzador con INT, lista de mago
r = c.post("/characters/2/edit", data={"name": "Thorgar Puñohierro", "level": 3, "class_id": class_id("fighter"),
           "subclass_id": sub_id("Caballero Arcano"), "intelligence": 12, "strength": 17}, follow_redirects=True)
th = row("SELECT * FROM characters WHERE id = 2")
print("Caballero arcano:", th["caster"], th["spell_ability"], th["spell_prep"], th["hit_die"])
assert (th["caster"], th["spell_ability"], th["spell_prep"], th["hit_die"]) == ("third", "intelligence", "known", 10)
assert {r_[0] for r_ in [tuple(x) for x in [row("SELECT name FROM character_proficiencies WHERE character_id = 2 AND kind = 'save' AND name = 'strength'")]]} == {"strength"}
b = page("/characters/2/spells")
assert pips(b, "Nivel 1") == (2, 0) and box(b, "Conocidos") == ["0", "/", "3"] and "trucos 0 / 2" in b
assert '"value": "wizard"' in b or "&#34;value&#34;: &#34;wizard&#34;" in c.get("/characters/2/spells").get_data(as_text=True)
r = c.post("/characters/2/edit", data={"name": "Thorgar", "class_id": class_id("fighter"), "subclass_id": sub_id("Cazador")},
           follow_redirects=True)
assert ("error", "Esa subclase no es de la clase elegida.") in flashes(r)

# --- 5. Crear personajes: valores por defecto, editables, y clase personalizada --------------------------
login("ana")
r = c.post("/characters/new", data={"name": "Mira", "level": 1, "campaign_id": 1, "class_id": class_id("wizard"),
           "intelligence": 16}, follow_redirects=True)
mira = row("SELECT * FROM characters WHERE name = 'Mira'")
saves = {x["name"] for x in [row("SELECT name FROM character_proficiencies WHERE character_id = ? AND name = ?", mira["id"], k) for k in ("intelligence", "wisdom")] if x}
assert (mira["hit_die"], mira["caster"], mira["spell_ability"], mira["spell_prep"]) == (6, "full", "intelligence", "prepared")
assert saves == {"intelligence", "wisdom"}                                                # salvaciones de mago
b = page(f"/characters/{mira['id']}/spells")
assert pips(b, "Nivel 1") == (2, 0) and box(b, "CD de salvación") == ["13"]               # 8 + 2 + 3
# Con el formulario completo, lo que manda es lo escrito a mano
r = c.post(f"/characters/{mira['id']}/edit", data={"name": "Mira", "level": 1, "class_id": class_id("wizard"), "profs_form": "1",
           "save_dexterity": "1", "hit_die": "8", "caster": "full", "spell_ability": "charisma", "spell_prep": "known"})
mira = row("SELECT * FROM characters WHERE name = 'Mira'")
assert (mira["hit_die"], mira["spell_ability"], mira["spell_prep"]) == (8, "charisma", "known")
assert one("SELECT COUNT(*) FROM character_proficiencies WHERE character_id = ? AND kind = 'save'", mira["id"]) == 1
# Personalizada
c.post("/characters/new", data={"name": "Vex", "level": 5, "campaign_id": 1, "class_id": "custom", "class_name": "Cazador de brujas",
       "subclass_id": "custom", "subclass_name": "Orden del Ocaso", "hit_die": "10", "caster": "pact", "spell_ability": "charisma",
       "spell_prep": "known", "profs_form": "1"})
vex = row("SELECT * FROM characters WHERE name = 'Vex'")
assert (vex["class_id"], vex["class_name"], vex["subclass_name"], vex["caster"]) == (None, "Cazador de brujas", "Orden del Ocaso", "pact")
b = page(f"/characters/{vex['id']}/spells")
assert pips(b, "Pacto (nivel 3)") == (2, 0) and "Descanso corto" in b
assert box(b, "Conocidos") == ["0"] and "trucos 0</small>" in b                            # homebrew: sin tablas de conocidos
c.post(f"/characters/{vex['id']}/slots/pact/use")
c.post(f"/characters/{vex['id']}/rest", data={"kind": "short"})
assert pips(page(f"/characters/{vex['id']}/spells"), "Pacto (nivel 3)") == (2, 0)
b = page(f"/characters/{vex['id']}/edit")
assert '<option value="custom" selected>' in b and 'value="Cazador de brujas"' in b

# --- 6. Homebrew del DM ----------------------------------------------------------------------------------
login("dm")
r = c.post("/library/classes", data={"name": "Cazador de sangre", "hit_die": "10", "caster": "half", "spell_ability": "intelligence",
           "spell_prep": "known", "save_strength": "1", "save_intelligence": "1", "subclass_level": "3"}, follow_redirects=True)
hb = row("SELECT * FROM classes WHERE name = 'Cazador de sangre'")
assert (hb["official"], hb["saves"], hb["caster"]) == (0, "strength,intelligence", "half")
c.post(f"/library/classes/{hb['id']}/subclasses", data={"name": "Orden del Licántropo"})
r = c.post("/library/classes", data={"name": "Mal", "caster": "full"}, follow_redirects=True)
assert ("error", "Una clase con conjuros necesita su característica mágica.") in flashes(r)
r = c.post(f"/library/classes/{class_id('wizard')}/delete", follow_redirects=True)
assert ("error", "Las clases oficiales no se pueden borrar.") in flashes(r)
assert "Cazador de sangre" in page("/characters/new") and "Orden del Licántropo" in page("/characters/new")
r = c.post("/library/spells", data={"name": "Rayo de sangre", "level": "2", "school": "Nigromancia", "classes": ["wizard", "warlock"],
           "concentration": "1", "description": "Homebrew de prueba"}, follow_redirects=True)
sp = row("SELECT * FROM spells WHERE name = 'Rayo de sangre'")
assert (sp["official"], sp["level"], sp["classes"], sp["concentration"]) == (0, 2, " wizard warlock ", 1)
assert "Rayo de sangre" in [x["label"] for x in c.get("/api/spells?cls=warlock&level=2").get_json()["results"]]
# Un objeto que concede un conjuro
ring = one("SELECT id FROM items WHERE name = 'Anillo de protección'")
c.post(f"/library/items/{ring}/spells", data={"spell_id": sp["id"]})
assert "Rayo de sangre" in page(f"/dm/items/{ring}/edit")
c.post(f"/characters/2/inventory/add", data={"item_id": ring, "quantity": 1, "visible": "1"})
inv = one("SELECT id FROM inventory_items WHERE character_id = 2 AND item_id = ?", ring)
c.post(f"/characters/2/inventory/{inv}/equip")
assert "Rayo de sangre" in page("/characters/2/spells")

# --- 7. Migración: clases de personajes antiguos por su nombre -------------------------------------------
from app.migrations import class_matching
with app.app_context():
    classes = get_db().execute("SELECT * FROM classes").fetchall()
    found = {t: (class_matching(t, classes) or {"name": None})["name"] for t in
             ("Exploradora", "monja", "Pícara", "PALADINA", "Mago", "Artífice", "Pirata")}
print("migración:", found)
assert found == {"Exploradora": "Explorador", "monja": "Monje", "Pícara": "Pícaro", "PALADINA": "Paladín",
                 "Mago": "Mago", "Artífice": "Artífice", "Pirata": None}
print("CLASES Y CONJUROS OK")
