"""Arranca un PostgreSQL temporal y ejecuta todas las pruebas contra él.

Necesita `pip install pgserver "psycopg[binary]"` en el entorno con el que se lance:
    python tests/run_pg.py
Los datos de PostgreSQL van a la carpeta temporal del sistema, no al proyecto.
"""
import os, subprocess, sys, tempfile
import pgserver, psycopg

here = os.path.dirname(os.path.abspath(__file__))
srv = pgserver.get_server(os.path.join(tempfile.gettempdir(), "backnpack-pgdata"), cleanup_mode="stop")
base = srv.get_uri()
admin = psycopg.connect(base, autocommit=True)

# script -> bases de datos que necesita (TEST_DB y, si hace falta, TEST_DB2)
SUITE = [
    ("smoke.py", 1), ("smoke_traits.py", 1), ("test_prod.py", 2), ("test_search.py", 1), ("test_avatar.py", 1),
    ("test_copy_avatar.py", 1), ("test_campaigns.py", 1), ("test_delete.py", 1), ("test_codes.py", 1),
    ("test_sheet.py", 1), ("test_distances.py", 1), ("test_notify.py", 1), ("test_effects.py", 1),
    ("test_hidden.py", 1), ("test_toggle.py", 1), ("test_magic.py", 1), ("test_hp.py", 1), ("test_srd.py", 1),
    ("test_weapons.py", 1), ("test_item_edit.py", 1),
]


def fresh(name):
    admin.execute(f"DROP DATABASE IF EXISTS {name}")
    admin.execute(f"CREATE DATABASE {name}")
    return base.rsplit("/", 1)[0] + "/" + name


clean = {k: v for k, v in os.environ.items() if k not in ("RENDER", "BACKNPACK_SECRET", "DM_PASSWORD", "INVITE_CODE")}
for script, n in SUITE:
    if not os.path.exists(os.path.join(here, script)):
        continue
    stem = script[:-3]
    env = {"TEST_DB": fresh(f"t_{stem}")}
    if n == 2:
        env["TEST_DB2"] = fresh(f"t_{stem}_2")
    print(f"\n===== {script} (PostgreSQL) =====", flush=True)
    if subprocess.run([sys.executable, os.path.join(here, script)], env={**clean, **env}).returncode:
        sys.exit(f"FALLO en {script}")
print("\nTODO OK EN POSTGRES")
