# -*- coding: utf-8 -*-
"""Git Ship CLI 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证以脚本方式运行时可找到包
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cli.app import main


if __name__ == "__main__":
    raise SystemExit(main())
