import sys
import json
import uuid
import argparse
import urllib.request
import zipfile
import subprocess
import webbrowser
import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import mammoth
import markdown

# --- CONFIGURATION ---
APP_DIR = Path.home() / ".docviewer"
LIB_FILE = APP_DIR / "library.json"
PDFJS_DIR = APP_DIR / "pdfjs"
UPLOAD_DIR = APP_DIR / "uploads"

SUPPORTED_EXTS = {".pdf", ".epub", ".docx", ".odt", ".odf", ".md", ".txt"}

app = FastAPI()

class PathRequest(BaseModel):
    path: str

# --- DATABASE LOGIC ---
def load_lib():
    if LIB_FILE.exists():
        return json.loads(LIB_FILE.read_text())
    return {}

def save_lib(lib_data):
    LIB_FILE.write_text(json.dumps(lib_data, indent=4))

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
def index():
    lib = load_lib()

    html = """
    <!DOCTYPE html>
    <html><head><title>My Library</title>
    <style>
        :root {
            --bg: #ffffff; --txt: #111827; --box: #f0f4f8; --border: #cbd5e1;
            --link: #0066cc; --btn: #ffffff; --btn-hover: #f8fafc; --ext: #e2e8f0;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #111827; --txt: #e2e8f0; --box: #1e293b; --border: #334155;
                --link: #60a5fa; --btn: #1e293b; --btn-hover: #334155; --ext: #334155;
            }
        }
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; background-color: var(--bg); color: var(--txt); }
        .upload-box { padding: 20px; background: var(--box); border-radius: 8px; margin-bottom: 2rem; border: 2px dashed var(--border); display: flex; flex-direction: column; gap: 15px; }
        .input-group { display: flex; align-items: center; gap: 10px; }
        .doc-item { padding: 12px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        a { text-decoration: none; color: var(--link); font-weight: bold; font-size: 1.1em; }
        a:hover { text-decoration: underline; }
        .ext { color: var(--txt); font-size: 0.8em; text-transform: uppercase; background: var(--ext); padding: 2px 6px; border-radius: 4px; }
        .del-btn { background: none; border: none; color: #ef4444; cursor: pointer; font-size: 1.2em; margin-left: 10px; }
        .del-btn:hover { color: #dc2626; transform: scale(1.1); }
        button { padding: 6px 12px; cursor: pointer; border-radius: 4px; border: 1px solid var(--border); background: var(--btn); color: var(--txt); }
        button:hover { background: var(--btn-hover); }
        input[type="text"], input[type="file"] { padding: 6px; border: 1px solid var(--border); border-radius: 4px; flex-grow: 1; background: var(--btn); color: var(--txt); }
        .status { font-weight: bold; margin-left: 10px; }
    </style>
    <script>
        async function uploadFile() {
            const fileInput = document.getElementById('fileInput');
            const status = document.getElementById('uploadStatus');
            if (!fileInput.files[0]) { status.innerText = " ⚠️ Select a file!"; return; }
            status.innerText = " ⏳ Uploading...";
            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            const response = await fetch('/upload', { method: "POST", body: formData });
            if (response.ok) { window.location.reload(); } else { status.innerText = " ❌ Upload failed."; }
        }
        async function importPath() {
            const pathInput = document.getElementById('pathInput').value;
            const status = document.getElementById('pathStatus');
            if (!pathInput) { status.innerText = " ⚠️ Enter a path!"; return; }
            status.innerText = " ⏳ Scanning...";
            const response = await fetch('/add-path', {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: pathInput })
            });
            const result = await response.json();
            if (response.ok) { alert(`Successfully added ${result.added} document(s)!`); window.location.reload(); }
            else { status.innerText = ` ❌ ${result.detail || 'Error'}`; }
        }
        async function deleteDoc(docId) {
            if (confirm("Delete this document from your library?")) {
                const response = await fetch(`/delete/${docId}`, { method: "DELETE" });
                if (response.ok) { window.location.reload(); }
            }
        }
    </script>
    </head><body>
    <h1>📚 My Document Library</h1>
    <div class="upload-box">
        <div class="input-group">
            <b>📁 Upload a Copy:</b>
            <input type="file" id="fileInput" accept=".pdf,.epub,.docx,.odt,.odf,.md,.txt">
            <button onclick="uploadFile()">Upload</button>
            <span id="uploadStatus" class="status"></span>
        </div>
        <hr style="width: 100%; border: 0; border-top: 1px solid var(--border); margin: 0;">
        <div class="input-group">
            <b>🔗 Link Local Path:</b>
            <input type="text" id="pathInput" placeholder="e.g., /home/user/Books or C:\\Documents\\paper.pdf">
            <button onclick="importPath()">Import Path</button>
            <span id="pathStatus" class="status"></span>
        </div>
    </div>
    <div>
    """

    if not lib:
        html += "<p>Your library is empty. Add a file above!</p>"
    else:
        for doc_id, doc in lib.items():
            html += f"""
            <div class='doc-item'>
                <a href='/view/{doc_id}' target='_blank'>📄 {doc['name']}</a>
                <div>
                    <span class='ext'>{doc['ext'].replace('.','')}</span>
                    <button class='del-btn' onclick="deleteDoc('{doc_id}')" title="Delete">🗑️</button>
                </div>
            </div>
            """

    html += "</div></body></html>"
    return HTMLResponse(html)

@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return HTMLResponse("Unsupported file format.", status_code=400)
    lib = load_lib()
    doc_id = str(uuid.uuid4())[:8]
    file_path = UPLOAD_DIR / f"{doc_id}{ext}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    lib[doc_id] = {"name": file.filename, "path": str(file_path), "ext": ext}
    save_lib(lib)
    return {"status": "success", "id": doc_id}

@app.post("/add-path")
def add_by_path(req: PathRequest):
    p = Path(req.path).expanduser().resolve()
    if not p.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    lib = load_lib()
    added = 0
    def add_file(file_path):
        ext = file_path.suffix.lower()
        if ext in SUPPORTED_EXTS:
            doc_id = str(uuid.uuid4())[:8]
            lib[doc_id] = {"name": file_path.name, "path": str(file_path), "ext": ext}
            return True
        return False
    if p.is_file():
        if add_file(p):
            added += 1
    elif p.is_dir():
        for f in p.rglob("*"):
            if f.is_file() and add_file(f):
                added += 1
    save_lib(lib)
    return {"status": "success", "added": added}

@app.delete("/delete/{doc_id}")
def delete_doc(doc_id: str):
    lib = load_lib()
    if doc_id in lib:
        doc_path = Path(lib[doc_id]["path"])
        if UPLOAD_DIR in doc_path.parents and doc_path.exists():
            doc_path.unlink()
        del lib[doc_id]
        save_lib(lib)
        return {"status": "success"}
    return HTMLResponse("Document not found.", status_code=404)

@app.get("/view/{doc_id}")
def view_doc(doc_id: str):
    lib = load_lib()
    if doc_id not in lib:
        return HTMLResponse("Document not found in library.", status_code=404)

    doc = lib[doc_id]
    ext = doc["ext"]
    file_path = doc["path"]

    # Shared Dark Mode CSS for document viewers
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
    lib = load_lib()
    if doc_id in lib:
        return FileResponse(lib[doc_id]["path"])
    return HTMLResponse("File missing", status_code=404)

# --- CLI LOGIC ---
def cli():
    parser = argparse.ArgumentParser(description="DocViewer: Read documents natively.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a file or scan an entire folder")
    add_parser.add_argument("path", type=str, help="Path to the file or directory")

    serve_parser = subparsers.add_parser("serve", help="Start the server")
    serve_parser.add_argument("--port", type=int, default=2005, help="Port to run on")

    args = parser.parse_args()
    APP_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "add":
        p = Path(args.path).resolve()
        if not p.exists():
            print(f"[-] Error: Path '{p}' does not exist.")
            sys.exit(1)

        lib = load_lib()
        added = 0

        def add_file(file_path):
            ext = file_path.suffix.lower()
            if ext in SUPPORTED_EXTS:
                doc_id = str(uuid.uuid4())[:8]
                lib[doc_id] = {"name": file_path.name, "path": str(file_path), "ext": ext}
                return True
            return False

        if p.is_file():
            if add_file(p):
                added += 1
                print(f"[+] Added '{p.name}'")
            else:
                print(f"[-] Unsupported format: {p.suffix}")
        elif p.is_dir():
            print(f"[*] Scanning folder '{p.name}' for supported documents...")
            for f in p.rglob("*"):
                if f.is_file() and add_file(f):
                    added += 1
                    print(f"  -> Added '{f.name}'")

        save_lib(lib)
        print(f"[+] Successfully added {added} document(s) to your library!")

    elif args.command == "serve":
        ensure_pdfjs()
        app.mount("/pdfjs", StaticFiles(directory=str(PDFJS_DIR)), name="pdfjs")
        print(f"[*] Starting WebReader on http://localhost:{args.port}")
        webbrowser.open(f"http://localhost:{args.port}")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
