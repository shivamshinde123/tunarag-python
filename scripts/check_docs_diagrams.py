from __future__ import annotations

import argparse
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

SITE_URL = "https://shivamshinde123.github.io/tunarag-python/"


class DiagramParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.runtime_diagrams = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "mermaid" in (attributes.get("class") or "").split():
            self.runtime_diagrams += 1
        if tag == "img" and attributes.get("src"):
            self.images.append(str(attributes["src"]))


def validate_image(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"Missing documentation image: {path}")
    if path.suffix == ".svg":
        root = ElementTree.parse(path).getroot()
        namespace = "{http://www.w3.org/2000/svg}"
        if root.tag != f"{namespace}svg" or not root.get("viewBox"):
            raise ValueError(f"Invalid SVG canvas: {path}")
        if not root.get("width") or not root.get("height") or root.get("width") == "100%":
            raise ValueError(f"SVG requires explicit intrinsic dimensions: {path}")
        if not root.findall(f".//{namespace}path"):
            raise ValueError(f"SVG has no rendered diagram paths: {path}")
        if root.findall(f".//{namespace}script"):
            raise ValueError(f"SVG must not require JavaScript: {path}")
    elif path.suffix == ".png":
        header = path.read_bytes()[:24]
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG: {path}")
        width, height = struct.unpack(">II", header[16:24])
        if width == 0 or height == 0:
            raise ValueError(f"Empty PNG: {path}")


def check_site(site: Path) -> tuple[int, int]:
    site = site.resolve()
    pages = sorted(site.rglob("*.html"))
    if not pages:
        raise ValueError(f"No built documentation pages in {site}")
    images: set[Path] = set()
    for page in pages:
        parser = DiagramParser()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.runtime_diagrams:
            raise ValueError(f"Browser-dependent Mermaid diagram in {page}")
        for source in parser.images:
            if source.startswith(SITE_URL):
                image = site / unquote(urlsplit(source[len(SITE_URL) :]).path)
            else:
                url = urlsplit(source)
                if url.scheme or url.netloc:
                    continue
                image = (
                    site / unquote(url.path).lstrip("/")
                    if url.path.startswith("/")
                    else page.parent / unquote(url.path)
                )
            image = image.resolve()
            if not image.is_relative_to(site):
                raise ValueError(f"Image escapes documentation site: {source}")
            validate_image(image)
            images.add(image)
    if not images:
        raise ValueError("Documentation contains no images")
    return len(pages), len(images)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check built documentation image assets")
    parser.add_argument("site", nargs="?", type=Path, default=Path("site"))
    args = parser.parse_args()
    pages, images = check_site(args.site)
    print(f"Verified {images} image assets across {pages} documentation pages")


if __name__ == "__main__":
    main()
