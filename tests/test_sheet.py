"""Iniciativa, inspiración, competencia, salvaciones y habilidades. TEST_DB opcional (Postgres)."""
import html as htmllib, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db

app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tempfile.mkdtemp(), "h.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def one(sql, *a): return q(sql, *a)[0][0]
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))
def sheet(cid):
    """{nombre: (total, competencia)} de salvaciones y habilidades, y la franja de combate."""
    b = c.get(f"/characters/{cid}").get_data(as_text=True)
    rows = re.findall(r'<li class="(is-prof)?[^"]*"[^>]*>\s*<span class="prof-dot prof-(\d)"[^>]*></span><span class="check-name">([^<]+?)\s*(?:<span[^>]*>\w+</span>)?</span><b class="check-total[^"]*">([^<]+)</b>', b)
    checks = {htmllib.unescape(n).strip(): (t.replace("−", "-"), int(lvl)) for _, lvl, n, t in rows}
    strip = dict((htmllib.unescape(k), v.replace("−", "-")) for k, v in
                 re.findall(r'<span class="combat-label">([^<]+)</span>\s*<b(?: class="[^"]*")?>(?:<span[^>]*>★</span>\s*)?([^<]+)</b>', b))
    return checks, strip

lyra = 1
login("ana")
checks, strip = sheet(lyra)
print("Lyra:", {k: checks[k] for k in ("Acrobacias", "Sigilo", "Percepción", "Fuerza", "Constitución")}, strip)
assert len(checks) == 24                                     # 6 salvaciones + 18 habilidades
assert checks["Acrobacias"] == ("+5", 1)                     # DES 17 (+3) + competencia +2
assert checks["Sigilo"] == ("+7", 2)                         # pericia: +3 + 2×2
assert checks["Fuerza"] == ("+2", 1) and checks["Constitución"] == ("+1", 0)
want = {"Iniciativa": "+3", "Competencia": "+2", "Percepción pasiva": "14", "Inspiración": "1"}
assert {k: strip[k] for k in want} == want, strip

# --- El ejemplo pedido, de punta a punta: DES 20, competencia +2, Acrobacias -> +7
r = c.post("/characters/new", data={"name": "Ágil", "campaign_id": 1, "level": 3, "dexterity": 20,
                                    "skill_acrobatics": "1", "save_dexterity": "1"})
agil = one("SELECT id FROM characters WHERE name = ?", "Ágil")
checks, strip = sheet(agil)
print("Ágil:", checks["Acrobacias"], checks["Destreza"], strip["Iniciativa"])
assert checks["Acrobacias"] == ("+7", 1) and checks["Destreza"] == ("+7", 1) and strip["Iniciativa"] == "+5"
assert checks["Sigilo"] == ("+5", 0)                         # sin competencia: solo el modificador

# Competencia fijada a mano, nivel alto, bonus de iniciativa y valores raros ignorados
base = {"name": "Ágil", "dexterity": 20, "skill_acrobatics": "1", "save_dexterity": "1"}
c.post(f"/characters/{agil}/edit", data={**base, "level": 3, "proficiency_bonus": "4", "initiative_bonus": "5",
                                          "skill_stealth": "9", "skill_inventada": "1"})
checks, strip = sheet(agil)
assert checks["Acrobacias"] == ("+9", 1) and strip["Competencia"] == "+4" and strip["Iniciativa"] == "+10"
assert checks["Sigilo"][1] == 0, "nivel de competencia inválido se ignora"
assert not q("SELECT 1 FROM character_proficiencies WHERE name = 'inventada'")
c.post(f"/characters/{agil}/edit", data={**base, "level": 9, "proficiency_bonus": ""})
checks, strip = sheet(agil)
assert strip["Competencia"] == "+4" and checks["Acrobacias"] == ("+9", 1)   # nivel 9 -> +4 automático
c.post(f"/characters/{agil}/edit", data={**base, "level": 3, "skill_acrobatics": "0"})
assert sheet(agil)[0]["Acrobacias"] == ("+5", 0)                             # quitar la competencia
# Si el formulario vuelve con error, se conserva lo marcado
r = c.post(f"/characters/{agil}/edit", data={"name": "", "skill_arcana": "2", "save_wisdom": "1"})
b = r.get_data(as_text=True)
assert re.search(r'name="skill_arcana"[^>]*>\s*<option value="0"\s*>—</option>\s*<option value="1"\s*>[^<]*</option>\s*<option value="2" selected', b)
assert re.search(r'name="save_wisdom" value="1" checked', b)

# --- Inspiración: el jugador gasta, no se da; el DM da
assert c.post(f"/characters/{lyra}/inspiration", data={"action": "give"}).status_code == 403
r = c.post(f"/characters/{lyra}/inspiration", data={"action": "use"}, follow_redirects=True)
assert one("SELECT inspiration FROM characters WHERE id = ?", lyra) == 0
r = c.post(f"/characters/{lyra}/inspiration", data={"action": "use"}, follow_redirects=True)
print("sin inspiración:", flashes(r))
assert one("SELECT inspiration FROM characters WHERE id = ?", lyra) == 0
c.post(f"/characters/{lyra}/edit", data={"name": "Lyra Vientoalto", "inspiration": "99", "dexterity": 17})
assert one("SELECT inspiration FROM characters WHERE id = ?", lyra) == 0, "el formulario no cambia la inspiración"
login("dm")
c.post(f"/characters/{lyra}/inspiration", data={"action": "give"})
c.post(f"/characters/{lyra}/inspiration", data={"action": "give"})
assert one("SELECT inspiration FROM characters WHERE id = ?", lyra) == 2
b = c.get("/dm/").get_data(as_text=True)
assert "★ 2" in b and "Inic." in b
assert "Recibe inspiración (le quedan 2)" in c.get(f"/characters/{lyra}").get_data(as_text=True)
print("FICHA OK")
