"""Migraciones incrementales del esquema.

schema.sql crea la versión 0. Cada entrada de MIGRATIONS sube una versión y se aplica
una sola vez (la versión se guarda en PRAGMA user_version en SQLite y en la tabla
schema_version en PostgreSQL). Para cambiar el esquema, añade una entrada nueva al
final; nunca edites las ya publicadas. Escribe el SQL en dialecto SQLite: db.script()
lo traduce a PostgreSQL (AUTOINCREMENT, REAL, CURRENT_TIMESTAMP).
"""

MIGRATIONS = [
    # 1: cualidades de objetos (bendiciones, maldiciones, usos limitados...)
    """
    CREATE TABLE item_traits (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id           INTEGER REFERENCES items(id) ON DELETE CASCADE,            -- plantilla del catálogo
        inventory_item_id INTEGER REFERENCES inventory_items(id) ON DELETE CASCADE,  -- objeto concreto
        name              TEXT    NOT NULL,
        kind              TEXT    NOT NULL CHECK (kind IN ('property', 'blessing', 'curse', 'charges')),
        description       TEXT,
        uses_max          INTEGER CHECK (uses_max IS NULL OR uses_max > 0),
        uses_current      INTEGER,
        recharge          TEXT,
        visible           INTEGER NOT NULL DEFAULT 1,
        CHECK ((item_id IS NULL) <> (inventory_item_id IS NULL))
    );
    CREATE INDEX idx_item_traits_item ON item_traits(item_id);
    CREATE INDEX idx_item_traits_inventory ON item_traits(inventory_item_id);
    """,
]


def migrate(db):
    version = db.get_version()
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        db.script(script)
        db.set_version(number)
    db.commit()
