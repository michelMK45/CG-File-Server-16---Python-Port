"""Memory.list_module_paths: the OS module list of the attached process (no memory access)."""
from __future__ import annotations

import os
import sys

from server16_py.memory_access import Memory


def test_not_attached_returns_empty_list():
    memory = Memory()
    assert memory.process_id == 0
    assert memory.list_module_paths() == []


def test_lists_modules_of_a_live_process():
    memory = Memory()
    memory.process_id = os.getpid()
    paths = [os.path.normcase(path) for path in memory.list_module_paths()]
    # a venv python.exe is a launcher: the running exe is the base interpreter, same file name
    assert os.path.basename(os.path.normcase(sys.executable)) in {os.path.basename(p) for p in paths}
    assert any(path.endswith(".dll") for path in paths)


def test_base_address_lookup_unchanged():
    memory = Memory()
    memory.process_id = os.getpid()
    assert memory._get_base_address(sys.executable) != 0
    assert memory._get_base_address(None) != 0   # no name -> first module, as before
    assert memory._get_base_address("definitely-not-loaded.exe") == 0
