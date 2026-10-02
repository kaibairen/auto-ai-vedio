# auto-ai-vedio

KEEP skill and prompt seed, plus **短剧 D-N0 / D-N1（门 G1b）**、**D-N2 分镜表（门 G2）**、**D-N3 单元卡（门 G3）+ library 薄挂点** and **D-N4 确定性按镜拼装** runtime for `pipeline_profile=drama`.

- `.skill/` — Skill packages (writing + generation). D-N1 **read-only** 女/男频编剧；D-N2 **read-only borrow** `.skill/writing/动态漫-转分镜`（`borrowed_dongman`）。不改教材正文。
- `.prompt/` — Prompt / instruction documents (koubo, generation, consistency, seedance). **Not** used by this drama runtime.
- `packages/drama-n0n1-core` · `packages/drama-n2-core` · `packages/drama-n3-core` · `packages/drama-look-core` · `packages/drama-n4-core` · `packages/episode-schema` · `apps/api` · `apps/cli` · `apps/workbench` — drama runtime
- `openapi/drama-n0n1.v0.yaml` · `openapi/drama-n2.v0.yaml` · `openapi/drama-n3.v0.yaml` · `openapi/drama-look.v0.yaml` · `openapi/drama-n4.v0.yaml` — OpenAPI **0.1.0** copies
- `docs/drama-n0n1.md` · `docs/drama-n2.md` · `docs/drama-n3.md` · `docs/drama-look.md` · `docs/drama-n4.md` — humans + bots; koubo-N1 isolation

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

## Drama D-N3 / G3 (021a + 021c)

After G2 is locked, materialize CHAR/SCENE working cards from cast, optionally **thicken** text slots (`appearance` / `immutable` / `light_anchor`) with `provider=llm`, optionally attach `CHAR@version` / `SCENE@version` or **attach-ref** a local look file into `episodes/<ep>/n3/looks/...` (`refs[{path,md5,role}]`), then confirm **gate G3**. Missing refs warn only (F1). `has_usable_ref` does **not** flip `usable_for_n4`. Thicken does not call image-gen or assemble N4. Promote is an explicit stub and does not auto-pass G3. N3 uses `template_paths` / `prompt_paths` (F3). Screen H shows CHAR/SCENE rows + ref chips (021b minimal; docs≠PASS).

```bash
aiv drama n3 materialize --project proj_01 --ep EP01 --actor yangzhou
# export AIV_OPENAI_API_KEY=...  # DeepSeek / OpenAI-compatible; thicken is llm-only
aiv drama n3 thicken --project proj_01 --ep EP01 --provider llm --actor eng-dogfood-029
aiv drama g3 confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
```

See [`docs/drama-n3.md`](docs/drama-n3.md). docs≠PASS. ForcePass=never.

## Drama D-N3 look (031)

After cards are thickened, generate one still per card (CHAR `face_front` CU / SCENE `plate_empty` LS). Writes `episodes/<ep>/n3/looks/{char|scene}/<id>/`, md5, and `refs[{path,md5,role}]`. **Does not** set `usable_for_n4=true`. Ark `ARK_API_KEY` (Seedream flash→pro→4.5) is primary; DashScope `DASHSCOPE_API_KEY` (wan2.7→pro) is backup. Isolated from `AIV_OPENAI_API_KEY`. Watermark OFF. Missing face / usable=false still **409** on N4 assemble.

```bash
# export ARK_API_KEY=...   # not AIV_OPENAI_API_KEY
aiv drama look generate --project proj_01 --ep EP01 --id CHAR-01 --actor eng-031
aiv drama look generate --project proj_01 --ep EP01 --id SCENE-01 --actor eng-031
```

See [`docs/drama-look.md`](docs/drama-look.md) and [`docs/RUN-NOTES-AIV-031-LOOK.md`](docs/RUN-NOTES-AIV-031-LOOK.md). docs≠PASS. ForcePass=never.

## Drama D-N4 assemble (026)

After G2+G3 are locked **and** `ready_for_n4=true` **and** `usable_for_n4=true` (real CHAR/SCENE refs on disk), `POST .../drama/n4/assemble` fills DIR slots (not LLM) and writes `episodes/EP##/EP##-prompts.jsonl`. `usable_for_n4=false` returns **409** + a missing-ref list and **does not write**. Input alias `seedance_2_0` persists as `seedance_2`. Bare `/n4` is isolated; use `/drama/n4/...`. N5 is not opened.

```bash
aiv drama n4 assemble --project proj_01 --ep EP01 --tool-profile seedance_2_0 --actor yangzhou
```

See [`docs/drama-n4.md`](docs/drama-n4.md). docs≠PASS. ForcePass=never.

**provisional (D-N0/D-N1):** D3 generate requires female\|male · D12 project-scoped library (no list/search) · D13–D15 no promote/fork · shot_cap hard 12.

See [`docs/drama-n0n1.md`](docs/drama-n0n1.md).
