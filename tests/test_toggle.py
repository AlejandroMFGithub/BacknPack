"""Efectos del jugador, activables, editables y fijos. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "tg.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def row(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchone()
def one(sql, *a): return row(sql, *a)[0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', htmllib.unescape(r.get_data(as_text=True)))
def page(cid): return htmllib.unescape(c.get(f"/characters/{cid}").get_data(as_text=True))
def stat(b, label):
    m = re.search(r'<span class="combat-label">' + label + r'</span><b class="calc-value">([^<]+)</b>', b)
    return m.group(1)
def fue(b): return int(re.search(r'<div class="label">FUE</div>\s*<div class="score calc-value">(\d+)</div>', b).group(1))
def cond(name): return one("SELECT id FROM conditions WHERE name = ?", name)
def post(cid, cond_id, action, **data):
    return c.post(f"/characters/{cid}/conditions/{cond_id}/{action}", data=data, follow_redirects=True)

LYRA, THORGAR = 1, 2
RAGE = {"name": "Furia", "kind": "buff", "duration": "1 minuto", "description": "Resistencia al daño contundente",
        "eff_t": ["strength", "saves"], "eff_op": ["add", "add"], "eff_v": ["2", "1"], "eff_cap": ["none", "none"],
        "visible": "", "locked": "1"}                      # el jugador no puede ocultarlo ni fijarlo

# --- 1. Datos de ejemplo: «Postura defensiva» de Thorgar empieza desactivada --------------------
login("bruno")
b = page(THORGAR)
assert stat(b, "Clase de armadura") == "18" and stat(b, "Velocidad") == "25 ft"
assert 'aria-label="Postura defensiva: inactivo"' in b and "Inactivo" in b
r = post(THORGAR, cond("Postura defensiva"), "toggle")
b = page(THORGAR)
print("postura activada: CA", stat(b, "Clase de armadura"), "| velocidad", stat(b, "Velocidad"))
assert stat(b, "Clase de armadura") == "19" and stat(b, "Velocidad") == "15 ft"
assert "Activa «Postura defensiva»" in b                         # queda en el historial
post(THORGAR, cond("Postura defensiva"), "toggle")
assert stat(page(THORGAR), "Clase de armadura") == "18"

# --- 2. El jugador crea su propio efecto ------------------------------------------------------
login("ana")
r = c.post(f"/characters/{LYRA}/conditions/add", data=RAGE, follow_redirects=True)
fury = row("SELECT * FROM conditions WHERE name = 'Furia'")
print("creado por el jugador:", dict(visible=fury["visible"], locked=fury["locked"], active=fury["active"], effects=fury["effects"]))
assert (fury["visible"], fury["locked"], fury["active"]) == (1, 0, 1)
b = page(LYRA)
assert fue(b) == 13                                                # FUE 11 + 2
assert "⚙ FUE +2 · Todas las salvaciones +1" in b

# Desactivar en combate: deja de contar
post(LYRA, fury["id"], "toggle")
assert one("SELECT active FROM conditions WHERE id = ?", fury["id"]) == 0
b = page(LYRA)
assert fue(b) == 11 and "(desactivado)" in b

# Editarlo
r = post(LYRA, fury["id"], "edit", name="Furia salvaje", kind="buff", duration="1 minuto",
         eff_t=["strength"], eff_op=["add"], eff_v=["4"], eff_cap=["none"], locked="1", visible="")
f2 = row("SELECT * FROM conditions WHERE id = ?", fury["id"])
assert f2["name"] == "Furia salvaje" and f2["effects"] == '[{"t":"strength","op":"add","v":4}]'
assert (f2["visible"], f2["locked"], f2["active"]) == (1, 0, 0)     # no cambia visibilidad, fijo ni activo
post(LYRA, fury["id"], "toggle")
assert fue(page(LYRA)) == 15

# --- 3. Lo que el jugador no puede tocar -------------------------------------------------------
blessing = cond("Bendición")                                       # fijo (lo puso el DM)
b = page(LYRA)
assert 'title="Efecto fijo: solo el DM puede cambiarlo"' in b and "🔒 Fijo" in b
for action, data in [("toggle", {}), ("delete", {}), ("edit", {"name": "Nada", "kind": "buff"})]:
    r = post(LYRA, blessing, action, **data)
    assert ("error", "«Bendición» es un efecto fijo: solo el DM puede cambiarlo.") in flashes(r), (action, flashes(r))
b_row = row("SELECT * FROM conditions WHERE id = ?", blessing)
assert (b_row["name"], b_row["active"]) == ("Bendición", 1)
mark = cond("Marca del licántropo")                                # oculto: para el jugador no existe
assert post(LYRA, mark, "toggle").status_code == 404 and post(LYRA, mark, "delete").status_code == 404
assert post(LYRA, fury["id"], "lock").status_code == 403           # fijar es cosa del DM
assert post(LYRA, fury["id"], "visibility").status_code == 403
assert post(THORGAR, cond("Postura defensiva"), "toggle").status_code == 403   # no es su personaje
login("bruno")
assert c.post(f"/characters/{LYRA}/conditions/add", data=RAGE).status_code == 403

# --- 4. El DM: alterna, edita y fija lo que quiera ----------------------------------------------
login("dm")
post(LYRA, fury["id"], "lock")
assert one("SELECT locked FROM conditions WHERE id = ?", fury["id"]) == 1
post(LYRA, mark, "toggle")
assert one("SELECT active FROM conditions WHERE id = ?", mark) == 0
assert "Desactiva «Marca" not in page(LYRA)                       # lo oculto no deja rastro en el historial
r = post(LYRA, blessing, "edit", name="Bendición", kind="buff", duration="1 minuto", visible="1", locked="",
         eff_t=["saves"], eff_op=["add"], eff_v=["2"], eff_cap=["none"])
b_row = row("SELECT * FROM conditions WHERE id = ?", blessing)
assert b_row["locked"] == 0 and b_row["effects"] == '[{"t":"saves","op":"add","v":2}]'
c.post(f"/characters/{LYRA}/conditions/add", data={**RAGE, "name": "Maldición de la luna", "kind": "curse",
       "visible": "1", "locked": "1"})
moon = row("SELECT * FROM conditions WHERE name = 'Maldición de la luna'")
assert (moon["visible"], moon["locked"]) == (1, 1)
b = htmllib.unescape(c.get("/dm/").get_data(as_text=True))
assert "🔒 Maldición de la luna" in b and 'class="badge badge-curse is-off"' in b  # la marca, desactivada

# Ahora el jugador sí puede con la Bendición, y ya no con su Furia
login("ana")
assert ("error", "«Furia salvaje» es un efecto fijo: solo el DM puede cambiarlo.") in flashes(post(LYRA, fury["id"], "toggle"))
post(LYRA, blessing, "delete")
assert row("SELECT id FROM conditions WHERE id = ?", blessing) is None
print("EFECTOS DEL JUGADOR OK")
