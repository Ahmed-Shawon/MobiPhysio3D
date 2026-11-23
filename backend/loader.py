"""Imports your existing training scripts by file path, without editing or copying them."""
import importlib.util
import sys
from pathlib import Path


def load_module(path: Path, unique_name: str, extra_sys_path: Path = None):
    """Load a .py file as a module under a unique name, so LSTM/ and GRU/ files
    with the same name (deep_tuning.py, pose_dataset.py) never clash."""
    if unique_name in sys.modules:
        return sys.modules[unique_name]
    if extra_sys_path is not None and str(extra_sys_path) not in sys.path:
        sys.path.insert(0, str(extra_sys_path))
    spec = importlib.util.spec_from_file_location(unique_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module
