import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parents[1] / "data" / "kitchenops.db"),
)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category TEXT NOT NULL DEFAULT 'Autre',
    unit TEXT NOT NULL DEFAULT 'u',
    current_qty REAL NOT NULL DEFAULT 0,
    par_level REAL NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    qty_delta REAL NOT NULL,
    absolute_after REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('CARTE','PLAT_DU_JOUR','PERSONNEL')),
    portions_default INTEGER NOT NULL DEFAULT 10,
    approved INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty_per_portion REAL NOT NULL,
    FOREIGN KEY(recipe_id) REFERENCES recipes(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_type TEXT NOT NULL CHECK(scan_type IN ('ORDER_DOC','COLD_ROOM')),
    image_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ANALYZED',
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER,
    supplier TEXT,
    document_type TEXT NOT NULL DEFAULT 'BON_COMMANDE',
    reference TEXT,
    document_date TEXT,
    total REAL,
    received INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_order_id INTEGER NOT NULL,
    product_id INTEGER,
    raw_name TEXT NOT NULL,
    qty REAL NOT NULL DEFAULT 0,
    unit TEXT,
    unit_price REAL,
    confidence REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(purchase_order_id) REFERENCES purchase_orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);
"""

def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
