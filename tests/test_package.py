from importlib import import_module


def test_public_package_imports() -> None:
    package = import_module("tunarag")

    assert package.__version__ == "0.1.0.dev0"