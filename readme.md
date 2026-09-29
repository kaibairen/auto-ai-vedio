# auto-ai-vedio

KEEP skill and prompt seed, plus **短剧 D-N0 / D-N1（门 G1b）** runtime for `pipeline_profile=drama`.

- `.skill/` — Skill packages (writing + generation). Runtime **read-only** references 女/男频编剧.
- `.prompt/` — Prompt / instruction documents (koubo, generation, consistency, seedance). **Not** used by this drama runtime.
- `packages/drama-n0n1-core` · `packages/episode-schema` · `apps/api` · `apps/cli` · `apps/workbench` — drama runtime
- `openapi/drama-n0n1.v0.yaml` — OpenAPI **0.1.0** copy
- `docs/drama-n0n1.md` — humans + bots; koubo-N1 isolation

docs≠PASS; ACCEPT≠merge. **ForcePass=never.** This PR does **not** include koubo-N1 runtime (`feature/koubo`).

## Drama D-N0 / D-N1

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
export AIV_LLM_PROVIDER=fixture
aiv --fixture --pretty drama demo --ep EP01 --lane female
pytest
aiv serve
```

Sole lock: `POST /api/v0/projects/{id}/episodes/{ep}/gates/g1b/confirm`. After pass, `next_edges: ["D-N2"]` are candidates only — D-N2 is not started. Downstream `GET .../drama/downstream` is **409** `upstream_unlocked` until locked.

**provisional:** D3 generate requires female\|male · D12 project-scoped library (no list/search) · D13–D15 no promote/fork · shot_cap hard 12.

See [`docs/drama-n0n1.md`](docs/drama-n0n1.md).
