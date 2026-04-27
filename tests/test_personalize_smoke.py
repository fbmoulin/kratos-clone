"""Smoke test — package importable and version exposed."""


def test_package_importable():
    import personalize

    assert hasattr(personalize, "__version__")
    assert isinstance(personalize.__version__, str)
