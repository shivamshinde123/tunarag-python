from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
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


def is_internal(location: str) -> bool:
    path = urlsplit(location).path.removeprefix("/tunarag-python/").strip("/")
    return any(path == name or path.startswith(name + "/") for name in INTERNAL_PAGES)


def check_public_site(site: Path) -> int:
    for name in INTERNAL_PAGES:
        if (site / name / "index.html").exists() or (site / (name + ".md")).exists():
            raise ValueError(f"Internal page was published: {name}")
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
    args = parser.parse_args()
    pages = check_public_site(args.site)
    print(f"Verified {pages} public pages; internal records excluded from publication and search")


if __name__ == "__main__":
    main()
