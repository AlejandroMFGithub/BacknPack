"""Imágenes de personaje. TEST_DB opcional (Postgres)."""
import io, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from app import create_app
from app.db import get_db

tmp = tempfile.mkdtemp()
app = create_app({"DATABASE": os.environ.get("TEST_DB") or os.path.join(tmp, "a.sqlite"),
                  "TESTING": True, "CSRF_ENABLED": False, "DEMO_DATA": True})
c = app.test_client()
def login(u):
    c.get("/logout"); c.post("/login", data={"username": u, "password": u})
    if u == "ana": c.post("/play/1")
def q(sql, *a):
    with app.app_context(): return get_db().execute(sql, a).fetchall()
def flashes(r): return re.findall(r'flash-(\w+)">([^<]*)<', r.get_data(as_text=True))
def img_bytes(fmt="JPEG", size=(3000, 2000), color=(200, 30, 30), exif=None, mode="RGB"):
    buf = io.BytesIO()
    im = Image.new(mode, size, color)
    kw = {"exif": exif} if exif is not None else {}
    im.save(buf, fmt, **kw)
    return buf.getvalue()
def upload(cid, data, name="foto.jpg"):
    return c.post(f"/characters/{cid}/avatar", data={"image": (io.BytesIO(data), name)},
                  content_type="multipart/form-data", follow_redirects=True)

lyra = q("SELECT id FROM characters WHERE name LIKE ?", "Lyra%")[0][0]
thor = q("SELECT id FROM characters WHERE name LIKE ?", "Thorgar%")[0][0]

login("ana")
# Sin imagen: inicial «L» sobre su color
b = c.get(f"/characters/{lyra}").get_data(as_text=True)
assert 'class="avatar avatar-lg"' in b and ">L<" in b.replace("\n", "").replace(" ", "")

# Foto grande de móvil con GPS en EXIF y orientación rotada
exif = Image.Exif()
exif[0x0112] = 6                               # Orientation: girar 90°
exif[0x8825] = {2: (40.0, 25.0, 0.0), 1: "N"}  # GPSInfo
raw = img_bytes(size=(4000, 3000), exif=exif)
print(f"subida: {len(raw)//1024} KB")
r = upload(lyra, raw)
print("subir:", flashes(r))
row = q("SELECT mime, data, version FROM character_avatars WHERE character_id = ?", lyra)[0]
data = bytes(row[1])
im = Image.open(io.BytesIO(data))
print(f"guardada: {row[0]} {im.size} {len(data)} bytes, exif={dict(im.getexif())}")
assert row[0] == "image/webp" and im.format == "WEBP" and im.size == (256, 256)
assert len(data) < 40 * 1024
assert not im.getexif().get(0x8825), "el GPS debe eliminarse"

# Se sirve con caché y versión; 304 si no ha cambiado
r = c.get(f"/characters/{lyra}/avatar?v={row[2]}")
assert r.status_code == 200 and r.headers["Content-Type"] == "image/webp" and r.data == data
assert "immutable" in r.headers["Cache-Control"] and r.headers["X-Content-Type-Options"] == "nosniff"
r2 = c.get(f"/characters/{lyra}/avatar", headers={"If-None-Match": r.headers["ETag"]})
assert r2.status_code == 304
b = c.get(f"/characters/{lyra}").get_data(as_text=True)
assert f"/characters/{lyra}/avatar?v={row[2]}" in b and "Quitar imagen" in b

# PNG con transparencia y GIF también valen
assert flashes(upload(lyra, img_bytes("PNG", (300, 500), (0, 0, 0, 0), mode="RGBA"), "t.png"))[0][0] == "ok"
assert flashes(upload(lyra, img_bytes("GIF", (64, 64), 5, mode="P"), "a.gif"))[0][0] == "ok"
v2 = q("SELECT version FROM character_avatars WHERE character_id = ?", lyra)[0][0]
assert v2 != row[2], "cada subida cambia la versión"

# Rechazos
print("texto:", flashes(upload(lyra, b"no soy una imagen" * 100, "falsa.png")))
print("vacío:", flashes(upload(lyra, b"", "x.png")))
bmp = io.BytesIO(); Image.new("RGB", (10, 10)).save(bmp, "BMP")
print("bmp:", flashes(upload(lyra, bmp.getvalue(), "x.bmp")))
bomb = io.BytesIO(); Image.new("1", (12000, 12000)).save(bomb, "PNG")   # 144 Mpx, pocos KB
print(f"bomba ({len(bomb.getvalue())//1024} KB):", flashes(upload(lyra, bomb.getvalue(), "b.png")))
r = upload(lyra, os.urandom(10 * 1024 * 1024), "enorme.jpg")
print("10 MB:", r.status_code, flashes(r))
assert r.status_code == 200 and "demasiado grande" in r.get_data(as_text=True)
assert q("SELECT version FROM character_avatars WHERE character_id = ?", lyra)[0][0] == v2, "un error no debe tocar la imagen"

# Permisos: ana no puede cambiar la de Thorgar; pero sí verla (aparece en intercambios)
assert c.post(f"/characters/{thor}/avatar", data={"image": (io.BytesIO(raw), "x.jpg")},
              content_type="multipart/form-data").status_code == 403
assert c.post(f"/characters/{thor}/avatar/delete").status_code == 403
# El buscador devuelve la imagen o la inicial
res = c.get("/api/characters?q=lyra").get_json()["results"][0]["avatar"]
assert res["url"] and res["url"].startswith(f"/characters/{lyra}/avatar?v=")
res = c.get("/api/characters?q=thorgar").get_json()["results"][0]["avatar"]
assert res["url"] is None and res["initial"] == "T" and res["color"].startswith("#")

# El DM puede cambiar la de cualquiera
login("dm")
assert flashes(upload(thor, img_bytes(size=(800, 800))))[0][0] == "ok"
b = c.get("/dm/").get_data(as_text=True)
assert f"/characters/{thor}/avatar?v=" in b and f"/characters/{lyra}/avatar?v=" in b
assert "avatar avatar-sm" in b                                            # icono pequeño en las listas

# Quitar imagen -> vuelve la inicial; borrar personaje -> se borra la imagen
login("ana")
print("quitar:", flashes(c.post(f"/characters/{lyra}/avatar/delete", follow_redirects=True)))
assert not q("SELECT 1 FROM character_avatars WHERE character_id = ?", lyra)
assert c.get(f"/characters/{lyra}/avatar").status_code == 404
login("dm")
c.post(f"/characters/{thor}/delete")
assert not q("SELECT 1 FROM character_avatars WHERE character_id = ?", thor)
print("AVATARES OK")
