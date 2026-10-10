import importlib.util
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

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


@pytest.mark.parametrize(
    "href",
    [
        "../comprehensive-testing/#results",
        CHECKER.SITE_URL + "decision/",
        "/tunarag-python/live-google-adk-testing/",
        "//shivamshinde123.github.io/tunarag-python/tech-stack/",
    ],
)
def test_stale_sidebar_or_body_links_are_rejected(public_site, href):
    (public_site / "usage").mkdir()
    (public_site / "usage/index.html").write_text(
        f'<nav><a href="{href}">Old page</a></nav>', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Stale internal-page link"):
        CHECKER.check_public_site(public_site)


def test_repository_source_links_are_not_retired_site_links(public_site):
    (public_site / "index.html").write_text(
        '<a href="https://github.com/shivamshinde123/tunarag-python/blob/main/docs/decision.md">'
        "Repository record</a>",
        encoding="utf-8",
    )
    assert CHECKER.check_public_site(public_site) == 1


def test_all_retired_urls_have_noindex_redirects_to_existing_public_targets(public_site):
    for target in CHECKER.REDIRECT_TARGETS.values():
        destination = public_site / urlsplit(target).path
        if destination.suffix == ".docx":
            destination.touch()
        else:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "index.html").touch()
    CHECKER.write_redirects(public_site)
    assert set(CHECKER.REDIRECT_TARGETS) == set(CHECKER.INTERNAL_PAGES)
    for name, target in CHECKER.REDIRECT_TARGETS.items():
        path = public_site / name / "index.html"
        content = path.read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex,follow">' in content
        assert 'http-equiv="refresh"' in content
        parser = CHECKER.LinkParser()
        parser.feed(content)
        base = urljoin(CHECKER.SITE_URL, name + "/")
        assert urljoin(base, parser.links[0]) == urljoin(CHECKER.SITE_URL, target)
    assert CHECKER.check_public_site(public_site) == 1
    path.write_text(content + "<p>Internal content must not be republished.</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="Internal page was published"):
        CHECKER.check_public_site(public_site)


def test_missing_redirect_destinations_are_rejected(public_site):
    with pytest.raises(ValueError, match="Missing redirect destination"):
        CHECKER.write_redirects(public_site)


def test_navigation_loads_fresh_sidebar_on_each_page():
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "navigation.instant" not in config


@pytest.mark.parametrize("href", ["missing/", CHECKER.SITE_URL + "missing/", "missing.docx"])
def test_missing_public_link_targets_are_rejected(public_site, href):
    (public_site / "index.html").write_text(f'<a href="{href}">Broken link</a>', encoding="utf-8")
    with pytest.raises(ValueError, match="Broken documentation link"):
        CHECKER.check_public_site(public_site)
