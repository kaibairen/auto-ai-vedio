"""D12–D15 hanging surface. Defaults are reversible; chosen stays null."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_schema.models import HANGING_D12, HANGING_D13, HANGING_D14, HANGING_D15


def hanging_bundle() -> dict[str, Any]:
    return {
        "d12_scope": deepcopy(HANGING_D12),
        "d13_promote": deepcopy(HANGING_D13),
        "d14_assets": deepcopy(HANGING_D14),
        "d15_fork": deepcopy(HANGING_D15),
        "note": (
            "待挂起面：实现表达 project_scope 能力与默认可覆盖假设，"
            "不静默替选 D12–D15；无静默 auto-promote。"
        ),
    }


def project_scope_capability() -> dict[str, Any]:
    return deepcopy(HANGING_D12)


def default_project_scope() -> str:
    """Reversible default assumption (not a silent D12 product choice)."""
    return "project"
