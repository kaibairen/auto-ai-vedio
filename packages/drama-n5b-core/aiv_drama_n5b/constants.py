"""N5b closed-set constants. Anchor: NOTE-AIV-036-N5B-API-SCOUT-v0."""

from __future__ import annotations

ARK_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
TASKS_PATH = "/contents/generations/tasks"
SEEDANCE_SKU_PRIMARY = "doubao-seedance-2-0-260128"
SEEDANCE_SKU_FAST = "doubao-seedance-2-0-fast-260128"
SEEDANCE_SKU_MINI = "doubao-seedance-2-0-mini-260615"
SEEDANCE_SKU_25 = "doubao-seedance-2-5-260628"
DEFAULT_RESOLUTION = "720p"
ALLOWED_DURATIONS = frozenset({5, 8, 10})
ASPECT_TO_RATIO = {
    "9:16": "9:16",
    "16:9": "16:9",
    "2.35:1": "21:9",
    "21:9": "21:9",
    "1:1": "1:1",
}
MAX_REF_IMAGES = 9
NEGATIVE_JOIN = "\n负面："
LIVE_JOB_ENV = "AIV_N5B_ALLOW_LIVE_JOB"
SKELETON_ID = "n5b-skeleton-v0"
TOOL_PROFILE_REQUIRED = "seedance_2"

# Persist / G5 refuse these payloads. Never generate them.
FAKE_PIXEL_MARKERS = (
    b"COLORBAR",
    b"colorbars",
    b"SMPTE_BARS",
    b"FAKE_PIXEL",
    b"fake-pixels",
)

G5_FORCE_MESSAGE = "ForcePass=never，禁止跳过门 G5"
G4_REQUIRED_MESSAGE = "门 G4 未锁定（或书面子集未过审），禁止 N5b submit"
LIVE_JOB_FORBIDDEN_MESSAGE = "N5b skeleton：默认禁真 Job POST（未设 AIV_N5B_ALLOW_LIVE_JOB）"
IMPL_HOLD_MESSAGE = "N5b IMPL HOLD：即便允许 live 标志，本骨架仍不 POST create task"
CLIPS_REQUIRED_MESSAGE = "门 G5 pass 需要 clips/<shot_id>.mp4 + .meta.json（SKU/job_id/md5），且 md5 与字节一致"
FAKE_PIXELS_MESSAGE = "禁假像素/彩条/静帧循环冒充 clips"
PROMPTS_REQUIRED_MESSAGE = "缺 EP##-prompts.jsonl；N5b 只映射已拼装行，不发明镜头"
