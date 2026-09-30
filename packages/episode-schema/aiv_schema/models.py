from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PIPELINE_DRAMA = "drama"
NODE_DN0 = "D-N0"
NODE_DN1 = "D-N1"
NODE_DN2 = "D-N2"
NODE_DN3 = "D-N3"
NODE_DN4 = "D-N4"
GATE_G1B = "g1b"
GATE_G2 = "g2"
GATE_G3 = "g3"

# D12–D15 hanging-surface defaults (reversible; chosen stays null — do not silent-pick).
HANGING_D12 = {
    "decision": "D12",
    "status": "pending_hanging",
    "reversible": True,
    "default_assumption": "project",
    "supported": ["project", "global"],
    "chosen": None,
    "silent_global_write": False,
}
HANGING_D13 = {
    "decision": "D13",
    "status": "pending_hanging",
    "reversible": True,
    "default_assumption": "manual_promote",
    "supported": ["auto", "manual"],
    "chosen": None,
    "auto_promote": False,
}
HANGING_D14 = {
    "decision": "D14",
    "status": "pending_hanging",
    "reversible": True,
    "default_assumption": "follow_d9",
    "supported": ["gitignore_object", "git_lfs", "d9_hybrid"],
    "chosen": None,
}
HANGING_D15 = {
    "decision": "D15",
    "status": "pending_hanging",
    "reversible": True,
    "default_assumption": "new_version_old_episodes_stable",
    "supported": ["same_char_versions", "new_char_id"],
    "chosen": None,
}

Lane = Literal["female", "male"]
LanePreference = Literal["female", "male", "unset"]
EpisodeStatus = Literal[
    "draft",
    "in_progress",
    "awaiting_g1b",
    "locked_g1b",
    "abandoned",
    "failed",
]
ProjectStatus = Literal["active", "archived"]
GateState = Literal["idle", "ready", "passed", "rejected"]
GateDecision = Literal["pass", "reject"]


class LibraryRef(BaseModel):
    id: str
    version: int = Field(ge=1)


class EpisodeLocks(BaseModel):
    g1b: bool = False
    g2: bool = False
    g3: bool = False


class EpisodeVersions(BaseModel):
    brief: int = 0
    outline: int = 0
    cast: int = 0
    storyboard: int = 0
    cards: int = 0
    episode: int = 1


class GateG1b(BaseModel):
    gate_id: Literal["g1b"] = "g1b"
    state: GateState = "idle"
    locked: bool = False
    version: int = 0
    last_decision: GateDecision | None = None
    note: str | None = None
    actor: str | None = None
    decided_at: str | None = None
