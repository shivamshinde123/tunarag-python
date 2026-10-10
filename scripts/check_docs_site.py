from __future__ import annotations

import argparse
import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

INTERNAL_PAGES = (
    "readme-example-verification",
    "live-integration-test-plan",
    "comprehensive-testing",
    "live-google-adk-testing",
    "quality-validation-plan",
    "reliability-validation",
    "multicorpus-validation",
    "product-requirements-document",
    "coding-conventions",
    "decision",
    "illustration-audit",
    "assets/diagrams/README",
    "ui-ux-wireframes",
    "file-folder-structure",
    "tech-stack",
    "usage-handbook",
)

SITE_URL = "https://shivamshinde123.github.io/tunarag-python/"
REDIRECT_TARGETS = {
    "readme-example-verification": "usage/#end-to-end-quickstart",
    "live-integration-test-plan": "usage/#evaluators-and-ragas",
    "comprehensive-testing": "usage/#production-checklist",
    "live-google-adk-testing": "usage/#google-adk-integration",
    "quality-validation-plan": "usage/#evaluators-and-ragas",
    "reliability-validation": "usage/#stopping-retries-and-concurrency",
    "multicorpus-validation": "usage/#evaluation-datasets",
    "product-requirements-document": "",
    "coding-conventions": "component-map/",
    "decision": "system-architecture-document/",
    "illustration-audit": "usage/#purpose-and-mental-model",
    "assets/diagrams/README": "system-architecture-document/",
    "ui-ux-wireframes": "usage/#running-optimization",
    "file-folder-structure": "component-map/",
    "tech-stack": "package-distribution/",
    "usage-handbook": "TunaRAG_Python_Usage_Handbook.docx",
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))


def redirect_html(name: str) -> str:
    target = "../" * len(name.split("/")) + REDIRECT_TARGETS[name]
    escaped = escape(target, quote=True)
    canonical = escape(urljoin(SITE_URL, REDIRECT_TARGETS[name]), quote=True)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="robots" content="noindex,follow">\n'
        f'<meta http-equiv="refresh" content="0; url={escaped}">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        "<title>Documentation page moved</title></head><body>\n"
        "<p>This page has been retired from the public documentation. "
        f'<a href="{escaped}">Continue to the current documentation</a>.</p>\n'
        "</body></html>\n"
    )


def write_redirects(site: Path) -> None:
    for name, target in REDIRECT_TARGETS.items():
        destination = site / urlsplit(target).path
        if not destination.is_file() and not (destination / "index.html").is_file():
            raise ValueError(f"Missing redirect destination: {target}")
        path = site / name / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redirect_html(name), encoding="utf-8")


def is_internal(location: str) -> bool:
    path = urlsplit(location).path.removeprefix("/tunarag-python/").strip("/")
    return any(path == name or path.startswith(name + "/") for name in INTERNAL_PAGES)


def check_public_site(site: Path) -> int:
    for name in INTERNAL_PAGES:
        page = site / name / "index.html"
        if (site / (name + ".md")).exists() or (
            page.exists() and page.read_text(encoding="utf-8") != redirect_html(name)
        ):
            raise ValueError(f"Internal page was published: {name}")
    for page in site.rglob("*.html"):
        parser = LinkParser()
        parser.feed(page.read_text(encoding="utf-8"))
        base = urljoin(SITE_URL, page.relative_to(site).as_posix())
        for href in parser.links:
            target = urljoin(base, href)
            url = urlsplit(target)
            root = urlsplit(SITE_URL)
            if url.netloc != root.netloc or not url.path.startswith(root.path):
                continue
            if is_internal(target):
                raise ValueError(f"Stale internal-page link in {page}: {href}")
            destination = (site / unquote(url.path[len(root.path) :])).resolve()
            if not destination.is_relative_to(site.resolve()) or (
                not destination.is_file() and not (destination / "index.html").is_file()
            ):
                raise ValueError(f"Broken documentation link in {page}: {href}")
    if list(site.rglob("*.mmd")):
        raise ValueError("Editable diagram sources must remain repository-only")
    for document in site.rglob("*.docx"):
        if document.name != "TunaRAG_Python_Usage_Handbook.docx":
            raise ValueError(f"Internal document was published: {document.name}")
    sitemap = ElementTree.parse(site / "sitemap.xml")
    locations = [
        element.text or ""
        for element in sitemap.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    ]
    search = json.loads((site / "search" / "search_index.json").read_text(encoding="utf-8"))
    indexed = [record["location"] for record in search["docs"]]
    for location in locations + indexed:
        if is_internal(location):
            raise ValueError(f"Internal page was indexed: {location}")
    return len(locations)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the public documentation boundary")
    parser.add_argument("site", nargs="?", type=Path, default=Path("site"))
    parser.add_argument("--write-redirects", action="store_true")
    args = parser.parse_args()
    if args.write_redirects:
        write_redirects(args.site)
    pages = check_public_site(args.site)
    print(f"Verified {pages} public pages; internal records excluded from publication and search")


if __name__ == "__main__":
    main()
