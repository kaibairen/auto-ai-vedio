# Changelog

## 0.2.11 — AIV-036 / U-033 SCENE-LOOK-EXEMPT + CHAR Mode A/B (docs≠PASS)

BRIEF-AIV-036 P0 · NOTE-AIV-036-SCENE-EXEMPT-EP01 · NOTE-AIV-036-LOOK-MODE-AB. ForcePass=never. Does **not** merge to main. Does not invent card/look `usable_for_n4=true`. Does not flip dogfood flags on disk.

- **SCENE EXEMPT** pinned `proj_01`/`EP01` (auditable; not global forever). SCENE cards drop out of `usable_for_n4` hard-AND and hard `missing_refs`. Missing plate → warn + `scene_look=exempt` / `SCENE-LOOK-EXEMPT=EP01`. CHAR Mode A face/full still 409.
- **Mode B**: P-CHAR = human-reviewed 合板 `look.usable_for_n4`. Missing face *file* does **not** 409 on that path. `generate-look` still writes `usable_for_n4=false`.
- Helpers: `attach_real_char_refs` / `attach_reviewed_look_sheet`. Tests: `test_n4_scene_look_exempt.py`, `test_n4_char_look_mode.py`.
- Evidence: [`docs/EVIDENCE-AIV-036-ENG-033-IMPL.md`](docs/EVIDENCE-AIV-036-ENG-033-IMPL.md).

## 0.2.10 — AIV-032 gold-A 3:2 CHAR turnaround look-generate (docs≠PASS)

BRIEF-AIV-032. ForcePass=never. Does **not** merge to main. Does not flip `usable_for_n4` or green N4. STYLE终句 + RECIPE§4 一字不改. No orphan generate scripts.

- Shared `assemble_gold_a_sheet_prompt` + `generate_gold_a_sheet` in `drama-n3-core` (CLI standalone `--card` and episode/HTTP/workbench).
- Ark Seedream: `POST …/api/v3/images/generations`, SKU flash→pro→4.5→wan2.7, size `2048x1365`, no `sequential_image_generation`.
- Face ref md5 bind **before** generate. Dry-run / recorded path when `ARK_API_KEY` is absent.
- CLI: `aiv drama n3 generate-look`. HTTP: `POST …/drama/n3/cards/generate-look`. Screen H trigger (default dry-run).
- Tests: `tests/drama/test_n3_look_generate.py`. Dogfood: [`docs/aiv-032-gold-sheet.md`](docs/aiv-032-gold-sheet.md).
- **ENG-004**: post-assemble **L3 adapter default ON** (CAM-002 live-r1 FAIL 缺真背 → live-r2 sheet `6ea71bec6df9c5d2fb1a3d8aa4f279e7`). STYLE/RECIPE§4 一字不改. Disable: `AIV_LOOK_PROMPT_ADAPTER=off|0|empty`.

## 0.2.9 — AIV-026 D-N4 deterministic prompt assemble (docs≠PASS)

Engineering on main tip `1c3b921d` (AIV-029 N3 thicken + 弹窗审判庭 already on main). ForcePass=never. Does **not** merge to main. Does not implement N5 / 补图 / Skill·MCP / FE UI. OpenAPI **0.1.0** increment (`openapi/drama-n4.v0.yaml`). **docs≠PASS**.

- New `packages/drama-n4-core`: assemble / validate / tool adapter registry. Assembly is **not** stuffed into `drama-n3-core`.
- API: `POST .../drama/n4/assemble` · `POST .../drama/n4/validate` · `GET .../drama/n4` · `GET .../drama/n4/status`. Bare `/n4` is 404 isolation (use `/drama/n4/...`), no longer `D-N4 is not implemented`.
- Writes `episodes/EP##/EP##-prompts.jsonl` (one shot per line) plus sidecar `EP##-prompts.v{n}.jsonl`. Soft validate does not write.
- **Hard gates** (PRD): `G2 locked ∧ G3 locked ∧ ready_for_n4 ∧ usable_for_n4`. `usable_for_n4=false` → **409** + missing-ref/missing-file list, **no write**. `ready_for_n4=false` → **409** `not_ready_for_n4`. Missing bound card → **422** `missing_card`. `force_reassemble` may rewrite while stale.
- DIR slot fill (非 LLM): `join_nonempty` ref_lead→主体特征→场锚→光色(有则拼，不造平光)→action→微表情→景别→运镜→时长。对白不进正词。CAM = DESIGN-026-CAM 中文短语；一镜一主运镜；Class-D ≥8. NEG_CORE 负面非空. CHAR-/SCENE- ID → 中文特征.
- Tool adapter: BRIEF alias `seedance_2_0` persists as closed-set **`seedance_2`**. Durations {5,8,10}; aspects 9:16|16:9|2.35:1; `max_prompt_len=800`; ref_images≤9. Overwrite traces `assemble_version` + sidecar + history. Upstream bump → N4 stale (align N3).
- Success envelope: `path` / `g2_fingerprint` / `card_fingerprint` / `first_shot_review`. After assemble, `n4-consumer` `started=true` and can read jsonl via `prompts_path`. Tests: `tests/drama/test_n4_*.py`.

## 0.2.8 — AIV-029 N3 card text thicken (docs≠PASS)

IMPL on main tip `9477302b`. ForcePass=never. Does **not** merge to main. Does not call image-gen, write look refs/md5 as success, flip `usable_for_n4`, assemble N4 jsonl, or open N5 / bot-MCP.

- **API / CLI**: `POST .../drama/n3/cards/thicken` and `aiv drama n3 thicken --provider llm`. Dogfood default = thicken **before** G3 lock (`unlock_edit` only if already locked).
- **MUST slots**: CHAR `appearance`+`immutable`; SCENE space `appearance`+`light_anchor`. KEEP `.prompt/consistency/人物卡模板/*` (+ limited 臭猫故事板参考) via `prompt_paths` / `thicken_prompt_paths`. SCENE template is **provisional_inline** (no invented KEEP path).
- **Optional** `.skill/writing/动态漫-人物小传` excerpt via `include_bio_skill` → `thicken_skill_paths` only. `.prompt` never leaks into N1/N2 `skill_paths`.
- **CAM** crop/framing lex soft-merges into appearance/light_anchor (does not block content review).
- **SCENE 同名**: ID authoritative; warn `duplicate_scene_name`; does not hard-block G3; no silent ID merge.
- **eng-029**: same `title_intent` fingerprint lineage as eng-027 → materialize → thicken → thickened card samples. SUCCESS ≠ green N4.
- Tests: `tests/drama/test_n3_thicken.py` (happy path + hard bans). OpenAPI stays **0.1.x**. **docs≠PASS**.
- **LOOP-CONTINUE**: SCENE `弹窗审判庭` (courtroom/space noun) materializes; `is_scene_b_class` no longer inherits CHAR `弹窗*` prefix skip. Bare `弹窗` / `弹窗字` / `系统音` and CHAR `弹窗王子` still DENY. Does not rewrite shot `scene_id` or dogfood cast names.

## 0.2.7 — AIV-025 Class-D thicken SHOULD + named_cast leak patch (docs≠PASS)

- **SCENE spatial first**: `is_scene_b_class` lets `…空间` / `…门厅` / `…战场` (and existing spatial tokens) pass through before `is_system_speaker`. Fixes live eng-025 `弹窗空间` `b_class_skipped` → G3 `card_missing_for_shot`. CHAR `弹窗王子` / bare `弹窗` still DENY.

Engineering fix stacked on PR#15 tip `01f6c7dc`. ForcePass=never. Does **not** merge to main. Does not rewrite eng-015/019/020*/021/023-live. OpenAPI stays **0.1.x**. **docs≠PASS** · ≠ product / G2 / G3 / LOOP-PASS.

- **Track A**: Class-D closed set unchanged; D≥8 hard floor kept. Storyboard Skill/guide + N2 LLM rules rotate WHIP_*/DOLLY_ZOOM/ROLL/HANDHELD/ORBIT with duration 8|10 on the same row. Validate emits SHOULD warns `class_d_count_below_suggest` / `class_d_kinds_below_suggest` / `class_d_monoculture` — never error, never alone block `ready_for_n4`.
- **Track B**: NAME-slot banlist increment (LK-01…06 + PRD leak table). Protect 程序员/豆包 and A-tier princes. one_line/outline prose 技术王子/两位王子 is not a name deny. Bare「王子」folds to 03/04. Not an Acc#3 mega-track reopen.
- Tests: `tests/drama/test_025_hygiene.py`. ForcePass still 400.

## 0.2.6 — AIV-023 named_cast Acc#3 banlist + SCENE bucket + Class-D ≥8 (docs≠PASS)

Engineering fix on PR#14 tip `39ce9c10`. ForcePass=never. Does **not** merge to main. Does not rewrite eng-015/019/020*/021-live. OpenAPI stays **0.1.x**. **docs≠PASS** · ≠ product / G2 / G3 / LOOP-PASS.

- **P0-A Banlist**: named_cast open / auto_merge / sidecar / N1 generate reject B-ACT/B-TAG/B-FRAG/B-GEN (`吐槽两位王子` / `技术王子` / `幕里两位王子` / 两位·两侧·幕里…王子 family) and bare CURSOR/CODEX. Merge-time prune of dirty CHAR rows. Not a post-hoc dogfood delete. ALLOW keeps 程序员/豆包 and A-tier `GPT(CODEX)王子` / `Opus5.5(CURSOR)王子` (and outline-equivalent titled princes).
- **P1-1 SCENE**: CHAR vs SCENE B-class split. Spatial short names (侧边栏空间 / 避难所门厅 / 侧边栏奶茶时刻 / 开源避难所入口) are not `b_class_skipped`. Generate prefers spatial aliases. Not a cast-name card patch.
- **P1-3 Class-D**: HANDHELD/WHIP_*/ORBIT/DOLLY_ZOOM/ROLL generate default + adsorb duration ≥8. Selected profile and still below 8 → `duration_below_camera_floor` hard; unset profile → thin warn.
- Tests: `tests/drama/test_023_hygiene.py`. Acc#1/#2 / ForcePass=never kept.

## 0.2.5 — AIV-021a/021b/021c N3-unit cards + G3 thin + library stubs + Screen H (docs≠PASS)

Based on main tip `2b6385ad` (PR#13 GAP-COPY already merged; this PR does **not** re-port banners/catalog). ForcePass=never. Does not merge to main. Does not rewrite eng-015/019/020*. OpenAPI stays **0.1.x**.

- **021a**: per-episode CHAR/SCENE working cards from cast only; N3 storyboard crop = read-only D-N2 column projection; G3 confirm/reject; G2 unlocked → 409; no auto-open D-N4.
- **F1**: missing ref → weak-binding warn, does not block G3; `usable_for_n4` is the hard gate. G3 pass ≠ usable_for_n4.
- **F2**: SCENE thin stub / one_line; no invented KEEP SCENE template paths.
- **F3**: N3 observability `template_paths` / `prompt_paths` only; `.prompt` never written into D-N1/D-N2 `skill_paths`.
- **021c**: `libraries/` schema (characters first; scenes stub) + attach/promote stubs. attach ≠ skip G3; promote ≠ auto-pass G3. `project_scope` capability; D12–D15 hanging defaults reversible; no silent auto-promote.
- Workbench Screen H: CHAR/SCENE card rows + `local` / `attached@version` / `none` chips; separate G3 locked vs `usable_for_n4` badges; F1 banner「视觉弱绑定 · 下游一致性自负」does **not** disable G3; G2 `locked`+`confirmed_by` gates materialize/write CTAs; `upstream_unlocked` copy distinguishes G2 vs G1b.
- docs≠PASS · ≠ product / G2 / G3 PASS.

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
