# -*- coding: utf-8 -*-
"""Git Ship GUI 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.main_window import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
