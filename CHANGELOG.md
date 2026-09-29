# Changelog

## N1 runtime (unreleased)

- Add N1 口播定稿 session machine, REST `/api/v0`, and `aiv n1` CLI.
- Gate lock is only `POST .../gates/g1/confirm`. No `n1/lock`, no ForcePass.
- Path B wizard skips defective step 3; `.prompt/koubo-长文章.md` is not rewritten.

### Known debt (kept)

- Path B source defect: missing step 3; frameworks 7/8 garbled in `.prompt/koubo-长文章.md`.
- D2 unset: after G1, `next_edges` stay blocked; no auto-advance to 编剧.
- D7 voice track not produced at N1.
