from importlib import import_module
from pathlib import Path


def test_public_package_imports() -> None:
    package = import_module("tunarag")

    assert package.__version__ == "0.1.0"
    assert Path(package.__file__).with_name("py.typed").is_file()
