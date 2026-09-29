# auto-ai-vedio

KEEP skill and prompt seed for the AI video line, plus a **minimal N1 口播定稿 runtime**.

- `.skill/` — Skill packages (writing + generation)
- `.prompt/` — Prompt / instruction documents (koubo, generation, consistency, seedance)
- `MANIFEST.md` — inventory (path, source, category)
- `src/aiv/` — N1 session machine, REST, CLI (`aiv n1 …`)
- `docs/n1.md` — how a human clicks the wizard and how a bot drives G1

See `README-STAGE.md` for the local staging note on the skill seed. docs≠PASS; ACCEPT≠merge.

## N1 口播定稿 (this runtime)

N1 only. Path A (口水话, ≤400) and path B (长文章, ≤500). Path B **skips** the missing curriculum step 3 and does **not** rewrite `.prompt/koubo-长文章.md`. Lock is **only** `POST /api/v0/projects/{id}/episodes/{ep}/gates/g1/confirm`. No ForcePass. After G1 the API returns `next_edges` but does **not** start 编剧 (D2 unset).

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
aiv n1 demo --project demo --ep EP01 --path A   # fixture, no API key
pytest
aiv serve   # wizard at /  + REST under /api/v0
```

Bot G1: walk `allowed_steps` via `POST .../n1/steps/{step}/submit`, then `POST .../gates/g1/confirm` with `decision=pass` and `actor`. Downstream `GET .../n1/final` is **409** until `locked: true`. Full contract: [`docs/n1.md`](docs/n1.md).
