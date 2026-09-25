"""
DocViewer Unified Reader Engine
Provides a Calibre-inspired, clean, and responsive e-reader experience
for EPUB, DOCX, ODT, Markdown, and TXT files.
"""

import re
import urllib.parse
import html as pyhtml
from typing import Optional, List, Dict, Any


def get_reader_css() -> str:
    return """
    :root, [data-theme="dark"] {
        color-scheme: dark;
        --bg-page: #0b0f19;
        --bg-surface: #111827;
        --bg-header: rgba(17, 24, 39, 0.96);
        --border-color: #1f2937;
        --text-primary: #cbd5e1;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent: #38bdf8;
        --accent-hover: #60a5fa;
        --accent-light: #1e293b;
        --toc-bg: #111827;
        --toc-hover: #1f2937;
        --toc-active: #1e3a5f;
        --toc-active-text: #38bdf8;
        --progress-track: #1f2937;
        --progress-fill: #38bdf8;
        --shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
        --code-bg: #1e293b;
        --code-border: #334155;
        --paper-shadow: 0 1px 3px rgba(0,0,0,0.3), 0 10px 25px -5px rgba(0,0,0,0.4);
    }

    [data-theme="light"] {
        color-scheme: light;
        --bg-page: #f1f5f9;
        --bg-surface: #ffffff;
        --bg-header: rgba(255, 255, 255, 0.96);
        --border-color: #e2e8f0;
        --text-primary: #1e293b;
        --text-secondary: #64748b;
        --text-muted: #94a3b8;
        --accent: #2563eb;
        --accent-hover: #1d4ed8;
        --accent-light: #eff6ff;
        --toc-bg: #ffffff;
        --toc-hover: #f8fafc;
        --toc-active: #eff6ff;
        --toc-active-text: #1d4ed8;
        --progress-track: #e2e8f0;
        --progress-fill: #2563eb;
        --shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.08);
        --code-bg: #f8fafc;
        --code-border: #e2e8f0;
        --paper-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 10px 25px -5px rgba(0,0,0,0.05);
    }

    [data-theme="sepia"] {
        color-scheme: light;
        --bg-page: #f4ebd9;
        --bg-surface: #fbf0d9;
        --bg-header: rgba(246, 237, 219, 0.96);
        --border-color: #e4d7bc;
        --text-primary: #3d2e1e;
        --text-secondary: #705842;
        --text-muted: #9c8269;
        --accent: #92400e;
        --accent-hover: #78350f;
        --accent-light: #f6eedb;
        --toc-bg: #f9eed5;
        --toc-hover: #eee0c2;
        --toc-active: #e5d2ac;
        --toc-active-text: #78350f;
        --progress-track: #e0d0b0;
        --progress-fill: #92400e;
        --shadow: 0 4px 20px -2px rgba(61, 46, 30, 0.12);
        --code-bg: #f1e3c7;
        --code-border: #ded0b4;
        --paper-shadow: 0 1px 3px rgba(61,46,30,0.08), 0 10px 25px -5px rgba(61,46,30,0.06);
    }

    /* Scrollbars */
    * {
        scrollbar-width: thin;
        scrollbar-color: #334155 #0b0f19;
    }
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
        background-color: var(--bg-page);
    }
    ::-webkit-scrollbar-track {
        background: var(--bg-page);
    }
    ::-webkit-scrollbar-thumb {
        background-color: #334155;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background-color: #475569;
    }
    [data-theme="light"] * {
        scrollbar-color: #cbd5e1 #f1f5f9;
    }
    [data-theme="light"] ::-webkit-scrollbar-thumb {
        background-color: #cbd5e1;
    }
    [data-theme="sepia"] * {
        scrollbar-color: #d1c0a0 #f4ebd9;
    }
    [data-theme="sepia"] ::-webkit-scrollbar-thumb {
        background-color: #d1c0a0;
    }

    * {
        box-sizing: border-box;
    }

    html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        background-color: var(--bg-page);
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
        overflow: hidden;
        -webkit-font-smoothing: antialiased;
    }

    /* Font Family Modifiers */
    [data-font="serif"] {
        --doc-font: "Literata", "Merriweather", "Georgia", "Cambria", "Times New Roman", serif;
    }
    [data-font="sans"] {
        --doc-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", sans-serif;
    }
    [data-font="mono"] {
        --doc-font: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }

    /* Top Chrome Toolbar */
    .calibre-header {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 52px;
        background: var(--bg-header);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-bottom: 1px solid var(--border-color);
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 14px;
        z-index: 1000;
        transition: transform 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
        user-select: none;
    }

    .header-group {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .header-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: transparent;
        border: 1px solid transparent;
        color: var(--text-primary);
        font-size: 13px;
        font-weight: 500;
        padding: 6px 10px;
        border-radius: 6px;
        cursor: pointer;
        text-decoration: none;
        transition: all 0.15s ease;
        line-height: 1;
        white-space: nowrap;
    }

    .header-btn:hover {
        background: var(--toc-hover);
        border-color: var(--border-color);
        color: var(--accent);
    }

    .header-btn-primary {
        background: var(--accent-light);
        color: var(--accent);
        border-color: rgba(37, 99, 235, 0.2);
    }
    .header-btn-primary:hover {
        background: var(--accent);
        color: #ffffff;
    }

    .header-icon-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        background: transparent;
        border: 1px solid transparent;
        color: var(--text-secondary);
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.15s ease;
        padding: 0;
        font-size: 14px;
        font-weight: 600;
    }

    .header-icon-btn:hover {
        background: var(--toc-hover);
        border-color: var(--border-color);
        color: var(--text-primary);
    }

    .header-badge {
        font-size: 11px;
        font-weight: 600;
        background: var(--accent);
        color: #ffffff;
        padding: 2px 6px;
        border-radius: 10px;
        min-width: 18px;
        text-align: center;
    }

    .header-center {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        max-width: 40%;
        overflow: hidden;
        text-align: center;
    }

    .doc-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--text-primary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }

    .chapter-badge {
        font-size: 11px;
        font-weight: 500;
        color: var(--text-secondary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
        margin-top: 1px;
    }

    .layout-segmented {
        display: flex;
        align-items: center;
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 2px;
        gap: 2px;
    }

    .layout-opt-btn {
        background: transparent;
        border: none;
        border-radius: 4px;
        padding: 4px 8px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 500;
        color: var(--text-secondary);
        transition: all 0.15s ease;
        display: flex;
        align-items: center;
        gap: 5px;
        user-select: none;
        white-space: nowrap;
    }

    .layout-opt-btn:hover {
        background: var(--toc-hover);
        color: var(--text-primary);
    }

    .layout-opt-btn.active {
        background: var(--bg-surface);
        color: var(--accent);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
        font-weight: 600;
    }

    @media (max-width: 900px) {
        .layout-opt-btn span {
            display: none;
        }
    }

    .theme-segmented {
        display: flex;
        align-items: center;
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 2px;
        gap: 2px;
    }

    .theme-opt-btn {
        background: transparent;
        border: none;
        border-radius: 4px;
        padding: 4px 6px;
        cursor: pointer;
        font-size: 13px;
        color: var(--text-secondary);
        transition: all 0.15s ease;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .theme-opt-btn.active {
        background: var(--bg-surface);
        color: var(--accent);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        font-weight: 600;
    }

    .font-size-group {
        display: flex;
        align-items: center;
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 2px;
    }

    .font-size-label {
        font-size: 11px;
        font-weight: 600;
        color: var(--text-secondary);
        padding: 0 5px;
        min-width: 36px;
        text-align: center;
        cursor: pointer;
        user-select: none;
    }

    .header-select {
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        color: var(--text-primary);
        font-size: 12px;
        font-weight: 500;
        padding: 5px 8px;
        border-radius: 6px;
        outline: none;
        cursor: pointer;
    }

    /* Left Slide-out TOC Drawer */
    .calibre-toc-drawer {
        position: fixed;
        top: 0;
        bottom: 0;
        left: -360px;
        width: 350px;
        max-width: 85vw;
        background: var(--toc-bg);
        border-right: 1px solid var(--border-color);
        box-shadow: var(--shadow);
        z-index: 2000;
        transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
        display: flex;
        flex-direction: column;
    }

    .calibre-toc-drawer.open {
        transform: translateX(360px);
    }

    .toc-drawer-header {
        padding: 14px 16px;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: var(--bg-surface);
    }

    .toc-drawer-title {
        font-size: 15px;
        font-weight: 600;
        color: var(--text-primary);
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .toc-filter-box {
        padding: 10px 14px;
        border-bottom: 1px solid var(--border-color);
        background: var(--bg-surface);
    }

    .toc-filter-input {
        width: 100%;
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        color: var(--text-primary);
        padding: 7px 12px;
        border-radius: 6px;
        font-size: 13px;
        outline: none;
        transition: border-color 0.15s ease;
    }

    .toc-filter-input:focus {
        border-color: var(--accent);
    }

    .toc-list-container {
        flex: 1;
        overflow-y: auto;
        padding: 8px 6px;
    }

    .toc-item {
        display: flex;
        align-items: center;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 13px;
        color: var(--text-primary);
        cursor: pointer;
        transition: all 0.15s ease;
        margin-bottom: 2px;
        line-height: 1.4;
        position: relative;
        text-decoration: none;
    }

    .toc-item:hover {
        background: var(--toc-hover);
        color: var(--accent);
    }

    .toc-item.active {
        background: var(--toc-active);
        color: var(--toc-active-text);
        font-weight: 600;
    }

    .toc-item.active::before {
        content: "";
        position: absolute;
        left: 0;
        top: 6px;
        bottom: 6px;
        width: 3px;
        background: var(--accent);
        border-radius: 0 2px 2px 0;
    }

    .toc-item.depth-0 { font-weight: 500; }
    .toc-item.depth-1 { padding-left: 24px; font-size: 12.5px; opacity: 0.95; }
    .toc-item.depth-2 { padding-left: 36px; font-size: 12px; opacity: 0.88; }
    .toc-item.depth-3 { padding-left: 48px; font-size: 12px; opacity: 0.82; }

    .toc-empty {
        padding: 24px;
        text-align: center;
        color: var(--text-muted);
        font-size: 13px;
    }

    .calibre-toc-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(2px);
        z-index: 1999;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.25s ease;
    }

    .calibre-toc-overlay.open {
        opacity: 1;
        pointer-events: auto;
    }

    /* Bottom Navigation / Progress Bar */
    .calibre-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 44px;
        background: var(--bg-header);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-top: 1px solid var(--border-color);
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 16px;
        z-index: 1000;
        transition: all 0.2s ease;
        user-select: none;
    }

    .calibre-progress-track {
        position: absolute;
        top: -3px;
        left: 0;
        right: 0;
        height: 5px;
        background: var(--progress-track);
        cursor: pointer;
        transition: height 0.15s ease;
    }

    .calibre-progress-track:hover {
        height: 9px;
        top: -5px;
    }

    .calibre-progress-fill {
        height: 100%;
        background: var(--progress-fill);
        width: 0%;
        transition: width 0.15s ease;
        position: relative;
    }

    .calibre-progress-tooltip {
        position: absolute;
        right: -18px;
        top: -26px;
        background: rgba(15, 23, 42, 0.9);
        color: #ffffff;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        pointer-events: none;
        opacity: 0;
        transform: translateY(4px);
        transition: all 0.15s ease;
        white-space: nowrap;
    }

    .calibre-progress-track:hover .calibre-progress-tooltip {
        opacity: 1;
        transform: translateY(0);
    }

    .footer-status {
        font-size: 12px;
        font-weight: 500;
        color: var(--text-secondary);
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Floating Navigation Chevrons */
    .floating-nav-btn {
        position: fixed;
        top: 50%;
        transform: translateY(-50%);
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        box-shadow: var(--shadow);
        color: var(--text-primary);
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 900;
        opacity: 0.25;
        transition: all 0.2s ease;
        user-select: none;
    }

    .floating-nav-btn:hover {
        opacity: 1;
        transform: translateY(-50%) scale(1.08);
        border-color: var(--accent);
        color: var(--accent);
    }

    .floating-prev { left: 16px; }
    .floating-next { right: 16px; }

    /* Reader Main Viewport & Typography */
    .reader-main-viewport {
        position: absolute;
        top: 52px;
        bottom: 44px;
        left: 0;
        right: 0;
        overflow-y: auto;
        overflow-x: hidden;
        scroll-behavior: smooth;
        background-color: var(--bg-page);
    }

    /* Scrolled Document Paper Container */
    .reader-paper-wrapper {
        min-height: 100%;
        padding: 2.5rem 1rem 4rem 1rem;
        display: flex;
        justify-content: center;
    }

    .reader-paper {
        background-color: var(--bg-surface);
        box-shadow: var(--paper-shadow);
        border-radius: 8px;
        border: 1px solid var(--border-color);
        padding: 3rem 3.5rem;
        width: 100%;
        transition: max-width 0.2s ease, background-color 0.2s ease, color 0.2s ease;
        color: var(--text-primary);
        font-family: var(--doc-font, serif);
        line-height: 1.75;
    }

    [data-width="normal"] .reader-paper { max-width: 780px; }
    [data-width="wide"] .reader-paper { max-width: 1080px; }
    [data-width="full"] .reader-paper { max-width: 100%; margin: 0 1rem; }

    /* Typography inside Paper */
    .reader-paper h1, .reader-paper h2, .reader-paper h3, .reader-paper h4, .reader-paper h5, .reader-paper h6 {
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
        font-weight: 700;
        line-height: 1.3;
        margin-top: 2rem;
        margin-bottom: 0.8rem;
        scroll-margin-top: 70px;
    }
    .reader-paper h1 { font-size: 2.1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.5rem; }
    .reader-paper h2 { font-size: 1.65rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.35rem; }
    .reader-paper h3 { font-size: 1.35rem; }
    .reader-paper h4 { font-size: 1.15rem; }

    .reader-paper p {
        margin: 1.1em 0;
        font-size: 1em;
        text-align: justify;
        hyphens: auto;
    }

    .reader-paper a {
        color: var(--accent);
        text-decoration: underline;
        text-underline-offset: 2px;
    }

    .reader-paper blockquote {
        margin: 1.5em 0;
        padding: 0.5em 1.25em;
        border-left: 4px solid var(--accent);
        background: var(--toc-hover);
        border-radius: 0 6px 6px 0;
        color: var(--text-secondary);
        font-style: italic;
    }

    .reader-paper img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 1.5rem auto;
        border-radius: 6px;
    }

    [data-theme="dark"] .reader-paper img {
        filter: brightness(0.85) contrast(1.05);
    }

    .reader-paper table {
        border-collapse: collapse;
        width: 100%;
        margin: 1.5rem 0;
        font-size: 0.95em;
    }

    .reader-paper th, .reader-paper td {
        border: 1px solid var(--border-color);
        padding: 8px 12px;
        text-align: left;
    }

    .reader-paper th {
        background: var(--toc-hover);
        font-weight: 600;
    }

    .reader-paper pre, .reader-paper code {
        font-family: "JetBrains Mono", "Fira Code", monospace;
        font-size: 0.9em;
    }

    .reader-paper code {
        background: var(--code-bg);
        border: 1px solid var(--code-border);
        border-radius: 4px;
        padding: 2px 5px;
    }

    .reader-paper pre {
        background: var(--code-bg);
        border: 1px solid var(--code-border);
        border-radius: 6px;
        padding: 14px;
        overflow-x: auto;
        line-height: 1.5;
    }

    .reader-paper pre code {
        background: transparent;
        border: none;
        padding: 0;
    }

    /* Plain Text Line Numbers */
    .txt-with-lines {
        font-family: var(--doc-font, monospace);
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.6;
    }

    .txt-line {
        display: flex;
    }

    .txt-line-num {
        display: inline-block;
        width: 48px;
        padding-right: 16px;
        color: var(--text-muted);
        text-align: right;
        user-select: none;
        font-size: 11px;
    }

    .txt-line-content {
        flex: 1;
    }

    /* EPUB Container */
    #epub-viewer-wrapper {
        position: absolute;
        top: 52px;
        bottom: 44px;
        left: 0;
        right: 0;
        background-color: var(--bg-page);
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
    }

    #epub-viewer {
        width: 100%;
        height: 100%;
        max-width: 820px;
        margin: 0 auto;
        position: relative;
        background-color: var(--bg-surface);
        box-shadow: var(--paper-shadow);
        transition: max-width 0.2s ease, background-color 0.2s ease;
    }

    /* Single Page measure constraints */
    [data-layout="single"] #epub-viewer,
    [data-spread="none"] #epub-viewer {
        max-width: 820px;
    }
    [data-layout="single"][data-width="wide"] #epub-viewer,
    [data-spread="none"][data-width="wide"] #epub-viewer {
        max-width: 1100px;
    }
    [data-layout="single"][data-width="full"] #epub-viewer,
    [data-spread="none"][data-width="full"] #epub-viewer {
        max-width: 100%;
    }

    /* Double Page (2-Page Spread) */
    [data-layout="double"] #epub-viewer,
    [data-spread="always"] #epub-viewer {
        max-width: 1480px;
        width: 96%;
    }
    [data-layout="double"][data-width="wide"] #epub-viewer,
    [data-spread="always"][data-width="wide"] #epub-viewer {
        max-width: 1720px;
        width: 98%;
    }
    [data-layout="double"][data-width="full"] #epub-viewer,
    [data-spread="always"][data-width="full"] #epub-viewer {
        max-width: 100%;
        width: 100%;
    }

    /* Subtle spine divider line between the 2 pages */
    [data-layout="double"] #epub-viewer::after,
    [data-spread="always"] #epub-viewer::after {
        content: "";
        position: absolute;
        top: 24px;
        bottom: 24px;
        left: 50%;
        width: 1px;
        background: var(--border-color);
        opacity: 0.55;
        pointer-events: none;
        z-index: 50;
    }

    @media (max-width: 768px) {
        [data-layout="double"] #epub-viewer::after,
        [data-spread="always"] #epub-viewer::after {
            display: none !important;
        }
    }

    /* Continuous Scroll Mode: Fits the screen completely! */
    [data-layout="scroll"] #epub-viewer-wrapper,
    [data-flow="scrolled-doc"] #epub-viewer-wrapper,
    [data-flow="scrolled"] #epub-viewer-wrapper {
        display: block !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        width: 100% !important;
        height: 100% !important;
        background-color: var(--bg-page);
        padding: 0 !important;
    }

    [data-layout="scroll"] #epub-viewer,
    [data-flow="scrolled-doc"] #epub-viewer,
    [data-flow="scrolled"] #epub-viewer {
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
        min-height: 100% !important;
        height: 100% !important;
        box-shadow: none !important;
        border: none !important;
        border-radius: 0 !important;
        background-color: var(--bg-surface);
    }

    [data-layout="scroll"] #epub-viewer::after,
    [data-flow="scrolled-doc"] #epub-viewer::after,
    [data-flow="scrolled"] #epub-viewer::after {
        display: none !important;
    }

    [data-layout="scroll"] .floating-nav-btn,
    [data-flow="scrolled-doc"] .floating-nav-btn,
    [data-flow="scrolled"] .floating-nav-btn {
        display: none !important;
    }

    [data-layout="scroll"] .epub-container,
    [data-flow="scrolled-doc"] .epub-container,
    [data-flow="scrolled"] .epub-container {
        width: 100% !important;
        max-width: 100% !important;
    }

    [data-layout="scroll"] .epub-view,
    [data-flow="scrolled-doc"] .epub-view,
    [data-flow="scrolled"] .epub-view {
        width: 100% !important;
        max-width: 100% !important;
    }

    [data-layout="scroll"] .epub-view iframe,
    [data-flow="scrolled-doc"] .epub-view iframe,
    [data-flow="scrolled"] .epub-view iframe {
        width: 100% !important;
        max-width: 100% !important;
    }

    .epub-nav-zone {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 18%;
        z-index: 100;
        cursor: pointer;
    }
    .epub-nav-zone-prev { left: 0; }
    .epub-nav-zone-next { right: 0; }

    /* Search Highlights */
    mark.docviewer-match {
        background-color: #fef08a !important;
        color: #854d0e !important;
        padding: 1px 3px;
        border-radius: 3px;
    }

    [data-theme="dark"] mark.docviewer-match {
        background-color: #854d0e !important;
        color: #fef08a !important;
    }

    mark.docviewer-match-active {
        background-color: #ea580c !important;
        color: #ffffff !important;
        outline: 2px solid #f97316;
        border-radius: 3px;
        box-shadow: 0 0 12px rgba(249, 115, 22, 0.8);
    }

    /* Floating Search Bar */
    .calibre-search-bar {
        position: fixed;
        top: 60px;
        right: 20px;
        z-index: 1500;
        display: none;
        align-items: center;
        gap: 8px;
        background: var(--bg-surface);
        border: 1px solid var(--border-color);
        box-shadow: var(--shadow);
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 13px;
    }

    .calibre-search-bar.active {
        display: flex;
    }

    .search-input-wrap {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .search-input-wrap input {
        background: var(--bg-page);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        padding: 5px 8px;
        color: var(--text-primary);
        font-size: 13px;
        width: 170px;
        outline: none;
    }

    .search-input-wrap input:focus {
        border-color: var(--accent);
    }

    .search-count {
        font-size: 12px;
        color: var(--text-secondary);
        font-variant-numeric: tabular-nums;
        font-weight: 500;
        min-width: 32px;
    }

    /* Responsive */
    @media (max-width: 768px) {
        .header-center { display: none; }
        .reader-paper { padding: 1.5rem 1rem; }
        .floating-nav-btn { display: none; }
        .hide-mobile { display: none !important; }
    }
    """


def get_reader_header_html(
    doc_name: str,
    is_epub: bool = False,
    is_txt: bool = False,
    stats_text: Optional[str] = None,
    profile_id: Optional[str] = None
) -> str:
    safe_name = pyhtml.escape(doc_name)
    return_url = f"/?profile={urllib.parse.quote(profile_id)}" if profile_id else "/"
    epub_flow_btn = """
    <div class="layout-segmented" title="Layout Mode">
        <button id="btn-layout-single" class="layout-opt-btn active" data-layout-val="single" title="Single Page (1-Page)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            <span>1-Page</span>
        </button>
        <button id="btn-layout-double" class="layout-opt-btn" data-layout-val="double" title="Double Page (2-Page Spread, Shortcut: d)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path></svg>
            <span>2-Page</span>
        </button>
        <button id="btn-layout-scroll" class="layout-opt-btn" data-layout-val="scroll" title="Continuous Scroll (Fit Screen)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="7 13 12 18 17 13"></polyline><polyline points="7 6 12 11 17 6"></polyline></svg>
            <span>Scroll</span>
        </button>
    </div>
    """ if is_epub else ""

    txt_lines_btn = """
    <button id="btn-lines-toggle" class="header-btn hide-mobile" title="Toggle line numbers">
        <span># Lines</span>
    </button>
    """ if is_txt else ""

    return f"""
    <header class="calibre-header">
        <div class="header-group">
            <a href="{return_url}" class="header-btn" title="Return to Library">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
                <span>Library</span>
            </a>
            <button id="btn-toggle-toc" class="header-btn header-btn-primary" title="Table of Contents (t)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                <span>Contents</span>
                <span id="toc-badge" class="header-badge">0</span>
            </button>
        </div>

        <div class="header-center">
            <div class="doc-title" title="{safe_name}">{safe_name}</div>
            <div id="active-chapter-name" class="chapter-badge">Loading...</div>
        </div>

        <div class="header-group">
            <button id="btn-search-toggle" class="header-icon-btn" title="Search in document (Ctrl+F / f)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            </button>

            {epub_flow_btn}
            {txt_lines_btn}

            <div class="theme-segmented hide-mobile">
                <button data-theme-val="light" class="theme-opt-btn" title="Light theme">☀️</button>
                <button data-theme-val="sepia" class="theme-opt-btn" title="Sepia theme">📜</button>
                <button data-theme-val="dark" class="theme-opt-btn" title="Dark theme">🌙</button>
            </div>

            <div class="font-size-group hide-mobile">
                <button id="btn-font-dec" class="theme-opt-btn" title="Decrease font size (-)">A-</button>
                <span id="font-size-label" class="font-size-label" title="Reset font size">100%</span>
                <button id="btn-font-inc" class="theme-opt-btn" title="Increase font size (+)">A+</button>
            </div>

            <select id="select-font-family" class="header-select hide-mobile" title="Font family">
                <option value="serif">Serif</option>
                <option value="sans">Sans</option>
                <option value="mono">Mono</option>
            </select>

            <select id="select-width" class="header-select hide-mobile" title="Reading measure width">
                <option value="normal">Normal</option>
                <option value="wide">Wide</option>
                <option value="full">Full</option>
            </select>

            <button id="btn-fullscreen" class="header-icon-btn hide-mobile" title="Toggle Fullscreen">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
            </button>
        </div>
    </header>
    """


def get_reader_drawer_html() -> str:
    return """
    <div id="calibre-toc-drawer" class="calibre-toc-drawer">
        <div class="toc-drawer-header">
            <div class="toc-drawer-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                <span>Table of Contents</span>
            </div>
            <button id="btn-close-toc" class="header-icon-btn" title="Close (Esc)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
        </div>
        <div class="toc-filter-box">
            <input type="search" id="toc-filter-input" class="toc-filter-input" placeholder="Filter chapters..." autocomplete="off" />
        </div>
        <div id="calibre-toc-list" class="toc-list-container">
            <div class="toc-empty">Loading contents...</div>
        </div>
    </div>
    <div id="calibre-toc-overlay" class="calibre-toc-overlay"></div>
    """


def get_reader_footer_html(extra_stats: Optional[str] = None) -> str:
    stats_span = f'<span class="hide-mobile">• {pyhtml.escape(extra_stats)}</span>' if extra_stats else ""
    return f"""
    <footer class="calibre-footer">
        <div id="calibre-progress-track" class="calibre-progress-track" title="Click to seek">
            <div id="calibre-progress-fill" class="calibre-progress-fill">
                <div id="calibre-progress-tooltip" class="calibre-progress-tooltip">0%</div>
            </div>
        </div>

        <button id="btn-footer-prev" class="header-btn" title="Previous page / section (← / PageUp)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
            <span>Previous</span>
        </button>

        <div class="footer-status">
            <span id="footer-location-label">0%</span>
            {stats_span}
        </div>

        <button id="btn-footer-next" class="header-btn" title="Next page / section (→ / Space / PageDown)">
            <span>Next</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
        </button>
    </footer>

    <button id="floating-prev" class="floating-nav-btn floating-prev" title="Previous page (←)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
    </button>
    <button id="floating-next" class="floating-nav-btn floating-next" title="Next page (→ / Space)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
    </button>
    """


def get_reader_search_bar_html(query: Optional[str] = None) -> str:
    safe_q = pyhtml.escape(query or "")
    is_active = "active" if query else ""
    return f"""
    <div id="calibre-search-bar" class="calibre-search-bar {is_active}">
        <div class="search-input-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <input type="text" id="calibre-search-input" value="{safe_q}" placeholder="Search in document..." autocomplete="off" />
            <span id="calibre-search-count" class="search-count">0/0</span>
        </div>
        <button id="btn-search-prev" class="header-icon-btn" title="Previous match (Shift+Enter)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg>
        </button>
        <button id="btn-search-next" class="header-icon-btn" title="Next match (Enter)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </button>
        <button id="btn-search-close" class="header-icon-btn" title="Close search (Esc)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
    </div>
    """


def render_epub_viewer(doc_id: str, doc_name: str, query: Optional[str] = None, match_idx: int = 0, profile_id: Optional[str] = None) -> str:
    """Renders the comprehensive Calibre-like EPUB reader."""
    css = get_reader_css()
    header_html = get_reader_header_html(doc_name, is_epub=True, profile_id=profile_id)
    drawer_html = get_reader_drawer_html()
    footer_html = get_reader_footer_html()
    search_bar_html = get_reader_search_bar_html(query)

    safe_title = pyhtml.escape(doc_name)
    initial_query_js = f'"{pyhtml.escape(query)}"' if query else '""'

    template = """<!DOCTYPE html>
<html lang="en" data-theme="dark" data-font="serif" data-width="normal">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%%SAFE_TITLE%%</title>
    <link rel="icon" type="image/png" href="/favicon.png">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.5/jszip.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js"></script>
    <style>
        %%CSS%%
    </style>
</head>
<body>
    %%HEADER_HTML%%
    %%DRAWER_HTML%%

    <div id="epub-viewer-wrapper">
        <div id="epub-viewer"></div>
    </div>

    %%FOOTER_HTML%%
    %%SEARCH_BAR_HTML%%

    <script>
    (function() {
        const docId = "%%DOC_ID%%";
        const docName = "%%DOC_NAME%%";
        const initialQuery = %%INITIAL_QUERY_JS%%;
        const initialMatchIdx = %%INITIAL_MATCH_IDX%%;

        // Theme and Preferences
        let currentTheme = localStorage.getItem('docviewer_theme') || 'dark';
        let currentFont = localStorage.getItem('docviewer_font') || 'serif';
        let currentWidth = localStorage.getItem('docviewer_width') || 'normal';
        let currentFontSize = parseInt(localStorage.getItem('docviewer_font_size') || '100', 10);

        // Layout: 'single' (1-Page), 'double' (2-Page Spread), 'scroll' (Continuous)
        let currentLayout = localStorage.getItem('docviewer_epub_layout_' + docId) 
                         || localStorage.getItem('docviewer_epub_layout');
        if (!currentLayout) {
            const oldFlow = localStorage.getItem('docviewer_flow_' + docId) || localStorage.getItem('docviewer_flow');
            currentLayout = (oldFlow === 'scrolled-doc' || oldFlow === 'scrolled') ? 'scroll' : 'single';
        }

        let currentFlow = (currentLayout === 'scroll') ? 'scrolled-doc' : 'paginated';
        let currentSpread = (currentLayout === 'double') ? 'always' : 'none';

        const rootEl = document.documentElement;
        function applyPreferences() {
            rootEl.setAttribute('data-theme', currentTheme);
            rootEl.setAttribute('data-font', currentFont);
            rootEl.setAttribute('data-width', currentWidth);
            rootEl.setAttribute('data-layout', currentLayout);
            rootEl.setAttribute('data-flow', currentFlow);
            rootEl.setAttribute('data-spread', currentSpread);
            
            // Update layout segmented control
            document.querySelectorAll('.layout-opt-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-layout-val') === currentLayout);
            });

            // Update theme segmented control
            document.querySelectorAll('.theme-opt-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme-val') === currentTheme);
            });

            // Update font indicators
            const fontLabel = document.getElementById('font-size-label');
            if (fontLabel) fontLabel.textContent = currentFontSize + '%';

            const selectFont = document.getElementById('select-font-family');
            if (selectFont) selectFont.value = currentFont;

            const selectWidth = document.getElementById('select-width');
            if (selectWidth) {
                selectWidth.value = currentWidth;
                selectWidth.disabled = (currentLayout === 'scroll');
            }

            // Sync with EPUB rendition styles
            if (rendition) {
                applyEpubThemeRules();
            }
        }

        // Generate theme CSS to inject directly inside EPUB iframes to override hardcoded publisher styles
        function getEpubIframeCss() {
            const fontFamilies = {
                'serif': '"Literata", "Merriweather", "Georgia", "Cambria", serif',
                'sans': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif',
                'mono': '"JetBrains Mono", "Fira Code", monospace'
            };
            const font = fontFamilies[currentFont] || fontFamilies['serif'];

            let bg = '#ffffff', fg = '#1e293b', link = '#2563eb', hColor = '#0f172a', border = '#e2e8f0', codeBg = '#f8fafc', scrollThumb = '#cbd5e1';
            if (currentTheme === 'sepia') {
                bg = '#fbf0d9'; fg = '#3d2e1e'; link = '#92400e'; hColor = '#291e10'; border = '#e4d7bc'; codeBg = '#f1e3c7'; scrollThumb = '#d1c0a0';
            } else if (currentTheme === 'dark') {
                bg = '#111827'; fg = '#cbd5e1'; link = '#38bdf8'; hColor = '#f1f5f9'; border = '#1f2937'; codeBg = '#1e293b'; scrollThumb = '#334155';
            }

            const imgFilter = currentTheme === 'dark' ? 'filter: brightness(0.85) contrast(1.05) !important;' : '';
            const isPaged = (currentLayout !== 'scroll');
            const isDouble = (currentLayout === 'double');

            return `
                * {
                    box-sizing: border-box !important;
                    scrollbar-width: thin;
                    scrollbar-color: ${scrollThumb} ${bg};
                }
                ::-webkit-scrollbar {
                    width: 8px;
                    height: 8px;
                    background-color: ${bg};
                }
                ::-webkit-scrollbar-track {
                    background: ${bg};
                }
                ::-webkit-scrollbar-thumb {
                    background-color: ${scrollThumb};
                    border-radius: 4px;
                }
                ::-webkit-scrollbar-thumb:hover {
                    background-color: ${currentTheme === 'dark' ? '#475569' : '#94a3b8'};
                }
                html {
                    background-color: ${bg} !important;
                    color: ${fg} !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    width: 100% !important;
                    height: 100% !important;
                    overflow: ${isPaged ? 'hidden' : 'auto'} !important;
                }
                body {
                    background-color: ${bg} !important;
                    color: ${fg} !important;
                    font-family: ${font} !important;
                    font-size: ${currentFontSize}% !important;
                    line-height: 1.75 !important;
                    box-sizing: border-box !important;
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                    padding: ${isPaged ? (isDouble ? '28px 44px' : '28px 36px') : '36px 6%'} !important;
                    ${isPaged ? 'height: 100% !important;' : 'min-height: 100% !important; height: auto !important;'}
                }
                p, div, span, li, blockquote, td, th {
                    color: ${fg} !important;
                    font-family: inherit !important;
                    line-height: inherit !important;
                }
                h1, h2, h3, h4, h5, h6 {
                    color: ${hColor} !important;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                }
                a, a:visited {
                    color: ${link} !important;
                    text-decoration: underline !important;
                }
                img, svg, image {
                    max-width: 100% !important;
                    height: auto !important;
                    ${imgFilter}
                }
                table {
                    border-collapse: collapse !important;
                    width: 100% !important;
                }
                th, td {
                    border: 1px solid ${border} !important;
                    padding: 8px !important;
                }
                pre, code {
                    background: ${codeBg} !important;
                    border-radius: 4px;
                }
            `;
        }

        function applyEpubThemeRules() {
            if (!rendition) return;
            try {
                const css = getEpubIframeCss();
                rendition.getContents().forEach(contents => {
                    let styleEl = contents.document.getElementById('docviewer-epub-override');
                    if (!styleEl) {
                        styleEl = contents.document.createElement('style');
                        styleEl.id = 'docviewer-epub-override';
                        contents.document.head.appendChild(styleEl);
                    }
                    styleEl.textContent = css;
                });
            } catch(e) {
                console.error("Error updating EPUB themes:", e);
            }
        }

        // Initialize Book & Rendition
        const book = ePub("/file/" + docId + ".epub");
        let rendition = null;
        let isLocationsReady = false;
        let tocEntries = [];
        let savedCfi = localStorage.getItem('docviewer_epub_cfi_' + docId);

        let lastWheelTime = 0;
        function handleWheel(e) {
            if (currentLayout === 'scroll') return;
            if (Math.abs(e.deltaY) < 16) return;
            const now = Date.now();
            if (now - lastWheelTime < 260) {
                e.preventDefault();
                return;
            }
            lastWheelTime = now;
            e.preventDefault();
            if (e.deltaY > 0) {
                nextPage();
            } else {
                prevPage();
            }
        }

        function handleResize() {
            if (!rendition) return;
            const viewerEl = document.getElementById("epub-viewer");
            if (viewerEl) {
                const w = viewerEl.clientWidth;
                const h = viewerEl.clientHeight;
                if (w > 0 && h > 0) {
                    rendition.resize(w, h);
                }
            }
        }

        let resizeDebounce = null;
        window.addEventListener('resize', function() {
            clearTimeout(resizeDebounce);
            resizeDebounce = setTimeout(handleResize, 150);
        });

        function initRendition() {
            const viewerEl = document.getElementById("epub-viewer");
            viewerEl.innerHTML = "";

            const isScroll = (currentLayout === 'scroll');
            const isDouble = (currentLayout === 'double');

            rendition = book.renderTo("epub-viewer", {
                width: "100%",
                height: "100%",
                flow: isScroll ? "scrolled" : "paginated",
                manager: isScroll ? "continuous" : "default",
                spread: isDouble ? "always" : "none",
                minSpreadWidth: isDouble ? 600 : 99999
            });

            // Register content hook for continuous styling, mouse events, and keyboard shortcuts
            rendition.hooks.content.register(function(contents) {
                const target = contents.document.head || contents.document.body || contents.document.documentElement;
                const styleEl = contents.document.createElement('style');
                styleEl.id = 'docviewer-epub-override';
                styleEl.textContent = getEpubIframeCss();
                target.appendChild(styleEl);

                // Mouse wheel page flipping inside iframe
                contents.document.addEventListener('wheel', handleWheel, { passive: false });

                // Mouse click page navigation in left/right margins inside iframe
                contents.document.addEventListener('click', function(e) {
                    if (currentLayout === 'scroll') return;
                    try {
                        const sel = contents.window.getSelection();
                        if (sel && sel.toString().trim().length > 0) return;
                    } catch (err) {}
                    if (e.target.closest('a, button, input, textarea, select')) return;

                    const docWidth = contents.document.documentElement.clientWidth || contents.window.innerWidth;
                    const x = e.clientX;
                    if (x < docWidth * 0.22) {
                        e.preventDefault();
                        prevPage();
                    } else if (x > docWidth * 0.78) {
                        e.preventDefault();
                        nextPage();
                    }
                });

                contents.document.addEventListener('keydown', function(e) {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                    if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
                        e.preventDefault();
                        prevPage();
                    } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
                        e.preventDefault();
                        nextPage();
                    } else if (e.key === 't' || e.key === 'T') {
                        e.preventDefault();
                        toggleToc();
                    } else if (e.key === 'f' && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault();
                        toggleSearch();
                    } else if (e.key === 'Escape') {
                        closeToc();
                        closeSearch();
                    } else if (e.key === '=' || e.key === '+') {
                        e.preventDefault();
                        changeFontSize(10);
                    } else if (e.key === '-' || e.key === '_') {
                        e.preventDefault();
                        changeFontSize(-10);
                    } else if (e.key === 'i' || (e.altKey && e.key.toLowerCase() === 'i')) {
                        e.preventDefault();
                        cycleTheme();
                    } else if (e.key === 'd' || e.key === 'D') {
                        e.preventDefault();
                        changeLayout(currentLayout === 'double' ? 'single' : 'double');
                    }
                });
            });

            // Navigation relocation event
            rendition.on('relocated', function(location) {
                if (!location || !location.start) return;
                const cfi = location.start.cfi;
                localStorage.setItem('docviewer_epub_cfi_' + docId, cfi);

                // Update percentage
                if (isLocationsReady && book.locations) {
                    const pct = book.locations.percentageFromCfi(cfi);
                    const pctInt = Math.round(pct * 100);
                    updateProgressBar(pctInt);
                }

                // Update active TOC item & Chapter name
                updateActiveChapter(location.start.href);
            });

            // Display saved position or start
            if (savedCfi && !initialQuery) {
                rendition.display(savedCfi);
            } else {
                rendition.display();
            }
        }

        function updateProgressBar(pctInt) {
            pctInt = Math.max(0, Math.min(100, pctInt));
            const fill = document.getElementById('calibre-progress-fill');
            const tooltip = document.getElementById('calibre-progress-tooltip');
            const locLabel = document.getElementById('footer-location-label');
            if (fill) fill.style.width = pctInt + '%';
            if (tooltip) tooltip.textContent = pctInt + '%';
            if (locLabel) locLabel.textContent = pctInt + '%';
        }

        function updateActiveChapter(href) {
            if (!href || tocEntries.length === 0) return;
            const pureHref = href.split('#')[0];
            const fileHref = pureHref.split('/').pop();
            let activeItem = null;

            for (const item of tocEntries) {
                const itemPure = (item.href || '').split('#')[0];
                const itemFile = itemPure.split('/').pop();
                if (item.href === href || itemPure === pureHref || (itemFile && itemFile === fileHref)) {
                    activeItem = item;
                    break;
                }
            }

            if (activeItem) {
                const chapterEl = document.getElementById('active-chapter-name');
                if (chapterEl) chapterEl.textContent = activeItem.label;

                document.querySelectorAll('#calibre-toc-list .toc-item').forEach(el => {
                    const isCur = el.getAttribute('data-href') === activeItem.href;
                    el.classList.toggle('active', isCur);
                });
            }
        }

        // Build Table of Contents
        book.loaded.navigation.then(function(nav) {
            const listEl = document.getElementById('calibre-toc-list');
            listEl.innerHTML = '';
            tocEntries = [];

            function flattenAndRender(items, depth) {
                items.forEach(item => {
                    tocEntries.push({ href: item.href, label: (item.label || '').trim() });

                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'toc-item depth-' + Math.min(depth, 3);
                    itemDiv.setAttribute('data-href', item.href);
                    itemDiv.textContent = (item.label || '').trim() || 'Untitled Section';

                    itemDiv.addEventListener('click', function() {
                        rendition.display(item.href);
                        closeToc();
                    });

                    listEl.appendChild(itemDiv);

                    if (item.subitems && item.subitems.length > 0) {
                        flattenAndRender(item.subitems, depth + 1);
                    }
                });
            }

            if (nav.toc && nav.toc.length > 0) {
                flattenAndRender(nav.toc, 0);
                const badge = document.getElementById('toc-badge');
                if (badge) badge.textContent = tocEntries.length;
            } else {
                listEl.innerHTML = '<div class="toc-empty">No Table of Contents found in this book.</div>';
            }
        });

        // Generate Locations for percentage calculation
        book.ready.then(function() {
            return book.locations.generate(1024);
        }).then(function() {
            isLocationsReady = true;
            if (rendition && rendition.currentLocation()) {
                const cfi = rendition.currentLocation().start.cfi;
                const pct = book.locations.percentageFromCfi(cfi);
                updateProgressBar(Math.round(pct * 100));
            }
        });

        // Scrubbable Progress Bar
        const progressTrack = document.getElementById('calibre-progress-track');
        if (progressTrack) {
            progressTrack.addEventListener('click', function(e) {
                const rect = progressTrack.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const ratio = Math.max(0, Math.min(1, clickX / rect.width));
                if (isLocationsReady && book.locations) {
                    const cfi = book.locations.cfiFromPercentage(ratio);
                    if (cfi) rendition.display(cfi);
                }
            });
        }

        // Navigation actions
        function prevPage() {
            if (rendition) rendition.prev();
        }
        function nextPage() {
            if (rendition) rendition.next();
        }

        document.getElementById('btn-footer-prev')?.addEventListener('click', prevPage);
        document.getElementById('btn-footer-next')?.addEventListener('click', nextPage);
        document.getElementById('floating-prev')?.addEventListener('click', prevPage);
        document.getElementById('floating-next')?.addEventListener('click', nextPage);

        // Window-level wheel handler for paginated reading
        window.addEventListener('wheel', handleWheel, { passive: false });

        // Outer wrapper margin click navigation
        const wrapperEl = document.getElementById('epub-viewer-wrapper');
        if (wrapperEl) {
            wrapperEl.addEventListener('click', function(e) {
                if (currentLayout === 'scroll') return;
                if (e.target.closest('.calibre-header, .calibre-footer, .calibre-toc-drawer, .calibre-search-bar, .floating-nav-btn, button, a')) return;
                try {
                    const sel = window.getSelection();
                    if (sel && sel.toString().trim().length > 0) return;
                } catch(err) {}

                const rect = wrapperEl.getBoundingClientRect();
                const x = e.clientX - rect.left;
                if (x < rect.width * 0.5) {
                    prevPage();
                } else {
                    nextPage();
                }
            });
        }

        // Keyboard Shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                return;
            }
            if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
                e.preventDefault();
                prevPage();
            } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
                e.preventDefault();
                nextPage();
            } else if (e.key === 't' || e.key === 'T') {
                e.preventDefault();
                toggleToc();
            } else if (e.key === 'f' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                toggleSearch();
            } else if (e.key === 'Escape') {
                closeToc();
                closeSearch();
            } else if (e.key === '=' || e.key === '+') {
                e.preventDefault();
                changeFontSize(10);
            } else if (e.key === '-' || e.key === '_') {
                e.preventDefault();
                changeFontSize(-10);
            } else if (e.key === 'i' || (e.altKey && e.key.toLowerCase() === 'i')) {
                e.preventDefault();
                cycleTheme();
            } else if (e.key === 'd' || e.key === 'D') {
                e.preventDefault();
                changeLayout(currentLayout === 'double' ? 'single' : 'double');
            }
        });

        function cycleTheme() {
            const themes = ['light', 'sepia', 'dark'];
            const nextTheme = themes[(themes.indexOf(currentTheme) + 1) % themes.length];
            currentTheme = nextTheme;
            localStorage.setItem('docviewer_theme', currentTheme);
            applyPreferences();
        }

        // TOC Drawer toggling
        const drawer = document.getElementById('calibre-toc-drawer');
        const overlay = document.getElementById('calibre-toc-overlay');
        function toggleToc() {
            const isOpen = drawer.classList.contains('open');
            if (isOpen) closeToc(); else openToc();
        }
        function openToc() {
            drawer.classList.add('open');
            overlay.classList.add('open');
            const activeItem = document.querySelector('#calibre-toc-list .toc-item.active');
            if (activeItem) {
                activeItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            document.getElementById('toc-filter-input')?.focus();
        }
        function closeToc() {
            drawer.classList.remove('open');
            overlay.classList.remove('open');
        }
        document.getElementById('btn-toggle-toc')?.addEventListener('click', toggleToc);
        document.getElementById('btn-close-toc')?.addEventListener('click', closeToc);
        overlay?.addEventListener('click', closeToc);

        // TOC Filtering
        document.getElementById('toc-filter-input')?.addEventListener('input', function(e) {
            const val = (e.target.value || '').toLowerCase().trim();
            document.querySelectorAll('#calibre-toc-list .toc-item').forEach(item => {
                const text = (item.textContent || '').toLowerCase();
                item.style.display = text.includes(val) ? 'flex' : 'none';
            });
        });

        // Theme switching
        document.querySelectorAll('.theme-opt-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                currentTheme = btn.getAttribute('data-theme-val');
                localStorage.setItem('docviewer_theme', currentTheme);
                applyPreferences();
            });
        });

        // Font Family switching
        document.getElementById('select-font-family')?.addEventListener('change', function(e) {
            currentFont = e.target.value;
            localStorage.setItem('docviewer_font', currentFont);
            applyPreferences();
        });

        // Width switching
        document.getElementById('select-width')?.addEventListener('change', function(e) {
            currentWidth = e.target.value;
            localStorage.setItem('docviewer_width', currentWidth);
            applyPreferences();
            setTimeout(handleResize, 60);
        });

        // Font Size Adjustments
        function changeFontSize(delta) {
            currentFontSize = Math.max(70, Math.min(200, currentFontSize + delta));
            localStorage.setItem('docviewer_font_size', currentFontSize);
            applyPreferences();
        }
        document.getElementById('btn-font-dec')?.addEventListener('click', () => changeFontSize(-10));
        document.getElementById('btn-font-inc')?.addEventListener('click', () => changeFontSize(10));
        document.getElementById('font-size-label')?.addEventListener('click', () => {
            currentFontSize = 100;
            localStorage.setItem('docviewer_font_size', 100);
            applyPreferences();
        });

        // Layout Mode Switching (Single Page, Double Page, Continuous Scroll)
        function changeLayout(newLayout) {
            if (newLayout === currentLayout) return;

            try {
                if (rendition && rendition.currentLocation && rendition.currentLocation() && rendition.currentLocation().start) {
                    savedCfi = rendition.currentLocation().start.cfi;
                    localStorage.setItem('docviewer_epub_cfi_' + docId, savedCfi);
                }
            } catch(e) {}

            currentLayout = newLayout;
            localStorage.setItem('docviewer_epub_layout_' + docId, currentLayout);
            localStorage.setItem('docviewer_epub_layout', currentLayout);

            if (currentLayout === 'scroll') {
                currentFlow = 'scrolled-doc';
                currentSpread = 'none';
            } else if (currentLayout === 'double') {
                currentFlow = 'paginated';
                currentSpread = 'always';
            } else {
                currentLayout = 'single';
                currentFlow = 'paginated';
                currentSpread = 'none';
            }
            localStorage.setItem('docviewer_flow_' + docId, currentFlow);

            applyPreferences();
            initRendition();
        }

        document.querySelectorAll('.layout-opt-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const layoutVal = btn.getAttribute('data-layout-val');
                if (layoutVal) changeLayout(layoutVal);
            });
        });

        // Fullscreen
        document.getElementById('btn-fullscreen')?.addEventListener('click', function() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });

        // Search in EPUB
        let epubMatches = [];
        let currentEpubMatchIdx = -1;
        const searchBar = document.getElementById('calibre-search-bar');
        const searchInput = document.getElementById('calibre-search-input');
        const searchCount = document.getElementById('calibre-search-count');

        function toggleSearch() {
            if (searchBar.classList.contains('active')) {
                closeSearch();
            } else {
                openSearch();
            }
        }
        function openSearch() {
            searchBar.classList.add('active');
            searchInput.focus();
            searchInput.select();
            if (searchInput.value.trim()) {
                performEpubSearch(searchInput.value.trim(), 0);
            }
        }
        function closeSearch() {
            searchBar.classList.remove('active');
        }

        document.getElementById('btn-search-toggle')?.addEventListener('click', toggleSearch);
        document.getElementById('btn-search-close')?.addEventListener('click', closeSearch);

        function performEpubSearch(query, targetIdx) {
            if (!query || !query.trim()) {
                epubMatches = [];
                currentEpubMatchIdx = -1;
                searchCount.textContent = '0/0';
                return;
            }
            targetIdx = targetIdx || 0;
            epubMatches = [];
            currentEpubMatchIdx = -1;
            searchCount.textContent = 'Searching...';

            const promises = book.spine.spineItems.map(function(item) {
                return item.load(book.load.bind(book))
                    .then(function() { return item.find(query); })
                    .then(function(res) { item.unload(); return res; })
                    .catch(function() { return []; });
            });

            Promise.all(promises).then(function(nested) {
                epubMatches = [].concat.apply([], nested);
                searchCount.textContent = epubMatches.length > 0 ? (targetIdx + 1) + '/' + epubMatches.length : '0/0';
                if (epubMatches.length > 0) {
                    epubMatches.forEach(function(m) {
                        try {
                            rendition.annotations.highlight(m.cfi, {}, function() {}, "docviewer-match", { fill: "#fde047", "fill-opacity": "0.5" });
                        } catch(e) {}
                    });
                    goToEpubMatch(Math.min(targetIdx, epubMatches.length - 1));
                }
            }).catch(function(e) {
                console.error("EPUB Search failed:", e);
                searchCount.textContent = '0/0';
            });
        }

        function goToEpubMatch(idx) {
            if (epubMatches.length === 0) return;
            currentEpubMatchIdx = (idx + epubMatches.length) % epubMatches.length;
            const match = epubMatches[currentEpubMatchIdx];
            rendition.display(match.cfi);
            searchCount.textContent = (currentEpubMatchIdx + 1) + '/' + epubMatches.length;
        }

        document.getElementById('btn-search-prev')?.addEventListener('click', () => goToEpubMatch(currentEpubMatchIdx - 1));
        document.getElementById('btn-search-next')?.addEventListener('click', () => goToEpubMatch(currentEpubMatchIdx + 1));

        searchInput?.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) goToEpubMatch(currentEpubMatchIdx - 1);
                else goToEpubMatch(currentEpubMatchIdx + 1);
            } else if (e.key === 'Escape') {
                closeSearch();
            }
        });
        searchInput?.addEventListener('input', function() {
            performEpubSearch(searchInput.value, 0);
        });

        // Initialize Preferences and Reader
        applyPreferences();
        initRendition();

        if (initialQuery) {
            openSearch();
            performEpubSearch(initialQuery, initialMatchIdx);
        }
    })();
    </script>
</body>
</html>"""

    return (
        template
        .replace("%%SAFE_TITLE%%", safe_title)
        .replace("%%CSS%%", css)
        .replace("%%HEADER_HTML%%", header_html)
        .replace("%%DRAWER_HTML%%", drawer_html)
        .replace("%%FOOTER_HTML%%", footer_html)
        .replace("%%SEARCH_BAR_HTML%%", search_bar_html)
        .replace("%%DOC_ID%%", doc_id)
        .replace("%%DOC_NAME%%", pyhtml.escape(doc_name))
        .replace("%%INITIAL_QUERY_JS%%", initial_query_js)
        .replace("%%INITIAL_MATCH_IDX%%", str(match_idx))
    )


def render_html_document_viewer(
    doc_id: str,
    doc_name: str,
    ext: str,
    body_html: str,
    query: Optional[str] = None,
    match_idx: int = 0,
    extra_stats: Optional[str] = None,
    profile_id: Optional[str] = None
) -> str:
    """
    Renders unified Calibre-like paper reading experience for
    DOCX, ODT, ODF, Markdown, and TXT documents.
    """
    css = get_reader_css()
    is_txt = (ext == ".txt")
    header_html = get_reader_header_html(doc_name, is_epub=False, is_txt=is_txt, stats_text=extra_stats, profile_id=profile_id)
    drawer_html = get_reader_drawer_html()
    footer_html = get_reader_footer_html(extra_stats=extra_stats)
    search_bar_html = get_reader_search_bar_html(query)

    safe_title = pyhtml.escape(doc_name)
    initial_query_js = f'"{pyhtml.escape(query)}"' if query else '""'

    # Code highlighting for markdown
    highlight_includes = ""
    if ext == ".md":
        highlight_includes = """
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" id="hljs-light-theme">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" id="hljs-dark-theme" disabled>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
        """

    template = """<!DOCTYPE html>
<html lang="en" data-theme="dark" data-font="serif" data-width="normal">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%%SAFE_TITLE%%</title>
    <link rel="icon" type="image/png" href="/favicon.png">
    %%HIGHLIGHT_INCLUDES%%
    <style>
        %%CSS%%
    </style>
</head>
<body>
    %%HEADER_HTML%%
    %%DRAWER_HTML%%

    <main id="reader-main-viewport" class="reader-main-viewport">
        <div class="reader-paper-wrapper">
            <article id="reader-paper-content" class="reader-paper">
                %%BODY_HTML%%
            </article>
        </div>
    </main>

    %%FOOTER_HTML%%
    %%SEARCH_BAR_HTML%%

    <script>
    (function() {
        const docId = "%%DOC_ID%%";
        const docName = "%%DOC_NAME%%";
        const initialQuery = %%INITIAL_QUERY_JS%%;
        const initialMatchIdx = %%INITIAL_MATCH_IDX%%;
        const isMarkdown = %%IS_MARKDOWN%%;
        const isTxt = %%IS_TXT%%;

        // Theme & typography
        let currentTheme = localStorage.getItem('docviewer_theme') || 'dark';
        let currentFont = localStorage.getItem('docviewer_font') || (isTxt ? 'mono' : 'serif');
        let currentWidth = localStorage.getItem('docviewer_width') || 'normal';
        let currentFontSize = parseInt(localStorage.getItem('docviewer_font_size') || '100', 10);
        let showLineNumbers = false;

        const rootEl = document.documentElement;
        const viewport = document.getElementById('reader-main-viewport');
        const paperContent = document.getElementById('reader-paper-content');

        function applyPreferences() {
            rootEl.setAttribute('data-theme', currentTheme);
            rootEl.setAttribute('data-font', currentFont);
            rootEl.setAttribute('data-width', currentWidth);
            paperContent.style.fontSize = currentFontSize + '%';

            // Update theme segmented control
            document.querySelectorAll('.theme-opt-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme-val') === currentTheme);
            });

            // Update font indicators
            const fontLabel = document.getElementById('font-size-label');
            if (fontLabel) fontLabel.textContent = currentFontSize + '%';

            const selectFont = document.getElementById('select-font-family');
            if (selectFont) selectFont.value = currentFont;

            const selectWidth = document.getElementById('select-width');
            if (selectWidth) selectWidth.value = currentWidth;

            // Highlight.js stylesheet toggling for Markdown
            if (isMarkdown) {
                const lightTheme = document.getElementById('hljs-light-theme');
                const darkTheme = document.getElementById('hljs-dark-theme');
                if (lightTheme && darkTheme) {
                    if (currentTheme === 'dark') {
                        lightTheme.disabled = true;
                        darkTheme.disabled = false;
                    } else {
                        lightTheme.disabled = false;
                        darkTheme.disabled = true;
                    }
                }
            }
        }

        // Build Table of Contents dynamically from headings
        let tocItems = [];
        function buildDynamicToc() {
            const listEl = document.getElementById('calibre-toc-list');
            listEl.innerHTML = '';
            tocItems = [];

            const headings = Array.from(paperContent.querySelectorAll('h1, h2, h3, h4, .txt-section-heading'));

            if (headings.length > 0) {
                headings.forEach((heading, idx) => {
                    if (!heading.id) {
                        heading.id = 'heading-' + idx;
                    }

                    let depth = 0;
                    if (heading.tagName === 'H1') depth = 0;
                    else if (heading.tagName === 'H2') depth = 1;
                    else if (heading.tagName === 'H3') depth = 2;
                    else if (heading.tagName === 'H4') depth = 3;

                    const title = (heading.textContent || '').trim() || ('Section ' + (idx + 1));
                    tocItems.push({ id: heading.id, el: heading, title: title, depth: depth });

                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'toc-item depth-' + depth;
                    itemDiv.textContent = title;
                    itemDiv.setAttribute('data-target-id', heading.id);

                    itemDiv.addEventListener('click', function() {
                        heading.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        closeToc();
                    });

                    listEl.appendChild(itemDiv);
                });
            } else {
                // If document has no explicit headings, generate milestone markers
                const paragraphs = Array.from(paperContent.querySelectorAll('p, pre, div')).filter(p => (p.textContent || '').trim().length > 30);
                if (paragraphs.length > 3) {
                    const milestones = [
                        { label: 'Beginning', ratio: 0 },
                        { label: 'Quarter Point', ratio: 0.25 },
                        { label: 'Halfway Point', ratio: 0.5 },
                        { label: 'Three Quarters', ratio: 0.75 },
                        { label: 'Ending', ratio: 0.95 }
                    ];
                    milestones.forEach((m, idx) => {
                        const targetP = paragraphs[Math.floor(m.ratio * (paragraphs.length - 1))];
                        if (!targetP.id) targetP.id = 'milestone-' + idx;
                        tocItems.push({ id: targetP.id, el: targetP, title: m.label, depth: 0 });

                        const itemDiv = document.createElement('div');
                        itemDiv.className = 'toc-item depth-0';
                        itemDiv.textContent = m.label;
                        itemDiv.addEventListener('click', function() {
                            targetP.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            closeToc();
                        });
                        listEl.appendChild(itemDiv);
                    });
                } else {
                    listEl.innerHTML = '<div class="toc-empty">Entire document fits on one section.</div>';
                }
            }

            const badge = document.getElementById('toc-badge');
            if (badge) badge.textContent = tocItems.length;

            if (tocItems.length > 0) {
                const chapterEl = document.getElementById('active-chapter-name');
                if (chapterEl) chapterEl.textContent = tocItems[0].title;
            }
        }

        // Active Section tracking via scroll
        function updateActiveSectionOnScroll() {
            const scrollH = viewport.scrollHeight - viewport.clientHeight;
            const progress = scrollH > 0 ? (viewport.scrollTop / scrollH) : 0;
            const pct = Math.round(progress * 100);

            // Update Progress Bar
            const fill = document.getElementById('calibre-progress-fill');
            const tooltip = document.getElementById('calibre-progress-tooltip');
            const locLabel = document.getElementById('footer-location-label');
            if (fill) fill.style.width = pct + '%';
            if (tooltip) tooltip.textContent = pct + '%';
            if (locLabel) locLabel.textContent = pct + '%';

            // Save scroll position
            localStorage.setItem('docviewer_scroll_' + docId, progress);

            // Find current heading in view
            if (tocItems.length > 0) {
                let currentItem = tocItems[0];
                const viewportTop = viewport.scrollTop + 80;

                for (let i = 0; i < tocItems.length; i++) {
                    const item = tocItems[i];
                    if (item.el.offsetTop <= viewportTop) {
                        currentItem = item;
                    } else {
                        break;
                    }
                }

                const chapterEl = document.getElementById('active-chapter-name');
                if (chapterEl && currentItem) chapterEl.textContent = currentItem.title;

                document.querySelectorAll('#calibre-toc-list .toc-item').forEach(el => {
                    const isCur = el.getAttribute('data-target-id') === currentItem.id;
                    el.classList.toggle('active', isCur);
                    if (isCur) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            }
        }

        viewport.addEventListener('scroll', updateActiveSectionOnScroll, { passive: true });

        // Scrubbable Progress Bar
        const progressTrack = document.getElementById('calibre-progress-track');
        if (progressTrack) {
            progressTrack.addEventListener('click', function(e) {
                const rect = progressTrack.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const ratio = Math.max(0, Math.min(1, clickX / rect.width));
                const targetScroll = ratio * (viewport.scrollHeight - viewport.clientHeight);
                viewport.scrollTo({ top: targetScroll, behavior: 'smooth' });
            });
        }

        // Navigation (Page Up / Down)
        function pageUp() {
            viewport.scrollBy({ top: -viewport.clientHeight * 0.85, behavior: 'smooth' });
        }
        function pageDown() {
            viewport.scrollBy({ top: viewport.clientHeight * 0.85, behavior: 'smooth' });
        }

        document.getElementById('btn-footer-prev')?.addEventListener('click', pageUp);
        document.getElementById('btn-footer-next')?.addEventListener('click', pageDown);
        document.getElementById('floating-prev')?.addEventListener('click', pageUp);
        document.getElementById('floating-next')?.addEventListener('click', pageDown);

        // Keyboard Shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                return;
            }
            if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
                e.preventDefault();
                pageUp();
            } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
                e.preventDefault();
                pageDown();
            } else if (e.key === 't' || e.key === 'T') {
                e.preventDefault();
                toggleToc();
            } else if (e.key === 'f' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                toggleSearch();
            } else if (e.key === 'Escape') {
                closeToc();
                closeSearch();
            } else if (e.key === '=' || e.key === '+') {
                e.preventDefault();
                changeFontSize(10);
            } else if (e.key === '-' || e.key === '_') {
                e.preventDefault();
                changeFontSize(-10);
            } else if (e.key === 'i' || (e.altKey && e.key.toLowerCase() === 'i')) {
                e.preventDefault();
                cycleTheme();
            }
        });

        function cycleTheme() {
            const themes = ['light', 'sepia', 'dark'];
            const nextTheme = themes[(themes.indexOf(currentTheme) + 1) % themes.length];
            currentTheme = nextTheme;
            localStorage.setItem('docviewer_theme', currentTheme);
            applyPreferences();
        }

        // TOC Drawer controls
        const drawer = document.getElementById('calibre-toc-drawer');
        const overlay = document.getElementById('calibre-toc-overlay');
        function toggleToc() {
            const isOpen = drawer.classList.contains('open');
            if (isOpen) closeToc(); else openToc();
        }
        function openToc() {
            drawer.classList.add('open');
            overlay.classList.add('open');
            const activeItem = document.querySelector('#calibre-toc-list .toc-item.active');
            if (activeItem) {
                activeItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            document.getElementById('toc-filter-input')?.focus();
        }
        function closeToc() {
            drawer.classList.remove('open');
            overlay.classList.remove('open');
        }
        document.getElementById('btn-toggle-toc')?.addEventListener('click', toggleToc);
        document.getElementById('btn-close-toc')?.addEventListener('click', closeToc);
        overlay?.addEventListener('click', closeToc);

        // TOC Filtering
        document.getElementById('toc-filter-input')?.addEventListener('input', function(e) {
            const val = (e.target.value || '').toLowerCase().trim();
            document.querySelectorAll('#calibre-toc-list .toc-item').forEach(item => {
                const text = (item.textContent || '').toLowerCase();
                item.style.display = text.includes(val) ? 'flex' : 'none';
            });
        });

        // Theme switching
        document.querySelectorAll('.theme-opt-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                currentTheme = btn.getAttribute('data-theme-val');
                localStorage.setItem('docviewer_theme', currentTheme);
                applyPreferences();
            });
        });

        // Font Family switching
        document.getElementById('select-font-family')?.addEventListener('change', function(e) {
            currentFont = e.target.value;
            localStorage.setItem('docviewer_font', currentFont);
            applyPreferences();
        });

        // Width switching
        document.getElementById('select-width')?.addEventListener('change', function(e) {
            currentWidth = e.target.value;
            localStorage.setItem('docviewer_width', currentWidth);
            applyPreferences();
        });

        // Font Size Adjustments
        function changeFontSize(delta) {
            currentFontSize = Math.max(70, Math.min(200, currentFontSize + delta));
            localStorage.setItem('docviewer_font_size', currentFontSize);
            applyPreferences();
        }
        document.getElementById('btn-font-dec')?.addEventListener('click', () => changeFontSize(-10));
        document.getElementById('btn-font-inc')?.addEventListener('click', () => changeFontSize(10));
        document.getElementById('font-size-label')?.addEventListener('click', () => {
            currentFontSize = 100;
            localStorage.setItem('docviewer_font_size', 100);
            applyPreferences();
        });

        // Fullscreen
        document.getElementById('btn-fullscreen')?.addEventListener('click', function() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });

        // Toggle line numbers for plain text
        if (isTxt) {
            document.getElementById('btn-lines-toggle')?.addEventListener('click', function() {
                showLineNumbers = !showLineNumbers;
                document.querySelectorAll('.txt-line-num').forEach(el => {
                    el.style.display = showLineNumbers ? 'inline-block' : 'none';
                });
            });
        }

        // Full-Text DOM Search
        let currentMatches = [];
        let currentMatchIdx = -1;
        const searchBar = document.getElementById('calibre-search-bar');
        const searchInput = document.getElementById('calibre-search-input');
        const searchCount = document.getElementById('calibre-search-count');

        function toggleSearch() {
            if (searchBar.classList.contains('active')) closeSearch(); else openSearch();
        }
        function openSearch() {
            searchBar.classList.add('active');
            searchInput.focus();
            searchInput.select();
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim(), 0);
            }
        }
        function closeSearch() {
            searchBar.classList.remove('active');
            unhighlight();
        }

        document.getElementById('btn-search-toggle')?.addEventListener('click', toggleSearch);
        document.getElementById('btn-search-close')?.addEventListener('click', closeSearch);

        function unhighlight() {
            const marks = paperContent.querySelectorAll('mark.docviewer-match');
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
            currentMatchIdx = -1;
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
                if (tag !== 'script' && tag !== 'style' && tag !== 'mark') {
                    Array.from(node.childNodes).forEach(child => highlightText(child, queryLower));
                }
            }
        }

        function performSearch(query, targetIdx) {
            targetIdx = targetIdx || 0;
            unhighlight();
            if (!query || !query.trim()) {
                searchCount.textContent = '0/0';
                return;
            }
            highlightText(paperContent, query.trim().toLowerCase());
            if (currentMatches.length > 0) {
                goToMatch(Math.min(targetIdx, currentMatches.length - 1));
            } else {
                searchCount.textContent = '0/0';
            }
        }

        function goToMatch(idx) {
            if (currentMatches.length === 0) {
                searchCount.textContent = '0/0';
                return;
            }
            if (currentMatchIdx >= 0 && currentMatchIdx < currentMatches.length) {
                currentMatches[currentMatchIdx].classList.remove('docviewer-match-active');
            }
            currentMatchIdx = (idx + currentMatches.length) % currentMatches.length;
            const active = currentMatches[currentMatchIdx];
            active.classList.add('docviewer-match-active');
            active.scrollIntoView({ behavior: 'smooth', block: 'center' });
            searchCount.textContent = (currentMatchIdx + 1) + '/' + currentMatches.length;
        }

        document.getElementById('btn-search-prev')?.addEventListener('click', () => goToMatch(currentMatchIdx - 1));
        document.getElementById('btn-search-next')?.addEventListener('click', () => goToMatch(currentMatchIdx + 1));

        searchInput?.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) goToMatch(currentMatchIdx - 1);
                else goToMatch(currentMatchIdx + 1);
            } else if (e.key === 'Escape') {
                closeSearch();
            }
        });
        searchInput?.addEventListener('input', function() {
            performSearch(searchInput.value, 0);
        });

        // Initialize Preferences, Syntax Highlighting, TOC, and Resuming Position
        applyPreferences();
        if (isMarkdown && window.hljs) {
            hljs.highlightAll();
        }
        buildDynamicToc();

        // Resume saved scroll position if no active search
        const savedScroll = parseFloat(localStorage.getItem('docviewer_scroll_' + docId));
        if (!isNaN(savedScroll) && savedScroll > 0 && !initialQuery) {
            setTimeout(() => {
                viewport.scrollTop = savedScroll * (viewport.scrollHeight - viewport.clientHeight);
            }, 100);
        }

        if (initialQuery) {
            openSearch();
            performSearch(initialQuery, initialMatchIdx);
        }
    })();
    </script>
</body>
</html>"""

    return (
        template
        .replace("%%SAFE_TITLE%%", safe_title)
        .replace("%%CSS%%", css)
        .replace("%%HEADER_HTML%%", header_html)
        .replace("%%DRAWER_HTML%%", drawer_html)
        .replace("%%FOOTER_HTML%%", footer_html)
        .replace("%%SEARCH_BAR_HTML%%", search_bar_html)
        .replace("%%BODY_HTML%%", body_html)
        .replace("%%DOC_ID%%", doc_id)
        .replace("%%DOC_NAME%%", pyhtml.escape(doc_name))
        .replace("%%INITIAL_QUERY_JS%%", initial_query_js)
        .replace("%%INITIAL_MATCH_IDX%%", str(match_idx))
        .replace("%%HIGHLIGHT_INCLUDES%%", highlight_includes)
        .replace("%%IS_MARKDOWN%%", "true" if ext == ".md" else "false")
        .replace("%%IS_TXT%%", "true" if is_txt else "false")
    )
