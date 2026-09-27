# coding: utf-8
"""Run the DLSS 5 protocol smoke test and the H3 Long Video selftest without ComfyUI.

    python_embeded/python.exe ComfyUI/custom_nodes/SergioNodes/selftest.py

The embedded Python does not put the working directory on sys.path, so this
wrapper exists instead of relying on `python -m dlss5.selftest`.
"""

from __future__ import annotations

UPSTREAM = None  # wrapper interno original de SergioNodes para los smoke tests del pack

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_SUITES = (
    ("DLSS5", "dlss5.selftest", "Smoke test del motor DLSS 5"),
    ("H3 Long Video", "h3_selftest", "Aritmética de latentes y pipeline de chunks de MiniMax H3"),
)


def main() -> int:
    exit_code = 0
    for label, module_name, description in _SUITES:
        print("=" * 68)
        print("{} — {}".format(label, description))
        print("=" * 68)
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # noqa: BLE001
            # Un pack opcional ausente no debe tumbar al resto.
            print("OMITIDO: no se pudo cargar {} ({}: {})".format(
                module_name, type(error).__name__, error))
            continue
        result = module.main() if hasattr(module, "main") else 0
        if result:
            exit_code = 1
        print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
