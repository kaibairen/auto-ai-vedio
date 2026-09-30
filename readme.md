# auto-ai-vedio

KEEP skill and prompt seed, plus **短剧 D-N0 / D-N1（门 G1b）** and **D-N2 分镜表（门 G2）** runtime for `pipeline_profile=drama`.

- `.skill/` — Skill packages (writing + generation). D-N1 **read-only** 女/男频编剧；D-N2 **read-only borrow** `.skill/writing/动态漫-转分镜`（`borrowed_dongman`）。不改教材正文。
- `.prompt/` — Prompt / instruction documents (koubo, generation, consistency, seedance). **Not** used by this drama runtime.
- `packages/drama-n0n1-core` · `packages/drama-n2-core` · `packages/episode-schema` · `apps/api` · `apps/cli` · `apps/workbench` — drama runtime
- `openapi/drama-n0n1.v0.yaml` · `openapi/drama-n2.v0.yaml` — OpenAPI **0.1.0** copies
- `docs/drama-n0n1.md` · `docs/drama-n2.md` — humans + bots; koubo-N1 isolation

docs≠PASS; ACCEPT≠merge. **ForcePass=never.** This PR does **not** include koubo-N1 runtime (`feature/koubo`). Does **not** auto-open D-N3. 018c workbench ships Screen E/F/G (min table + G2 button state); not a product PASS.

## Drama D-N0 / D-N1

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
export AIV_LLM_PROVIDER=fixture
aiv --fixture --pretty drama demo --ep EP01 --lane female
pytest
aiv serve
```

Intent confirm (before generate): `POST /api/v0/projects/{id}/episodes/{ep}/drama/intent/confirm`. Unconfirmed generate → **422 `intent_unconfirmed`**. Sole G1b lock: `POST .../gates/g1b/confirm`. After pass, `next_edges: ["D-N2"]` are candidates only — D-N2 is not started. Downstream `GET .../drama/downstream` is **409** `upstream_unlocked` until locked.

## Drama D-N2 / G2

After G1b is locked, generate a storyboard, edit/reorder, then confirm **gate G2**. `provider=fixture` (default / no key) is deterministic; `provider=llm` calls a live OpenAI-compatible Chat (same `AIV_OPENAI_*` as D-N1) and **422s** if the key is missing — no silent fixture fallback. Pass returns `next_edges: ["D-N3"]` as candidates only — D-N3 is **not** created. ForcePass=never. `tool_profile` may be empty (does not block G2; forbids `ready_for_n4`).

BRIEF-AIV-017a (FREEZE O1=A / O2 / O5): generate auto-registers named on-screen roles; sidecar-add does not unlock G1b or rewrite outline; default `named_cast_check=warn` and G2 pass blocks leftover `named_cast_*`.

BRIEF-AIV-020 P0: B-class names (系统音 / 半截台词 / 动词短语 / dirty prefix) do not open CHAR; A-class princes auto-enter + hang `char_ids`; generate adsorbs durations to {5,8,10} (profile unset) or the selected profile's closed set; skill path + excerpt/trace persist on generate/GET/validate (`n2_request`).

```bash
aiv drama storyboard generate --project proj_01 --ep EP01 --provider fixture
# export AIV_OPENAI_API_KEY=...  # and optionally AIV_OPENAI_BASE_URL / AIV_OPENAI_MODEL
aiv drama storyboard generate --project proj_01 --ep EP01 --provider llm
aiv drama g2 confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
```

See [`docs/drama-n2.md`](docs/drama-n2.md). Frozen O1–O9: outline+cast→storyboard; borrowed_dongman; NODE-SPEC+`bridge_id`; API/DB+csv/md; named ID hard-reject / NONE ok; `shot_cap`≤12; English CAM codes; optional `tool_profile`.

**provisional (D-N0/D-N1):** D3 generate requires female\|male · D12 project-scoped library (no list/search) · D13–D15 no promote/fork · shot_cap hard 12.

See [`docs/drama-n0n1.md`](docs/drama-n0n1.md).
