from __future__ import annotations

import hashlib
import json
from pathlib import Path

RULESET_PATH = Path(__file__).with_name("seams_ruleset.json")


def ruleset_bytes() -> bytes:
    return RULESET_PATH.read_bytes()


def ruleset_md5() -> str:
    return hashlib.md5(ruleset_bytes()).hexdigest()


def load_ruleset() -> dict:
    return json.loads(ruleset_bytes().decode("utf-8"))
