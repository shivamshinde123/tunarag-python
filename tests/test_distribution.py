import io
import runpy
import tarfile
import zipfile
from pathlib import Path

import pytest

check_distribution = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "check_distribution.py")
)["check_distribution"]


@pytest.mark.parametrize("source", [False, True])
@pytest.mark.parametrize("extra", [None, "tests/test_example.py", ".env", "docs/image.png"])
@pytest.mark.parametrize("include_license", [False, True])
def test_distribution_allowlist(
    tmp_path: Path, source: bool, extra: str | None, include_license: bool
) -> None:
    if source:
        archive = tmp_path / "tunarag_python-0.3.0.tar.gz"
        names = [
            "src/tunarag/__init__.py",
            "src/tunarag/py.typed",
            "pyproject.toml",
            "README.md",
            "CHANGELOG.md",
            "PKG-INFO",
        ]
        if include_license:
            names.append("LICENSE")
        if extra:
            names.append(extra)
        with tarfile.open(archive, "w:gz") as output:
            for name in names:
                member = tarfile.TarInfo("tunarag_python-0.3.0/" + name)
                member.size = 1
                output.addfile(member, io.BytesIO(b"x"))
    else:
        archive = tmp_path / "tunarag_python-0.3.0-py3-none-any.whl"
        names = ["tunarag/__init__.py", "tunarag/py.typed"]
        names += [
            "tunarag_python-0.3.0.dist-info/" + name for name in ("METADATA", "WHEEL", "RECORD")
        ]
        if include_license:
            names.append("tunarag_python-0.3.0.dist-info/licenses/LICENSE")
        if extra:
            names.append(extra)
        with zipfile.ZipFile(archive, "w") as output:
            for name in names:
                output.writestr(name, "x")
    if extra or not include_license:
        with pytest.raises(ValueError, match="forbidden" if extra else "missing"):
            check_distribution(archive)
    else:
        check_distribution(archive)


def test_repository_license_has_disclaimers() -> None:
    license_text = (Path(__file__).parents[1] / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License")
    assert 'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY' in license_text
    assert "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM" in license_text
