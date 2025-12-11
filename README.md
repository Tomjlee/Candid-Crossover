Static HTML site generator from WordPress (Squarespace export)
==============================================================

This project converts a WordPress WXR export file (the XML you exported from Squarespace → WordPress) into a clean, static HTML site with page and blog templates.

What you get
------------
- Pages preserved in nested folders (e.g., `about/team/index.html`)
- Blog posts under `blog/<slug>/index.html` and a `blog/index.html`
- Simple, responsive styles in `static/styles.css`
- Optional media downloading and URL rewriting to local `assets/`

Prerequisites
-------------
- Python 3.9+ installed

Quick start (Windows PowerShell)
--------------------------------
1) Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies:

```powershell
pip install -r requirements.txt
```

3) Run the converter:

```powershell
python .\scripts\wxr_to_html.py "Squarespace-Wordpress-Export-10-24-2025 (1).xml" --download-media --site-title "My Site"
```

Flags:
- `--output PATH` (default `site`) to choose the output folder
- `--site-title "Title"` to override the title from the XML
- `--download-media` to download remote images/files to `assets/` and rewrite URLs

4) Open your site:
- Double-click `site\index.html` or open it in your browser

Notes and limitations
---------------------
- Navigation uses top-level published pages ordered by WordPress `menu_order` then title.
- Page hierarchy is preserved for nested pages using parent relationships.
- Posts are dated if timestamps exist in the export.
- Media download tries to fetch any `http(s)` URLs found in `src` or `href` attributes; if a download fails, the original URL is retained.

Project layout
--------------
- `scripts/wxr_to_html.py`: converter script
- `templates/`: base, page, and post templates
- `static/`: stylesheet copied to the site output
- `site/`: generated output (created after you run the script)


