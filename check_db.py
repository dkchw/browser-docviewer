
import sqlite3
from pathlib import Path

APP_DIR = Path.home() / ".docviewer"
DB_FILE = APP_DIR / "library.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    return conn

def check_parent_values():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, parent FROM items WHERE type = 'folder'")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}, Parent: {repr(row[2])}")

if __name__ == "__main__":
    check_parent_values()
