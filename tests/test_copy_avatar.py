"""copy-to-postgres conserva las imágenes. Uso: TEST_DB=<postgres vacía> python test_copy_avatar.py"""
import io, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from app import create_app
from app.db import get_db
from app.models import Avatar

src = os.path.join(tempfile.mkdtemp(), "src.sqlite")
local = create_app({"DATABASE": src, "TESTING": True, "DEMO_DATA": True})
buf = io.BytesIO(); Image.new("RGB", (500, 500), (10, 120, 200)).save(buf, "PNG")
with local.app_context():
    Avatar.save(1, buf.getvalue())
    original = bytes(Avatar.get(1)["data"])

os.environ["DM_PASSWORD"] = "clave-larga-123"
remote = create_app({"DATABASE": os.environ["TEST_DB"], "TESTING": True})
res = remote.test_cli_runner().invoke(args=["copy-to-postgres", "--source", src, "--yes"])
print(res.output)
assert res.exit_code == 0, res.exception
with remote.app_context():
    copied = Avatar.get(1)
    assert bytes(copied["data"]) == original and copied["mime"] == "image/webp"
c = remote.test_client()
remote.config["CSRF_ENABLED"] = False
c.post("/login", data={"username": "ana", "password": "ana"})
r = c.get("/characters/1/avatar")
assert r.status_code == 200 and r.data == original
print("COPIA DE IMÁGENES OK")
