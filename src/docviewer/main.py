import sys
import re
import json
import uuid
import argparse
import urllib.request
import urllib.parse
import html as pyhtml
import zipfile
import xml.etree.ElementTree as ET
import subprocess
import webbrowser
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

import mimetypes
mimetypes.add_type("application/javascript", ".mjs")

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import mammoth
import markdown

try:
    from docviewer.reader import render_epub_viewer, render_html_document_viewer
except ImportError:
    try:
        from .reader import render_epub_viewer, render_html_document_viewer
    except ImportError:
        from reader import render_epub_viewer, render_html_document_viewer

# --- CONFIGURATION ---
APP_DIR = Path.home() / ".docviewer"
DB_FILE = APP_DIR / "library.db"
PDFJS_DIR = APP_DIR / "pdfjs-6.2.108-legacy"
UPLOAD_DIR = APP_DIR / "uploads"

SUPPORTED_EXTS = {".pdf", ".epub", ".docx", ".odt", ".odf", ".md", ".txt"}

app = FastAPI()

# In-memory dictionary for temporary "Quick Views"
TEMP_LIB = {}

class PathRequest(BaseModel):
    path: str
    parent: Optional[str] = None
    profile: str = "default"

class MoveRequest(BaseModel):
    doc_id: str
    target_folder: Optional[str] = None

class RenameRequest(BaseModel):
    name: str

# --- DATABASE LOGIC ---
def get_db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT,
                ext TEXT,
                type TEXT NOT NULL, -- 'file' or 'folder'
                parent TEXT,
                created_at INTEGER DEFAULT (cast(strftime('%s','now') as int)),
                last_opened INTEGER DEFAULT 0,
                is_starred INTEGER DEFAULT 0,
                is_pinned INTEGER DEFAULT 0,
                cover_path TEXT,
                FOREIGN KEY (parent) REFERENCES items (id) ON DELETE CASCADE
            )
        ''')
        conn.execute("UPDATE items SET parent = NULL WHERE parent = ''")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                rank INTEGER DEFAULT 0
            )
        ''')
        conn.execute("INSERT OR IGNORE INTO profiles (id, name, rank) VALUES ('default', 'Default Profile', 0)")
        
        for col, col_def in [
            ("created_at", "INTEGER DEFAULT (cast(strftime('%s','now') as int))"),
            ("last_opened", "INTEGER DEFAULT 0"),
            ("is_starred", "INTEGER DEFAULT 0"),
            ("is_pinned", "INTEGER DEFAULT 0"),
            ("cover_path", "TEXT"),
            ("profile_id", "TEXT DEFAULT 'default'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE items ADD COLUMN {col} {col_def}")
            except Exception:
                pass
        
        LIB_FILE = APP_DIR / "library.json"
        if LIB_FILE.exists():
            try:
                import json
                lib_data = json.loads(LIB_FILE.read_text())
                for doc_id, doc in lib_data.items():
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
def patch_pdfjs_invert_mode(pdfjs_dir: Path):
    web_dir = pdfjs_dir / "web"
    if not web_dir.exists():
        return

    invert_css_path = web_dir / "invert.css"
    invert_css_content = """/* PDF.js Color Inversion / Night Mode */
#pdf-invert-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: rgba(17, 24, 39, 0.94);
    color: #f1f5f9;
    padding: 8px 18px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.18);
    z-index: 10000;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease, transform 0.2s ease;
    backdrop-filter: blur(8px);
}

#pdf-invert-toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
}

/* Invert Button Active Glow */
#pdfInvertButton.active, #secondaryPdfInvert.active {
    background-color: var(--button-hover-color, rgba(255, 255, 255, 0.18)) !important;
    color: #38bdf8 !important;
}

#pdfInvertButton.active svg {
    color: #38bdf8 !important;
}

/* Dark Invert Mode: White pages become Black, Black text becomes White */
html[data-pdf-color-mode="dark-invert"] {
    color-scheme: dark !important;
}

html[data-pdf-color-mode="dark-invert"] #viewerContainer {
    background-color: #0b0f19 !important;
}

html[data-pdf-color-mode="dark-invert"] #viewer.pdfViewer .page,
html[data-pdf-color-mode="dark-invert"] #thumbnailView .thumbnail {
    background-color: #121826 !important;
    border-color: #1f2937 !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6) !important;
}

html[data-pdf-color-mode="dark-invert"] #viewer.pdfViewer .page canvas,
html[data-pdf-color-mode="dark-invert"] #thumbnailView .thumbnailImage {
    filter: invert(1) hue-rotate(180deg) contrast(0.96) brightness(0.96) !important;
    background-color: #121826 !important;
}

html[data-pdf-color-mode="dark-invert"] #viewer.pdfViewer .page .textLayer ::selection {
    background: rgba(56, 189, 248, 0.4) !important;
}

/* Sepia Warm Mode: Reduces eye fatigue and blue light */
html[data-pdf-color-mode="sepia"] #viewerContainer {
    background-color: #e8dcbe !important;
}

html[data-pdf-color-mode="sepia"] #viewer.pdfViewer .page,
html[data-pdf-color-mode="sepia"] #thumbnailView .thumbnail {
    background-color: #fbf0d9 !important;
    border-color: #dfd3ba !important;
    box-shadow: 0 4px 16px rgba(61, 46, 30, 0.15) !important;
}

/* Dark Scrollbars for Night Mode */
html[data-pdf-color-mode="dark-invert"] * {
    scrollbar-width: thin;
    scrollbar-color: #334155 #0b0f19;
}
html[data-pdf-color-mode="dark-invert"] ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
    background-color: #0b0f19;
}
html[data-pdf-color-mode="dark-invert"] ::-webkit-scrollbar-track {
    background: #0b0f19;
}
html[data-pdf-color-mode="dark-invert"] ::-webkit-scrollbar-thumb {
    background-color: #334155;
    border-radius: 4px;
}
html[data-pdf-color-mode="dark-invert"] ::-webkit-scrollbar-thumb:hover {
    background-color: #475569;
}

@media (prefers-color-scheme: dark) {
    * {
        scrollbar-width: thin;
        scrollbar-color: #334155 #1e293b;
    }
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
        background-color: #1e293b;
    }
    ::-webkit-scrollbar-track {
        background: #1e293b;
    }
    ::-webkit-scrollbar-thumb {
        background-color: #334155;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background-color: #475569;
    }
}
"""
    invert_css_path.write_text(invert_css_content, encoding="utf-8")

    invert_mjs_path = web_dir / "invert.mjs"
    invert_mjs_content = """// PDF.js Color Inversion / Night Mode Controller
(function() {
    const MODES = ['normal', 'dark-invert', 'sepia'];
    const LABELS = {
        'normal': '☀️ Normal Colors',
        'dark-invert': '🌙 Inverted Night Mode (White text on black)',
        'sepia': '📜 Sepia Warm Mode'
    };

    let currentMode = localStorage.getItem('docviewer_pdf_color_mode') || 'normal';

    function showToast(msg) {
        let toast = document.getElementById('pdf-invert-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'pdf-invert-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('show');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => {
            toast.classList.remove('show');
        }, 1500);
    }

    function applyMode(mode, notify = false) {
        currentMode = mode;
        localStorage.setItem('docviewer_pdf_color_mode', mode);
        document.documentElement.setAttribute('data-pdf-color-mode', mode);

        const btn = document.getElementById('pdfInvertButton');
        const secBtn = document.getElementById('secondaryPdfInvert');
        const isActive = (mode !== 'normal');

        if (btn) {
            btn.classList.toggle('active', isActive);
            btn.title = `Color Mode: ${LABELS[mode]} (Alt+I / i to toggle)`;
        }
        if (secBtn) {
            secBtn.classList.toggle('active', isActive);
        }

        if (notify) {
            showToast(LABELS[mode]);
        }
    }

    function cycleMode() {
        const nextIdx = (MODES.indexOf(currentMode) + 1) % MODES.length;
        applyMode(MODES[nextIdx], true);
    }

    // Keyboard shortcut: Alt+I or i
    window.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }
        if ((e.altKey && e.key.toLowerCase() === 'i') || (e.key === 'i' && !e.ctrlKey && !e.metaKey && !e.altKey)) {
            e.preventDefault();
            cycleMode();
        }
    });

    function initButtons() {
        applyMode(currentMode, false);

        const btn = document.getElementById('pdfInvertButton');
        if (btn && !btn._boundInvert) {
            btn._boundInvert = true;
            btn.addEventListener('click', cycleMode);
        }

        const secBtn = document.getElementById('secondaryPdfInvert');
        if (secBtn && !secBtn._boundInvert) {
            secBtn._boundInvert = true;
            secBtn.addEventListener('click', cycleMode);
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', initButtons);
    } else {
        initButtons();
    }
})();
"""
    invert_mjs_path.write_text(invert_mjs_content, encoding="utf-8")

    # Patch viewer.html
    viewer_html_path = web_dir / "viewer.html"
    if viewer_html_path.exists():
        html = viewer_html_path.read_text(encoding="utf-8")
        modified = False

        if "invert.css" not in html:
            html = html.replace('</head>', '    <link rel="stylesheet" href="invert.css" />\n  </head>')
            modified = True

        if "invert.mjs" not in html:
            html = html.replace('</head>', '    <script src="invert.mjs" type="module"></script>\n  </head>')
            modified = True

        if 'id="pdfInvertButton"' not in html:
            button_html = '''
                <button
                  id="pdfInvertButton"
                  class="toolbarButton"
                  type="button"
                  tabindex="0"
                  title="Reverse Colors / Night Mode (Alt+I / i)"
                  aria-label="Reverse Colors / Night Mode"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-top:2px;">
                    <circle cx="12" cy="12" r="9"></circle>
                    <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"></path>
                  </svg>
                  <span class="visuallyHidden">Reverse Colors</span>
                </button>
'''
            if '<div id="secondaryToolbarToggle"' in html:
                html = html.replace('<div id="secondaryToolbarToggle"', button_html + '                <div id="secondaryToolbarToggle"')
                modified = True

        if 'id="secondaryPdfInvert"' not in html:
            sec_button_html = '''
                      <button id="secondaryPdfInvert" class="toolbarButton labeled" type="button" tabindex="0">
                        <span class="toolbarButtonIcon" style="display:inline-flex;align-items:center;justify-content:center;">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="9"></circle>
                            <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"></path>
                          </svg>
                        </span>
                        <span>Reverse Colors / Night Mode</span>
                      </button>
'''
            if '<div class="horizontalToolbarSeparator"></div>' in html:
                html = html.replace('<div class="horizontalToolbarSeparator"></div>', sec_button_html + '                      <div class="horizontalToolbarSeparator"></div>', 1)
                modified = True

        if modified:
            viewer_html_path.write_text(html, encoding="utf-8")

def ensure_pdfjs():
    if PDFJS_DIR.exists():
        patch_pdfjs_invert_mode(PDFJS_DIR)
        return
    print("[*] First run detected. Downloading PDF.js viewer...")
    PDFJS_DIR.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/mozilla/pdf.js/releases/download/v6.2.108/pdfjs-6.2.108-legacy-dist.zip"
    zip_path = APP_DIR / "pdfjs.zip"

    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(PDFJS_DIR)
    zip_path.unlink()
    patch_pdfjs_invert_mode(PDFJS_DIR)
    print("[*] PDF.js installed successfully.")

# --- SEARCH HELPERS ---
def get_descendant_folder_ids(conn, root_folder_id, profile_id):
    descendants = {root_folder_id}
    queue = [root_folder_id]
    while queue:
        curr = queue.pop(0)
        children = conn.execute(
            "SELECT id FROM items WHERE parent = ? AND type = 'folder' AND profile_id = ?",
            (curr, profile_id)
        ).fetchall()
        for ch in children:
            cid = ch["id"]
            if cid not in descendants:
                descendants.add(cid)
                queue.append(cid)
    return descendants

def get_folder_path_map(conn, profile_id):
    folders = conn.execute("SELECT id, name, parent FROM items WHERE type = 'folder' AND profile_id = ?", (profile_id,)).fetchall()
    f_dict = {f["id"]: {"name": f["name"], "parent": f["parent"]} for f in folders}
    path_map = {}
    for fid in f_dict:
        parts = []
        curr = fid
        visited = set()
        while curr and curr in f_dict and curr not in visited:
            visited.add(curr)
            parts.append(f_dict[curr]["name"])
            curr = f_dict[curr]["parent"]
        parts.reverse()
        path_map[fid] = " / ".join(parts)
    return path_map

def extract_match_snippets(text: str, query: str, max_snippets: int = 4, context_len: int = 60):
    snippets = []
    q_lower = query.lower()
    text_lower = text.lower()
    start_pos = 0
    total_count = 0
    while True:
        idx = text_lower.find(q_lower, start_pos)
        if idx == -1:
            break
        total_count += 1
        if len(snippets) < max_snippets:
            c_start = max(0, idx - context_len)
            c_end = min(len(text), idx + len(query) + context_len)
            prefix = "..." if c_start > 0 else ""
            suffix = "..." if c_end < len(text) else ""
            before = text[c_start:idx].replace("\r", " ").replace("\n", " ")
            matched = text[idx:idx + len(query)]
            after = text[idx + len(query):c_end].replace("\r", " ").replace("\n", " ")
            safe_before = pyhtml.escape(before)
            safe_matched = pyhtml.escape(matched)
            safe_after = pyhtml.escape(after)
            snippet_html = f"{prefix}{safe_before}<mark class=\"search-hit\">{safe_matched}</mark>{safe_after}{suffix}"
            snippets.append(snippet_html)
        start_pos = idx + len(query)
    return total_count, snippets

def search_file_content(file_path: Path, ext: str, query: str, max_snippets: int = 4):
    if not file_path.exists():
        return 0, []
    total_matches = 0
    results = []
    try:
        if ext in [".pdf", ".epub"]:
            import pymupdf
            try:
                pymupdf.TOOLS.mupdf_display_errors(False)
                pymupdf.TOOLS.mupdf_display_warnings(False)
            except Exception:
                pass
            doc = pymupdf.open(file_path)
            q_lower = query.lower()
            loc_name = "Page" if ext == ".pdf" else "Section"
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_text = page.get_text()
                if q_lower in page_text.lower():
                    cnt, snips = extract_match_snippets(page_text, query, max_snippets=2)
                    total_matches += cnt
                    for s in snips:
                        if len(results) < max_snippets:
                            results.append({
                                "location": f"{loc_name} {page_idx + 1}",
                                "page": page_idx + 1,
                                "match_idx": len(results),
                                "snippet": s
                            })
        elif ext == ".docx":
            import mammoth
            with open(file_path, "rb") as docx_file:
                raw_text = mammoth.extract_raw_text(docx_file).value
            cnt, snips = extract_match_snippets(raw_text, query, max_snippets=max_snippets)
            total_matches = cnt
            for i, s in enumerate(snips):
                results.append({"location": f"Match {i + 1}", "page": None, "match_idx": i, "snippet": s})
        elif ext in [".odt", ".odf"]:
            with zipfile.ZipFile(file_path, "r") as zf:
                if "content.xml" in zf.namelist():
                    content_xml = zf.read("content.xml")
                    root = ET.fromstring(content_xml)
                    raw_text = " ".join(root.itertext())
                    cnt, snips = extract_match_snippets(raw_text, query, max_snippets=max_snippets)
                    total_matches = cnt
                    for i, s in enumerate(snips):
                        results.append({"location": f"Match {i + 1}", "page": None, "match_idx": i, "snippet": s})
        elif ext in [".txt", ".md"]:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            for l_idx, line in enumerate(lines):
                if query.lower() in line.lower():
                    cnt, snips = extract_match_snippets(line, query, max_snippets=1)
                    total_matches += cnt
                    for s in snips:
                        if len(results) < max_snippets:
                            results.append({"location": f"Line {l_idx + 1}", "page": None, "match_idx": len(results), "snippet": s})
    except Exception as e:
        print(f"Error searching inside {file_path}: {e}")
    return total_matches, results

# --- FASTAPI ROUTES ---
@app.get("/")
def index(request: Request, profile: str = None, folder: str = None, sort: str = "name_asc", view: str = "grid", q: str = None, search_mode: str = "name", recursive: int = 1):
    # Normalize empty string to None for SQLite NULL comparisons
    if folder == "": folder = None
    if not profile: 
        profile = request.cookies.get("active_profile") or request.cookies.get("default_profile", "default")
    q = q.strip() if q else None
    if search_mode not in ("name", "content"):
        search_mode = "name"
    try:
        recursive = int(recursive)
    except:
        recursive = 1
    
    with get_db() as conn:
        profiles_db = conn.execute("SELECT * FROM profiles ORDER BY rank ASC, name ASC").fetchall()
        valid_profile_ids = [p['id'] for p in profiles_db]
        if profile not in valid_profile_ids:
            profile = "default" if "default" in valid_profile_ids else (valid_profile_ids[0] if valid_profile_ids else "default")
        
        if folder:
            parent_item = conn.execute("SELECT * FROM items WHERE id = ? AND profile_id = ?", (folder, profile)).fetchone()
            if not parent_item or parent_item["type"] != "folder":
                folder = None

        all_folders = conn.execute("SELECT id, name FROM items WHERE type = 'folder' AND profile_id = ?", (profile,)).fetchall()
        folder_path_map = get_folder_path_map(conn, profile)

        content_results = []
        total_content_hits = 0

        # Scope definition
        if folder:
            descendants = get_descendant_folder_ids(conn, folder, profile) if recursive else {folder}
            parent_filter_clause = f"parent IN ({','.join('?' for _ in descendants)})"
            parent_filter_params = list(descendants)
        else:
            if recursive:
                parent_filter_clause = "1=1"
                parent_filter_params = []
            else:
                parent_filter_clause = "parent IS NULL"
                parent_filter_params = []

        if q and search_mode == "content":
            sql = f"SELECT * FROM items WHERE profile_id = ? AND type = 'file' AND {parent_filter_clause}"
            candidates = conn.execute(sql, (profile, *parent_filter_params)).fetchall()
            for cand in candidates:
                if cand["path"]:
                    cp = Path(cand["path"])
                    if cp.exists():
                        tot, snips = search_file_content(cp, cand["ext"], q, max_snippets=4)
                        if tot > 0:
                            total_content_hits += tot
                            content_results.append({
                                "id": cand["id"],
                                "name": cand["name"],
                                "ext": cand["ext"],
                                "cover_path": cand["cover_path"],
                                "parent": cand["parent"],
                                "folder_path": folder_path_map.get(cand["parent"], "Library Root"),
                                "total": tot,
                                "snippets": snips
                            })
            content_results.sort(key=lambda x: x["total"], reverse=True)
            items = []
        elif q and search_mode == "name":
            sql = f"SELECT * FROM items WHERE profile_id = ? AND {parent_filter_clause} AND name LIKE ? COLLATE NOCASE"
            items = conn.execute(sql, (profile, *parent_filter_params, f"%{q}%")).fetchall()
        else:
            items = conn.execute("SELECT * FROM items WHERE parent IS ? AND profile_id = ?", (folder, profile)).fetchall()
    
    items_list = [dict(row) for row in items]
    
    def get_sort_key(x, s):
        if s == "name_desc": return (x["type"] != "folder", x["name"].lower())
        if s == "type_asc": return (x["type"] != "folder", x["ext"] or "", x["name"].lower())
        if s == "type_desc": return (x["type"] != "folder", x["ext"] or "", x["name"].lower())
        if s == "newest": return (-x.get("created_at", 0),)
        if s == "latest_use": return (-x.get("last_opened", 0),)
        if s == "starred": return (not x.get("is_starred", 0), x["name"].lower())
        return (x["type"] != "folder", x["name"].lower())
        
    is_rev = sort in ("name_desc", "type_desc")
    pinned = sorted([x for x in items_list if x.get("is_pinned", 0)], key=lambda x: get_sort_key(x, sort), reverse=is_rev)
    unpinned = sorted([x for x in items_list if not x.get("is_pinned", 0)], key=lambda x: get_sort_key(x, sort), reverse=is_rev)
    sorted_items = pinned + unpinned

    profile_options = ""
    profile_export_list = ""
    for p in profiles_db:
        selected = "selected" if p['id'] == profile else ""
        profile_options += f"<option value='{p['id']}' {selected}>{p['name']}</option>"
        profile_export_list += f"<div style='display: flex; justify-content: space-between; padding: 8px; border: 1px solid var(--border); border-radius: 6px;'><span>{p['name']}</span><a href='/export?profile_id={p['id']}' style='font-size: 13px; color: var(--accent); text-decoration: none; font-weight: 500;'>Export</a></div>"

    breadcrumbs = []
    curr = folder
    with get_db() as conn:
        while curr:
            item = conn.execute("SELECT name, parent FROM items WHERE id = ?", (curr,)).fetchone()
            if item:
                breadcrumbs.append(f"<a href='/?folder={curr}&profile={profile}&sort={sort}&view={view}'>{item['name']}</a>")
                curr = item['parent']
            else:
                curr = None
    breadcrumbs.append(f"<a href='/?profile={profile}&sort={sort}&view={view}'>Library</a>")
    breadcrumbs.reverse()
    breadcrumb_html = " <span class='sep'>/</span> ".join(breadcrumbs)

    folder_options = "".join([f"<option value='{f['id']}'>{f['name']}</option>" for f in all_folders if f['id'] != folder])

    safe_q = pyhtml.escape(q or "")
    search_banner_html = ""
    if q:
        scope_str = "in this folder & subfolders" if folder and recursive else ("in this folder" if folder else ("in entire profile" if recursive else "in library root"))
        if search_mode == "content":
            doc_count = len(content_results)
            count_str = f"<b>{total_content_hits}</b> match{'es' if total_content_hits != 1 else ''} across <b>{doc_count}</b> document{'s' if doc_count != 1 else ''}"
            mode_label = "Inside-File Content Search"
        else:
            count_str = f"<b>{len(sorted_items)}</b> item{'s' if len(sorted_items) != 1 else ''} found"
            mode_label = "Name Search"

        search_banner_html = f'''
        <div class="search-banner">
            <div class="search-banner-text">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                <span>{mode_label} for "<b>{safe_q}</b>" ({scope_str}): {count_str}</span>
            </div>
            <button class="search-clear-action" onclick="clearSearch()">Clear Search &times;</button>
        </div>
        '''

    clear_btn_html = f'<button class="search-clear-btn" onclick="clearSearch()" title="Clear search">&times;</button>' if q else ''

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
                color-scheme: dark;
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
            * {{
                box-sizing: border-box;
                scrollbar-width: thin;
                scrollbar-color: #334155 #0b0f19;
            }}
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
                background-color: var(--bg);
            }}
            ::-webkit-scrollbar-track {{
                background: var(--bg);
            }}
            ::-webkit-scrollbar-thumb {{
                background-color: #334155;
                border-radius: 4px;
            }}
            ::-webkit-scrollbar-thumb:hover {{
                background-color: #475569;
            }}
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
            aside {{
                width: 320px;
                background-color: var(--sidebar-bg);
                backdrop-filter: blur(16px);
                border-right: var(--glass-border);
                padding: 40px 28px;
                display: flex;
                flex-direction: column;
                gap: 36px;
                overflow-y: auto;
                box-shadow: 4px 0 24px rgba(0,0,0,0.02);
                z-index: 10;
            }}
            .logo-container {{ display: flex; align-items: center; gap: 12px; }}
            .logo-icon {{
                background: linear-gradient(135deg, var(--accent), var(--accent-hover));
                color: white; width: 36px; height: 36px; display: flex;
                align-items: center; justify-content: center; border-radius: 10px;
                font-weight: bold; font-size: 18px; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            }}
            h1 {{
                font-size: 24px; font-weight: 700; margin: 0; letter-spacing: -0.03em;
                background: linear-gradient(to right, var(--text-main), var(--text-muted));
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }}
            .sidebar-section {{ display: flex; flex-direction: column; gap: 14px; }}
            .section-label {{
                font-size: 11px; text-transform: uppercase; letter-spacing: 0.15em;
                color: var(--text-muted); font-weight: 700; display: flex; align-items: center; gap: 8px;
            }}
            .section-label::after {{ content: ""; flex: 1; height: 1px; background: var(--border); }}
            .input-group {{ display: flex; flex-direction: column; gap: 10px; }}
            input[type="text"], input[type="file"], select {{
                padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border);
                background: var(--card-bg); color: var(--text-main); font-family: inherit;
                font-size: 14px; width: 100%; outline: none; transition: all 0.2s ease;
            }}
            input[type="text"]:focus, select:focus {{ border-color: var(--accent); }}
            input[type="file"]::file-selector-button {{
                border: none; background: var(--accent); color: white;
                padding: 6px 12px; border-radius: 6px; cursor: pointer;
                margin-right: 12px; font-family: inherit; font-weight: 500; font-size: 13px;
            }}
            button {{
                padding: 12px 16px; border-radius: 8px; border: none;
                background: var(--accent); color: white; font-weight: 600;
                cursor: pointer; transition: all 0.2s ease; font-size: 14px;
                display: flex; align-items: center; justify-content: center; gap: 8px;
            }}
            button:hover {{ transform: translateY(-2px); background: var(--accent-hover); }}
            button.secondary {{ background: var(--card-bg); color: var(--text-main); border: 1px solid var(--border); }}
            button.secondary:hover {{ background: var(--hover); border-color: var(--text-muted); }}

            main {{
                flex: 1; padding: 40px 60px; overflow-y: auto;
                display: flex; flex-direction: column; gap: 32px;
            }}
            .header-bar {{
                display: flex; justify-content: space-between; align-items: center;
                flex-wrap: wrap; gap: 20px; background: var(--sidebar-bg);
                backdrop-filter: blur(12px); padding: 16px 24px; border-radius: 16px;
                border: var(--glass-border); box-shadow: var(--shadow);
            }}
            .breadcrumbs {{ font-size: 16px; font-weight: 500; display: flex; align-items: center; gap: 10px; }}
            .breadcrumbs a {{ color: var(--text-muted); text-decoration: none; padding: 4px 8px; border-radius: 6px; }}
            .breadcrumbs a:hover {{ color: var(--text-main); background: var(--hover); }}
            .breadcrumbs .sep {{ color: var(--border); font-weight: 300; }}
            .breadcrumbs a:last-child {{ color: var(--accent); pointer-events: none; font-weight: 600; background: rgba(99, 102, 241, 0.1); }}

            .controls {{ display: flex; align-items: center; gap: 16px; }}
            .control-group {{ display: flex; align-items: center; gap: 8px; background: var(--card-bg); padding: 4px; border-radius: 10px; border: 1px solid var(--border); }}
            .control-btn {{ background: transparent; border: none; padding: 8px 12px; border-radius: 6px; color: var(--text-muted); font-size: 13px; }}
            .control-btn:hover {{ background: var(--hover); color: var(--text-main); transform: none; }}
            .control-btn.active {{ background: var(--bg); color: var(--accent); box-shadow: var(--shadow); font-weight: 600; }}
            .controls select {{ padding: 8px 32px 8px 12px; height: auto; border-radius: 8px; background-color: transparent; border: none; font-weight: 500; cursor: pointer; }}

            /* VIEW MODES */
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 24px; }}
            .list {{ display: flex; flex-direction: column; gap: 12px; }}
            .thumbnail {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 24px; }}
            
            .item-card {{
                background: var(--card-bg); border: var(--glass-border); border-radius: 16px;
                padding: 20px; display: flex; flex-direction: column; gap: 16px;
                transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1); position: relative;
                box-shadow: var(--shadow); backdrop-filter: blur(8px); overflow: hidden;
            }}
            .list .item-card {{ flex-direction: row; align-items: center; padding: 12px 20px; gap: 24px; }}
            .thumbnail .item-card {{ padding: 12px; gap: 12px; align-items: center; text-align: center; }}
            
            .item-card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 24px -8px rgba(0,0,0,0.15); background: var(--card-hover); border-color: var(--accent); }}
            .list .item-card:hover {{ transform: translateX(4px); }}
            .thumbnail .item-card:hover {{ transform: translateY(-4px); }}

            .item-info {{ display: flex; align-items: flex-start; gap: 16px; flex: 1; }}
            .list .item-info {{ align-items: center; }}
            .thumbnail .item-info {{ flex-direction: column; align-items: center; width: 100%; }}

            .item-icon {{
                font-size: 28px; line-height: 1; color: var(--folder-icon); background: rgba(245, 158, 11, 0.1);
                width: 48px; height: 48px; display: flex; align-items: center; justify-content: center;
                border-radius: 12px; transition: transform 0.2s; flex-shrink: 0;
            }}
            .item-icon.file-icon {{ color: var(--accent); background: rgba(99, 102, 241, 0.1); }}
            
            /* Cover Images */
            .cover-img {{
                width: 48px; height: 48px; border-radius: 10px; object-fit: cover;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex-shrink: 0;
            }}
            .thumbnail .cover-img {{
                width: 100%; height: 220px; border-radius: 12px;
            }}
            .thumbnail .item-icon {{
                width: 100%; height: 220px; border-radius: 12px; font-size: 64px;
            }}

            .item-details {{ flex: 1; min-width: 0; width: 100%; }}
            .item-name {{
                font-size: 16px; font-weight: 600; color: var(--link); text-decoration: none;
                line-height: 1.4; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            }}
            .item-name:hover {{ color: var(--accent); }}
            .item-meta {{ font-size: 13px; color: var(--text-muted); display: flex; align-items: center; gap: 10px; margin-top: 6px; }}
            .thumbnail .item-meta {{ justify-content: center; }}
            
            .ext-pill {{ background: rgba(99, 102, 241, 0.1); color: var(--accent); padding: 4px 8px; border-radius: 6px; text-transform: uppercase; font-size: 11px; font-weight: 700; }}
            .folder-pill {{ background: rgba(245, 158, 11, 0.1); color: var(--folder-icon); }}
            .status-icons {{ display: flex; gap: 4px; align-items: center; }}

            .item-actions {{ display: flex; align-items: center; gap: 8px; margin-top: auto; border-top: 1px solid var(--border); padding-top: 16px; width: 100%; }}
            .list .item-actions {{ margin-top: 0; border-top: none; padding-top: 0; width: auto; }}
            .thumbnail .item-actions {{ justify-content: center; flex-wrap: wrap; }}

            .action-btn {{
                background: transparent; border: none; cursor: pointer; padding: 8px;
                border-radius: 8px; color: var(--text-muted); transition: all 0.2s;
                display: flex; align-items: center; justify-content: center;
            }}
            .action-btn:hover {{ background: var(--hover); color: var(--accent); transform: none; }}
            .action-btn.active.star {{ color: #fbbf24; }}
            .action-btn.active.pin {{ color: #10b981; }}
            .action-btn.delete:hover {{ color: #ef4444; background: rgba(239, 68, 68, 0.1); }}

            .move-wrapper {{ flex: 1; }}
            .thumbnail .move-wrapper {{ display: none; }}
            .move-wrapper select {{ font-size: 13px; padding: 8px 12px; height: auto; background: var(--bg); }}

            .empty-state {{ text-align: center; padding: 120px 0; color: var(--text-muted); display: flex; flex-direction: column; align-items: center; gap: 16px; }}
            .empty-icon {{ font-size: 48px; opacity: 0.5; }}
            
            /* File upload cover overlay hidden */
            .cover-upload {{ display: none; }}

            body.drag-active::after {{
                content: "Drop files to upload";
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(99, 102, 241, 0.9);
                color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 32px;
                font-weight: 700;
                z-index: 9999;
                pointer-events: none;
            }}

            .modal-overlay {{
                display: none;
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 10000;
                align-items: center; justify-content: center;
                backdrop-filter: blur(4px);
            }}
            .modal-content {{
                background: var(--bg);
                padding: 24px;
                border-radius: 12px;
                width: 500px;
                max-width: 90%;
                box-shadow: var(--shadow);
                display: flex; flex-direction: column; gap: 16px;
                position: relative;
            }}
            .close-modal {{
                position: absolute; top: 16px; right: 16px;
                background: transparent; border: none; font-size: 24px; cursor: pointer; color: var(--text-muted);
            }}
            .dropzone-area {{
                position: relative;
                border: 2px dashed var(--accent);
                border-radius: 8px;
                padding: 32px 16px;
                text-align: center;
                background: rgba(99, 102, 241, 0.05);
                transition: all 0.2s;
                cursor: pointer;
            }}
            .dropzone-area:hover {{
                background: rgba(99, 102, 241, 0.1);
                border-color: var(--accent-hover);
            }}
            .dropzone-area.drag-over {{
                background: rgba(99, 102, 241, 0.2);
                border-color: var(--accent);
                border-style: solid;
            }}
            .dropzone-area input[type="file"] {{
                position: absolute;
                width: 100%; height: 100%;
                top: 0; left: 0;
                opacity: 0;
                cursor: pointer;
            }}
            .dropzone-text {{
                font-weight: 600; color: var(--accent); font-size: 18px; pointer-events: none;
            }}
            .dropzone-subtext {{
                font-size: 13px; color: var(--text-muted); margin-top: 8px; pointer-events: none;
            }}
            /* SEARCH BAR */
            .search-bar {{
                display: flex; align-items: center; gap: 8px;
                background: var(--card-bg); border: 1px solid var(--border);
                border-radius: 12px; padding: 4px 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
                flex: 1; max-width: 520px; min-width: 260px;
            }}
            .search-input-wrap {{
                display: flex; align-items: center; gap: 8px; flex: 1; position: relative;
            }}
            .search-input-wrap input {{
                width: 100%; border: none; background: transparent;
                padding: 6px 4px; font-size: 13px; color: var(--text-main); outline: none;
            }}
            .search-input-wrap input:focus {{ border: none; box-shadow: none; }}
            .search-icon {{ color: var(--text-muted); flex-shrink: 0; }}
            .search-clear-btn {{
                background: transparent; border: none; color: var(--text-muted);
                cursor: pointer; padding: 2px 6px; font-size: 16px; line-height: 1;
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
            }}
            .search-clear-btn:hover {{ color: var(--text-main); transform: none; }}
            .search-mode-toggles {{
                display: flex; background: var(--bg); border-radius: 8px;
                padding: 2px; border: 1px solid var(--border); gap: 2px;
            }}
            .search-mode-btn {{
                background: transparent; border: none; padding: 4px 8px;
                font-size: 11px; font-weight: 500; color: var(--text-muted);
                border-radius: 6px; cursor: pointer; transition: all 0.15s;
            }}
            .search-mode-btn:hover {{ color: var(--text-main); transform: none; }}
            .search-mode-btn.active {{
                background: var(--accent); color: white; font-weight: 600;
            }}
            .recursive-label {{
                display: flex; align-items: center; gap: 4px; font-size: 12px;
                color: var(--text-muted); cursor: pointer; user-select: none; padding: 0 4px;
            }}
            .recursive-label input {{ cursor: pointer; accent-color: var(--accent); margin: 0; }}
            .search-submit-btn {{
                background: var(--accent); color: white; border: none;
                border-radius: 8px; padding: 6px 8px; cursor: pointer;
                display: flex; align-items: center; justify-content: center;
            }}
            .search-submit-btn:hover {{ background: var(--accent-hover); transform: none; }}

            /* SEARCH BANNER */
            .search-banner {{
                background: var(--card-bg); border: 1px solid var(--border);
                border-radius: 12px; padding: 12px 20px; display: flex;
                justify-content: space-between; align-items: center; gap: 16px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.04);
            }}
            .search-banner-text {{
                font-size: 14px; color: var(--text-main); display: flex; align-items: center; gap: 8px;
            }}
            .search-clear-action {{
                background: transparent; color: var(--accent); border: 1px solid var(--accent);
                padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 500;
                cursor: pointer;
            }}
            .search-clear-action:hover {{ background: rgba(99, 102, 241, 0.1); transform: none; }}

            /* CONTENT SEARCH RESULTS */
            .content-results-container {{
                display: flex; flex-direction: column; gap: 20px; width: 100%;
            }}
            .content-result-card {{
                background: var(--card-bg); border: var(--glass-border);
                border-radius: 16px; padding: 20px 24px; display: flex;
                flex-direction: column; gap: 16px; box-shadow: var(--shadow);
                transition: all 0.2s;
            }}
            .content-result-card:hover {{
                border-color: var(--accent); box-shadow: 0 8px 24px rgba(0,0,0,0.08);
            }}
            .content-card-header {{
                display: flex; align-items: center; gap: 16px;
                border-bottom: 1px solid var(--border); padding-bottom: 12px;
            }}
            .content-card-title {{
                font-size: 16px; font-weight: 600; color: var(--text-main);
                text-decoration: none; display: flex; align-items: center; gap: 8px;
            }}
            .content-card-title:hover {{ color: var(--accent); }}
            .content-card-meta {{
                display: flex; align-items: center; gap: 12px; font-size: 12px;
                color: var(--text-muted); margin-top: 4px;
            }}
            .match-badge {{
                background: rgba(99, 102, 241, 0.15); color: var(--accent);
                font-weight: 600; padding: 3px 10px; border-radius: 12px;
                font-size: 12px; white-space: nowrap;
            }}
            .snippets-list {{ display: flex; flex-direction: column; gap: 8px; }}
            .snippet-item {{
                background: rgba(0, 0, 0, 0.02); border: 1px solid var(--border);
                border-radius: 10px; padding: 10px 14px; display: flex;
                align-items: center; justify-content: space-between; gap: 16px;
            }}
            @media (prefers-color-scheme: dark) {{
                .snippet-item {{ background: rgba(255, 255, 255, 0.02); }}
            }}
            .snippet-left {{ display: flex; align-items: flex-start; gap: 12px; flex: 1; min-width: 0; }}
            .snippet-loc {{
                background: var(--bg); border: 1px solid var(--border);
                color: var(--text-muted); font-size: 11px; font-weight: 600;
                padding: 3px 6px; border-radius: 6px; white-space: nowrap; flex-shrink: 0;
            }}
            .snippet-text {{ font-size: 13px; line-height: 1.5; color: var(--text-main); word-break: break-word; }}
            mark.search-hit {{
                background: #fef08a; color: #854d0e; padding: 1px 3px; border-radius: 3px; font-weight: 600;
            }}
            .jump-link-btn {{
                display: inline-flex; align-items: center; gap: 6px;
                background: var(--accent); color: white; text-decoration: none;
                font-size: 12px; font-weight: 600; padding: 6px 12px;
                border-radius: 8px; white-space: nowrap; transition: all 0.2s; flex-shrink: 0;
            }}
            .jump-link-btn:hover {{ background: var(--accent-hover); transform: translateY(-1px); }}
        </style>
        <script>
            const currentProfile = "{profile}";
            const currentFolder = "{folder or ''}";
            const currentSort = "{sort}";
            const currentView = "{view}";
            const currentQ = "{safe_q}";
            const currentSearchMode = "{search_mode}";
            const currentRecursive = {1 if recursive else 0};
            
            function updateParams(params) {{
                const url = new URL(window.location.href);
                if (currentProfile && !url.searchParams.get('profile')) {{
                    url.searchParams.set('profile', currentProfile);
                }}
                for (const [key, value] of Object.entries(params)) {{
                    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
                    else url.searchParams.delete(key);
                }}
                window.location.href = url.toString();
            }}

            function submitSearch() {{
                const input = document.getElementById('searchInput');
                const val = input ? input.value.trim() : '';
                updateParams({{ q: val }});
            }}

            function clearSearch() {{
                updateParams({{ q: '' }});
            }}

            function setSearchMode(mode) {{
                const input = document.getElementById('searchInput');
                const val = input ? input.value.trim() : '';
                updateParams({{ search_mode: mode, q: val }});
            }}

            function toggleRecursive(checked) {{
                updateParams({{ recursive: checked ? '1' : '0' }});
            }}

            function switchProfile(val) {{
                if (val !== currentProfile) {{
                    document.cookie = "active_profile=" + encodeURIComponent(val) + "; path=/; max-age=31536000; SameSite=Lax";
                    updateParams({{profile: val, folder: '', q: ''}});
                }}
            }}
            function setDefaultProfile() {{
                document.cookie = "default_profile=" + encodeURIComponent(currentProfile) + "; path=/; max-age=31536000; SameSite=Lax";
                document.cookie = "active_profile=" + encodeURIComponent(currentProfile) + "; path=/; max-age=31536000; SameSite=Lax";
                alert("This profile is now your default when you open the app!");
            }}
            
            async function addProfile() {{
                const name = prompt("Enter profile name:");
                if (!name) return;
                const response = await fetch('/profile', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{action: 'add', name}})
                }});
                if (response.ok) {{
                    const data = await response.json();
                    document.cookie = "active_profile=" + encodeURIComponent(data.id) + "; path=/; max-age=31536000; SameSite=Lax";
                    updateParams({{profile: data.id, folder: '', q: ''}});
                }}
            }}
            async function renameProfile() {{
                const name = prompt("Enter new profile name:");
                if (!name) return;
                const response = await fetch('/profile', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{action: 'rename', id: currentProfile, name}})
                }});
                if (response.ok) window.location.reload();
            }}
            async function removeProfile() {{
                if (currentProfile === 'default') {{ alert("Cannot remove default profile"); return; }}
                if (!confirm("Are you sure you want to remove this profile? All items in it will be lost!")) return;
                const response = await fetch('/profile', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{action: 'remove', id: currentProfile}})
                }});
                if (response.ok) {{
                    document.cookie = "active_profile=default; path=/; max-age=31536000; SameSite=Lax";
                    updateParams({{profile: 'default', folder: '', q: ''}});
                }}
            }}

            async function toggleStar(docId) {{
                const response = await fetch(`/toggle-star/${{docId}}`, {{ method: "POST" }});
                if (response.ok) window.location.reload();
            }}

            async function togglePin(docId) {{
                const response = await fetch(`/toggle-pin/${{docId}}`, {{ method: "POST" }});
                if (response.ok) window.location.reload();
            }}

            async function uploadCover(docId) {{
                const input = document.getElementById('cover-upload-' + docId);
                if (!input.files[0]) return;
                const formData = new FormData();
                formData.append("file", input.files[0]);
                const response = await fetch(`/upload-cover/${{docId}}`, {{ method: "POST", body: formData }});
                if (response.ok) window.location.reload();
                else alert("Failed to upload cover.");
            }}

            function triggerCoverUpload(docId) {{
                document.getElementById('cover-upload-' + docId).click();
            }}

            let pendingUploads = [];
            let isUploading = false;
            
            async function processUploadQueue() {{
                if (isUploading || pendingUploads.length === 0) return;
                isUploading = true;
                
                document.getElementById('upload-progress-container').style.display = 'block';
                const listEl = document.getElementById('upload-progress-list');
                const titleEl = document.getElementById('upload-progress-title');
                
                while (pendingUploads.length > 0) {{
                    const item = pendingUploads.shift();
                    titleEl.innerText = `Uploading... (${{pendingUploads.length}} remaining)`;
                    
                    const itemEl = document.createElement('div');
                    itemEl.style.marginBottom = '8px';
                    itemEl.style.fontSize = '12px';
                    itemEl.innerText = `${{item.name}} - Uploading...`;
                    listEl.prepend(itemEl);
                    
                    try {{
                        const response = await fetch(item.url, {{ method: "POST", body: item.formData }});
                        if (response.ok) {{
                            itemEl.innerText = `${{item.name}} - Done`;
                            itemEl.style.color = '#10b981';
                        }} else {{
                            itemEl.innerText = `${{item.name}} - Failed`;
                            itemEl.style.color = '#ef4444';
                        }}
                    }} catch (e) {{
                        itemEl.innerText = `${{item.name}} - Failed`;
                        itemEl.style.color = '#ef4444';
                    }}
                }}
                
                titleEl.innerText = "Uploads Complete";
                isUploading = false;
                
                setTimeout(() => {{
                    window.location.reload();
                }}, 1500);
            }}

            function uploadFiles(files) {{
                if (!files || files.length === 0) return;
                const statusEl = document.getElementById('upload-status');
                if (statusEl) statusEl.innerText = "Added " + files.length + " file(s) to queue.";
                
                for (let i = 0; i < files.length; i++) {{
                    const formData = new FormData();
                    formData.append("file", files[i]);
                    const url = currentFolder ? `/upload?folder=${{currentFolder}}&profile=${{currentProfile}}` : `/upload?profile=${{currentProfile}}`;
                    pendingUploads.push({{
                        name: files[i].name,
                        formData: formData,
                        url: url
                    }});
                }}
                processUploadQueue();
            }}

            function handleZoneDragOver(e) {{
                e.preventDefault();
                e.currentTarget.classList.add('drag-over');
            }}
            
            function handleZoneDragLeave(e) {{
                e.preventDefault();
                e.currentTarget.classList.remove('drag-over');
            }}
            
            async function handleZoneDrop(e) {{
                e.preventDefault();
                e.currentTarget.classList.remove('drag-over');
                
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
                    uploadFiles(e.dataTransfer.files);
                    return;
                }}
                
                const uriList = e.dataTransfer.getData("text/uri-list");
                if (uriList) {{
                    const statusEl = document.getElementById('upload-status');
                    if (statusEl) statusEl.innerText = "Linking files... please wait";
                    
                    const urls = uriList.split("\\n");
                    let linked = false;
                    for (let url of urls) {{
                        url = url.trim();
                        if (url.startsWith("file://")) {{
                            let localPath = decodeURIComponent(url.substring(7));
                            try {{
                                const response = await fetch('/add-path', {{
                                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ path: localPath, parent: currentFolder || null, profile: currentProfile }})
                                }});
                                if (response.ok) linked = true;
                            }} catch (err) {{}}
                        }}
                    }}
                    if (linked) window.location.reload();
                    else if (statusEl) statusEl.innerText = "";
                }}
            }}

            function openUploadModal() {{
                document.getElementById('upload-modal').style.display = 'flex';
                document.getElementById('upload-status').innerText = "";
            }}
            function closeUploadModal() {{
                document.getElementById('upload-modal').style.display = 'none';
            }}

            async function importPath() {{
                let pathInput = document.getElementById('pathInput').value;
                if (!pathInput) return;
                const prefix = localStorage.getItem('docviewer_path_prefix') || '';
                if (prefix && !pathInput.startsWith(prefix)) pathInput = prefix + pathInput;
                const response = await fetch('/add-path', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ path: pathInput, parent: currentFolder || null, profile: currentProfile }})
                }});
                if (response.ok) window.location.reload();
            }}

            async function createFolder() {{
                const name = prompt("Folder name:");
                if (!name) return;
                const response = await fetch('/create-folder', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ name: name, parent: currentFolder || null, profile: currentProfile }})
                }});
                if (response.ok) window.location.reload();
            }}

            async function renameItem(docIdOrEl, currentName) {{
                let docId = docIdOrEl;
                if (typeof docIdOrEl === 'object' && docIdOrEl !== null && docIdOrEl.dataset) {{
                    docId = docIdOrEl.dataset.id;
                    currentName = docIdOrEl.dataset.name;
                }}
                const newName = prompt("Enter new name:", currentName);
                if (!newName || newName.trim() === "" || newName === currentName) return;
                try {{
                    const response = await fetch(`/rename/${{docId}}`, {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ name: newName }})
                    }});
                    if (response.ok) window.location.reload();
                    else alert("Failed to rename item.");
                }} catch (err) {{
                    alert("Error renaming item: " + err.message);
                }}
            }}

            async function moveItem(docId, targetFolder) {{
                if (!targetFolder) return;
                const response = await fetch('/move-item', {{
                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ doc_id: docId, target_folder: targetFolder === 'root' ? null : targetFolder }})
                }});
                if (response.ok) window.location.reload();
            }}

            async function deleteItem(docIdOrEl, name, isFolder) {{
                let docId = docIdOrEl;
                if (typeof docIdOrEl === 'object' && docIdOrEl !== null && docIdOrEl.dataset) {{
                    docId = docIdOrEl.dataset.id;
                    name = docIdOrEl.dataset.name;
                    isFolder = docIdOrEl.dataset.folder === 'true';
                }}
                const deleteFromDrive = localStorage.getItem('docviewer_delete_from_drive') === 'true';
                let msg = isFolder ? `Delete folder "${{name}}" and all its contents?` : `Delete "${{name}}"?`;
                if (deleteFromDrive && !isFolder) {{
                    msg += "\\n(File will also be permanently deleted from drive)";
                }}
                if (confirm(msg)) {{
                    try {{
                        const response = await fetch(`/delete/${{docId}}?delete_from_drive=${{deleteFromDrive}}`, {{ method: "DELETE" }});
                        if (response.ok) {{
                            window.location.reload();
                        }} else {{
                            const errText = await response.text();
                            alert("Failed to delete item: " + errText);
                        }}
                    }} catch (err) {{
                        alert("Error deleting item: " + err.message);
                    }}
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

            let dragCounter = 0;
            function handleDragEnter(e) {{
                e.preventDefault();
                dragCounter++;
                document.body.classList.add('drag-active');
            }}
            function handleDragLeave(e) {{
                e.preventDefault();
                dragCounter--;
                if (dragCounter === 0) {{
                    document.body.classList.remove('drag-active');
                }}
            }}
            function handleDragOver(e) {{
                e.preventDefault();
            }}
            async function handleDrop(e) {{
                e.preventDefault();
                dragCounter = 0;
                document.body.classList.remove('drag-active');
                
                let uploaded = false;
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
                    uploadFiles(e.dataTransfer.files);
                }} else {{
                    const uriList = e.dataTransfer.getData("text/uri-list");
                    if (uriList) {{
                        const urls = uriList.split("\\n");
                        for (let url of urls) {{
                            url = url.trim();
                            if (url.startsWith("file://")) {{
                                let localPath = decodeURIComponent(url.substring(7));
                                const prefix = localStorage.getItem('docviewer_path_prefix') || '';
                                if (prefix && !localPath.startsWith(prefix)) localPath = prefix + localPath;
                                await fetch('/add-path', {{
                                    method: "POST", headers: {{ "Content-Type": "application/json" }},
                                    body: JSON.stringify({{ path: localPath, parent: currentFolder || null, profile: currentProfile }})
                                }});
                                uploaded = true;
                            }}
                        }}
                    }}
                }}
                if (uploaded) window.location.reload();
            }}
        </script>
    </head>
    <body ondragenter="handleDragEnter(event)" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event)">
        <div id="upload-progress-container" style="display:none; position: fixed; bottom: 20px; right: 20px; width: 320px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: var(--shadow); z-index: 1000; overflow: hidden; font-family: sans-serif;">
            <div style="padding: 12px; background: var(--accent); color: white; font-weight: bold; display: flex; justify-content: space-between; align-items: center;">
                <span id="upload-progress-title">Uploading...</span>
                <button onclick="document.getElementById('upload-progress-container').style.display='none'" style="background: none; border: none; color: white; cursor: pointer; font-size: 16px;">&times;</button>
            </div>
            <div style="padding: 12px; max-height: 200px; overflow-y: auto;" id="upload-progress-list">
            </div>
        </div>
        <aside>
            <div class="logo-container" style="cursor: pointer;" onclick="window.location.href='/?profile=' + encodeURIComponent(currentProfile)">
                <div class="logo-icon">D</div>
                <h1>DocViewer</h1>
            </div>
            
            <div class="sidebar-section">
                <span class="section-label">Library Profile</span>
                <select id="profileSelect" onchange="switchProfile(this.value)" style="width: 100%; margin-bottom: 8px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; padding: 6px; color: var(--txt);">
                    {profile_options}
                </select>
                <div style="display: flex; gap: 4px; margin-bottom: 4px;">
                    <button class="secondary" onclick="addProfile()" style="flex: 1; padding: 4px; font-size: 12px;">Add</button>
                    <button class="secondary" onclick="renameProfile()" style="flex: 1; padding: 4px; font-size: 12px;">Rename</button>
                    <button class="secondary" onclick="removeProfile()" style="flex: 1; padding: 4px; font-size: 12px; color: #ef4444;">Del</button>
                </div>
                <button class="secondary" onclick="setDefaultProfile()" style="width: 100%; padding: 4px; font-size: 12px; text-align: center;">Set as Default</button>

            </div>

            <div class="sidebar-section">
                <span class="section-label">Management</span>
                <button onclick="createFolder()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>
                    New Folder
                </button>
            </div>

            <div class="sidebar-section">
                <span class="section-label">Upload</span>
                <button onclick="openUploadModal()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    Upload Files & Folders
                </button>
            </div>

            <div class="sidebar-section">
                <span class="section-label">Link Directory or File</span>
                <div class="input-group">
                    <input type="text" id="pathInput" placeholder="Enter local path...">
                    <button class="secondary" onclick="importPath()">Link Path</button>
                </div>
            </div>
            
            <div class="sidebar-section">
                <span class="section-label">Settings</span>
                <button onclick="openSettingsModal()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                    Settings & Backup
                </button>
                <input type="file" id="importZipInput" style="display:none;" accept=".zip" onchange="importBackup(this.files[0])">
            </div>
        </aside>

        <main>
            <div class="header-bar">
                <div class="breadcrumbs">{breadcrumb_html}</div>
                
                <div class="search-bar">
                    <div class="search-input-wrap">
                        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <input type="text" id="searchInput" placeholder="Search by name or inside files..." value="{safe_q}" onkeydown="if(event.key==='Enter') submitSearch()">
                        {clear_btn_html}
                    </div>
                    <div class="search-mode-toggles">
                        <button class="search-mode-btn {'active' if search_mode == 'name' else ''}" onclick="setSearchMode('name')" title="Search file and folder names">Name</button>
                        <button class="search-mode-btn {'active' if search_mode == 'content' else ''}" onclick="setSearchMode('content')" title="Search text inside files (PDF, EPUB, DOCX, ODT, TXT)">Inside File</button>
                    </div>
                    <label class="recursive-label" title="Search across all subfolders recursively">
                        <input type="checkbox" id="recursiveCheckbox" {'checked' if recursive else ''} onchange="toggleRecursive(this.checked)">
                        <span>Subfolders</span>
                    </label>
                    <button class="search-submit-btn" onclick="submitSearch()" title="Search">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                    </button>
                </div>

                <div class="controls">
                    <div class="control-group" style="padding: 0; background: transparent; border: none;">
                        <span style="font-size: 13px; color: var(--text-muted); font-weight: 500;">Sort:</span>
                        <select onchange="updateParams({{sort: this.value}})" style="background: var(--card-bg); border: 1px solid var(--border);">
                            <option value="name_asc" { 'selected' if sort == 'name_asc' else '' }>Name (A-Z)</option>
                            <option value="name_desc" { 'selected' if sort == 'name_desc' else '' }>Name (Z-A)</option>
                            <option value="type_asc" { 'selected' if sort == 'type_asc' else '' }>Type (A-Z)</option>
                            <option value="type_desc" { 'selected' if sort == 'type_desc' else '' }>Type (Z-A)</option>
                            <option value="newest" { 'selected' if sort == 'newest' else '' }>Newly Added</option>
                            <option value="latest_use" { 'selected' if sort == 'latest_use' else '' }>Latest Use</option>
                            <option value="starred" { 'selected' if sort == 'starred' else '' }>Starred First</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <button class="control-btn { 'active' if view == 'thumbnail' else '' }" onclick="updateParams({{view: 'thumbnail'}})" title="Thumbnail View">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                        </button>
                        <button class="control-btn { 'active' if view == 'grid' else '' }" onclick="updateParams({{view: 'grid'}})" title="Grid View">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                        </button>
                        <button class="control-btn { 'active' if view == 'list' else '' }" onclick="updateParams({{view: 'list'}})" title="List View">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                        </button>
                    </div>
                </div>
            </div>
            
    '''

    if q and search_mode == "content":
        if not content_results:
            html += f'''
            {search_banner_html}
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <h3>No documents containing "{safe_q}" found</h3>
                <p style="color: var(--text-muted); font-size: 14px; margin-top: 8px;">Try another query or enable "Subfolders" to search deeper.</p>
            </div>
            '''
        else:
            html += f'''
            {search_banner_html}
            <div class="content-results-container">
            '''
            for cr in content_results:
                doc_id = cr["id"]
                ext = cr["ext"] or ""
                ext_name = ext.replace(".", "").upper() if ext else "FILE"
                cover_path = cr["cover_path"]
                cb = ""
                if cover_path:
                    import os
                    try: cb = f"?t={int(os.path.getmtime(cover_path))}"
                    except: pass
                
                first_pg = cr["snippets"][0]["page"] if cr["snippets"] else None
                if ext == ".pdf" and first_pg:
                    doc_view_url = f"/view/{doc_id}?page={first_pg}&search={urllib.parse.quote(q)}#page={first_pg}&search={urllib.parse.quote(q)}&phrase=true"
                else:
                    doc_view_url = f"/view/{doc_id}?q={urllib.parse.quote(q)}&match=0"

                if cover_path:
                    c_img = f'<a href="{doc_view_url}" target="_blank" class="cover-wrapper" style="text-decoration: none;"><img src="/cover/{doc_id}{cb}" class="cover-img" alt="Cover" /></a>'
                elif ext == ".pdf":
                    c_img = f'<a href="{doc_view_url}" target="_blank" class="cover-wrapper" style="text-decoration: none;"><img src="/cover/{doc_id}" class="cover-img" alt="Cover" onerror="this.outerHTML=\'<div class=&quot;item-icon file-icon&quot;><svg width=&quot;24&quot; height=&quot;24&quot; viewBox=&quot;0 0 24 24&quot; fill=&quot;none&quot; stroke=&quot;currentColor&quot; stroke-width=&quot;2&quot; stroke-linecap=&quot;round&quot; stroke-linejoin=&quot;round&quot;><path d=&quot;M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z&quot;></path><polyline points=&quot;14 2 14 8 20 8&quot;></polyline></svg></div>\'"/></a>'
                else:
                    c_img = f'<a href="{doc_view_url}" target="_blank" class="cover-wrapper" style="text-decoration: none;"><div class="item-icon file-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></div></a>'

                snippets_html = ""
                for s_idx, snip in enumerate(cr["snippets"]):
                    loc = snip["location"]
                    pg = snip["page"]
                    midx = snip.get("match_idx", s_idx)
                    if ext == ".pdf" and pg:
                        jump_url = f"/view/{doc_id}?page={pg}&search={urllib.parse.quote(q)}#page={pg}&search={urllib.parse.quote(q)}&phrase=true"
                        btn_label = f"Jump to {loc}"
                    else:
                        jump_url = f"/view/{doc_id}?q={urllib.parse.quote(q)}&match={midx}"
                        btn_label = f"Jump to {loc}"

                    snippets_html += f'''
                    <div class="snippet-item">
                        <div class="snippet-left">
                            <span class="snippet-loc">{loc}</span>
                            <div class="snippet-text">{snip['snippet']}</div>
                        </div>
                        <a href="{jump_url}" target="_blank" class="jump-link-btn" title="Open and jump to {loc}">
                            <span>{btn_label}</span>
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                        </a>
                    </div>
                    '''

                extra_note = ""
                if cr["total"] > len(cr["snippets"]):
                    extra_count = cr["total"] - len(cr["snippets"])
                    extra_note = f"<div style='font-size: 12px; color: var(--text-muted); padding: 4px 8px;'>+ {extra_count} more match(es) in this file — <a href='{doc_view_url}' target='_blank' style='color: var(--accent); font-weight: 500;'>Open document to view all</a></div>"

                safe_cr_name = pyhtml.escape(cr['name'], quote=True)
                folder_link = f"/?folder={cr['parent']}&profile={profile}" if cr["parent"] else f"/?profile={profile}"
                html += f'''
                <div class="content-result-card">
                    <div class="content-card-header">
                        {c_img}
                        <div style="flex: 1; min-width: 0;">
                            <a href="{doc_view_url}" target="_blank" class="content-card-title">{cr['name']}</a>
                            <div class="content-card-meta">
                                <span class="ext-pill">{ext_name}</span>
                                <a href="{folder_link}" style="color: var(--text-muted); text-decoration: none;">📁 {cr['folder_path']}</a>
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div class="match-badge">{cr['total']} match{'es' if cr['total'] != 1 else ''}</div>
                            <button class="action-btn delete" data-id="{doc_id}" data-name="{safe_cr_name}" data-folder="false" onclick="deleteItem(this)" title="Delete"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
                        </div>
                    </div>
                    <div class="snippets-list">
                        {snippets_html}
                        {extra_note}
                    </div>
                </div>
                '''
            html += "</div>"
    else:
        if search_banner_html:
            html += search_banner_html
        html += f'''
            <div class="{view}">
        '''

        if not sorted_items:
            empty_msg = f'No items matching "{safe_q}" found' if q else 'This folder is empty'
            empty_icon = '🔍' if q else '📂'
            html += f'''
                </div>
                <div class="empty-state">
                    <div class="empty-icon">{empty_icon}</div>
                    <h3>{empty_msg}</h3>
                </div>
            '''
        else:
            for doc in sorted_items:
                doc_id = doc["id"]
                is_folder = doc["type"] == "folder"
                is_starred = doc.get("is_starred", 0)
                is_pinned = doc.get("is_pinned", 0)
                cover_path = doc.get("cover_path")
                
                cb = ""
                if cover_path:
                    import os
                    try:
                        cb = f"?t={int(os.path.getmtime(cover_path))}"
                    except:
                        pass
                
                if cover_path:
                    cover_html = f'<img src="/cover/{doc_id}{cb}" class="cover-img" alt="Cover" />'
                elif doc.get("ext") == ".pdf":
                    cover_html = f'<img src="/cover/{doc_id}" class="cover-img" alt="Cover" onerror="this.outerHTML=\'<div class=&quot;item-icon file-icon&quot;><svg width=&quot;24&quot; height=&quot;24&quot; viewBox=&quot;0 0 24 24&quot; fill=&quot;none&quot; stroke=&quot;currentColor&quot; stroke-width=&quot;2&quot; stroke-linecap=&quot;round&quot; stroke-linejoin=&quot;round&quot;><path d=&quot;M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z&quot;></path><polyline points=&quot;14 2 14 8 20 8&quot;></polyline></svg></div>\'"/>'
                elif is_folder:
                    cover_html = '<div class="item-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></div>'
                else:
                    cover_html = '<div class="item-icon file-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg></div>'
                    
                meta_html = ""
                if is_folder:
                    meta_html += "<span class='ext-pill folder-pill'>Folder</span>"
                else:
                    ext_name = doc['ext'].replace('.','') if doc['ext'] else 'FILE'
                    meta_html += f"<span class='ext-pill'>{ext_name}</span>"

                if recursive and doc.get("parent") != folder and doc.get("parent"):
                    p_name = folder_path_map.get(doc["parent"], "")
                    if p_name:
                        meta_html += f"<a href='/?folder={doc['parent']}&profile={profile}' style='font-size: 11px; color: var(--text-muted); text-decoration: none; padding: 2px 6px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px;' title='Location: {p_name}'>📁 {p_name}</a>"
                    
                link = f"/?folder={doc_id}&profile={profile}&sort={sort}&view={view}" if is_folder else f"/view/{doc_id}"
                target = "" if is_folder else "target='_blank'"
                
                explorer_btn = f'''<button class="action-btn" onclick="openExplorer('{doc_id}')" title="Show in File Explorer"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></button>''' if doc["path"] else ""
                
                cover_btn = f'''
                    <input type="file" id="cover-upload-{doc_id}" class="cover-upload" onchange="uploadCover('{doc_id}')" accept="image/*">
                    <button class="action-btn" onclick="triggerCoverUpload('{doc_id}')" title="Change Cover"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg></button>
                ''' if not is_folder else ""
                
                move_options = f"<option value=''>Move to...</option><option value='root'>Library Root</option>{folder_options}"
                move_dropdown = f"<select onchange='moveItem(&quot;{doc_id}&quot;, this.value)'>{move_options}</select>"

                star_icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>' if is_starred else '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>'
                star_btn = f'''<button class="action-btn star {'active' if is_starred else ''}" onclick="toggleStar('{doc_id}')" title="Star">{star_icon}</button>'''

                pin_icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.68V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3v4.68a2 2 0 0 1-1.11 1.87l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg>' if is_pinned else '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.68V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3v4.68a2 2 0 0 1-1.11 1.87l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg>'
                pin_btn = f'''<button class="action-btn pin {'active' if is_pinned else ''}" onclick="togglePin('{doc_id}')" title="Pin">{pin_icon}</button>'''

                status_icons = ""
                if is_pinned: status_icons += f"<span style='color: #10b981;' title='Pinned'>{pin_icon}</span>"
                if is_starred: status_icons += f"<span style='color: #fbbf24;' title='Starred'>{star_icon}</span>"
                if status_icons: meta_html = f"<div class='status-icons'>{status_icons}</div>" + meta_html

                safe_attr_name = pyhtml.escape(doc['name'], quote=True)
                
                rename_btn = f'''<button class="action-btn" data-id="{doc_id}" data-name="{safe_attr_name}" onclick="renameItem(this)" title="Rename"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button>'''
                
                html += f'''
                    <div class="item-card">
                        <div class="item-info">
                            {cover_html}
                            <div class="item-details">
                                <a href="{link}" {target} class="item-name" title="{doc['name']}">{doc['name']}</a>
                                <div class="item-meta">{meta_html}</div>
                            </div>
                        </div>
                        <div class="item-actions">
                            <div class="move-wrapper">{move_dropdown}</div>
                            {rename_btn}
                            {cover_btn}
                            {star_btn}
                            {pin_btn}
                            {explorer_btn}
                            <button class="action-btn delete" data-id="{doc_id}" data-name="{safe_attr_name}" data-folder="{str(is_folder).lower()}" onclick="deleteItem(this)" title="Delete"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
                        </div>
                    </div>
                '''
            html += "</div>"

    html += '''
        </main>

        <div id="upload-modal" class="modal-overlay" onclick="if(event.target === this) closeUploadModal()">
            <div class="modal-content">
                <button class="close-modal" onclick="closeUploadModal()">&times;</button>
                <h2 style="margin-top: 0; margin-bottom: 8px;">Upload Files</h2>
                
                <div class="dropzone-area" 
                     ondragover="handleZoneDragOver(event)" 
                     ondragleave="handleZoneDragLeave(event)" 
                     ondrop="handleZoneDrop(event)"
                     onclick="document.getElementById('hiddenFileInput').click()">
                    <div class="dropzone-text">Click or Drop Files Here</div>
                    <div class="dropzone-subtext">Supports PDF, EPUB, DOCX, MD, TXT. Select multiple files.</div>
                    <input type="file" id="hiddenFileInput" onchange="uploadFiles(this.files)" multiple style="display: none;">
                </div>
                
                <div class="dropzone-area"
                     ondragover="handleZoneDragOver(event)" 
                     ondragleave="handleZoneDragLeave(event)" 
                     ondrop="handleZoneDrop(event)"
                     onclick="document.getElementById('hiddenFolderInput').click()">
                    <div class="dropzone-text">Click or Drop Folder Here</div>
                    <div class="dropzone-subtext">Uploads all supported files within a folder</div>
                    <input type="file" id="hiddenFolderInput" onchange="uploadFiles(this.files)" webkitdirectory directory style="display: none;">
                </div>
                
                <div id="upload-status" style="text-align: center; color: var(--accent); font-weight: 500; height: 20px;"></div>
            </div>
        </div>


        <div id="settings-modal" class="modal-overlay" onclick="if(event.target === this) closeSettingsModal()">
            <div class="modal-content" style="width: 600px; max-height: 85vh; overflow-y: auto;">
                <button class="close-modal" onclick="closeSettingsModal()">&times;</button>
                <h2 style="margin-top: 0; margin-bottom: 16px;">Settings & Storage</h2>
                
                <div style="margin-bottom: 24px;">
                    <h3 style="margin-top: 0; margin-bottom: 8px;">Path Prefix</h3>
                    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">If you run this inside Distrobox/Docker, pasted local paths might need a prefix (e.g. <code>/run/host</code>) to work correctly.</p>
                    <div class="input-group">
                        <input type="text" id="settingsPathPrefix" placeholder="e.g. /run/host" onchange="localStorage.setItem('docviewer_path_prefix', this.value.trim())">
                    </div>
                </div>

                <div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border);">
                    <h3 style="margin-top: 0; margin-bottom: 8px;">Drive & Storage Management</h3>
                    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">Manage disk space used by uploaded documents and covers in <code>~/.docviewer</code>.</p>
                    
                    <div id="storageStatsBox" style="background: var(--card-bg, #1e293b); padding: 12px; border-radius: 6px; border: 1px solid var(--border); margin-bottom: 12px; font-size: 13px; display: flex; justify-content: space-around; text-align: center;">
                        <div><div style="color: var(--text-muted); font-size: 11px;">UPLOADED FILES</div><b id="statUploads">Loading...</b></div>
                        <div><div style="color: var(--text-muted); font-size: 11px;">COVERS & THUMBNAILS</div><b id="statCovers">Loading...</b></div>
                        <div><div style="color: var(--text-muted); font-size: 11px;">LIBRARY ITEMS</div><b id="statItems">Loading...</b></div>
                    </div>

                    <div style="margin-bottom: 14px; background: rgba(255, 255, 255, 0.03); padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border);">
                        <label style="display: flex; align-items: flex-start; gap: 10px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="deleteFromDriveToggle" style="margin-top: 3px;" onchange="localStorage.setItem('docviewer_delete_from_drive', this.checked ? 'true' : 'false')">
                            <span>
                                <b>Delete linked files from drive:</b> When deleting linked items, permanently remove the original PDF/document from your computer drive as well (not just from the DocViewer library).
                            </span>
                        </label>
                    </div>

                    <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                        <button onclick="cleanupStorage()" style="flex: 1;">Clean Orphaned & Deleted Files</button>
                        <button class="secondary" onclick="cleanMissingDriveFiles()" style="flex: 1;">Clean Missing Drive Files</button>
                    </div>
                    <p style="font-size: 12px; color: var(--text-muted); margin: 0; line-height: 1.5;">
                        • <b>Clean Orphaned & Deleted Files:</b> Scans <code>.docviewer</code> and permanently deletes unreferenced PDF copies, leftover covers, and temp files.<br>
                        • <b>Clean Missing Drive Files:</b> Removes library entries whose source files have been deleted/moved from your computer drive.
                    </p>
                </div>

                <div>
                    <h3 style="margin-top: 0; margin-bottom: 8px;">Backup & Restore</h3>
                    <div style="display: flex; gap: 8px; margin-bottom: 16px;">
                        <button onclick="window.location.href='/export'" style="flex: 1;">Export Entire Library</button>
                        <button class="secondary" onclick="document.getElementById('importZipInput').click()" style="flex: 1;">Import Backup</button>
                    </div>
                    
                    <h4 style="margin-top: 0; margin-bottom: 8px;">Export Individual Profiles</h4>
                    <div style="display: flex; flex-direction: column; gap: 8px; max-height: 200px; overflow-y: auto;">
                        {profile_export_list}
                    </div>
                </div>
            </div>
        </div>
        <script>
            document.getElementById('settingsPathPrefix').value = localStorage.getItem('docviewer_path_prefix') || '';
            const deleteToggle = document.getElementById('deleteFromDriveToggle');
            if (deleteToggle) {
                deleteToggle.checked = localStorage.getItem('docviewer_delete_from_drive') === 'true';
            }

            async function refreshStorageStats() {
                try {
                    const res = await fetch('/storage-stats');
                    if (res.ok) {
                        const data = await res.json();
                        document.getElementById('statUploads').innerText = `${data.upload_count} files (${data.upload_size})`;
                        document.getElementById('statCovers').innerText = `${data.cover_count} files (${data.cover_size})`;
                        document.getElementById('statItems').innerText = `${data.item_count} items`;
                    }
                } catch(e) {}
            }

            function openSettingsModal() { 
                document.getElementById('settings-modal').style.display = 'flex';
                refreshStorageStats();
            }
            function closeSettingsModal() { document.getElementById('settings-modal').style.display = 'none'; }
            
            async function cleanupStorage() {
                if (!confirm("This will scan .docviewer on your drive and delete any orphaned PDFs, leftover covers, and temp files that do not belong to active library items. Continue?")) return;
                const response = await fetch('/cleanup', { method: "POST" });
                if (response.ok) {
                    const data = await response.json();
                    alert(`Cleanup complete!\n- Deleted ${data.cleaned_uploads} orphaned PDF(s)\n- Deleted ${data.cleaned_covers} leftover cover(s)\n- Deleted ${data.cleaned_temp} temp file(s)\n- Total space freed: ${data.freed_mb} MB`);
                    refreshStorageStats();
                } else {
                    alert("Cleanup failed.");
                }
            }

            async function cleanMissingDriveFiles() {
                if (!confirm("This will scan the library and remove entries whose files have been deleted or moved from your drive. Continue?")) return;
                const response = await fetch('/clean-missing-drive-files', { method: "POST" });
                if (response.ok) {
                    const data = await response.json();
                    alert(`Cleaned ${data.removed_count} missing item(s) whose files were deleted from the drive.`);
                    if (data.removed_count > 0) window.location.reload();
                    else refreshStorageStats();
                } else {
                    alert("Failed to clean missing drive files.");
                }
            }
        </script>
    </body>
    </html>
    '''
    html = html.replace("{profile_export_list}", profile_export_list)
    response = HTMLResponse(html)
    response.set_cookie("active_profile", profile, max_age=31536000, path="/", samesite="lax")
    return response

@app.post("/profile")
def manage_profile(req: dict):
    action = req.get("action")
    import uuid
    with get_db() as conn:
        if action == "add":
            pid = str(uuid.uuid4())[:8]
            conn.execute("INSERT INTO profiles (id, name, rank) VALUES (?, ?, 0)", (pid, req["name"]))
            conn.commit()
            return {"status": "success", "id": pid}
        elif action == "rename":
            conn.execute("UPDATE profiles SET name = ? WHERE id = ?", (req["name"], req["id"]))
            conn.commit()
            return {"status": "success"}
        elif action == "remove":
            if req["id"] == 'default': return {"error": "cannot remove default"}
            items = conn.execute("SELECT id, path, cover_path FROM items WHERE profile_id = ?", (req["id"],)).fetchall()
            cover_dir = APP_DIR / "covers"
            for it in items:
                if it["path"]:
                    p = Path(it["path"])
                    if (UPLOAD_DIR in p.parents or UPLOAD_DIR.resolve() in p.resolve().parents) and p.exists():
                        try: p.unlink()
                        except Exception: pass
                if it["cover_path"]:
                    cp = Path(it["cover_path"])
                    if cp.exists():
                        try: cp.unlink()
                        except Exception: pass
                if cover_dir.exists():
                    for cp in cover_dir.glob(f"{it['id']}.*"):
                        if cp.exists():
                            try: cp.unlink()
                            except Exception: pass
            conn.execute("DELETE FROM profiles WHERE id = ?", (req["id"],))
            conn.execute("DELETE FROM items WHERE profile_id = ?", (req["id"],))
            conn.commit()
            return {"status": "success"}
    return {"error": "unknown action"}

@app.post("/upload")
def upload_file(file: UploadFile = File(...), folder: str = None, profile: str = "default"):
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
            "INSERT INTO items (id, name, path, ext, type, parent, profile_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, file.filename, str(file_path), ext, "file", folder, profile)
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
                        "INSERT INTO items (id, name, path, ext, type, parent, profile_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (doc_id, path.name, str(path), ext, "file", pid, req.profile)
                    )
                    added += 1
                    return doc_id
            elif path.is_dir():
                conn.execute(
                    "INSERT INTO items (id, name, path, type, parent, profile_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (doc_id, path.name, str(path), "folder", pid, req.profile)
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

@app.post("/rename/{doc_id}")
def rename_item(doc_id: str, req: RenameRequest):
    name = req.name.strip()
    if not name:
        return {"error": "Name cannot be empty"}
    with get_db() as conn:
        conn.execute("UPDATE items SET name = ? WHERE id = ?", (name, doc_id))
        conn.commit()
    return {"status": "success"}

@app.get("/favicon.ico")
def favicon_ico():
    return FileResponse(Path(__file__).parent / "favicon.png")

@app.get("/favicon.png")
def favicon():
    return FileResponse(Path(__file__).parent / "favicon.png")

@app.get("/export")
def export_data(background_tasks: __import__("fastapi").BackgroundTasks, profile_id: str = None):
    import tempfile, zipfile, json, os
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
        with get_db() as conn:
            if profile_id:
                profiles = [dict(r) for r in conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchall()]
                items = [dict(r) for r in conn.execute("SELECT * FROM items WHERE profile_id = ?", (profile_id,)).fetchall()]
            else:
                profiles = [dict(r) for r in conn.execute("SELECT * FROM profiles").fetchall()]
                items = [dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
            
        metadata = {"profiles": profiles, "items": items}
        zf.writestr("data.json", json.dumps(metadata))
        
        for item in items:
            if item["type"] == "file" and item.get("path"):
                p = Path(item["path"])
                if p.exists():
                    zf.write(p, f"files/{item['id']}{item.get('ext', '')}")
            
            if item.get("cover_path"):
                cp = Path(item["cover_path"])
                if cp.exists():
                    zf.write(cp, f"covers/{cp.name}")
                    
    background_tasks.add_task(os.unlink, tmp.name)
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return FileResponse(tmp.name, media_type="application/zip", filename=f"docviewer_backup_{timestamp}.zip")

@app.post("/import")
def import_data(file: UploadFile = File(...)):
    import tempfile, zipfile, json, shutil, os
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_name = tmp.name
        
    try:
        with zipfile.ZipFile(tmp_name, 'r') as zf:
            data = json.loads(zf.read("data.json"))
            
            with get_db() as conn:
                for p in data.get("profiles", []):
                    conn.execute("INSERT OR REPLACE INTO profiles (id, name, rank) VALUES (?, ?, ?)", (p["id"], p["name"], p["rank"]))
                    
                for item in data.get("items", []):
                    new_path = None
                    if item["type"] == "file":
                        zip_file_path = f"files/{item['id']}{item.get('ext', '')}"
                        if zip_file_path in zf.namelist():
                            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                            dest = UPLOAD_DIR / f"{item['id']}{item.get('ext', '')}"
                            with open(dest, "wb") as f:
                                f.write(zf.read(zip_file_path))
                            new_path = str(dest)
                    
                    new_cover_path = None
                    if item.get("cover_path"):
                        old_cover_name = Path(item["cover_path"]).name
                        zip_cover_path = f"covers/{old_cover_name}"
                        if zip_cover_path in zf.namelist():
                            cover_dir = APP_DIR / "covers"
                            cover_dir.mkdir(parents=True, exist_ok=True)
                            dest = cover_dir / old_cover_name
                            with open(dest, "wb") as f:
                                f.write(zf.read(zip_cover_path))
                            new_cover_path = str(dest)
                            
                    conn.execute("""
                        INSERT OR REPLACE INTO items 
                        (id, name, path, ext, type, parent, created_at, last_opened, is_starred, is_pinned, cover_path, profile_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["id"], item["name"], new_path or item.get("path"), item.get("ext"), 
                        item["type"], item.get("parent"), item.get("created_at"), 
                        item.get("last_opened"), item.get("is_starred"), item.get("is_pinned"), 
                        new_cover_path, item.get("profile_id", "default")
                    ))
                conn.commit()
    except Exception as e:
        os.unlink(tmp_name)
        return {"error": str(e)}
        
    os.unlink(tmp_name)
    return {"status": "success"}

@app.post("/create-folder")
def create_folder(req: dict):
    name = req.get("name", "New Folder")
    parent = req.get("parent") if req.get("parent") else None
    profile = req.get("profile", "default")
    doc_id = str(uuid.uuid4())[:8]
    with get_db() as conn:
        conn.execute(
            "INSERT INTO items (id, name, type, parent, profile_id) VALUES (?, ?, ?, ?, ?)",
            (doc_id, name, "folder", parent, profile)
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
def delete_doc(doc_id: str, delete_from_drive: bool = False):
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
        
        cover_dir = APP_DIR / "covers"
        for d_id in to_delete:
            d_item = conn.execute("SELECT path, cover_path FROM items WHERE id = ?", (d_id,)).fetchone()
            if d_item:
                # 1. Delete document file from disk
                if d_item["path"]:
                    doc_path = Path(d_item["path"])
                    is_upload = (UPLOAD_DIR in doc_path.parents) or (UPLOAD_DIR.resolve() in doc_path.resolve().parents)
                    if (is_upload or delete_from_drive) and doc_path.exists():
                        try:
                            doc_path.unlink()
                        except Exception as e:
                            print(f"Error unlinking {doc_path}: {e}")
                
                # 2. Delete cover file from disk
                if d_item["cover_path"]:
                    cp = Path(d_item["cover_path"])
                    if cp.exists():
                        try:
                            cp.unlink()
                        except Exception:
                            pass
                if cover_dir.exists():
                    for cp in cover_dir.glob(f"{d_id}.*"):
                        if cp.exists():
                            try:
                                cp.unlink()
                            except Exception:
                                pass
            conn.execute("DELETE FROM items WHERE id = ?", (d_id,))
        conn.commit()
    
    return {"status": "success"}

@app.post("/cleanup")
def cleanup_files():
    cleaned_uploads = 0
    cleaned_covers = 0
    cleaned_temp = 0
    freed_bytes = 0
    with get_db() as conn:
        items = [dict(r) for r in conn.execute("SELECT * FROM items").fetchall()]
        
    valid_paths = set()
    valid_covers = set()
    valid_ids = set()
    for item in items:
        valid_ids.add(item["id"])
        if item.get("path"):
            valid_paths.add(str(Path(item["path"]).resolve()))
            valid_paths.add(str(Path(item["path"])))
        if item.get("cover_path"):
            valid_covers.add(str(Path(item["cover_path"]).resolve()))
            valid_covers.add(str(Path(item["cover_path"])))
        
    # Clean uploads
    if UPLOAD_DIR.exists():
        for p in UPLOAD_DIR.iterdir():
            if p.is_file():
                is_valid = (str(p.resolve()) in valid_paths) or (str(p) in valid_paths) or (p.stem in valid_ids)
                if not is_valid:
                    sz = p.stat().st_size
                    try:
                        p.unlink()
                        cleaned_uploads += 1
                        freed_bytes += sz
                    except Exception as e:
                        print(f"Error unlinking orphan upload {p}: {e}")
                
    # Clean covers
    cover_dir = APP_DIR / "covers"
    if cover_dir.exists():
        for p in cover_dir.iterdir():
            if p.is_file():
                is_valid = (str(p.resolve()) in valid_covers) or (str(p) in valid_covers) or (p.stem in valid_ids)
                if not is_valid:
                    sz = p.stat().st_size
                    try:
                        p.unlink()
                        cleaned_covers += 1
                        freed_bytes += sz
                    except Exception as e:
                        print(f"Error unlinking orphan cover {p}: {e}")

    # Clean temporary files in APP_DIR (test zip, pdfjs.zip, obsolete pdfjs dir)
    if APP_DIR.exists():
        for p in APP_DIR.iterdir():
            if p.is_file() and (p.suffix in {".zip", ".tmp"} or p.name.startswith("tmp_")):
                sz = p.stat().st_size
                try:
                    p.unlink()
                    cleaned_temp += 1
                    freed_bytes += sz
                except Exception:
                    pass
            elif p.is_dir() and p.name == "pdfjs-6.2.108":
                import shutil
                sz = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                try:
                    shutil.rmtree(p)
                    cleaned_temp += 1
                    freed_bytes += sz
                except Exception:
                    pass
                
    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    return {
        "status": "success",
        "cleaned_uploads": cleaned_uploads,
        "cleaned_covers": cleaned_covers,
        "cleaned_temp": cleaned_temp,
        "total_cleaned": cleaned_uploads + cleaned_covers + cleaned_temp,
        "freed_mb": freed_mb
    }

@app.post("/clean-missing-drive-files")
def clean_missing_drive_files():
    removed_count = 0
    cover_dir = APP_DIR / "covers"
    with get_db() as conn:
        items = [dict(r) for r in conn.execute("SELECT * FROM items WHERE type = 'file'").fetchall()]
        for item in items:
            p = Path(item["path"]) if item.get("path") else None
            if not p or not p.exists():
                if item.get("cover_path"):
                    cp = Path(item["cover_path"])
                    if cp.exists():
                        try: cp.unlink()
                        except Exception: pass
                if cover_dir.exists():
                    for cp in cover_dir.glob(f"{item['id']}.*"):
                        if cp.exists():
                            try: cp.unlink()
                            except Exception: pass
                conn.execute("DELETE FROM items WHERE id = ?", (item["id"],))
                removed_count += 1
        conn.commit()
    return {"status": "success", "removed_count": removed_count}

@app.get("/storage-stats")
def storage_stats():
    upload_count = 0
    upload_bytes = 0
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.iterdir():
            if f.is_file():
                upload_count += 1
                upload_bytes += f.stat().st_size

    cover_count = 0
    cover_bytes = 0
    cover_dir = APP_DIR / "covers"
    if cover_dir.exists():
        for f in cover_dir.iterdir():
            if f.is_file():
                cover_count += 1
                cover_bytes += f.stat().st_size

    with get_db() as conn:
        item_count = conn.execute("SELECT COUNT(*) FROM items WHERE type = 'file'").fetchone()[0]

    def fmt(b):
        if b >= 1024 * 1024 * 1024:
            return f"{round(b / (1024 * 1024 * 1024), 2)} GB"
        return f"{round(b / (1024 * 1024), 1)} MB"

    return {
        "upload_count": upload_count,
        "upload_size": fmt(upload_bytes),
        "cover_count": cover_count,
        "cover_size": fmt(cover_bytes),
        "item_count": item_count
    }

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


def update_last_opened(doc_id: str):
    if not doc_id.startswith("tmp_"):
        with get_db() as conn:
            conn.execute("UPDATE items SET last_opened = cast(strftime('%s','now') as int) WHERE id = ?", (doc_id,))
            conn.commit()

@app.post("/toggle-star/{doc_id}")
def toggle_star(doc_id: str):
    with get_db() as conn:
        conn.execute("UPDATE items SET is_starred = 1 - is_starred WHERE id = ?", (doc_id,))
        conn.commit()
    return {"status": "success"}

@app.post("/toggle-pin/{doc_id}")
def toggle_pin(doc_id: str):
    with get_db() as conn:
        conn.execute("UPDATE items SET is_pinned = 1 - is_pinned WHERE id = ?", (doc_id,))
        conn.commit()
    return {"status": "success"}

@app.post("/upload-cover/{doc_id}")
def upload_cover(doc_id: str, file: UploadFile = File(...)):
    item = get_item(doc_id)
    if not item: return HTMLResponse("Not found", status_code=404)
    ext = Path(file.filename).suffix.lower()
    cover_dir = APP_DIR / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f"{doc_id}{ext}"
    with open(cover_path, "wb") as buffer:
        import shutil
        shutil.copyfileobj(file.file, buffer)
    with get_db() as conn:
        conn.execute("UPDATE items SET cover_path = ? WHERE id = ?", (str(cover_path), doc_id))
        conn.commit()
    return {"status": "success"}

@app.get("/cover/{doc_id}")
def get_cover(doc_id: str):
    item = get_item(doc_id)
    if not item:
        return HTMLResponse("No cover", status_code=404)
        
    if item.get("cover_path") and Path(item["cover_path"]).exists():
        return FileResponse(item["cover_path"])
        
    if item.get("path") and item.get("ext") == ".pdf":
        try:
            import pymupdf
            try:
                pymupdf.TOOLS.mupdf_display_errors(False)
                pymupdf.TOOLS.mupdf_display_warnings(False)
            except Exception:
                pass
            pdf_path = item["path"]
            if Path(pdf_path).exists():
                doc = pymupdf.open(pdf_path)
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=150)
                cover_dir = APP_DIR / "covers"
                cover_dir.mkdir(parents=True, exist_ok=True)
                cover_path = cover_dir / f"{doc_id}.png"
                pix.save(str(cover_path))
                
                with get_db() as conn:
                    conn.execute("UPDATE items SET cover_path = ? WHERE id = ?", (str(cover_path), doc_id))
                    conn.commit()
                return FileResponse(cover_path)
        except Exception as e:
            print(f"Failed to generate thumbnail for {item['path']}: {e}")
            
    return HTMLResponse("No cover", status_code=404)

def get_viewer_search_assets(doc_name: str, query: Optional[str] = None, match_idx: int = 0):
    safe_query = pyhtml.escape(query or "")
    is_active_display = "flex" if query else "none"
    toggle_display = "none" if query else "flex"

    search_css = """
    .docviewer-search-bar {
        position: fixed;
        top: 16px;
        right: 20px;
        z-index: 999999;
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(17, 24, 39, 0.92);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 10px;
        padding: 6px 10px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.35), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #f1f5f9;
    }
    .docviewer-search-input-wrap {
        display: flex;
        align-items: center;
        gap: 6px;
        background: rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 6px;
        padding: 4px 8px;
    }
    .docviewer-search-input-wrap svg {
        color: #94a3b8;
        flex-shrink: 0;
    }
    #docviewer-search-input {
        background: transparent;
        border: none;
        outline: none;
        color: #ffffff;
        font-size: 13px;
        width: 150px;
    }
    #docviewer-search-input::placeholder {
        color: #94a3b8;
    }
    .docviewer-search-count {
        font-size: 12px;
        color: #cbd5e1;
        white-space: nowrap;
        padding: 0 4px;
        font-variant-numeric: tabular-nums;
        font-weight: 500;
    }
    .docviewer-search-actions {
        display: flex;
        align-items: center;
        gap: 3px;
    }
    .docviewer-search-btn {
        background: transparent;
        border: none;
        outline: none;
        color: #cbd5e1;
        cursor: pointer;
        border-radius: 5px;
        padding: 5px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.15s ease;
    }
    .docviewer-search-btn:hover {
        background: rgba(255, 255, 255, 0.2);
        color: #ffffff;
    }
    .docviewer-search-close:hover {
        background: rgba(239, 68, 68, 0.3);
        color: #fca5a5;
    }
    .docviewer-search-toggle-btn {
        position: fixed;
        top: 16px;
        right: 20px;
        z-index: 999998;
        background: rgba(17, 24, 39, 0.85);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 50%;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #f1f5f9;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        transition: all 0.2s ease;
    }
    .docviewer-search-toggle-btn:hover {
        background: rgba(30, 41, 59, 0.95);
        transform: scale(1.05);
    }
    mark.docviewer-match {
        background-color: #fef08a;
        color: #854d0e;
        padding: 1px 3px;
        border-radius: 3px;
    }
    @media (prefers-color-scheme: dark) {
        mark.docviewer-match {
            background-color: #854d0e;
            color: #fef08a;
        }
    }
    mark.docviewer-match-active {
        background-color: #ea580c !important;
        color: #ffffff !important;
        outline: 2px solid #f97316;
        border-radius: 3px;
        box-shadow: 0 0 12px rgba(249, 115, 22, 0.8);
    }
    """

    search_html = f"""
    <button id="docviewer-search-toggle" class="docviewer-search-toggle-btn" style="display: {toggle_display};" title="Search document (Ctrl+F)">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
    </button>
    <div id="docviewer-search-bar" class="docviewer-search-bar" style="display: {is_active_display};">
        <div class="docviewer-search-input-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <input type="text" id="docviewer-search-input" value="{safe_query}" placeholder="Search in document..." />
            <span id="docviewer-search-count" class="docviewer-search-count">0/0</span>
        </div>
        <div class="docviewer-search-actions">
            <button id="docviewer-prev-btn" title="Previous match (Shift+Enter / ↑)" class="docviewer-search-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg>
            </button>
            <button id="docviewer-next-btn" title="Next match (Enter / ↓)" class="docviewer-search-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
            </button>
            <button id="docviewer-close-btn" title="Close search (Esc)" class="docviewer-search-btn docviewer-search-close">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
        </div>
    </div>
    """

    search_js = """
    <script>
    (function() {
        let currentMatches = [];
        let currentIndex = -1;

        function unhighlight() {
            const marks = document.querySelectorAll('mark.docviewer-match');
            marks.forEach(function(m) {
                const parent = m.parentNode;
                if (parent) {
                    while (m.firstChild) {
                        parent.insertBefore(m.firstChild, m);
                    }
                    parent.removeChild(m);
                    parent.normalize();
                }
            });
            currentMatches = [];
            currentIndex = -1;
        }

        function highlightText(node, queryLower) {
            if (node.nodeType === Node.TEXT_NODE) {
                const val = node.nodeValue;
                const valLower = val.toLowerCase();
                let idx = valLower.indexOf(queryLower);
                if (idx !== -1) {
                    const frag = document.createDocumentFragment();
                    let lastIdx = 0;
                    while (idx !== -1) {
                        if (idx > lastIdx) {
                            frag.appendChild(document.createTextNode(val.substring(lastIdx, idx)));
                        }
                        const mark = document.createElement('mark');
                        mark.className = 'docviewer-match';
                        mark.textContent = val.substring(idx, idx + queryLower.length);
                        frag.appendChild(mark);
                        currentMatches.push(mark);
                        lastIdx = idx + queryLower.length;
                        idx = valLower.indexOf(queryLower, lastIdx);
                    }
                    if (lastIdx < val.length) {
                        frag.appendChild(document.createTextNode(val.substring(lastIdx)));
                    }
                    node.parentNode.replaceChild(frag, node);
                }
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                if (tag !== 'script' && tag !== 'style' && tag !== 'mark' && !node.closest('.docviewer-search-bar') && !node.closest('.docviewer-search-toggle-btn')) {
                    const children = Array.from(node.childNodes);
                    for (const child of children) {
                        highlightText(child, queryLower);
                    }
                }
            }
        }

        function performSearch(query, targetIdx) {
            if (targetIdx === undefined) targetIdx = 0;
            unhighlight();
            if (!query || !query.trim()) {
                updateCounter();
                return;
            }
            highlightText(document.body, query.trim().toLowerCase());
            if (currentMatches.length > 0) {
                goToMatch(Math.min(targetIdx, currentMatches.length - 1));
            } else {
                updateCounter();
            }
        }

        function goToMatch(idx) {
            if (currentMatches.length === 0) {
                updateCounter();
                return;
            }
            if (currentIndex >= 0 && currentIndex < currentMatches.length) {
                currentMatches[currentIndex].classList.remove('docviewer-match-active');
            }
            currentIndex = (idx + currentMatches.length) % currentMatches.length;
            const active = currentMatches[currentIndex];
            active.classList.add('docviewer-match-active');
            active.scrollIntoView({ behavior: 'smooth', block: 'center' });
            updateCounter();
        }

        function updateCounter() {
            const countEl = document.getElementById('docviewer-search-count');
            if (!countEl) return;
            if (currentMatches.length === 0) {
                countEl.textContent = '0/0';
            } else {
                countEl.textContent = (currentIndex + 1) + '/' + currentMatches.length;
            }
        }

        window.addEventListener('DOMContentLoaded', function() {
            const input = document.getElementById('docviewer-search-input');
            const prevBtn = document.getElementById('docviewer-prev-btn');
            const nextBtn = document.getElementById('docviewer-next-btn');
            const closeBtn = document.getElementById('docviewer-close-btn');
            const bar = document.getElementById('docviewer-search-bar');
            const toggleBtn = document.getElementById('docviewer-search-toggle');

            const urlParams = new URLSearchParams(window.location.search);
            const qParam = urlParams.get('search') || urlParams.get('q') || (input ? input.value : '');
            const matchParam = parseInt(urlParams.get('match') || '0', 10);

            if (qParam && input) {
                input.value = qParam;
                if (bar) bar.style.display = 'flex';
                if (toggleBtn) toggleBtn.style.display = 'none';
                performSearch(qParam, isNaN(matchParam) ? 0 : matchParam);
            }

            if (input) {
                input.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        if (e.shiftKey) goToMatch(currentIndex - 1);
                        else goToMatch(currentIndex + 1);
                    } else if (e.key === 'Escape') {
                        if (bar) bar.style.display = 'none';
                        if (toggleBtn) toggleBtn.style.display = 'flex';
                        unhighlight();
                    }
                });
                input.addEventListener('input', function() {
                    performSearch(input.value, 0);
                });
            }

            if (prevBtn) prevBtn.addEventListener('click', function() { goToMatch(currentIndex - 1); });
            if (nextBtn) nextBtn.addEventListener('click', function() { goToMatch(currentIndex + 1); });
            if (closeBtn) {
                closeBtn.addEventListener('click', function() {
                    if (bar) bar.style.display = 'none';
                    if (toggleBtn) toggleBtn.style.display = 'flex';
                    unhighlight();
                });
            }
            if (toggleBtn) {
                toggleBtn.addEventListener('click', function() {
                    toggleBtn.style.display = 'none';
                    if (bar) {
                        bar.style.display = 'flex';
                        if (input) {
                            input.focus();
                            input.select();
                            if (input.value) performSearch(input.value, 0);
                        }
                    }
                });
            }

            document.addEventListener('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
                    e.preventDefault();
                    if (toggleBtn) toggleBtn.style.display = 'none';
                    if (bar) {
                        bar.style.display = 'flex';
                        if (input) {
                            input.focus();
                            input.select();
                        }
                    }
                } else if (e.key === 'F3') {
                    e.preventDefault();
                    if (e.shiftKey) goToMatch(currentIndex - 1);
                    else goToMatch(currentIndex + 1);
                }
            });
        });
    })();
    </script>
    """
    return search_css, search_html, search_js

@app.get("/view/{doc_id}")
def view_doc(doc_id: str, request: Request, page: Optional[int] = None, search: Optional[str] = None, q: Optional[str] = None, match: Optional[int] = 0):
    doc = get_item(doc_id)
    if not doc:
        return HTMLResponse("Document not found or temporary session expired.", status_code=404)
    update_last_opened(doc_id)

    ext = doc["ext"]
    file_path = doc["path"]
    profile_id = doc.get("profile_id", "default")

    query = search or q or request.query_params.get("search") or request.query_params.get("q")
    page_num = page or request.query_params.get("page")
    match_idx = match if match is not None else request.query_params.get("match", 0)
    try:
        match_idx = int(match_idx)
    except:
        match_idx = 0

    if query:
        query = query.strip()

    if ext == ".pdf":
        params = []
        if page_num:
            params.append(f"page={page_num}")
        if query:
            params.append(f"search={urllib.parse.quote(query)}")
            params.append("phrase=true")
        hash_frag = f"#{'&'.join(params)}" if params else ""
        return RedirectResponse(url=f"/pdfjs-v6/web/viewer.html?file=/file/{doc_id}{hash_frag}")

    elif ext == ".epub":
        return HTMLResponse(render_epub_viewer(
            doc_id=doc_id,
            doc_name=doc["name"],
            query=query,
            match_idx=match_idx,
            profile_id=profile_id
        ))

    elif ext == ".docx":
        with open(file_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
        html_content = result.value
        words = len(re.sub(r'<[^>]+>', ' ', html_content).split())
        extra_stats = f"{words:,} words • ~{max(1, round(words / 200))} min read" if words > 0 else None
        return HTMLResponse(render_html_document_viewer(
            doc_id=doc_id,
            doc_name=doc["name"],
            ext=".docx",
            body_html=html_content,
            query=query,
            match_idx=match_idx,
            extra_stats=extra_stats,
            profile_id=profile_id
        ))

    elif ext in [".odt", ".odf"]:
        try:
            result = subprocess.run(["pandoc", file_path, "-t", "html"], capture_output=True, text=True, check=True)
            html_content = result.stdout
            words = len(re.sub(r'<[^>]+>', ' ', html_content).split())
            extra_stats = f"{words:,} words • ~{max(1, round(words / 200))} min read" if words > 0 else None
            return HTMLResponse(render_html_document_viewer(
                doc_id=doc_id,
                doc_name=doc["name"],
                ext=ext,
                body_html=html_content,
                query=query,
                match_idx=match_idx,
                extra_stats=extra_stats,
                profile_id=profile_id
            ))
        except Exception as e:
            return HTMLResponse(f"<b>Error:</b> Requires 'pandoc' installed on system (or pandoc failed: {e}).", status_code=500)

    elif ext == ".txt":
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        words = len(content.split())
        extra_stats = f"{words:,} words • ~{max(1, round(words / 200))} min read" if words > 0 else None

        lines = content.splitlines()
        formatted_lines = []
        chapter_pattern = re.compile(r'^(chapter|section|part|book|\d+\.|\={3,}|\-{3,})', re.IGNORECASE)
        for idx, line in enumerate(lines, 1):
            safe_line = pyhtml.escape(line)
            stripped = line.strip()
            if stripped and (chapter_pattern.match(stripped) or (stripped.isupper() and 3 <= len(stripped) <= 60)):
                formatted_lines.append(f'<h2 class="txt-section-heading" id="txt-sec-{idx}">{safe_line}</h2>')
            else:
                formatted_lines.append(f'<div class="txt-line"><span class="txt-line-num" style="display:none;">{idx}</span><span class="txt-line-content">{safe_line or "&nbsp;"}</span></div>')
        body_html = f'<div class="txt-with-lines">{"".join(formatted_lines)}</div>'

        return HTMLResponse(render_html_document_viewer(
            doc_id=doc_id,
            doc_name=doc["name"],
            ext=".txt",
            body_html=body_html,
            query=query,
            match_idx=match_idx,
            extra_stats=extra_stats,
            profile_id=profile_id
        ))

    elif ext == ".md":
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        words = len(content.split())
        extra_stats = f"{words:,} words • ~{max(1, round(words / 200))} min read" if words > 0 else None
        html_content = markdown.markdown(
            content,
            extensions=['fenced_code', 'tables', 'toc', 'attr_list', 'def_list', 'footnotes']
        )
        return HTMLResponse(render_html_document_viewer(
            doc_id=doc_id,
            doc_name=doc["name"],
            ext=".md",
            body_html=html_content,
            query=query,
            match_idx=match_idx,
            extra_stats=extra_stats,
            profile_id=profile_id
        ))

    return HTMLResponse("Unsupported file format.", status_code=400)

@app.get("/file/{doc_id}")
def get_file(doc_id: str):
    if doc_id.endswith(".epub"):
        doc_id = doc_id[:-5]
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
        app.mount("/pdfjs-v6", StaticFiles(directory=str(PDFJS_DIR)), name="pdfjs")
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
        app.mount("/pdfjs-v6", StaticFiles(directory=str(PDFJS_DIR)), name="pdfjs")
        url = f"http://localhost:{args.port}/view/{doc_id}"

        print(f"[*] Opening '{p.name}' in Quick View Mode...")
        print(f"[*] Close the server (Ctrl+C) when finished reading.")
        webbrowser.open(url)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
