import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_docs_site", ROOT / "scripts" / "check_docs_site.py"
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


@pytest.fixture
def public_site(tmp_path):
    (tmp_path / "search").mkdir()
    (tmp_path / "search/search_index.json").write_text(
        json.dumps({"docs": [{"location": "usage/#installation"}]}), encoding="utf-8"
    )
    (tmp_path / "sitemap.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://shivamshinde123.github.io/tunarag-python/usage/</loc></url>"
        "</urlset>",
        encoding="utf-8",
    )
    return tmp_path


def test_public_site_accepts_user_docs_and_handbook(public_site):
    (public_site / "TunaRAG_Python_Usage_Handbook.docx").touch()
    assert CHECKER.check_public_site(public_site) == 1


@pytest.mark.parametrize("surface", ["file", "search", "sitemap", "diagram", "document"])
def test_internal_publication_is_rejected(public_site, surface):
    if surface == "file":
        (public_site / "decision").mkdir()
        (public_site / "decision/index.html").touch()
    elif surface == "search":
        (public_site / "search/search_index.json").write_text(
            json.dumps({"docs": [{"location": "decision/#history"}]}), encoding="utf-8"
        )
    elif surface == "sitemap":
        path = public_site / "sitemap.xml"
        path.write_text(path.read_text().replace("usage/", "decision/"), encoding="utf-8")
    elif surface == "diagram":
        (public_site / "source.mmd").touch()
    else:
        (public_site / "internal.docx").touch()
    with pytest.raises(ValueError, match="Internal|repository-only"):
        CHECKER.check_public_site(public_site)


def test_internal_sources_are_retained_but_excluded_from_site():
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    nav = config.split("nav:", 1)[1].split("exclude_docs:", 1)[0]
    exclusions = config.split("exclude_docs:", 1)[1]
    for page in CHECKER.INTERNAL_PAGES:
        assert (ROOT / "docs" / (page + ".md")).is_file()
        assert page + ".md" in exclusions
        assert page + ".md" not in nav


def test_usage_guide_reuses_all_examples_without_readme_preamble():
    usage = (ROOT / "docs/usage.md").read_text(encoding="utf-8")
    assert 'include-markdown "../README.md" start="## Purpose and mental model"' in usage
    assert "TunaRAG_Python_Usage_Handbook.docx" in usage
