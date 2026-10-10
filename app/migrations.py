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
    # 2: nombres normalizados (sin tildes ni mayúsculas) para el buscador
    """
    ALTER TABLE items ADD COLUMN search_name TEXT NOT NULL DEFAULT '';
    ALTER TABLE characters ADD COLUMN search_name TEXT NOT NULL DEFAULT '';
    CREATE INDEX idx_items_category ON items(category);
    CREATE INDEX idx_inventory_character ON inventory_items(character_id);
    """,
    # 3: rellena search_name en las filas que ya existían
    lambda db: _backfill_search_names(db),
    # 4: imagen de cada personaje (aparte, para no cargar los bytes en cada lista)
    """
    CREATE TABLE character_avatars (
        character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
        mime         TEXT NOT NULL,
        data         BLOB NOT NULL,
        version      TEXT NOT NULL  -- cambia en cada subida: invalida la caché del navegador
    );
    """,
    # 5: campañas («mundos»): agrupan personajes, tiendas y botines
    """
    CREATE TABLE campaigns (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        description TEXT,
        is_open     INTEGER NOT NULL DEFAULT 1,  -- los jugadores pueden crear personajes en ella
        archived    INTEGER NOT NULL DEFAULT 0,  -- oculta y bloqueada para los jugadores
        created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    ALTER TABLE characters ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE;
    ALTER TABLE shops ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE;
    ALTER TABLE loot_pools ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE;
    CREATE INDEX idx_characters_campaign ON characters(campaign_id);
    CREATE INDEX idx_shops_campaign ON shops(campaign_id);
    CREATE INDEX idx_loot_campaign ON loot_pools(campaign_id);
    ALTER TABLE users ADD COLUMN last_campaign_id INTEGER;  -- el DM vuelve a la última campaña usada
    """,
    # 6: lo que ya existía pasa a una «Campaña principal»
    lambda db: _adopt_orphans(db),
]

CAMPAIGN_TABLES = ("characters", "shops", "loot_pools")


def _adopt_orphans(db):
    if not any(db.execute(f"SELECT 1 FROM {t} WHERE campaign_id IS NULL LIMIT 1").fetchone()
               for t in CAMPAIGN_TABLES):
        return
    campaign_id = db.insert(
        "INSERT INTO campaigns (name, description) VALUES (?, ?)",
        ("Campaña principal", "Creada automáticamente con los personajes, tiendas y botines que ya existían."),
    )
    for table in CAMPAIGN_TABLES:
        db.execute(f"UPDATE {table} SET campaign_id = ? WHERE campaign_id IS NULL", (campaign_id,))


def _backfill_search_names(db):
    from .text import normalize
    for table in ("items", "characters"):
        for row in db.execute(f"SELECT id, name FROM {table}").fetchall():
            db.execute(f"UPDATE {table} SET search_name = ? WHERE id = ?", (normalize(row["name"]), row["id"]))


def migrate(db):
    """Aplica las migraciones pendientes. Cada una es SQL (texto) o una función(db)."""
    version = db.get_version()
    for number, step in enumerate(MIGRATIONS[version:], start=version + 1):
        if callable(step):
            step(db)
        else:
            db.script(step)
        db.set_version(number)
    db.commit()
