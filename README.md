# 📚 DocViewer

A lightweight, universal local web server for reading and managing your documents. Built with FastAPI and powered by modern web parsers, it renders your files as native HTML so browser extensions (like dictionary lookups or text-to-speech) work flawlessly across all formats.

## Features
* **Universal Support:** Read `.pdf`, `.epub`, `.docx`, `.odt`, `.txt`, and `.md` files in your browser.
* **Web Native:** Converts EPUBs, DOCX, and Markdown to pure HTML on the fly.
* **Auto Dark Mode:** Respects your system's dark/light mode preference across all documents.
* **Local Library:** Keeps track of your documents in a clean web UI without moving your original files.
* **Web & CLI Imports:** Upload copies through the browser, or map entire local folders directly.

## Installation

This tool is designed to be installed globally using [uv](https://github.com/astral-sh/uv).

Navigate to this directory in your terminal and run:
```bash
uv tool install .
Note: To read .odt files, you must have Pandoc installed on your system.

Usage
Start the web interface (defaults to http://localhost:2005):

Bash
docviewer serve
(You can also specify a custom port: docviewer serve --port 8080)

Adding Documents via CLI
You can also bypass the Web UI and add files straight from your terminal. Scan single files or entire directories recursively:

Bash
docviewer add "C:\Users\Name\Books"
docviewer add "~/Documents/research.pdf"
