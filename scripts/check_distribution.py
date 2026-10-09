"""Reject repository-only assets and private files in release archives."""

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check_distribution(archive: Path) -> None:
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as wheel:
            names = [entry.filename for entry in wheel.infolist() if not entry.is_dir()]
        allowed_root = {"METADATA", "WHEEL", "RECORD"}
        required = {"tunarag/__init__.py", "tunarag/py.typed"}
        prefix = ("tunarag",)
        metadata_suffix = ".dist-info"
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as source:
            members = [member for member in source.getmembers() if not member.isdir()]
        if any(not member.isfile() for member in members):
            raise ValueError("Source archive must not contain links or special files")
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1 or not next(iter(roots)).startswith("tunarag_python-"):
            raise ValueError(f"Unexpected source archive root: {roots}")
        names = [member.name for member in members]
        allowed_root = {"pyproject.toml", "README.md", "CHANGELOG.md", "PKG-INFO"}
        required = allowed_root | {"src/tunarag/__init__.py", "src/tunarag/py.typed"}
        allowed_root.add(".gitignore")
        prefix = ("src", "tunarag")
        metadata_suffix = ""
    else:
        raise ValueError(f"Unsupported archive: {archive}")
    invalid = []
    normalized = set()
    for name in names:
        original = PurePosixPath(name)
        path = original if metadata_suffix else PurePosixPath(*original.parts[1:])
        normalized.add(str(path))
        runtime = path.parts[: len(prefix)] == prefix and (
            path.suffix == ".py" or path.name == "py.typed"
        )
        metadata = (
            len(path.parts) == 2
            and path.parts[0].startswith("tunarag_python-")
            and path.parts[0].endswith(metadata_suffix)
            if metadata_suffix
            else len(path.parts) == 1
        ) and path.name in allowed_root
        if original.is_absolute() or ".." in original.parts or not (runtime or metadata):
            invalid.append(name)
    missing = required - normalized
    if invalid or missing:
        raise ValueError(f"{archive.name}: forbidden={invalid}, missing={sorted(missing)}")
    print(f"{archive.name}: {archive.stat().st_size:,} bytes; contents verified")


if __name__ == "__main__":
    distributions = sorted(Path(sys.argv[1] if len(sys.argv) > 1 else "dist").iterdir())
    if not distributions:
        raise SystemExit("No release archives found")
    for distribution in distributions:
        check_distribution(distribution)
