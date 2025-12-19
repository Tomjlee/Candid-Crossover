#!/usr/bin/env python3
"""
Generate Jinja head/footer include partials from local CSS/JS assets.

Usage:
  python scripts/generate_theme_includes_from_assets.py --assets-dir site/assets --templates-dir templates

This writes:
  - templates/_head_includes.html (links to *.css)
  - templates/_footer_includes.html (scripts for *.js)
"""
from __future__ import annotations

import argparse
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Jinja include files from local assets")
    parser.add_argument("--assets-dir", type=Path, default=Path("site/assets"), help="Directory with local CSS/JS assets")
    parser.add_argument("--templates-dir", type=Path, default=Path("templates"), help="Templates directory")
    parser.add_argument("--head-template", type=str, default="_head_includes.html", help="Head partial filename")
    parser.add_argument("--footer-template", type=str, default="_footer_includes.html", help="Footer partial filename")
    args = parser.parse_args()

    css_files = sorted([p for p in args.assets_dir.glob("**/*.css") if p.is_file()])
    js_files = sorted([p for p in args.assets_dir.glob("**/*.js") if p.is_file()])

    head_lines: list[str] = []
    for css in css_files:
        rel_from_assets = css.relative_to(args.assets_dir).as_posix()
        head_lines.append(f'<link rel="stylesheet" href="{{{{ base_path }}}}assets/{rel_from_assets}">')

    footer_lines: list[str] = []
    for js in js_files:
        rel_from_assets = js.relative_to(args.assets_dir).as_posix()
        footer_lines.append(f'<script src="{{{{ base_path }}}}assets/{rel_from_assets}" defer></script>')

    ensure_dir(args.templates_dir)
    (args.templates_dir / args.head_template).write_text("\n".join(head_lines) + ("\n" if head_lines else ""), encoding="utf-8")
    (args.templates_dir / args.footer_template).write_text("\n".join(footer_lines) + ("\n" if footer_lines else ""), encoding="utf-8")

    print("Generated:")
    print(f"  {args.templates_dir / args.head_template} ({len(head_lines)} CSS)")
    print(f"  {args.templates_dir / args.footer_template} ({len(footer_lines)} JS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






