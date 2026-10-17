"""Carga el catálogo del SRD 5.1 en castellano (app/data/srd_es.json): conjuros y objetos.

Se ejecuta una vez, con la migración que lo añade. Lo que ya existe con el mismo nombre no se
duplica: se completa (efectos, precio, datos del conjuro) sin pisar lo que haya editado el DM.
El fichero se genera con tools/build_srd.py.
"""
import json
import os

from ..text import normalize

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "srd_es.json")


def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def import_srd(db):
    data = load()
    spell_ids = _import_spells(db, data["spells"])
    _import_items(db, data["items"], spell_ids)


def _import_spells(db, spells):
    existing = {r["search_name"]: r for r in db.execute("SELECT * FROM spells").fetchall()}
    new_rows, updates = [], []
    for s in spells:
        row = existing.get(normalize(s["name"]))
        if row is None:
            new_rows.append((s["name"], normalize(s["name"]), s["level"], s["school"], s["casting_time"],
                             s["spell_range"], s["components"], s["duration"], s["concentration"], s["ritual"],
                             f" {' '.join(s['classes'])} ", s["description"]))
        elif row["official"]:
            # Los oficiales que ya había: datos del SRD; listas de clase unidas (p. ej. el artífice)
            classes = sorted(set((row["classes"] or "").split()) | set(s["classes"]))
            updates.append((s["level"], s["school"], s["casting_time"], s["spell_range"], s["components"],
                            s["duration"], s["concentration"], s["ritual"], f" {' '.join(classes)} ", row["id"]))
    db.many(
        """INSERT INTO spells (name, search_name, level, school, casting_time, spell_range, components, duration,
                               concentration, ritual, classes, description, official)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""", new_rows,
    )
    db.many(
        """UPDATE spells SET level = ?, school = ?, casting_time = ?, spell_range = ?, components = ?, duration = ?,
                             concentration = ?, ritual = ?, classes = ? WHERE id = ?""", updates,
    )
    ids = {r["search_name"]: r["id"] for r in db.execute("SELECT id, search_name FROM spells").fetchall()}
    return {s["srd"]: ids[normalize(s["name"])] for s in spells}


def _import_items(db, items, spell_ids):
    existing = {r["search_name"]: r for r in db.execute("SELECT * FROM items").fetchall()}
    new_rows, fills = [], []
    for it in items:
        effects = json.dumps(it["effects"], ensure_ascii=False, separators=(",", ":")) if it["effects"] else None
        row = existing.get(normalize(it["name"]))
        if row is None:
            new_rows.append((it["name"], normalize(it["name"]), it["category"], it["rarity"], it["weight"],
                             it["properties"], it["description"], it["attunement"], effects, it["cost_cp"]))
        else:  # ya existía (p. ej. del catálogo básico): solo se completa lo que falta
            fills.append((effects, it["cost_cp"], it["properties"], it["description"], row["id"]))
    db.many(
        """INSERT INTO items (name, search_name, category, rarity, weight, properties, description, attunement,
                              effects, cost_cp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", new_rows,
    )
    db.many(
        """UPDATE items SET effects = COALESCE(effects, ?), cost_cp = COALESCE(cost_cp, ?),
                            properties = CASE WHEN properties IS NULL OR properties = '' THEN ? ELSE properties END,
                            description = CASE WHEN description IS NULL OR description = '' THEN ? ELSE description END
           WHERE id = ?""", fills,
    )
    ids = {r["search_name"]: r["id"] for r in db.execute("SELECT id, search_name FROM items").fetchall()}
    linked = {(r["item_id"], r["spell_id"]) for r in db.execute("SELECT item_id, spell_id FROM item_spells").fetchall()}
    grants = []
    for it in items:
        item_id = ids[normalize(it["name"])]
        for key in it["spells"]:
            pair = (item_id, spell_ids[key])
            if pair not in linked:
                linked.add(pair)
                grants.append(pair)
    db.many("INSERT INTO item_spells (item_id, spell_id) VALUES (?, ?)", grants)
