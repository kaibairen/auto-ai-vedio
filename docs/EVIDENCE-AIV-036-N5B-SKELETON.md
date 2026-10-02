# EVIDENCE · AIV-036-ENG-N5B-SKELETON

| 项 | 值 |
|----|----|
| ASSIGN | AIV-036-ENG-N5B-SKELETON |
| 锚 | NOTE-AIV-036-N5B-API-SCOUT-v0 |
| SCOUT md5 | **`a11e4b39460139ef8d4dac78ef86768a`** |
| ForcePass | never |
| 真 Job POST | **0**（默认 + 本骨架 IMPL HOLD） |
| 假像素 | 未写入任何 clips 字节 |
| LOOP-PASS | **否** |
| N6 | 不做 |
| merge | **否**（draft PR） |

## BLOCK 码（submit）

| 条件 | HTTP | code |
|------|------|------|
| G4 未锁且无书面子集 | 409 | `g4_required` |
| 未设 `AIV_N5B_ALLOW_LIVE_JOB` | 409 | `live_job_forbidden` |
| 标志已设（骨架仍不 POST） | 409 | `n5b_impl_hold` |
| ForcePass 键 | 400 | `force_pass_forbidden` |

`details.posted=false`。CI 只走 mock HTTP 单测 client；submit 路径不调用 `httpx.post`。

## Tests (this tip)

`pytest tests` → **280 passed**. N5b-specific: `test_n5b_map.py` (5) · `test_n5b_gates.py` (10) · `test_n5b_api.py` (6). No live Ark Job POST.

## 包

`packages/drama-n5b-core/` · CLI `aiv drama n5b submit|status|gate g5` · API `/drama/n5b/jobs` · `/drama/n5b/status` · `/gates/g5`。

## 协调

并行 N5a（宫格 + 写 `gate_g4`）是**另一条** draft。本 PR 只读 `gate_g4.locked` / `written_subset`，不合并对方 WIP。
