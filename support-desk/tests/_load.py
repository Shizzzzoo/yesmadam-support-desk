"""Load a function's code.py by path so its pure helpers can be unit-tested."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_fn(function_name: str):
    path = os.path.join(ROOT, "functions", function_name, "code.py")
    spec = importlib.util.spec_from_file_location(f"fn_{function_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
