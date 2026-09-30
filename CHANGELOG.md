# Changelog

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
