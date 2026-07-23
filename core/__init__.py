# -*- coding: utf-8 -*-
"""git-ship 核心逻辑包。"""

from core.git_ops import GitResult
from core.workflow import WorkflowResult, bootstrap, ship

__all__ = [
    "GitResult",
    "WorkflowResult",
    "bootstrap",
    "ship",
]
