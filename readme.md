# auto-ai-vedio

KEEP skill/prompt seed plus **N1 口播定稿** runtime.

- `.skill/` · `.prompt/` · `MANIFEST.md` — KEEP seed
- `packages/n1-core` · `apps/api` · `apps/cli` · `apps/workbench` — N1 runtime
- `docs/n1.md` — humans + bots; provisional table

docs≠PASS; ACCEPT≠merge. **N1 only.** ForcePass=never.

## N1

Path A (口水话 ≤400) and path B (长文章 ≤500). B uses step `b3_skipped` (source defect); `.prompt/koubo-长文章.md` is not rewritten. Sole lock: `POST /gates/g1/confirm`. After lock, `next_edges` stay blocked (D2 unset).

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
aiv --fixture n1 demo --ep EP01 --path A
pytest
aiv serve
```

Bot: walk `session.current_step` via `POST .../n1/steps/{step}/submit`, then `POST .../gates/g1/confirm` `{decision: pass, actor}`. Downstream `GET .../n1/artifact` is **409** `upstream_unlocked` until locked. Details: [`docs/n1.md`](docs/n1.md).

**provisional:** P-D1 default A · P-D2 no auto 编剧 · P-D7 no voice file · P-STACK=Python (ENG preferred TS; see docs) · P-PROJ `default` + `episodes/EP##/`.
