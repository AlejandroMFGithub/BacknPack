"""Distancias en pies y casillas: migración de datos reales y textos nuevos. TEST_DB opcional."""
import os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

# --- 1. Migración sobre una copia de la base de datos real (solo SQLite)
if not os.environ.get("TEST_DB"):
    copy = os.path.join(tempfile.mkdtemp(), "real.sqlite")
    shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "backnpack.sqlite"), copy)
    app = create_app({"DATABASE": copy, "TESTING": True, "CSRF_ENABLED": False})
    with app.app_context():
        db = get_db()
        speeds = dict(db.execute("SELECT name, speed FROM characters").fetchall())
        print("velocidades:", speeds)
        assert speeds["Lyra Vientoalto"] == 35 and speeds["Thorgar Puñohierro"] == 25
        assert speeds["Mahara Oshi"] == 50, "50 ya parecía pies: no se toca"
        texts = [r[0] for r in db.execute("SELECT properties FROM items WHERE properties LIKE '%ft%'").fetchall()]
        names = [r[0] for r in db.execute("SELECT name FROM items WHERE name LIKE 'Cuerda%'").fetchall()]
        print("textos:", texts, names)
        assert any("(20/60 ft / 4/12 casillas)" in t for t in texts)
        assert any("Luz brillante 20 ft / 4 casillas, tenue 20 ft / 4 casillas más" in t for t in texts)
        assert "Cuerda de cáñamo (50 ft / 10 casillas)" in names, names  # (y las del catálogo del SRD)
        leftovers = db.execute("SELECT name, properties FROM items WHERE properties LIKE '% m)%' OR properties LIKE '% m,%'").fetchall()
        assert not leftovers, leftovers
    create_app({"DATABASE": copy, "TESTING": True})  # arrancar otra vez no vuelve a convertir
    with create_app({"DATABASE": copy, "TESTING": True}).app_context():
        assert get_db().execute("SELECT speed FROM characters WHERE name LIKE 'Lyra%'").fetchone()[0] == 35
    print("migración OK")

# --- 2. Lo que se introduce a partir de ahora
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "n.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def one(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()[0]
c.post("/login", data={"username": "dm", "password": "dm"})
b = c.get("/characters/1").get_data(as_text=True)
# 35 ft de base + 10 (Paso largo) − 5 (maldición oculta) = 40 ft, en ámbar
assert '<span class="combat-label">Velocidad</span><b class="calc-value">40 ft</b><small>8 casillas</small>' in b
assert '<span class="calc-line calc-base"><span>Velocidad base (ft)</span><b>35 ft</b></span>' in b
b = c.get("/characters/1/edit").get_data(as_text=True)
assert 'Velocidad (ft) <input name="speed" type="number" step="5" min="0" value="35">' in b
c.post("/characters/1/edit", data={"name": "Lyra Vientoalto", "speed": "40", "notes": "Salta 3 m de longitud"})
assert one("SELECT speed FROM characters WHERE id = 1") == 40
assert one("SELECT notes FROM characters WHERE id = 1") == "Salta 10 ft / 2 casillas de longitud"
c.post("/dm/items", data={"name": "Jabalina de prueba", "category": "Arma", "properties": "1d6 perforante · arrojadiza (9/36 m)",
                          "description": "Alcance de 30 pies"})
props, desc = one("SELECT properties FROM items WHERE name = 'Jabalina de prueba'"), one("SELECT description FROM items WHERE name = 'Jabalina de prueba'")
print("objeto nuevo:", props, "|", desc)
assert props == "1d6 perforante · arrojadiza (30/120 ft / 6/24 casillas)" and desc == "Alcance de 30 ft / 6 casillas"
c.post("/characters/1/conditions/add", data={"name": "Telaraña", "kind": "condition", "visible": "1",
                                            "description": "Área de 6 m", "duration": "1 hora"})
assert one("SELECT description FROM conditions WHERE name = 'Telaraña'") == "Área de 20 ft / 4 casillas"
inv = one("SELECT id FROM inventory_items WHERE character_id = 1 LIMIT 1")
c.post(f"/characters/1/inventory/{inv}/traits", data={"name": "Aura", "kind": "property", "visible": "1",
                                                     "description": "Radio de 10 ft"})
assert one("SELECT description FROM item_traits WHERE name = 'Aura'") == "Radio de 10 ft / 2 casillas"
c.post("/loot/new", data={"name": "Pozo", "kind": "environment", "description": "Un pozo de 30 metros"})
assert one("SELECT description FROM loot_pools WHERE name = 'Pozo'") == "Un pozo de 100 ft / 20 casillas"
c.post("/characters/new", data={"name": "Por defecto", "campaign_id": 1, "user_id": 1})
assert one("SELECT speed FROM characters WHERE name = 'Por defecto'") == 30
print("DISTANCIAS OK")
