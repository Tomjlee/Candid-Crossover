#!/usr/bin/env python3
"""
Mirror a site's theme assets (CSS/JS) from a live URL and produce Jinja partials
that the generator can include to replicate the original look.

Outputs:
  - templates/_head_includes.html
  - templates/_footer_includes.html
  - site/assets/* (downloaded CSS/JS/fonts if directly referenced)
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "asset"
    # basic cleanup
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name)
    return name


def download(url: str, target: Path) -> bool:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        ensure_dir(target.parent)
        target.write_bytes(resp.content)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror theme assets from a live URL")
    parser.add_argument("url", help="Public URL of your live site (homepage recommended)")
    parser.add_argument("--assets-dir", type=Path, default=Path("site/assets"), help="Directory to store downloaded assets")
    parser.add_argument("--templates-dir", type=Path, default=Path("templates"), help="Templates directory")
    parser.add_argument("--head-template", type=str, default="_head_includes.html", help="Head partial filename")
    parser.add_argument("--footer-template", type=str, default="_footer_includes.html", help="Footer partial filename")
    parser.add_argument("--no-download", action="store_true", help="Do not download assets, keep remote URLs")
    args = parser.parse_args()

    resp = requests.get(args.url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    head = soup.find("head") or soup
    body = soup.find("body") or soup

    # Collect head links and scripts
    head_links = head.find_all("link")
    head_scripts = head.find_all("script", src=True)
    body_scripts = body.find_all("script", src=True)

    downloaded_map = {}  # remote_url -> local_relative

    def mirror_src_or_href(tag, attr: str) -> str:
        url = tag.get(attr) or ""
        if not url:
            return ""
        full = urljoin(args.url, url)
        if args.no-download:
            return full
        name = safe_name_from_url(full)
        local_rel = f"assets/{name}"
        local_path = args.assets_dir / name
        if full not in downloaded_map:
            if download(full, local_path):
                downloaded_map[full] = local_rel
            else:
                downloaded_map[full] = full  # fallback to remote
        return downloaded_map[full]

    # Build head partial
    head_lines: list[str] = []
    for ln in head_links:
        rel = (ln.get("rel") or [])
        rel_lower = [r.lower() for r in rel]
        if "stylesheet" in rel_lower or ln.get("as") in ("style", "font") or ln.get("href"):
            href = mirror_src_or_href(ln, "href")
            if not href:
                continue
            # use Jinja base_path prefix for local
            if href.startswith("assets/"):
                href = "{{ base_path }}" + href
            # replicate important attributes
            attrs = []
            for k in ("rel", "as", "type", "crossorigin", "media", "integrity", "referrerpolicy"):
                v = ln.get(k)
                if v:
                    if isinstance(v, list):
                        v = " ".join(v)
                    attrs.append(f'{k}="{v}"')
            attrs_str = " ".join(attrs) if attrs else 'rel="stylesheet"'
            head_lines.append(f'<link {attrs_str} href="{href}">')

    for sc in head_scripts:
        src = mirror_src_or_href(sc, "src")
        if not src:
            continue
        if src.startswith("assets/"):
            src = "{{ base_path }}" + src
        attrs = []
        for k in ("type", "crossorigin", "defer", "async", "integrity", "referrerpolicy"):
            if sc.has_attr(k):
                v = sc.get(k)
                if v is True or v is None:
                    attrs.append(k)
                else:
                    attrs.append(f'{k}="{v}"')
        attrs_str = " ".join(attrs) if attrs else ""
        if attrs_str:
            head_lines.append(f'<script src="{src}" {attrs_str}></script>')
        else:
            head_lines.append(f'<script src="{src}"></script>')

    # Build footer partial from body scripts
    footer_lines: list[str] = []
    for sc in body_scripts:
        src = mirror_src_or_href(sc, "src")
        if not src:
            continue
        if src.startswith("assets/"):
            src = "{{ base_path }}" + src
        attrs = []
        for k in ("type", "crossorigin", "defer", "async", "integrity", "referrerpolicy"):
            if sc.has_attr(k):
                v = sc.get(k)
                if v is True or v is None:
                    attrs.append(k)
                else:
                    attrs.append(f'{k}="{v}"')
        attrs_str = " ".join(attrs) if attrs else ""
        if attrs_str:
            footer_lines.append(f'<script src="{src}" {attrs_str}></script>')
        else:
            footer_lines.append(f'<script src="{src}"></script>')

    # Write partials
    ensure_dir(args.templates_dir)
    (args.templates_dir / args.head_template).write_text("\n".join(head_lines) + ("\n" if head_lines else ""), encoding="utf-8")
    (args.templates_dir / args.footer_template).write_text("\n".join(footer_lines) + ("\n" if footer_lines else ""), encoding="utf-8")

    print("Theme partials written:")
    print(f"  {args.templates_dir / args.head_template}")
    print(f"  {args.templates_dir / args.footer_template}")
    if not args.no-download:
        print(f"Assets downloaded to: {args.assets_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






