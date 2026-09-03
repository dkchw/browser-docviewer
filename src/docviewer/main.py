import sys
import json
import uuid
import argparse
import urllib.request
import zipfile
import subprocess
import webbrowser
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import mammoth
import markdown

# --- CONFIGURATION ---
APP_DIR = Path.home() / ".docviewer"
DB_FILE = APP_DIR / "library.db"
PDFJS_DIR = APP_DIR / "pdfjs"
UPLOAD_DIR = APP_DIR / "uploads"

SUPPORTED_EXTS = {".pdf", ".epub", ".docx", ".odt", ".odf", ".md", ".txt"}

app = FastAPI()

# In-memory dictionary for temporary "Quick Views"
TEMP_LIB = {}

class PathRequest(BaseModel):
    path: str
    parent: Optional[str] = None

class MoveRequest(BaseModel):
    doc_id: str
    target_folder: Optional[str] = None

# --- DATABASE LOGIC ---
def get_db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT,
                ext TEXT,
                type TEXT NOT NULL, -- 'file' or 'folder'
                parent TEXT,
                FOREIGN KEY (parent) REFERENCES items (id) ON DELETE CASCADE
            )
        """)
        # Ensure parents are NULL not empty string
        conn.execute("UPDATE items SET parent = NULL WHERE parent = ''")
        
        # Migration from JSON if exists
        LIB_FILE = APP_DIR / "library.json"
        if LIB_FILE.exists():
            try:
                lib_data = json.loads(LIB_FILE.read_text())
                for doc_id, doc in lib_data.items():
                    # Normalize empty string parents to NULL
                    p = doc.get("parent")
                    if not p: p = None
                    conn.execute(
                        "INSERT OR IGNORE INTO items (id, name, path, ext, type, parent) VALUES (?, ?, ?, ?, ?, ?)",
                        (doc_id, doc["name"], doc.get("path"), doc.get("ext"), doc.get("type", "file"), p)
                    )
                LIB_FILE.unlink()
            except:
                pass
        conn.commit()

def get_item(doc_id: str):
    if doc_id.startswith("tmp_"):
        return TEMP_LIB.get(doc_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None

# --- SETUP PDF.JS ---
def ensure_pdfjs():
    if PDFJS_DIR.exists():
        return
    print("[*] First run detected. Downloading PDF.js viewer...")
    PDFJS_DIR.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/mozilla/pdf.js/releases/download/v4.0.379/pdfjs-4.0.379-dist.zip"
    zip_path = APP_DIR / "pdfjs.zip"

    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(PDFJS_DIR)
    zip_path.unlink()
    print("[*] PDF.js installed successfully.")

# --- FASTAPI ROUTES ---
@app.get("/")
def index(folder: str = None, sort: str = "name_asc", view: str = "grid"):
    # Normalize empty string to None for SQLite NULL comparisons
    if folder == "": folder = None
    
    with get_db() as conn:
        if folder:
            parent_item = conn.execute("SELECT * FROM items WHERE id = ?", (folder,)).fetchone()
            if not parent_item or parent_item["type"] != "folder":
                folder = None
        
        items = conn.execute("SELECT * FROM items WHERE parent IS ?", (folder,)).fetchall()
        all_folders = conn.execute("SELECT id, name FROM items WHERE type = 'folder'").fetchall()
    
    # Sorting logic
    if sort == "name_desc":
        sorted_items = sorted(items, key=lambda x: (x["type"] != "folder", x["name"].lower()), reverse=True)
    elif sort == "type_asc":
        sorted_items = sorted(items, key=lambda x: (x["type"] != "folder", x["ext"] or "", x["name"].lower()))
    elif sort == "type_desc":
        sorted_items = sorted(items, key=lambda x: (x["type"] != "folder", x["ext"] or "", x["name"].lower()), reverse=True)
    else: # name_asc
        sorted_items = sorted(items, key=lambda x: (x["type"] != "folder", x["name"].lower()))

    breadcrumbs = []
    curr = folder
    with get_db() as conn:
        while curr:
            item = conn.execute("SELECT name, parent FROM items WHERE id = ?", (curr,)).fetchone()
            if item:
                breadcrumbs.append(f"<a href='/?folder={curr}&sort={sort}&view={view}'>{item['name']}</a>")
                curr = item['parent']
            else:
                curr = None
    breadcrumbs.append(f"<a href='/?sort={sort}&view={view}'>Library</a>")
    breadcrumbs.reverse()
    breadcrumb_html = " <span class='sep'>/</span> ".join(breadcrumbs)

    folder_options = "".join([f"<option value='{f['id']}'>{f['name']}</option>" for f in all_folders if f['id'] != folder])

    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DocViewer</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #f3f4f6;
                --sidebar-bg: rgba(255, 255, 255, 0.7);
                --text-main: #1f2937;
                --text-muted: #6b7280;
                --accent: #6366f1;
                --accent-hover: #4f46e5;
                --border: rgba(229, 231, 235, 0.5);
                --card-bg: rgba(255, 255, 255, 0.8);
                --card-hover: rgba(255, 255, 255, 1);
                --folder-icon: #f59e0b;
                --hover: rgba(243, 244, 246, 0.8);
                --link: #111827;
                --glass-border: 1px solid rgba(255, 255, 255, 0.3);
                --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            }}

            @media (prefers-color-scheme: dark) {{
                :root {{
                    --bg: #0f172a;
                    --sidebar-bg: rgba(30, 41, 59, 0.7);
                    --text-main: #f1f5f9;
                    --text-muted: #94a3b8;
                    --accent: #818cf8;
                    --accent-hover: #6366f1;
                    --border: rgba(51, 65, 85, 0.5);
                    --card-bg: rgba(30, 41, 59, 0.6);
                    --card-hover: rgba(30, 41, 59, 0.9);
                    --folder-icon: #fbbf24;
                    --hover: rgba(51, 65, 85, 0.8);
                    --link: #f8fafc;
                    --glass-border: 1px solid rgba(255, 255, 255, 0.05);
                    --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
                }}
            }}

            * {{ box-sizing: border-box; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                background-image: 
                    radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0, transparent 50%), 
                    radial-gradient(at 50% 0%, hsla(225,39%,30%,0.2) 0, transparent 50%), 
                    radial-gradient(at 100% 0%, hsla(339,49%,30%,0.2) 0, transparent 50%);
                color: var(--text-main);
                margin: 0;
                display: flex;
                height: 100vh;
                overflow: hidden;
            }}

            @media (prefers-color-scheme: light) {{
                body {{
                    background-image: 
                        radial-gradient(at 0% 0%, hsla(253,100%,96%,1) 0, transparent 50%), 
                        radial-gradient(at 50% 0%, hsla(225,100%,94%,0.8) 0, transparent 50%), 
                        radial-gradient(at 100% 0%, hsla(339,100%,94%,0.8) 0, transparent 50%);
                }}
            }}

            aside {{
                width: 320px;
                background-color: var(--sidebar-bg);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border-right: var(--glass-border);
                padding: 40px 28px;
                display: flex;
                flex-direction: column;
                gap: 36px;
                overflow-y: auto;
                box-shadow: 4px 0 24px rgba(0,0,0,0.02);
                z-index: 10;
            }}

            .logo-container {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}

            .logo-icon {{
                background: linear-gradient(135deg, var(--accent), var(--accent-hover));
                color: white;
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                font-weight: bold;
                font-size: 18px;
                box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            }}

            h1 {{
                font-size: 24px;
                font-weight: 700;
                margin: 0;
                letter-spacing: -0.03em;
                background: linear-gradient(to right, var(--text-main), var(--text-muted));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}

            .sidebar-section {{
                display: flex;
                flex-direction: column;
                gap: 14px;
            }}

            .section-label {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.15em;
                color: var(--text-muted);
                font-weight: 700;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .section-label::after {{
                content: "";
                flex: 1;
                height: 1px;
                background: var(--border);
            }}

            .input-group {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}

            input[type="text"], input[type="file"], select {{
                padding: 12px 14px;
                border-radius: 8px;
                border: 1px solid var(--border);
                background: var(--card-bg);
                color: var(--text-main);
                font-family: inherit;
                font-size: 14px;
                width: 100%;
                outline: none;
                transition: all 0.2s ease;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.01);
            }}

            input[type="text"]:focus, select:focus {{
                border-color: var(--accent);
                box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
            }}

            input[type="file"]::file-selector-button {{
                border: none;
                background: var(--accent);
                color: white;
                padding: 6px 12px;
                border-radius: 6px;
                cursor: pointer;
                margin-right: 12px;
                font-family: inherit;
                font-weight: 500;
                font-size: 13px;
                transition: background 0.2s;
            }}

            input[type="file"]::file-selector-button:hover {{
                background: var(--accent-hover);
            }}

            button {{
                padding: 12px 16px;
                border-radius: 8px;
                border: none;
                background: var(--accent);
                color: white;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                font-size: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                box-shadow: 0 4px 10px rgba(99, 102, 241, 0.25);
            }}

            button:hover {{ 
                transform: translateY(-2px);
                box-shadow: 0 6px 14px rgba(99, 102, 241, 0.35);
                background: var(--accent-hover);
            }}
            
            button:active {{
                transform: translateY(0);
            }}
            
            button.secondary {{ 
                background: var(--card-bg); 
                color: var(--text-main); 
                border: 1px solid var(--border); 
                box-shadow: var(--shadow);
            }}
            button.secondary:hover {{
                background: var(--hover);
                border-color: var(--text-muted);
            }}

            main {{
                flex: 1;
                padding: 40px 60px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 32px;
                position: relative;
            }}
            
            .header-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 20px;
                background: var(--sidebar-bg);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                padding: 16px 24px;
                border-radius: 16px;
                border: var(--glass-border);
                box-shadow: var(--shadow);
            }}

            .breadcrumbs {{
                font-size: 16px;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 10px;
            }}

            .breadcrumbs a {{
                color: var(--text-muted);
                text-decoration: none;
                transition: color 0.2s;
                padding: 4px 8px;
                border-radius: 6px;
            }}

            .breadcrumbs a:hover {{ 
                color: var(--text-main); 
                background: var(--hover);
            }}
            
            .breadcrumbs .sep {{ color: var(--border); font-weight: 300; }}
            .breadcrumbs a:last-child {{ 
                color: var(--accent); 
                pointer-events: none; 
                font-weight: 600;
                background: rgba(99, 102, 241, 0.1);
            }}

            .controls {{
                display: flex;
                align-items: center;
                gap: 16px;
            }}
            
            .control-group {{
                display: flex;
                align-items: center;
                gap: 8px;
                background: var(--card-bg);
                padding: 4px;
                border-radius: 10px;
                border: 1px solid var(--border);
            }}
            
            .control-btn {{
                background: transparent;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                color: var(--text-muted);
                box-shadow: none;
                font-size: 13px;
            }}
            
            .control-btn:hover {{
                transform: none;
                box-shadow: none;
                background: var(--hover);
                color: var(--text-main);
            }}
            
            .control-btn.active {{
                background: var(--bg);
                color: var(--accent);
                box-shadow: var(--shadow);
                font-weight: 600;
            }}

            .controls select {{
                padding: 8px 32px 8px 12px;
                height: auto;
                border-radius: 8px;
                background-color: transparent;
                border: none;
                font-weight: 500;
                cursor: pointer;
            }}

            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 24px;
            }}
            
            .list {{
                display: flex;
                flex-direction: column;
                gap: 12px;
            }}

            .item-card {{
                background: var(--card-bg);
                border: var(--glass-border);
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
                position: relative;
                box-shadow: var(--shadow);
                backdrop-filter: blur(8px);
            }}
            
            .list .item-card {{
                flex-direction: row;
                align-items: center;
                padding: 12px 20px;
                gap: 24px;
            }}

            .item-card:hover {{
                transform: translateY(-4px);
                box-shadow: 0 12px 24px -8px rgba(0,0,0,0.15);
                background: var(--card-hover);
                border-color: var(--accent);
            }}
            
            .list .item-card:hover {{
                transform: translateX(4px);
            }}

            .item-info {{
                display: flex;
                align-items: flex-start;
                gap: 16px;
                flex: 1;
            }}
            
            .list .item-info {{
                align-items: center;
            }}

            .item-icon {{
                font-size: 28px;
                line-height: 1;
                color: var(--folder-icon);
                background: rgba(245, 158, 11, 0.1);
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 12px;
                transition: transform 0.2s;
            }}
            
            .item-icon.file-icon {{
                color: var(--accent);
                background: rgba(99, 102, 241, 0.1);
            }}
            
            .item-card:hover .item-icon {{
                transform: scale(1.1);
            }}

            .item-details {{
                flex: 1;
                min-width: 0;
            }}

            .item-name {{
                font-size: 16px;
                font-weight: 600;
                color: var(--link);
                text-decoration: none;
                line-height: 1.4;
                display: block;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                transition: color 0.2s;
            }}

            .item-name:hover {{ 
                color: var(--accent);
            }}

            .item-meta {{
                font-size: 13px;
                color: var(--text-muted);
                display: flex;
                align-items: center;
                gap: 10px;
                margin-top: 6px;
            }}
            
            .list .item-meta {{
                margin-top: 0;
            }}

            .ext-pill {{
                background: rgba(99, 102, 241, 0.1);
                color: var(--accent);
                padding: 4px 8px;
                border-radius: 6px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                font-size: 11px;
                font-weight: 700;
            }}
            
            .folder-pill {{
                background: rgba(245, 158, 11, 0.1);
                color: var(--folder-icon);
            }}

            .item-actions {{
                display: flex;
                align-items: center;
                gap: 8px;
                margin-top: auto;
                border-top: 1px solid var(--border);
                padding-top: 16px;
            }}
            
            .list .item-actions {{
                margin-top: 0;
                border-top: none;
                padding-top: 0;
            }}

            .action-btn {{
                background: transparent;
                border: none;
                cursor: pointer;
                padding: 8px;
                border-radius: 8px;
                color: var(--text-muted);
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: none;
            }}

            .action-btn:hover {{ 
                background: var(--hover); 
                color: var(--accent); 
                transform: none;
                box-shadow: none;
            }}
            .action-btn.delete:hover {{ color: #ef4444; background: rgba(239, 68, 68, 0.1); }}

            .move-wrapper {{ flex: 1; }}
            .move-wrapper select {{
                font-size: 13px;
                padding: 8px 12px;
                height: auto;
                background: var(--bg);
            }}

            .empty-state {{
                text-align: center;
                padding: 120px 0;
                color: var(--text-muted);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 16px;
            }}
            
            .empty-icon {{
                font-size: 48px;
                opacity: 0.5;
            }}
            
            .empty-state h3 {{
                margin: 0;
                color: var(--text-main);
                font-size: 20px;
            }}

            ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
            ::-webkit-scrollbar-track {{ background: transparent; }}
            ::-webkit-scrollbar-thumb {{ background: rgba(156, 163, 175, 0.5); border-radius: 10px; border: 2px solid var(--bg); }}
            ::-webkit-scrollbar-thumb:hover {{ background: rgba(107, 114, 128, 0.8); }}

        </style>
        <script>
            const currentFolder = "{folder or ''}";
            const currentSort = "{sort}";
            const currentView = "{view}";
            
            function updateParams(params) {{
                const url = new URL(window.location.href);
                for (const [key, value] of Object.entries(params)) {{
                    if (value) url.searchParams.set(key, value);
                    else url.searchParams.delete(key);
                }}
                window.location.href = url.toString();
            }}

            async function uploadFile() {{
                const fileInput = document.getElementById('fileInput');
                if (!fileInput.files[0]) return;
                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                const url = currentFolder ? `/upload?folder=${{currentFolder}}` : '/upload';
                const response = await fetch(url, {{ method: "POST", body: formData }});
                if (response.ok) window.location.reload();
            }}

            async function importPath() {{
                const pathInput = document.getElementById('pathInput').value;
                if (!pathInput) return;
                const response = await fetch('/add-path', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ path: pathInput, parent: currentFolder || null }})
                }});
                if (response.ok) window.location.reload();
            }}

            async function createFolder() {{
                const name = prompt("Folder name:");
                if (!name) return;
                const response = await fetch('/create-folder', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ name: name, parent: currentFolder || null }})
                }});
                if (response.ok) window.location.reload();
            }}

            async function moveItem(docId, targetFolder) {{
                if (!targetFolder) return;
                const response = await fetch('/move-item', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ doc_id: docId, target_folder: targetFolder === 'root' ? null : targetFolder }})
                }});
                if (response.ok) window.location.reload();
                else {{
                    const result = await response.json();
                    alert(`Error: ${{result.detail}}`);
                }}
            }}

            async function deleteItem(docId, name, isFolder) {{
                const msg = isFolder ? `Delete folder "${{name}}" and all its contents?` : `Delete "${{name}}"?`;
                if (confirm(msg)) {{
                    const response = await fetch(`/delete/${{docId}}`, {{ method: "DELETE" }});
                    if (response.ok) window.location.reload();
                    else alert("Failed to delete item.");
                }}
            }}

            async function openExplorer(docId) {{
                await fetch(`/open-explorer/${{docId}}`, {{ method: "POST" }});
            }}

            async function quickView() {{
                const pathInput = document.getElementById('quickPathInput').value;
                if (!pathInput) return;
                const response = await fetch('/quick-view-path', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ path: pathInput }})
                }});
                const result = await response.json();
                if (response.ok) window.open(`/view/${{result.id}}`, '_blank');
            }}
        </script>
    </head>
    <body>
        <aside>
            <div class="logo-container">
                <div class="logo-icon">D</div>
                <h1>DocViewer</h1>
            </div>
            
            <div class="sidebar-section">
                <span class="section-label">Management</span>
                <button onclick="createFolder()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>
                    New Folder
                </button>
            </div>

            <div class="sidebar-section">
                <span class="section-label">Upload Local File</span>
                <div class="input-group">
                    <input type="file" id="fileInput" onchange="uploadFile()">
                </div>
            </div>

            <div class="sidebar-section">
                <span class="section-label">Link Directory or File</span>
                <div class="input-group">
                    <input type="text" id="pathInput" placeholder="Enter local path...">
                    <button class="secondary" onclick="importPath()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                        Link Path
                    </button>
                </div>
            </div>

            <div class="sidebar-section">
                <span class="section-label">Quick View</span>
                <div class="input-group">
                    <input type="text" id="quickPathInput" placeholder="No-save view path...">
                    <button class="secondary" onclick="quickView()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                        Open Temp View
                    </button>
                </div>
            </div>
        </aside>

        <main>
            <div class="header-bar">
                <div class="breadcrumbs">{breadcrumb_html}</div>
                
                <div class="controls">
                    <div class="control-group" style="padding: 0; background: transparent; border: none;">
                        <span style="font-size: 13px; color: var(--text-muted); font-weight: 500;">Sort:</span>
                        <select onchange="updateParams({{sort: this.value}})" style="background: var(--card-bg); border: 1px solid var(--border);">
                            <option value="name_asc" { 'selected' if sort == 'name_asc' else '' }>Name (A-Z)</option>
                            <option value="name_desc" { 'selected' if sort == 'name_desc' else '' }>Name (Z-A)</option>
                            <option value="type_asc" { 'selected' if sort == 'type_asc' else '' }>Type (A-Z)</option>
                            <option value="type_desc" { 'selected' if sort == 'type_desc' else '' }>Type (Z-A)</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <button class="control-btn { 'active' if view == 'grid' else '' }" onclick="updateParams({{view: 'grid'}})" title="Grid View">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                        </button>
                        <button class="control-btn { 'active' if view == 'list' else '' }" onclick="updateParams({{view: 'list'}})" title="List View">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                        </button>
                    </div>
                </div>
            </div>
            
            <div class="{view}">
    '''

    if not sorted_items:
        html += '''
            </div>
            <div class="empty-state">
                <div class="empty-icon">📂</div>
                <h3>This folder is empty</h3>
                <p>Upload a file or create a new folder to get started.</p>
            </div>
        '''
    else:
        for doc in sorted_items:
            doc_id = doc["id"]
            is_folder = doc["type"] == "folder"
            
            if is_folder:
                icon_html = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>'
                icon_class = ""
                meta_html = "<span class='ext-pill folder-pill'>Folder</span>"
            else:
                icon_html = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
                icon_class = "file-icon"
                ext_name = doc['ext'].replace('.','') if doc['ext'] else 'FILE'
                meta_html = f"<span class='ext-pill'>{ext_name}</span>"
                
            link = f"/?folder={doc_id}&sort={sort}&view={view}" if is_folder else f"/view/{doc_id}"
            target = "" if is_folder else "target='_blank'"
            
            explorer_btn = f'''<button class="action-btn" onclick="openExplorer('{doc_id}')" title="Show in File Explorer">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
            </button>''' if doc["path"] else ""
            
            move_options = f"<option value=''>Move to...</option><option value='root'>Library Root</option>{folder_options}"
            move_dropdown = f"<select onchange='moveItem(\"{doc_id}\", this.value)'>{move_options}</select>"

            # Escape single quotes for JS
            safe_name = doc['name'].replace("'", "\\'")
            
            html += f'''
                <div class="item-card">
                    <div class="item-info">
                        <div class="item-icon {icon_class}">{icon_html}</div>
                        <div class="item-details">
                            <a href="{link}" {target} class="item-name" title="{doc['name']}">{doc['name']}</a>
                            <div class="item-meta">{meta_html}</div>
                        </div>
                    </div>
                    <div class="item-actions">
                        <div class="move-wrapper">
                            {move_dropdown}
                        </div>
                        {explorer_btn}
                        <button class="action-btn delete" onclick="deleteItem('{doc_id}', '{safe_name}', {str(is_folder).lower()})" title="Delete">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </div>
                </div>
            '''
        html += "</div>"

    html += '''
        </main>
    </body>
    </html>
    '''
    return HTMLResponse(html)

def upload_file(file: UploadFile = File(...), folder: str = None):
    # Normalize empty string to None
    if not folder: folder = None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return HTMLResponse("Unsupported file format.", status_code=400)
    doc_id = str(uuid.uuid4())[:8]
    file_path = UPLOAD_DIR / f"{doc_id}{ext}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO items (id, name, path, ext, type, parent) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, file.filename, str(file_path), ext, "file", folder)
        )
        conn.commit()
    return {"status": "success", "id": doc_id}

@app.post("/add-path")
def add_by_path(req: PathRequest):
    p = Path(req.path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    
    # Normalize parent ID
    parent_id = req.parent if req.parent else None
    
    added = 0
    with get_db() as conn:
        def add_item(path, pid=None):
            nonlocal added
            doc_id = str(uuid.uuid4())[:8]
            if path.is_file():
                ext = path.suffix.lower()
                if ext in SUPPORTED_EXTS:
                    conn.execute(
                        "INSERT INTO items (id, name, path, ext, type, parent) VALUES (?, ?, ?, ?, ?, ?)",
                        (doc_id, path.name, str(path), ext, "file", pid)
                    )
                    added += 1
                    return doc_id
            elif path.is_dir():
                conn.execute(
                    "INSERT INTO items (id, name, path, type, parent) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, path.name, str(path), "folder", pid)
                )
                added += 1
                try:
                    for item in sorted(path.iterdir()):
                        add_item(item, doc_id)
                except PermissionError:
                    pass
                return doc_id
            return None

        add_item(p, parent_id)
        conn.commit()
    return {"status": "success", "added": added}

@app.post("/move-item")
def move_item(req: MoveRequest):
    # Normalize target folder ID
    target = req.target_folder if req.target_folder else None
    with get_db() as conn:
        if target:
            if target == req.doc_id:
                raise HTTPException(status_code=400, detail="Cannot move folder into itself.")
            
            curr = target
            while curr:
                row = conn.execute("SELECT parent FROM items WHERE id = ?", (curr,)).fetchone()
                if not row: break
                if row["parent"] == req.doc_id:
                     raise HTTPException(status_code=400, detail="Cannot move folder into its own subfolder.")
                curr = row["parent"]

        conn.execute("UPDATE items SET parent = ? WHERE id = ?", (target, req.doc_id))
        conn.commit()
    return {"status": "success"}

@app.post("/create-folder")
def create_folder(req: dict):
    name = req.get("name", "New Folder")
    # Normalize parent ID
    parent = req.get("parent") if req.get("parent") else None
    doc_id = str(uuid.uuid4())[:8]
    with get_db() as conn:
        conn.execute(
            "INSERT INTO items (id, name, type, parent) VALUES (?, ?, ?, ?)",
            (doc_id, name, "folder", parent)
        )
        conn.commit()
    return {"status": "success", "id": doc_id}

@app.post("/quick-view-path")
def quick_view_path(req: PathRequest):
    p = Path(req.path).expanduser().resolve()
    if not p.is_file():
        raise HTTPException(status_code=400, detail="File does not exist.")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    doc_id = "tmp_" + str(uuid.uuid4())[:8]
    TEMP_LIB[doc_id] = {"name": p.name + " (Temp View)", "path": str(p), "ext": ext, "type": "file"}
    return {"status": "success", "id": doc_id}

@app.delete("/delete/{doc_id}")
def delete_doc(doc_id: str):
    item = get_item(doc_id)
    if not item:
        return HTMLResponse("Item not found.", status_code=404)
    
    with get_db() as conn:
        to_delete = [doc_id]
        def find_children(pid):
            children = conn.execute("SELECT id, type FROM items WHERE parent = ?", (pid,)).fetchall()
            for child in children:
                to_delete.append(child["id"])
                if child["type"] == "folder":
                    find_children(child["id"])
        
        if item["type"] == "folder":
            find_children(doc_id)
        
        for d_id in to_delete:
            d_item = conn.execute("SELECT path FROM items WHERE id = ?", (d_id,)).fetchone()
            if d_item and d_item["path"]:
                doc_path = Path(d_item["path"])
                if UPLOAD_DIR in doc_path.parents and doc_path.exists():
                    doc_path.unlink()
            conn.execute("DELETE FROM items WHERE id = ?", (d_id,))
        conn.commit()
    
    return {"status": "success"}

@app.post("/open-explorer/{doc_id}")
def open_explorer(doc_id: str):
    doc = get_item(doc_id)
    if not doc or not doc.get("path"):
        raise HTTPException(status_code=404, detail="Path not found for this item.")
    
    p = Path(doc["path"]).resolve()
    if not p.exists():
         raise HTTPException(status_code=404, detail="Item no longer exists on disk.")
    
    if sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(p)])
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(p)])
    else:
        try:
            subprocess.run(["xdg-open", str(p.parent if p.is_file() else p)])
        except:
            pass
    return {"status": "success"}

@app.get("/view/{doc_id}")
def view_doc(doc_id: str):
    doc = get_item(doc_id)
    if not doc:
        return HTMLResponse("Document not found or temporary session expired.", status_code=404)

    ext = doc["ext"]
    file_path = doc["path"]

    viewer_css = """
    :root { --bg: #ffffff; --txt: #111827; --code-bg: #f4f4f4; --border: #ddd; }
    @media (prefers-color-scheme: dark) { :root { --bg: #111827; --txt: #e2e8f0; --code-bg: #1e293b; --border: #334155; } }
    body { font-family: serif; line-height: 1.6; max-width: 800px; margin: 2rem auto; padding: 0 1rem; font-size: 18px; background-color: var(--bg); color: var(--txt); }
    pre, code { background: var(--code-bg); border-radius: 4px; }
    pre { padding: 12px; overflow-x: auto; }
    code { padding: 2px 4px; font-size: 0.9em; font-family: monospace; }
    blockquote { border-left: 4px solid var(--border); margin: 0; padding-left: 16px; color: #888; }
    table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid var(--border); padding: 8px; text-align: left; }
    """

    if ext == ".pdf":
        return RedirectResponse(url=f"/pdfjs/web/viewer.html?file=/file/{doc_id}")

    elif ext == ".epub":
        html = f"""<!DOCTYPE html>
        <html><head><title>{doc['name']}</title>
          <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.5/jszip.min.js"></script>
          <script src="https://cdn.jsdelivr.net/npm/epubjs/dist/epub.min.js"></script>
          <style>
            :root {{ --bg: #ffffff; }} @media (prefers-color-scheme: dark) {{ :root {{ --bg: #111827; }} }}
            body, html {{ margin: 0; padding: 0; height: 100%; background-color: var(--bg); }}
            #viewer {{ width: 100vw; height: 100vh; }}
          </style>
        </head><body><div id="viewer"></div><script>
            var isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            var book = ePub("/file/{doc_id}");
            var rendition = book.renderTo("viewer", {{ width: "100%", height: "100%", flow: "scrolled-doc" }});
            rendition.themes.default({{ body: {{ background: isDark ? '#111827' : '#ffffff', color: isDark ? '#e2e8f0' : '#111827' }} }});
            rendition.display();
          </script></body></html>"""
        return HTMLResponse(html)

    elif ext == ".docx":
        with open(file_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
        return HTMLResponse(f"<!DOCTYPE html><html><head><title>{doc['name']}</title><style>{viewer_css}</style></head><body>{result.value}</body></html>")

    elif ext in [".odt", ".odf"]:
        try:
            result = subprocess.run(["pandoc", file_path, "-t", "html"], capture_output=True, text=True, check=True)
            return HTMLResponse(f"<!DOCTYPE html><html><head><title>{doc['name']}</title><style>{viewer_css}</style></head><body>{result.stdout}</body></html>")
        except Exception:
            return HTMLResponse("<b>Error:</b> Requires 'pandoc' installed on system.", status_code=500)

    elif ext == ".txt":
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return HTMLResponse(f"<!DOCTYPE html><html><head><title>{doc['name']}</title><style>{viewer_css} body {{ font-family: system-ui, sans-serif; white-space: pre-wrap; }}</style></head><body>{content}</body></html>")

    elif ext == ".md":
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        html_content = markdown.markdown(content, extensions=['fenced_code', 'tables'])
        return HTMLResponse(f"<!DOCTYPE html><html><head><title>{doc['name']}</title><style>{viewer_css} body {{ font-family: system-ui, sans-serif; }}</style></head><body>{html_content}</body></html>")

    return HTMLResponse("Unsupported file format.", status_code=400)

@app.get("/file/{doc_id}")
def get_file(doc_id: str):
    doc = get_item(doc_id)
    if doc and doc.get("path"):
        return FileResponse(doc["path"])
    return HTMLResponse("File missing", status_code=404)

# --- CLI LOGIC ---
def cli():
    parser = argparse.ArgumentParser(description="DocViewer: Read documents natively.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a file or scan an entire folder")
    add_parser.add_argument("path", type=str, help="Path to the file or directory")

    serve_parser = subparsers.add_parser("serve", help="Start the server")
    serve_parser.add_argument("--port", type=int, default=2005, help="Port to run on")

    open_parser = subparsers.add_parser("open", help="Quick view a file without adding it to the library")
    open_parser.add_argument("path", type=str, help="Path to the file to open temporarily")
    open_parser.add_argument("--port", type=int, default=2005, help="Port to run on")

    args = parser.parse_args()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    if args.command == "add":
        p = Path(args.path).resolve()
        if not p.exists():
            print(f"[-] Error: Path '{p}' does not exist.")
            sys.exit(1)

        added = 0
        with get_db() as conn:
            def add_item(path, parent_id=None):
                nonlocal added
                doc_id = str(uuid.uuid4())[:8]
                if path.is_file():
                    ext = path.suffix.lower()
                    if ext in SUPPORTED_EXTS:
                        conn.execute(
                            "INSERT INTO items (id, name, path, ext, type, parent) VALUES (?, ?, ?, ?, ?, ?)",
                            (doc_id, path.name, str(path), ext, "file", parent_id)
                        )
                        added += 1
                        print(f"  -> Added file: {path.name}")
                        return doc_id
                elif path.is_dir():
                    conn.execute(
                        "INSERT INTO items (id, name, path, type, parent) VALUES (?, ?, ?, ?, ?)",
                        (doc_id, path.name, str(path), "folder", parent_id)
                    )
                    added += 1
                    print(f"  -> Added folder: {path.name}")
                    try:
                        for item in sorted(path.iterdir()):
                            add_item(item, doc_id)
                    except PermissionError:
                        pass
                    return doc_id
                return None

            add_item(p)
            conn.commit()
        print(f"[+] Successfully added {added} item(s) to your library!")

    elif args.command == "serve":
        ensure_pdfjs()
        app.mount("/pdfjs", StaticFiles(directory=str(PDFJS_DIR)), name="pdfjs")
        print(f"[*] Starting WebReader on http://localhost:{args.port}")
        webbrowser.open(f"http://localhost:{args.port}")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")

    elif args.command == "open":
        p = Path(args.path).expanduser().resolve()
        if not p.is_file():
            print(f"[-] Error: File '{p}' does not exist.")
            sys.exit(1)

        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            print(f"[-] Unsupported format: {p.suffix}")
            sys.exit(1)

        # Load it into the temporary library
        doc_id = "tmp_" + str(uuid.uuid4())[:8]
        TEMP_LIB[doc_id] = {"name": p.name + " (Temp View)", "path": str(p), "ext": ext, "type": "file"}

        ensure_pdfjs()
        app.mount("/pdfjs", StaticFiles(directory=str(PDFJS_DIR)), name="pdfjs")
        url = f"http://localhost:{args.port}/view/{doc_id}"

        print(f"[*] Opening '{p.name}' in Quick View Mode...")
        print(f"[*] Close the server (Ctrl+C) when finished reading.")
        webbrowser.open(url)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
