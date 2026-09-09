def test_app_imports_and_has_main():
    import importlib.util
    import os

    p = os.path.join(os.path.dirname(__file__), "..", "app.py")
    spec = importlib.util.spec_from_file_location("app_mod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert hasattr(m, "main")
