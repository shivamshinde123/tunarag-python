import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_docs_diagrams", ROOT / "scripts" / "check_docs_diagrams.py"
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
RENDER_SPEC = importlib.util.spec_from_file_location(
    "render_docs_diagrams", ROOT / "scripts" / "render_docs_diagrams.py"
)
assert RENDER_SPEC is not None and RENDER_SPEC.loader is not None
RENDERER = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(RENDERER)


def test_documentation_diagrams_are_static_and_have_editable_sources():
    diagrams = set()
    for page in (ROOT / "docs").rglob("*.md"):
        content = page.read_text(encoding="utf-8")
        assert "```mermaid" not in content, page
        for image in re.findall(r"!\[[^\]]*\]\(([^)]+\.svg)\)", content):
            path = page.parent / image
            CHECKER.validate_image(path)
            assert path.with_suffix(".mmd").is_file(), path
            diagrams.add(path.resolve())
    assert len(diagrams) == 10


@pytest.mark.parametrize("source", ["image.png", CHECKER.SITE_URL + "image.png"])
def test_built_site_resolves_relative_and_public_image_urls(tmp_path, source):
    (tmp_path / "index.html").write_text(f'<img src="{source}">', encoding="utf-8")
    (tmp_path / "image.png").write_bytes(
        (ROOT / "docs/assets/diagrams/optimization-loop.png").read_bytes()
    )
    assert CHECKER.check_site(tmp_path) == (1, 1)


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ('<pre class="mermaid">flowchart TD</pre>', "Browser-dependent"),
        ('<img src="missing.png">', "Missing documentation image"),
        ('<img src="../outside.png">', "escapes documentation"),
    ],
)
def test_built_site_rejects_broken_diagrams(tmp_path, html, message):
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        CHECKER.check_site(tmp_path)


def test_empty_svg_is_rejected(tmp_path):
    path = tmp_path / "empty.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1" width="1" height="1"/>'
    )
    with pytest.raises(ValueError, match="no rendered diagram paths"):
        CHECKER.validate_image(path)


def test_renderer_sets_intrinsic_dimensions_without_changing_labels():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        'style="max-height: 1000px;" viewBox="4 4 462 1224">'
        '<path d="M0 0L1 1"/><text>ADK pipeline</text></svg>'
    )
    rendered = RENDERER.set_intrinsic_dimensions(content)
    assert 'width="462" height="1224"' in rendered
    assert "max-height" not in rendered
    assert "ADK pipeline" in rendered
    assert RENDERER.set_intrinsic_dimensions(rendered) == rendered


def test_percentage_only_svg_is_rejected(tmp_path):
    path = tmp_path / "collapsed.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 1 10">'
        '<path d="M0 0L1 1"/></svg>'
    )
    with pytest.raises(ValueError, match="explicit intrinsic dimensions"):
        CHECKER.validate_image(path)
