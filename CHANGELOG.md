# Changelog

## 0.1.0 — 018d COPY-CONTRACT honest increment (docs≠PASS)

OpenAPI **stays 0.1.0** (not 0.2.0). Sync ErrorCode + bilingual `messages.zh|en` + workbench 中文横幅.

- GAP-COPY: workbench Screen E banners for `tool_profile_unset` / `duration_bucket_mismatch` / `ready_for_n4_requires_tool_profile`.
- ERR-SYNC: `intent_unconfirmed` · `intent_stale` · `intent_lane_conflict` · `named_cast_gate` · duration bucket machine codes.
- Thin handler `POST .../drama/copy-contract/evaluate` so enum ⊆ codes handlers raise.
- CI: `tests/contract/test_error_codes_sync.py`. ForcePass=never. ≠产品 / G2 PASS.

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
