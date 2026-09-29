# Changelog

## N1 runtime (unreleased)

- N1 session machine + REST + `aiv` CLI + workbench, aligned to BRIEF-AIV-008 and N1 seat contracts.
- Gate lock only `POST .../gates/g1/confirm`. No `n1/lock`, no ForcePass.
- Path B: explicit `b3_skipped` + `defects: missing_step_3`; `.prompt/koubo-长文章.md` not rewritten.
- Package layout: `packages/n1-core`, `apps/api`, `apps/cli`, `apps/workbench`.

### Known debt

- Path B curriculum missing step 3; frameworks 7/8 garbled in source.
- D2 unset: `next_edges` only after G1.
- D7 voice track not produced.
- P-STACK: Python instead of ENG’s TS default (one stack).
