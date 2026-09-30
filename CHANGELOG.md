# Changelog

## 0.2.4 — 018d GAP-COPY 出片横幅 + ErrorCode sync (docs≠PASS)

Port of closed PR #10 leftovers onto main tip after #12. ForcePass=never. OpenAPI stays **0.1.0**. Does not rewrite N0–N2 LLM body generation.

- Workbench Screen E: `tool_profile` select, chips「出片：未选工具 / 时长未对齐 / 时长已对齐」, banners for `tool_profile_unset` / `duration_bucket_mismatch` / `ready_for_n4_requires_tool_profile`.
- Intent / named_cast Chinese from #12 kept; not duplicated.
- Honest ErrorCode: n2 enum adds `named_cast_gate` · `named_cast_missing` · `ready_for_n4_requires_tool_profile` (already raised or raised by evaluate).
- `GET /api/v0/drama/error-catalog` + `POST .../drama/copy-contract/evaluate` overlay (uses live N2 duration tables).
- CI: `tests/contract/test_error_codes_sync.py`. docs≠PASS.

## 0.2.3 — BRIEF-AIV-020 cast hygiene + duration buckets + skill excerpt (docs≠PASS)

LOOP-CONTINUE R4 (eng-020r3 FIT-GAP Acc#3): reject sentence-level outline fragments (`豆包当众拆穿两个王子` / `包的开源权重反制两个闭源王子`) and quantity generics (`两侧王子`); fold those hits onto GPT/Opus A slots. Acc#1/#2 brand-fold and P0-B/C unchanged.

LOOP-CONTINUE R3 (eng-020r2 FIT-GAP): fold bare `CURSOR`/`CODEX` onto `Opus5.5王子`/`GPT王子` (never a bare-brand CHAR); glue `CURSOR（Opus5.5王子）` to one entity; hang A-class prince ids on dialogue/confrontation shots so clean slots are not orphans. A1 half-line/generic skip kept. P0-B/C unchanged.

LOOP-CONTINUE (eng-020 FIT-GAP): skip dialogue half-slices `你被双王子` / `而是两王子` and generic titles `王国王子` / `AI王子`; full lines with `双王子` still map to GPT/Opus (or CODEX/CURSOR) A slots. P0-B/C unchanged.

P0 engineering loop on tip `0d16e92` (PR#11 stack). ForcePass=never. Does not merge to main. Does not rewrite eng-015/019 dogfood artifacts.

- **P0-A**: named_cast skips B-class (`【系统音】` / 系统音 / 弹窗 / 旁白 / 广播半截台词 / 动词短语 / leading `/`); dedupes near-duplicates; A-class `CODEX王子` / `CURSOR(Opus5.5)王子` (or outline-equivalent) auto-enter cast and hang `char_ids`. Collection `两王子` / `指出两王子` resolve to individual A slots. Sidecar still does not unlock G1b or rewrite outline; bump `cast.version` + warn `named_cast_auto_merged` / `named_cast_sidecar_added` on generate/GET/validate.
- **P0-B**: generate adsorbs `duration_s` onto {5,8,10} when `tool_profile` is unset (bucket stays null, O9). Selected profile hard-adsorbs onto that profile's closed set and writes a matching bucket (017b O3, no collision). PUT mismatch still errors.
- **P0-C**: persist `skill_paths` (entry+guide), `skill_excerpt`, `skill_trace` (path/chars/sha256). Generate/GET/validate expose `n2_request` skill evidence (not flag-only).

## 0.2.2 — BRIEF-AIV-018c workbench + episode projection (docs≠PASS)

Workbench E–G MVP on the 018a + 017a stack. ForcePass=never. Does not merge to main. Does not substitute PRs #5–#9.

- `.aiv/episode.json` writes nested `intent`, `versions`, `gates.g1b/g2`, `storyboard_meta.shot_cap` (no `shot_budget` write), optional `skill_paths`, `projection_dirty`.
- Screen E: min storyboard columns, cast chips `id · name`, refresh after sidecar.
- FE-D1 banner `v{old} → v{new}`; FE-D3 client-disable G2 pass on blocking `named_cast_*` (looks at `locked`/`confirmed_by`).
- Screen F/G: validate issues + G2 confirm state + locked summary. No auto-nav to D-N3.
- Optional 018b FE debt: foldable read-only「本次 Skill」from generate envelopes.
- A2 intent confirm stays on the 018a track.

## 0.2.1 — BRIEF-AIV-017a named-cast (O1/O2/O5, docs≠PASS)

Frozen FREEZE O1=A / O2 / O5 on drama D-N2 only. ForcePass=never. Does not change O9 coerce.

- **O1=A**: after storyboard generate, auto-register high-confidence named speakers/agents from action/dialogue; merge into cast; wire `char_ids`.
- **O2**: `POST .../drama/cast/sidecar-add` does **not** unlock G1b or rewrite locked outline body; bumps `cast.version`; API/UI `cast_changed` + hints.
- **O5**: default `named_cast_check=warn` (`AIV_NAMED_CAST_CHECK=off|warn|error`); issues `named_cast_*`. G2 pass blocks if any remain (`named_cast_gate`). Strict/error is the knob.
- Workbench Screen E surfaces the hint. Thin chips still only reflect `char_ids` (no auto-add from FE).

## 0.2.0 — drama D-N2 storyboard + gate G2 (docs≠PASS)

Implements `pipeline_profile=drama` **D-N2** (storyboard) + gate **G2** against OpenAPI **0.1.0**.

- REST `/api/v0/.../drama/storyboard*` and `/gates/g2` match `openapi/drama-n2.v0.yaml`.
- CLI `aiv drama storyboard ...` / `aiv drama g2 ...`; `provider=fixture` without keys; `provider=llm` is a live OpenAI-compatible StoryboardProvider (same `AIV_OPENAI_*` as D-N1; no silent fixture fallback).
- API/DB (JsonStore tables `drama_storyboard` + `drama_storyboard_shot`) is source; disk projection `EP##-分镜.csv` + `EP##-分镜.md` + `.aiv/episode.json`.
- ForcePass=never; G1b unlocked → 409; G2 pass → `next_edges: ["D-N3"]` candidates only (no D-N3 job).
- Isolated from koubo-N1; bare `/n2` 404. Thin FE for D-N2 **not** shipped (API+CLI debt).

### Frozen O1–O9 (DESIGN-ACCEPT; not a product PASS)

- O1 outline+cast → storyboard (no script hard gate)
- O2 `storyboard_skill: borrowed_dongman` (read-only borrow)
- O3/O8 NODE-SPEC columns + required `bridge_id`; angle/speed in notes
- O4 API/DB + csv/md projection
- O5 unknown named CHAR/SCENE → `cast_id_unknown`; NONE allowed
- O6 inherit `shot_cap`; hard ≤12
- O7 English CAM codes on disk/DB
- O9 empty `tool_profile` does not block G2; forbids `ready_for_n4`

## 0.1.1 — drama D-N0 / D-N1 + intent confirm 018a (docs≠PASS)

OpenAPI **version string remains 0.1.0**. Incremental honest contract: `intent_unconfirmed` / `intent_stale` / `intent_lane_conflict` plus `POST .../drama/intent/confirm|clear`.

- Episode-level authoritative `intent.confirmed` + `intent.fingerprint` (API SoT, mirrored to `.aiv/episode.json`). Not a dogfood file.
- generateOutline hard-gated: unconfirmed → 422 `intent_unconfirmed`; MUST drift → 422 `intent_stale`.
- Confirm blocked on lane×preattach conflict → 422 `intent_lane_conflict` (track B: follow precast lane). No `lane_cast_mismatch`.
- `hero_one_line` must be persisted on brief/cast before confirm.
- Workbench A2 screen; Outline generate disabled + zero request when unconfirmed. No photography/look gate on confirm.
- ForcePass=never (`skip_intent` rejected). Package boundary: drama-n0n1-core + apps/api + workbench. Not drama-n2-core.

## 0.1.0 — drama D-N0 / D-N1 runtime (docs≠PASS)

Implements `pipeline_profile=drama` **D-N0** (brief) + **D-N1** (outline/cast · gate **G1b**) against OpenAPI **0.1.0**.

- REST `/api/v0` matches `openapi/drama-n0n1.v0.yaml`.
- CLI `aiv drama ...`; fixture LLM so tests run without keys.
- Disk projection: `episodes/EP##/.aiv/episode.json`, `EP##-brief.yaml`, `EP##-大纲.md`, `EP##-cast.yaml`.
- ForcePass=never; no koubo-N1 runtime; no D-N2 auto-start.

### Provisional (not a product PASS)

- **D3**: generate requires `female|male`; unset → 422 `lane_required`; no `dual_skill_preview`.
- **D12**: project-scoped library only; list/search paths absent from OpenAPI — not implemented; attach uses explicit `character_id@version`.
- **D13–D15**: no promote/fork; `library_ref` reserved.
- **shot_cap**: hard cap 12.

### Known gaps / debt

- Library list/search not in OpenAPI → dogfood seed via CLI `aiv drama library put` or `PUT /library/characters/{id}` (extension, not list/search).
- Downstream read for D-N2 consumers: `GET .../drama/downstream` (not in OpenAPI; read-only; 409 `upstream_unlocked` if G1b unlocked).
