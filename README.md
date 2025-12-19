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

Match the original theme (mirror CSS/JS)
---------------------------------------
If you want the generated site to look exactly like the live site (same CSS/JS/fonts):

```powershell
# 1) Mirror the theme from your live URL (downloads CSS/JS to site\assets and writes template partials)
python .\scripts\mirror_theme.py "https://YOUR-LIVE-SITE.com"

# 2) Rebuild the site using your export (now templates will include the mirrored assets)
python .\scripts\wxr_to_html.py ".\Squarespace-Wordpress-Export-10-24-2025 (1).xml" --download-media --output .\site --site-title "My Site"
```

Notes:
- The mirror step writes `templates\_head_includes.html` and `templates\_footer_includes.html` and downloads assets into `site\assets`.
- The generator auto-detects those partials and includes them instead of the default stylesheet.
- If you already manually downloaded your theme assets, you can place them in `site\assets` and hand-edit `templates\_head_includes.html`/`_footer_includes.html` to reference them, e.g.:
  ```html
  <link rel="stylesheet" href="{{ base_path }}assets/theme.css">
  <script src="{{ base_path }}assets/theme.js" defer></script>
  ```

Offline-only workflow (no live URL)
-----------------------------------
If your site isn’t live but you have local CSS/JS files from the old theme:

```powershell
# Put all your theme files under site\assets (e.g., site\assets\theme.css, site\assets\main.js, etc.)

# Auto-generate the Jinja includes from what's in site\assets
python .\scripts\generate_theme_includes_from_assets.py --assets-dir .\site\assets --templates-dir .\templates

# Rebuild the site (uses the generated includes instead of the default stylesheet)
python .\scripts\wxr_to_html.py ".\Squarespace-Wordpress-Export-10-24-2025 (1).xml" --download-media --output .\site --site-title "My Site"
```

Tip: If you need a specific load order, rename files in `site\assets` so they sort alphabetically (e.g., `00-reset.css`, `10-theme.css`, `20-overrides.css`).

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


