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
    # 7: código para unirse a una campaña y jugadores que pertenecen a cada una
    """
    ALTER TABLE campaigns ADD COLUMN join_code TEXT;
    CREATE UNIQUE INDEX idx_campaigns_join_code ON campaigns(join_code);
    CREATE TABLE campaign_members (
        campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        joined_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (campaign_id, user_id)
    );
    """,
    # 8: códigos para las campañas existentes; quien ya tenía personajes en una, es miembro
    lambda db: _codes_and_members(db),
    # 9: iniciativa, inspiración, competencia y competencias en salvaciones y habilidades
    """
    ALTER TABLE characters ADD COLUMN inspiration INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE characters ADD COLUMN initiative_bonus INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE characters ADD COLUMN proficiency_bonus INTEGER;  -- NULL = automático según el nivel
    CREATE TABLE character_proficiencies (
        character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
        kind         TEXT    NOT NULL CHECK (kind IN ('save', 'skill')),
        name         TEXT    NOT NULL,
        level        INTEGER NOT NULL DEFAULT 1 CHECK (level IN (1, 2)),  -- 1 competencia, 2 pericia
        PRIMARY KEY (character_id, kind, name)
    );
    """,
    # 10: distancias en pies y casillas (velocidad y textos que hablaban de metros)
    lambda db: _distances_to_feet(db),
    # 11: cuándo vio el destinatario la propuesta (para avisarle solo una vez)
    "ALTER TABLE trades ADD COLUMN seen_at TEXT;",
    # 12: efectos mecánicos (JSON) de objetos, cualidades y estados sobre la ficha
    """ALTER TABLE items ADD COLUMN effects TEXT;
       ALTER TABLE item_traits ADD COLUMN effects TEXT;
       ALTER TABLE conditions ADD COLUMN effects TEXT;""",
    # 13: personajes ocultos al resto de jugadores (NULL visible, 'player' o 'dm' según quién lo ocultó)
    "ALTER TABLE characters ADD COLUMN hidden_by TEXT;",
    # 14: efectos que se activan y desactivan, y fijos (el jugador no puede quitarlos). Los que
    #     ya existían los puso el DM y el jugador no podía quitarlos: quedan fijos.
    """ALTER TABLE conditions ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
       ALTER TABLE conditions ADD COLUMN locked INTEGER NOT NULL DEFAULT 0;
       UPDATE conditions SET locked = 1;""",
    # 15: clases, subclases y conjuros (catálogo oficial + homebrew) y la magia de cada personaje
    """CREATE TABLE classes (
           id             INTEGER PRIMARY KEY AUTOINCREMENT,
           code           TEXT,                       -- clave de las clases oficiales (bard…); NULL = homebrew
           name           TEXT    NOT NULL,
           search_name    TEXT    NOT NULL DEFAULT '',
           official       INTEGER NOT NULL DEFAULT 0,
           hit_die        INTEGER NOT NULL DEFAULT 8,
           saves          TEXT,                       -- "strength,constitution"
           caster         TEXT    NOT NULL DEFAULT 'none',
           spell_ability  TEXT,
           spell_prep     TEXT,
           subclass_level INTEGER NOT NULL DEFAULT 3,
           proficiencies  TEXT,
           description    TEXT
       );
       CREATE TABLE subclasses (
           id            INTEGER PRIMARY KEY AUTOINCREMENT,
           class_id      INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
           name          TEXT    NOT NULL,
           official      INTEGER NOT NULL DEFAULT 0,
           caster        TEXT,                        -- NULL = la de la clase
           spell_ability TEXT,
           spell_prep    TEXT,
           progress      TEXT,                        -- tablas oficiales de trucos/conocidos propias
           description   TEXT
       );
       CREATE TABLE spells (
           id            INTEGER PRIMARY KEY AUTOINCREMENT,
           name          TEXT    NOT NULL,
           search_name   TEXT    NOT NULL DEFAULT '',
           level         INTEGER NOT NULL DEFAULT 0,  -- 0 = truco
           school        TEXT,
           casting_time  TEXT,
           spell_range   TEXT,
           components    TEXT,
           duration      TEXT,
           concentration INTEGER NOT NULL DEFAULT 0,
           ritual        INTEGER NOT NULL DEFAULT 0,
           classes       TEXT,                        -- " bard cleric " (claves de clase, para buscar)
           description   TEXT,
           official      INTEGER NOT NULL DEFAULT 0
       );
       CREATE INDEX idx_spells_search ON spells (search_name);
       CREATE INDEX idx_spells_level ON spells (level, search_name);
       CREATE TABLE item_spells (
           item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
           spell_id INTEGER NOT NULL REFERENCES spells(id) ON DELETE CASCADE,
           PRIMARY KEY (item_id, spell_id)
       );
       CREATE TABLE character_spells (
           id              INTEGER PRIMARY KEY AUTOINCREMENT,
           character_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
           spell_id        INTEGER NOT NULL REFERENCES spells(id) ON DELETE CASCADE,
           source          TEXT    NOT NULL DEFAULT 'class',
           prepared        INTEGER NOT NULL DEFAULT 0,
           always_prepared INTEGER NOT NULL DEFAULT 0,
           notes           TEXT,
           UNIQUE (character_id, spell_id)
       );
       CREATE TABLE character_spell_slots (
           character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
           slot         TEXT    NOT NULL,             -- "1".."9" o "pact"
           used         INTEGER NOT NULL DEFAULT 0,
           max_override INTEGER,                      -- NULL = el de la tabla de su clase
           PRIMARY KEY (character_id, slot)
       );
       ALTER TABLE characters ADD COLUMN class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL;
       ALTER TABLE characters ADD COLUMN subclass_id INTEGER REFERENCES subclasses(id) ON DELETE SET NULL;
       ALTER TABLE characters ADD COLUMN subclass_name TEXT;
       ALTER TABLE characters ADD COLUMN hit_die INTEGER;
       ALTER TABLE characters ADD COLUMN caster TEXT NOT NULL DEFAULT 'none';
       ALTER TABLE characters ADD COLUMN spell_ability TEXT;
       ALTER TABLE characters ADD COLUMN spell_prep TEXT;""",
    lambda db: _official_classes_and_spells(db),
]

# Columnas de texto libre donde puede haber distancias
DISTANCE_TEXT_COLUMNS = {
    "items": ("name", "properties", "description"),
    "item_traits": ("name", "description", "recharge"),
    "conditions": ("name", "description", "duration"),
    "shops": ("description",),
    "loot_pools": ("description",),
    "campaigns": ("description",),
    "characters": ("notes",),
}


def _distances_to_feet(db):
    from .text import distances, meters_to_feet, normalize
    # Velocidad: estaba en metros. Las que ya parecen pies (múltiplos de 5 desde 20) no se tocan.
    for row in db.execute("SELECT id, speed FROM characters").fetchall():
        speed = row["speed"] or 0
        if not (speed >= 20 and speed % 5 == 0):
            db.execute("UPDATE characters SET speed = ? WHERE id = ?", (meters_to_feet(speed), row["id"]))
    for table, columns in DISTANCE_TEXT_COLUMNS.items():
        for row in db.execute(f"SELECT id, {', '.join(columns)} FROM {table}").fetchall():
            changed = {col: distances(row[col]) for col in columns if row[col] and distances(row[col]) != row[col]}
            if not changed:
                continue
            if table == "items" and "name" in changed:
                changed["search_name"] = normalize(changed["name"])
            sets = ", ".join(f"{col} = ?" for col in changed)
            db.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*changed.values(), row["id"]))

CAMPAIGN_TABLES = ("characters", "shops", "loot_pools")


def _official_classes_and_spells(db):
    """Carga las clases y conjuros oficiales y asigna su clase a los personajes que ya existían
    (por el nombre escrito: «Exploradora» → Explorador), con sus valores por defecto de magia."""
    from .models.class_data import CLASSES
    from .models.spell_data import SPELLS
    from .text import normalize
    for code, name, die, saves, caster, ability, prep, sub_level, profs, subclasses in CLASSES:
        class_id = db.insert(
            """INSERT INTO classes (code, name, search_name, official, hit_die, saves, caster, spell_ability,
                                    spell_prep, subclass_level, proficiencies)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
            (code, name, normalize(name), die, ",".join(saves), caster, ability, prep, sub_level, profs),
        )
        for sub in subclasses:
            sub_name, sub_caster, sub_ability, progress, sub_prep = (tuple(sub) + (None,) * 5)[:5]
            db.execute(
                """INSERT INTO subclasses (class_id, name, official, caster, spell_ability, spell_prep, progress)
                   VALUES (?, ?, 1, ?, ?, ?, ?)""",
                (class_id, sub_name, sub_caster, sub_ability, sub_prep, progress),
            )
    for name, level, school, cast, rng, comp, dur, conc, ritual, classes, desc in SPELLS:
        db.execute(
            """INSERT INTO spells (name, search_name, level, school, casting_time, spell_range, components, duration,
                                   concentration, ritual, classes, description, official)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (name, normalize(name), level, school, cast, rng, comp, dur, conc, ritual, f" {classes} ", desc),
        )
    # La varita del catálogo básico concede su conjuro
    wand = db.execute("SELECT id FROM items WHERE name = 'Varita de proyectiles mágicos'").fetchone()
    missile = db.execute("SELECT id FROM spells WHERE name = 'Proyectil mágico'").fetchone()
    if wand and missile:
        db.execute("INSERT INTO item_spells (item_id, spell_id) VALUES (?, ?)", (wand["id"], missile["id"]))
    # Personajes existentes: su clase por el nombre (masculino o femenino)
    classes = db.execute("SELECT * FROM classes").fetchall()
    for ch in db.execute("SELECT id, class_name FROM characters WHERE class_name IS NOT NULL").fetchall():
        match = class_matching(ch["class_name"], classes)
        if match:
            db.execute(
                """UPDATE characters SET class_id = ?, class_name = ?, hit_die = ?, caster = ?, spell_ability = ?,
                   spell_prep = ? WHERE id = ?""",
                (match["id"], match["name"], match["hit_die"], match["caster"], match["spell_ability"],
                 match["spell_prep"], ch["id"]),
            )


def class_matching(text, classes):
    """La clase cuyo nombre coincide con el texto, sin tildes y aceptando el femenino."""
    from .text import normalize
    wanted = normalize(text or "")
    if not wanted:
        return None
    for row in classes:
        base = row["search_name"]
        variants = {base, base + "a", base[:-1] + "a" if base.endswith(("o", "e")) else base}  # monje → monja
        if wanted in variants:
            return row
    return None


def _codes_and_members(db):
    from .models.campaign import new_join_code
    for row in db.execute("SELECT id FROM campaigns WHERE join_code IS NULL").fetchall():
        db.execute("UPDATE campaigns SET join_code = ? WHERE id = ?", (new_join_code(db), row["id"]))
    db.execute(
        """INSERT INTO campaign_members (campaign_id, user_id)
           SELECT DISTINCT campaign_id, user_id FROM characters WHERE campaign_id IS NOT NULL"""
    )


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
