import sqlite3

DB_NAME = "wallpaper.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        added_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interval INTEGER,
        order_type TEXT,
        autostart INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id INTEGER,
        changed_at TEXT
    )
    """)

    conn.commit()
    conn.close()