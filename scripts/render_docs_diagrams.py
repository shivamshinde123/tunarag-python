from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

DIAGRAMS = Path(__file__).resolve().parents[1] / "docs" / "assets" / "diagrams"


def set_intrinsic_dimensions(content: str) -> str:
    root = ElementTree.fromstring(content)
    _, _, width, height = root.attrib["viewBox"].split()
    opening = re.search(r"<svg\b[^>]*>", content)
    if opening is None:
        raise ValueError("Rendered diagram has no SVG root")
    tag = opening.group()
    tag = re.sub(r'\s(?:width|height|style)="[^"]*"', "", tag)
    tag = tag[:-1] + f' width="{width}" height="{height}" style="background-color: white;">'
    return content[: opening.start()] + tag + content[opening.end() :]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Pages SVGs with explicit intrinsic sizes")
    parser.add_argument("--renderer", required=True, type=Path, help="Mermaid CLI src/cli.js path")
    parser.add_argument("--puppeteer-config", type=Path)
    args = parser.parse_args()
    for source in sorted(DIAGRAMS.glob("*.mmd")):
        output = source.with_suffix(".svg")
        if not output.exists():
            continue
        command = [
            "node",
            str(args.renderer),
            "-i",
            str(source),
            "-o",
            str(output),
            "--size",
            "1000",
            "-b",
            "white",
            "-t",
            "neutral",
        ]
        if args.puppeteer_config:
            command.extend(["-p", str(args.puppeteer_config)])
        subprocess.run(command, check=True)
        output.write_text(
            set_intrinsic_dimensions(output.read_text(encoding="utf-8")), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
