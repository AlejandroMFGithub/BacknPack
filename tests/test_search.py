"""Buscador, filtros, orden y paginación con un catálogo grande. TEST_DB opcional (Postgres)."""
import os, re, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.db import get_db
from app.models import Item, Character

tmp = tempfile.mkdtemp()
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tmp, "s.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
cats = ["Arma", "Armadura", "Consumible", "Objeto maravilloso", "Tesoro"]
rars = ["Común", "Poco común", "Raro", "Muy raro", "Legendario"]
with app.app_context():
    for i in range(1200):
        Item.create({"name": f"Objeto {i:04d} de prueba", "category": cats[i % 5], "rarity": rars[i % 5], "weight": i % 7})
    Item.create({"name": "Pocíón 100% pura", "category": "Consumible"})   # % literal y tildes
    Item.create({"name": "Espada de Ébano", "category": "Arma", "rarity": "Artefacto"})
    ana = get_db().execute("SELECT id FROM users WHERE username = 'ana'").fetchone()[0]
    for i in range(70):
        Character.create(ana, {"name": f"Secuaz {i:02d}"}, 1)

c = app.test_client()
def login(u): c.get("/logout"); c.post("/login", data={"username": u, "password": u})
def j(url):
    r = c.get(url); assert r.status_code == 200, (url, r.status_code); return r.get_json()
def html(url):
    r = c.get(url); assert r.status_code == 200, (url, r.status_code); return r.get_data(as_text=True)
def ids(sql, *a):
    with app.app_context(): return [r[0] for r in get_db().execute(sql, a).fetchall()]

login("dm")
# --- API de objetos
t = time.perf_counter(); d = j("/api/items?q=pocion"); dt = (time.perf_counter() - t) * 1000
labels = [r["label"] for r in d["results"]]
print("pocion ->", labels, f"({dt:.0f} ms)")
assert labels[0] == "Pocíón 100% pura" and "Poción de curación" in labels, labels   # sin tildes, empieza-por primero
assert j("/api/items?q=EBANO")["results"][0]["label"] == "Espada de Ébano"      # mayúsculas/tildes
assert j("/api/items?q=%25")["total"] == 1, "el % debe buscarse literal, no como comodín"
d = j("/api/items?q=objeto")
with_objeto = ids("SELECT COUNT(*) FROM items WHERE search_name LIKE ?", "%objeto%")[0]    # 1.200 de prueba + los del SRD
assert len(d["results"]) == 20 and d["has_more"] and d["total"] == with_objeto >= 1200
d2 = j("/api/items?q=objeto&page=2")
assert not {r["id"] for r in d["results"]} & {r["id"] for r in d2["results"]}, "páginas solapadas"
d = j("/api/items?q=objeto&category=Tesoro&rarity=Legendario")
assert d["total"] == 240 and all("Tesoro · Legendario" in r["sub"] for r in d["results"])
assert j("/api/items?category=NoExiste")["total"] > 1200                        # filtro inválido = sin filtro
# --- API de personajes y usuarios
assert j("/api/characters?q=secuaz")["total"] == 70
assert j("/api/characters?q=ana")["total"] >= 71                               # busca también por jugador
assert j("/api/users?q=bru")["results"][0]["label"] == "bruno"
# --- Catálogo paginado, filtros, orden y orden inválido
b = html("/dm/items")
assert "Página 1 de" in b and "Siguiente" in b
b = html("/dm/items?category=Arma&rarity=Artefacto")
assert "Espada de Ébano" in b and "Objeto 0000" not in b
b = html("/dm/items?sort=rarity_desc")
assert b.index("Espada de Ébano") < b.index("Objeto 0004")                      # Artefacto antes que Legendario
b = html("/dm/items?sort=DROP%20TABLE%20items")
assert "Catálogo" in b                                                         # orden desconocido -> por defecto
b = html("/dm/items?page=999")
pages = -(-ids("SELECT COUNT(*) FROM items")[0] // 50)
assert f"Página {pages} de {pages}" in b                                       # página fuera de rango
# --- Panel DM y personajes con muchos
b = html("/dm/?q=secuaz&sort=recent")
assert "Secuaz 69" in b and "Secuaz 00" not in b and "Página 1 de 2" in b
assert "Secuaz 00" in html("/dm/?q=secuaz&sort=recent&page=2")
# --- Inventario: filtro y orden
lyra = ids("SELECT id FROM characters WHERE name LIKE ?", "Lyra%")[0]
inv = lambda b: b[b.index('id="inventario"'):]                                 # solo la sección del inventario
b = inv(html(f"/characters/{lyra}?q=daga"))
assert "Daga" in b and "Arco corto" not in b and "1 de " in b
b = inv(html(f"/characters/{lyra}?sort=weight"))
assert b.index("Armadura de cuero") < b.index("Daga")
b = inv(html(f"/characters/{lyra}?category=Consumible"))
assert "Poción de curación" in b and "Arco corto" not in b
# --- DM: dar objeto por id (buscador) y botín por item_id / currency_id
r = c.post(f"/characters/{lyra}/inventory/add", data={"item_id": "", "quantity": 1}, follow_redirects=True)
assert "Elige un objeto" in r.get_data(as_text=True)
r = c.post("/loot/1/entries", data={"item_id": 999999, "quantity": 1}, follow_redirects=True)
assert r.status_code == 200 and "no existe" in r.get_data(as_text=True)
ebano = ids("SELECT id FROM items WHERE name = ?", "Espada de Ébano")[0]
c.post("/loot/1/entries", data={"item_id": ebano, "quantity": 1})
pp = ids("SELECT id FROM currencies WHERE code = 'pp'")[0]
c.post("/loot/1/entries", data={"currency_id": pp, "quantity": 5})
assert "Espada de Ébano" in html("/loot/1")
# --- Nuevo personaje con dueño elegido; dueño inexistente
r = c.post("/characters/new", data={"name": "Fantasma", "user_id": 99999}, follow_redirects=True)
assert "no existe" in r.get_data(as_text=True)
# --- Tienda: ordenar por precio, comprar como, volver con filtros
b = html("/shops/1?sort=price")
assert b.index("Flechas (20)") < b.index("Cota de malla")
b = html("/shops/1?sort=price_desc")
assert b.index("Cota de malla") < b.index("Flechas (20)")
b = html("/shops/1")
assert "Elige un personaje" in b and 'name="character_id"' not in b            # DM aún no eligió
b = html(f"/shops/1?as={lyra}&q=escudo")
assert 'name="character_id"' in b and "Escudo" in b and "Cota de malla" not in b
listing = ids("SELECT si.id FROM shop_items si JOIN items i ON i.id = si.item_id WHERE i.name = 'Escudo'")[0]
po = ids("SELECT id FROM currencies WHERE code = 'po'")[0]
r = c.post(f"/shops/1/buy/{listing}", data={"character_id": lyra, "quantity": 1, "currency_id": po},
           headers={"Referer": f"http://localhost/shops/1?as={lyra}&q=escudo"})
assert r.status_code == 302 and r.headers["Location"].endswith(f"/shops/1?as={lyra}&q=escudo"), r.headers["Location"]
r = c.post(f"/shops/1/buy/{listing}", data={"character_id": lyra, "quantity": 1, "currency_id": po},
           headers={"Referer": "https://evil.example/robar"})
assert "evil" not in r.headers["Location"], "no debe redirigir fuera del sitio"
# --- Intercambios: filtro por estado
assert "Sin intercambios" in html("/trades/?status=accepted") or "Ningún intercambio" in html("/trades/?status=accepted")

# --- Jugador: permisos del buscador
login("ana"); c.post(f"/play/{lyra}")
assert c.get("/api/items?q=a").status_code in (302, 403)
assert c.get("/api/users").status_code in (302, 403)
d = j("/api/characters?mine=1&q=")
assert d["total"] == 71 and all("ana" in r["sub"] for r in d["results"])
thor = ids("SELECT id FROM characters WHERE name LIKE ?", "Thorgar%")[0]
assert all(r["id"] != thor for r in j(f"/api/characters?q=thor&exclude={thor}")["results"])
b = html(f"/shops/1?as={thor}")                                                # el jugador compra siempre como Lyra
assert f'name="character_id" value="{lyra}"' in b and f'name="character_id" value="{thor}"' not in b
b = html("/characters/?q=secuaz 0")
assert "Secuaz 05" in b and "Secuaz 15" not in b
print("BÚSQUEDA OK")
