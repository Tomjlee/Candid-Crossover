#!/usr/bin/env python3
"""
Convert a WordPress WXR export into a static HTML site.

Outputs:
  - site/index.html (home)
  - site/<page-slug>/index.html (for each page; nested paths reflect parent pages)
  - site/blog/index.html and site/blog/<post-slug>/index.html (for posts, if any)
  - site/static/* (copied styles)
  - site/assets/* (optional downloaded media)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape


WXR_NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "wp": "http://wordpress.org/export/1.2/",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    # Decode HTML entities just in case
    value = html.unescape(value)
    # Replace non alphanumeric with hyphens
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "item"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class ContentItem:
    post_id: int
    post_type: str
    status: str
    title: str
    slug: str
    content_html: str
    date: Optional[dt.datetime]
    parent_id: Optional[int]
    menu_order: int
    categories: List[str] = field(default_factory=list)


def parse_wxr(input_xml: Path) -> Tuple[str, Dict[int, ContentItem]]:
    tree = ET.parse(str(input_xml))
    root = tree.getroot()

    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Invalid WXR: missing <channel>")

    site_title = (channel.findtext("title") or "").strip()

    items: Dict[int, ContentItem] = {}
    for item in channel.findall("item"):
        post_type = item.findtext("wp:post_type", default="", namespaces=WXR_NS) or ""
        post_status = item.findtext("wp:status", default="", namespaces=WXR_NS) or ""
        if post_type not in {"page", "post"}:
            # Skip attachments, nav_menu_item, etc.
            continue

        post_id_text = item.findtext("wp:post_id", default="", namespaces=WXR_NS) or "0"
        try:
            post_id = int(post_id_text)
        except ValueError:
            continue

        raw_title = item.findtext("title") or ""
        raw_slug = item.findtext("wp:post_name", default="", namespaces=WXR_NS) or ""
        raw_content = item.findtext("content:encoded", default="", namespaces=WXR_NS) or ""
        raw_date = item.findtext("wp:post_date", default="", namespaces=WXR_NS) or ""
        raw_parent = item.findtext("wp:post_parent", default="", namespaces=WXR_NS) or "0"
        raw_menu_order = item.findtext("wp:menu_order", default="0", namespaces=WXR_NS) or "0"

        try:
            parent_id = int(raw_parent)
        except ValueError:
            parent_id = 0
        parent_id = parent_id if parent_id > 0 else None

        try:
            menu_order = int(raw_menu_order)
        except ValueError:
            menu_order = 0

        parsed_date: Optional[dt.datetime] = None
        raw_date = (raw_date or "").strip()
        if raw_date:
            try:
                parsed_date = dt.datetime.fromisoformat(raw_date)
            except Exception:
                parsed_date = None

        categories: List[str] = []
        for cat in item.findall("category"):
            term = (cat.text or "").strip()
            if term:
                categories.append(term)

        title = raw_title.strip() or f"{post_type.title()} {post_id}"
        slug = (raw_slug.strip() or slugify(title)) or f"{post_type}-{post_id}"

        items[post_id] = ContentItem(
            post_id=post_id,
            post_type=post_type,
            status=post_status,
            title=title,
            slug=slug,
            content_html=raw_content,
            date=parsed_date,
            parent_id=parent_id,
            menu_order=menu_order,
            categories=categories,
        )

    return site_title, items


def build_hierarchy(items: Dict[int, ContentItem]) -> Tuple[List[ContentItem], List[ContentItem], Dict[int, List[int]]]:
    pages = [i for i in items.values() if i.post_type == "page" and i.status == "publish"]
    posts = [i for i in items.values() if i.post_type == "post" and i.status == "publish"]

    # Map parent -> children (for pages)
    children_by_parent: Dict[int, List[int]] = {}
    for page in pages:
        parent = page.parent_id or 0
        children_by_parent.setdefault(parent, []).append(page.post_id)

    # Order page children by menu_order then title
    for pid, lst in children_by_parent.items():
        lst.sort(key=lambda cid: (items[cid].menu_order, items[cid].title.lower()))

    posts.sort(key=lambda p: (p.date or dt.datetime.min), reverse=True)
    return pages, posts, children_by_parent


def compute_page_path(page: ContentItem, items: Dict[int, ContentItem]) -> Tuple[List[str], str]:
    # Build segments from ancestors -> current
    segments: List[str] = [page.slug]
    cursor = page
    chain_guard = 0
    while cursor.parent_id and chain_guard < 64:
        parent = items.get(cursor.parent_id)
        if not parent:
            break
        segments.append(parent.slug)
        cursor = parent
        chain_guard += 1
    segments = list(reversed(segments))
    rel_dir = "/".join(segments)
    url_path = f"{rel_dir}/index.html"
    return segments, url_path


def base_path_for_output(url_path: str) -> str:
    # "about/team/index.html" -> "../../"
    depth = url_path.count("/") - 1  # count folders
    if depth <= 0:
        return ""
    return "../" * depth


_SRC_HREF_RE = re.compile(r"""(?P<attr>\s(?:src|href))=(?P<q>['"])(?P<url>.*?)(?P=q)""", re.IGNORECASE)


def rewrite_and_download_assets(
    html_content: str,
    assets_dir: Path,
    should_download: bool,
) -> Tuple[str, List[str]]:
    downloaded: List[str] = []

    def replace(m: re.Match) -> str:
        attr = m.group("attr")
        quoted = m.group("q")
        url = (m.group("url") or "").strip()
        if not url or url.startswith(("data:", "mailto:", "tel:", "#")):
            return m.group(0)

        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path:
            filename = Path(parsed.path).name or "asset"
            safe_name = slugify(Path(filename).stem) + Path(filename).suffix.lower()
            local_rel = f"assets/{safe_name}"
            local_path = assets_dir / safe_name

            if should_download and not local_path.exists():
                try:
                    resp = requests.get(url, timeout=20)
                    resp.raise_for_status()
                    ensure_dir(assets_dir)
                    local_path.write_bytes(resp.content)
                    downloaded.append(url)
                except Exception:
                    # If download fails, keep original URL
                    return m.group(0)

            # Rewrite to local asset path regardless if we downloaded (only when should_download is True)
            if should_download:
                return f'{attr}={quoted}{local_rel}{quoted}'
            else:
                return m.group(0)
        return m.group(0)

    new_html = _SRC_HREF_RE.sub(replace, html_content)
    return new_html, downloaded


def copy_static(output_dir: Path, repo_root: Path) -> None:
    src_static = repo_root / "static"
    dst_static = output_dir / "static"
    ensure_dir(dst_static)
    for item in src_static.glob("**/*"):
        if item.is_file():
            rel = item.relative_to(src_static)
            target = dst_static / rel
            ensure_dir(target.parent)
            shutil.copy2(item, target)


def render_site(
    input_xml: Path,
    output_dir: Path,
    site_title_override: Optional[str],
    download_media: bool,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template_dir = repo_root / "templates"

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    page_tpl = env.get_template("page.html")
    post_tpl = env.get_template("post.html")
    base_tpl = env.get_template("base.html")  # for index rendering via include

    # Detect optional theme includes generated by mirror script
    theme_head_path = template_dir / "_head_includes.html"
    theme_footer_path = template_dir / "_footer_includes.html"
    def _has_nonempty(p: Path) -> bool:
        try:
            return p.exists() and p.read_text(encoding="utf-8").strip() != ""
        except Exception:
            return False
    has_theme_head = _has_nonempty(theme_head_path)
    has_theme_footer = _has_nonempty(theme_footer_path)

    site_title_from_wxr, items = parse_wxr(input_xml)
    pages, posts, children_by_parent = build_hierarchy(items)

    site_title = site_title_override or site_title_from_wxr or "Website"

    # Build top-level nav pages
    top_level_ids = children_by_parent.get(0, [])
    nav_pages: List[Dict[str, str]] = []
    for pid in top_level_ids:
        pg = items[pid]
        _, url_path = compute_page_path(pg, items)
        nav_pages.append({"title": pg.title, "url_path": url_path})

    # Prepare output
    ensure_dir(output_dir)
    copy_static(output_dir, repo_root)
    assets_dir = output_dir / "assets"

    current_year = dt.datetime.now().year

    # Render pages
    for page in pages:
        segments, url_path = compute_page_path(page, items)
        out_file = output_dir / url_path
        ensure_dir(out_file.parent)
        base_path = base_path_for_output(url_path)

        body_html = page.content_html or ""
        body_html, _ = rewrite_and_download_assets(body_html, assets_dir, download_media)

        html_out = page_tpl.render(
            page_title=page.title,
            site_title=site_title,
            nav_pages=nav_pages,
            base_path=base_path,
            current_year=current_year,
            theme_head=has_theme_head,
            theme_footer=has_theme_footer,
            title=page.title,
            body=body_html,
        )
        out_file.write_text(html_out, encoding="utf-8")

    # Render posts
    blog_dir = output_dir / "blog"
    ensure_dir(blog_dir)
    for post in posts:
        url_path = f"blog/{post.slug}/index.html"
        out_file = output_dir / url_path
        ensure_dir(out_file.parent)
        base_path = base_path_for_output(url_path)

        date_iso = post.date.isoformat() if post.date else ""
        date_human = post.date.strftime("%b %d, %Y") if post.date else ""

        body_html = post.content_html or ""
        body_html, _ = rewrite_and_download_assets(body_html, assets_dir, download_media)

        html_out = post_tpl.render(
            page_title=post.title,
            site_title=site_title,
            nav_pages=nav_pages,
            base_path=base_path,
            current_year=current_year,
            theme_head=has_theme_head,
            theme_footer=has_theme_footer,
            title=post.title,
            body=body_html,
            date_iso=date_iso,
            date_human=date_human,
            categories=post.categories,
        )
        out_file.write_text(html_out, encoding="utf-8")

    # Render blog index
    blog_index = output_dir / "blog" / "index.html"
    ensure_dir(blog_index.parent)
    blog_cards = []
    for post in posts:
        date_human = post.date.strftime("%b %d, %Y") if post.date else ""
        blog_cards.append(
            {
                "title": post.title,
                "href": f"blog/{post.slug}/index.html",
                "subtitle": date_human,
            }
        )
    base_path = base_path_for_output("blog/index.html")
    blog_html = env.from_string(
        """{% set content %}
<section>
  <h1>Blog</h1>
  {% if posts|length == 0 %}
    <p>No posts yet.</p>
  {% else %}
  <ul class="index-list">
    {% for p in posts %}
      <li class="index-card">
        <a href="{{ base_path }}{{ p.href }}">
          <h3>{{ p.title }}</h3>
          {% if p.subtitle %}<p>{{ p.subtitle }}</p>{% endif %}
        </a>
      </li>
    {% endfor %}
  </ul>
  {% endif %}
</section>
{% endset %}
{% include "base.html" with context %}
"""
    ).render(
        page_title="Blog",
        site_title=site_title,
        nav_pages=nav_pages,
        base_path=base_path,
        current_year=current_year,
        theme_head=has_theme_head,
        theme_footer=has_theme_footer,
        posts=blog_cards,
    )
    blog_index.write_text(blog_html, encoding="utf-8")

    # Render site index
    home_cards = []
    for pid in children_by_parent.get(0, []):
        pg = items[pid]
        _, page_url = compute_page_path(pg, items)
        subtitle = ""
        if pg.content_html:
            # take first 140 characters without tags as preview
            text = re.sub(r"<[^>]+>", "", pg.content_html or "")
            subtitle = (text.strip()[:140] + "…") if len(text.strip()) > 140 else text.strip()
        home_cards.append({"title": pg.title, "href": page_url, "subtitle": subtitle})

    latest_posts = []
    for post in posts[:6]:
        date_human = post.date.strftime("%b %d, %Y") if post.date else ""
        latest_posts.append(
            {"title": post.title, "href": f"blog/{post.slug}/index.html", "subtitle": date_human}
        )

    home_html = env.from_string(
        """{% set content %}
<section>
  <h1>Welcome</h1>
  {% if pages|length > 0 %}
  <h2>Pages</h2>
  <ul class="index-list">
    {% for p in pages %}
      <li class="index-card">
        <a href="{{ p.href }}">
          <h3>{{ p.title }}</h3>
          {% if p.subtitle %}<p>{{ p.subtitle }}</p>{% endif %}
        </a>
      </li>
    {% endfor %}
  </ul>
  {% endif %}

  <h2>Latest posts</h2>
  {% if posts|length == 0 %}
    <p>No posts yet.</p>
  {% else %}
  <ul class="index-list">
    {% for p in posts %}
      <li class="index-card">
        <a href="blog/{{ p.href.split('blog/', 1)[1] }}">
          <h3>{{ p.title }}</h3>
          {% if p.subtitle %}<p>{{ p.subtitle }}</p>{% endif %}
        </a>
      </li>
    {% endfor %}
  </ul>
  {% endif %}
</section>
{% endset %}
{% include "base.html" with context %}
"""
    ).render(
        page_title="Home",
        site_title=site_title,
        nav_pages=nav_pages,
        base_path="",
        current_year=current_year,
        theme_head=has_theme_head,
        theme_footer=has_theme_footer,
        pages=home_cards,
        posts=latest_posts,
    )
    (output_dir / "index.html").write_text(home_html, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert WordPress WXR export to static HTML site")
    parser.add_argument("input_xml", type=Path, help="Path to WordPress XML export (.xml)")
    parser.add_argument("-o", "--output", type=Path, default=Path("site"), help="Output directory (default: site)")
    parser.add_argument("--site-title", type=str, default=None, help="Override site title")
    parser.add_argument(
        "--download-media",
        action="store_true",
        help="Download external images/files to assets and rewrite content URLs",
    )
    args = parser.parse_args(argv)

    if not args.input_xml.exists():
        print(f"Input XML not found: {args.input_xml}", file=sys.stderr)
        return 2

    try:
        render_site(
            input_xml=args.input_xml,
            output_dir=args.output,
            site_title_override=args.site_title,
            download_media=args.download_media,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Done. Site generated at: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


