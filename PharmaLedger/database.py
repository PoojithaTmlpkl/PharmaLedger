import sqlite3

def get_db():
    conn = sqlite3.connect("pharmaledger.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS drugs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_uid TEXT UNIQUE,
        drug_name TEXT,
        batch_no TEXT,
        quantity INTEGER,
        status TEXT,
        owner_role TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS ledger(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_uid TEXT,
        event TEXT,
        location TEXT,
        prev_hash TEXT,
        curr_hash TEXT,
        timestamp TEXT
    )""")

    db.commit()
    db.close()
