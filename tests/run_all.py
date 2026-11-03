"""Ejecuta todas las pruebas con SQLite (cada una con su base de datos temporal).

    .venv/Scripts/python.exe tests/run_all.py          # todas
    .venv/Scripts/python.exe tests/run_all.py armas    # solo las que contengan «armas» en el nombre

Para PostgreSQL: tests/run_pg.py
"""
import os, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

here = os.path.dirname(os.path.abspath(__file__))
only = sys.argv[1] if len(sys.argv) > 1 else ""
scripts = sorted(f for f in os.listdir(here)
                 if f.endswith(".py") and (f.startswith("test_") or f.startswith("smoke")) and only in f)
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
failed = []
for script in scripts:
    if script in ("test_prod.py", "test_copy_avatar.py"):  # solo tienen sentido contra PostgreSQL
        continue
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(here, script)], env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    last = (r.stdout.strip().splitlines() or [""])[-1]
    ok = r.returncode == 0
    print(f"{'OK ' if ok else 'FALLO'} {script:24} {time.time() - t:5.1f} s  {last[:80] if ok else ''}")
    if not ok:
        failed.append(script)
        print("\n".join((r.stdout + r.stderr).strip().splitlines()[-12:]))
print("\nTODO OK" if not failed else f"\nFALLAN: {', '.join(failed)}")
sys.exit(1 if failed else 0)
