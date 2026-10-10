-- Esquema base de BacknPack, versión 0. Escrito para SQLite; db.py lo traduce a PostgreSQL.
-- Los cambios posteriores están en migrations.py.

DROP TABLE IF EXISTS character_avatars;
DROP TABLE IF EXISTS item_traits;
DROP TABLE IF EXISTS activity_log;
DROP TABLE IF EXISTS trade_lines;
DROP TABLE IF EXISTS trades;
DROP TABLE IF EXISTS loot_entries;
DROP TABLE IF EXISTS loot_pools;
DROP TABLE IF EXISTS shop_items;
DROP TABLE IF EXISTS shops;
DROP TABLE IF EXISTS conditions;
DROP TABLE IF EXISTS inventory_items;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS character_currencies;
DROP TABLE IF EXISTS currencies;
DROP TABLE IF EXISTS characters;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS campaigns;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'player' CHECK (role IN ('dm', 'player')),
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE characters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    race         TEXT,
    class_name   TEXT,
    level        INTEGER NOT NULL DEFAULT 1,
    background   TEXT,
    alignment    TEXT,
    strength     INTEGER NOT NULL DEFAULT 10,
    dexterity    INTEGER NOT NULL DEFAULT 10,
    constitution INTEGER NOT NULL DEFAULT 10,
    intelligence INTEGER NOT NULL DEFAULT 10,
    wisdom       INTEGER NOT NULL DEFAULT 10,
    charisma     INTEGER NOT NULL DEFAULT 10,
    hp_max       INTEGER NOT NULL DEFAULT 10,
    hp_current   INTEGER NOT NULL DEFAULT 10,
    armor_class  INTEGER NOT NULL DEFAULT 10,
    speed        REAL    NOT NULL DEFAULT 9,  -- metros
    notes        TEXT,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- value_cp: valor de 1 unidad expresado en piezas de cobre. 0 = no convertible.
CREATE TABLE currencies (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    code     TEXT    NOT NULL UNIQUE,
    name     TEXT    NOT NULL,
    value_cp INTEGER NOT NULL DEFAULT 0 CHECK (value_cp >= 0)
);

CREATE TABLE character_currencies (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    currency_id  INTEGER NOT NULL REFERENCES currencies(id) ON DELETE CASCADE,
    amount       INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    PRIMARY KEY (character_id, currency_id)
);

-- Catálogo de objetos (plantillas) que gestiona el DM
CREATE TABLE items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    category   TEXT    NOT NULL DEFAULT 'Misceláneo',
    rarity     TEXT    NOT NULL DEFAULT 'Común',
    weight     REAL    NOT NULL DEFAULT 0,
    properties TEXT,
    description TEXT,
    attunement INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Objetos que posee cada personaje. visible = 0 -> solo lo ve el DM
CREATE TABLE inventory_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id      INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    equipped     INTEGER NOT NULL DEFAULT 0,
    visible      INTEGER NOT NULL DEFAULT 1
);

-- Bufos, maldiciones y estados
CREATE TABLE conditions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    kind         TEXT    NOT NULL CHECK (kind IN ('buff', 'curse', 'condition')),
    description  TEXT,
    duration     TEXT,
    visible      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shops (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    description    TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    allow_exchange INTEGER NOT NULL DEFAULT 1,  -- acepta pagar con otras divisas convertibles
    created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shop_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id     INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price       INTEGER NOT NULL CHECK (price >= 0),
    currency_id INTEGER NOT NULL REFERENCES currencies(id) ON DELETE CASCADE,
    stock       INTEGER CHECK (stock IS NULL OR stock >= 0)  -- NULL = ilimitado
);

-- Botín tras combate o recogible en un entorno
CREATE TABLE loot_pools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    kind        TEXT    NOT NULL DEFAULT 'combat' CHECK (kind IN ('combat', 'environment')),
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE loot_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id     INTEGER NOT NULL REFERENCES loot_pools(id) ON DELETE CASCADE,
    item_id     INTEGER REFERENCES items(id) ON DELETE CASCADE,
    currency_id INTEGER REFERENCES currencies(id) ON DELETE CASCADE,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    CHECK ((item_id IS NULL) <> (currency_id IS NULL))
);

CREATE TABLE trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    from_character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    to_character_id   INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled')),
    message           TEXT,
    created_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at       TEXT
);

-- direction: 'give' = lo entrega quien propone; 'take' = lo entrega el destinatario
CREATE TABLE trade_lines (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id          INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    direction         TEXT    NOT NULL CHECK (direction IN ('give', 'take')),
    inventory_item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
    currency_id       INTEGER REFERENCES currencies(id) ON DELETE SET NULL,
    quantity          INTEGER NOT NULL CHECK (quantity > 0),
    label             TEXT    NOT NULL
);

CREATE TABLE activity_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    message      TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
