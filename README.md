# 📚 DocViewer

A lightweight, local web server for reading and managing documents natively in your browser. 

DocViewer turns your browser into a high-performance document reader. By converting formats like EPUB, DOCX, and Markdown into native HTML, it ensures that your favorite browser extensions—like dictionaries, translators, and text-to-speech—work perfectly across all your books and papers. 

## Features
* **Universal Support:** Read `.pdf`, `.epub`, `.docx`, `.odt`, `.txt`, and `.md` files in your browser.
* **Web Native:** Converts EPUBs, DOCX, and Markdown to pure HTML on the fly.
* **Auto Dark Mode:** Respects your system's dark/light mode preference automatically.
* **Local Library:** Keeps track of your documents in a clean web UI.
* **No File Duplication (Optional):** Upload copies, OR map entire local folders directly.
* **Quick View:** Temporarily open a file in your browser without saving it to your library.

---

## 🚀 First-Time Setup

This tool is built with Python and installed globally using **uv** (a lightning-fast Python package manager). If you're starting from scratch, follow these steps:

### 1. Install `uv`
If you don't have `uv` installed yet, open your terminal and run the command for your operating system:

**macOS & Linux:**
```bash
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
```

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm [https://astral.sh/uv/install.ps1](https://astral.sh/uv/install.ps1) | iex"
```
*(Note: You may need to restart your terminal after installing `uv` for the first time).*

### 2. Install DocViewer
Navigate to the folder containing this project in your terminal, then install it globally:

```bash
uv tool install .
```
*(If you are updating to a new version of DocViewer later, run `uv tool install . --force`)*

---

## 📖 Usage

### Start the Web Interface
To launch your library dashboard (defaults to `http://localhost:2005`):
```bash
docviewer serve
```
*(You can specify a custom port with `docviewer serve --port 8080`)*

Once the server is running, you can manage your files directly in the browser via the Web UI.

### CLI Commands (Terminal)
You can also bypass the Web UI and manage files straight from your terminal.

**Add files or scan entire directories:**
Recursively scans a folder and adds all supported documents to your library.
```bash
docviewer add "C:\Users\Name\Books"
docviewer add "~/Documents/research.pdf"
```

**Quick View (Temporary Mode):**
Instantly spin up the server, open a specific file in your browser, and forget it ever existed once you close the server. Great for quickly checking a file without cluttering your library.
```bash
docviewer open "~/Downloads/temporary_book.epub"
```

---

## ⚙️ Requirements
* **Python 3.8+**
* To read `.odt` or `.odf` files, you must have [Pandoc](https://pandoc.org/) installed on your system. All other formats work out-of-the-box!
