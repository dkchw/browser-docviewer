
import sqlite3
from pathlib import Path
import os
import sys

# Add src to path so we can import docviewer
sys.path.append(os.path.join(os.getcwd(), "src"))
from docviewer.main import init_db

APP_DIR = Path.home() / ".docviewer"
DB_FILE = APP_DIR / "library.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def check_folders():
    if not DB_FILE.exists():
        print("Database does not exist.")
        return

    init_db() # This should run the migration

    with get_db() as conn:
        items = conn.execute("SELECT * FROM items").fetchall()
        print(f"Total items in DB: {len(items)}")
        for item in items:
            print(f"ID: {item['id']}, Name: {item['name']}, Type: {item['type']}, Parent: {repr(item['parent'])}")

if __name__ == "__main__":
    check_folders()
