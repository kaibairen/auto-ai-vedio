"""018d T-CI: OpenAPI ErrorCode ↔ handler raise sites ↔ bilingual catalog."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from aiv_drama.copy_contract import (
    DOCUMENTED_USER_FACING_HTTP,
    GAP_COPY_CODES,
    HTTP_ERROR_CODES,
    ISSUE_CODES,
    MESSAGES,
    N0N1_ERROR_CODES,
    N2_ERROR_CODES,
    REQUIRED_018D_HTTP,
)

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_N0N1 = ROOT / "openapi" / "drama-n0n1.v0.yaml"
OPENAPI_N2 = ROOT / "openapi" / "drama-n2.v0.yaml"
HANDLER_DIRS = (
    ROOT / "packages" / "drama-n0n1-core",
    ROOT / "apps" / "api",
)
WORKBENCH_JS = ROOT / "apps" / "workbench" / "drama.js"

APP_ERROR_RE = re.compile(
    r'AppError\(\s*[^,]+,\s*["\']([a-z][a-z0-9_]*)["\']',
    re.M,
)
RAISE_HARD_RE = re.compile(r'raise_hard\(\s*["\']([a-z][a-z0-9_]*)["\']', re.M)
CODE_LITERAL_RE = re.compile(
    r'["\']code["\']\s*:\s*["\']([a-z][a-z0-9_]*)["\']',
    re.M,
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _error_enum(doc: dict) -> set[str]:
    enum = doc["components"]["schemas"]["ErrorCode"]["enum"]
    return set(enum)


def _handler_codes() -> set[str]:
    found: set[str] = set()
    for folder in HANDLER_DIRS:
        for path in folder.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            found.update(APP_ERROR_RE.findall(text))
            found.update(RAISE_HARD_RE.findall(text))
            if path.name in {"app.py", "routes.py"}:
                found.update(CODE_LITERAL_RE.findall(text))
    return found


def test_openapi_version_stays_0_1_0():
    for path in (OPENAPI_N0N1, OPENAPI_N2):
        doc = _load_yaml(path)
        assert doc["info"]["version"] == "0.1.0"
        raw = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^  version: 0\.1\.0\s*$", raw)
        assert not re.search(r"(?m)^  version: 0\.2\.0\s*$", raw)
        assert "诚实" in raw or "018d" in raw


def test_c1_python_catalog_equals_openapi_enum():
    e_n0 = _error_enum(_load_yaml(OPENAPI_N0N1))
    e_n2 = _error_enum(_load_yaml(OPENAPI_N2))
    assert e_n0 == set(N0N1_ERROR_CODES)
    assert e_n2 == set(N2_ERROR_CODES)
    assert e_n0 | e_n2 == set(HTTP_ERROR_CODES)


def test_c2_handler_codes_subseteq_enum_and_enum_subseteq_handlers():
    e = _error_enum(_load_yaml(OPENAPI_N0N1)) | _error_enum(_load_yaml(OPENAPI_N2))
    h = _handler_codes()
    extra_handlers = h - e
    missing_raises = e - h
    assert extra_handlers == set(), f"handlers raise undeclared codes: {sorted(extra_handlers)}"
    assert missing_raises == set(), f"enum codes never raised by handlers: {sorted(missing_raises)}"


def test_c3_required_018d_codes_in_enum():
    e = _error_enum(_load_yaml(OPENAPI_N0N1)) | _error_enum(_load_yaml(OPENAPI_N2))
    missing = set(REQUIRED_018D_HTTP) - e
    assert missing == set(), missing
    n0 = _error_enum(_load_yaml(OPENAPI_N0N1))
    assert {"intent_unconfirmed", "intent_stale", "intent_lane_conflict"} <= n0
    n2 = _error_enum(_load_yaml(OPENAPI_N2))
    assert {"named_cast_gate", "duration_bucket_mismatch"} <= n2


def test_documented_user_facing_subseteq_enum():
    e = _error_enum(_load_yaml(OPENAPI_N0N1)) | _error_enum(_load_yaml(OPENAPI_N2))
    missing = set(DOCUMENTED_USER_FACING_HTTP) - e
    assert missing == set(), missing


def test_c4_bilingual_or_zh_for_catalog_and_gap_copy():
    for code in sorted(HTTP_ERROR_CODES | ISSUE_CODES | GAP_COPY_CODES | {"duration_below_camera_floor"}):
        row = MESSAGES[code]
        assert row["zh"].strip(), code
        assert row["en"].strip(), code
        assert not row["zh"].isascii() or code in {"duration_below_camera_floor"}, code
    zh_unset = MESSAGES["tool_profile_unset"]["zh"]
    assert "尚未选择出片工具" in zh_unset
    assert "可进下一出片节点" in zh_unset
    zh_mis = MESSAGES["duration_bucket_mismatch"]["zh"]
    assert "对不上" in zh_mis
    assert "工具档" in zh_mis
    assert "请先选择出片工具" in MESSAGES["ready_for_n4_requires_tool_profile"]["zh"]


def test_c5_no_force_pass_success_registration():
    e = _error_enum(_load_yaml(OPENAPI_N0N1)) | _error_enum(_load_yaml(OPENAPI_N2))
    assert "force_pass" not in e
    assert "force_pass_forbidden" in e
    assert "force_pass" not in MESSAGES
    js = WORKBENCH_JS.read_text(encoding="utf-8")
    assert "force_pass" not in js or "force_pass_forbidden" in js


def test_workbench_gap_copy_banners_wired():
    js = WORKBENCH_JS.read_text(encoding="utf-8")
    html = (ROOT / "apps" / "workbench" / "index.html").read_text(encoding="utf-8")
    assert "COPY_BANNERS" in js
    for code in (
        "tool_profile_unset",
        "duration_bucket_mismatch",
        "ready_for_n4_requires_tool_profile",
        "named_cast_gate",
        "intent_unconfirmed",
        "intent_stale",
        "intent_lane_conflict",
    ):
        assert code in js, code
    assert "尚未选择出片工具" in js
    assert "对不上当前工具档" in js
    assert "请先选择出片工具" in js
    assert "未入表的具名" in js
    assert "请先完成意图确认" in js
    assert 'id="cast-hint"' in html
    assert 'id="export-chip"' in html
    assert "出片：未选工具" in html
    assert "ready_for_n4" in html


def test_n2_issue_codes_documented_not_http_enum():
    n2 = _load_yaml(OPENAPI_N2)
    issue_enum = set(n2["components"]["schemas"]["ValidateIssueCode"]["enum"])
    http_enum = set(n2["components"]["schemas"]["ErrorCode"]["enum"])
    assert "tool_profile_unset" in issue_enum
    assert "tool_profile_unset" not in http_enum
    assert issue_enum == set(ISSUE_CODES)
