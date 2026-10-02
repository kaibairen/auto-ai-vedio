# RUN-NOTES · AIV-031-IMPL-BE-001（look refs / md5 / N4 409）

| 项 | 值 |
|----|----|
| 席 | AI视频-后端 |
| BRIEF | BRIEF-AIV-031-LOOK-IMPL · BE slice |
| 基线 | main `4d651a6cb003a16dcdef6e53c2ee0c85df8df3ca` |
| 本拍 tip | `614703f9556b3d3a6a1d58189d4ba2a7749998bf` |
| 性质 | BE 契约落地 · **≠绿 N4** · **≠LOOP-PASS** · 不合 main |
| 硬 | ForcePass=never · 禁自翻 `usable_for_n4` · 禁热链 path |

## 做了

1. **looks 树权威** `episodes/<ep>/n3/looks/{char|scene}/<card_id>/` + `face_<view>.png` / `plate_<view>.png`；`ensure_*` mkdir（含 `web_refs/`）。
2. **refs 挂载** MUST `path`∧`md5`∧`role`；禁 `http(s)`/`data:` 热链；写盘后重算 md5；文件不在或 md5 漂 → `missing_file`。
3. **has_usable_ref（CHAR）** 非空 path+md5 + `role∈{face,full}` + `missing_file≠true`。`style_ref`/`web_source` **不计**。
4. **missing_ref / weak_binding** 在 refs 空或 CHAR 缺 MUST `face` 时刷新。仅 `full` → `has_usable_ref=true` 仍 `missing_ref=true`。
5. **usable 分槽** `has_usable_ref` **不**推导 `usable_for_n4`。attach-ref / library attach / thicken / G3 confirm **只可把 usable 置 false**，从不置 true。
6. **N4 409 回归** `usable_for_n4=false` → HTTP 409 `usable_for_n4_false`，`details.missing_refs[{id,kind,name,reason}]`，`reason∈{missing_ref,missing_file}`，`written=false`。ForcePass / force / skip_gate → 400。
7. **Key 隔离** Settings 增加 `ark_api_key`←`ARK_API_KEY`、`dashscope_api_key`←`DASHSCOPE_API_KEY`，**不**回退 `AIV_OPENAI_API_KEY`。BE 单测只用本地 fixture，不打 Ark/DashScope。

## 未做（ENG / 挂起面）

- 真 Seedream / wan 客户端与狗粮出图（`aiv_drama_n3/image_providers.py` 仅 hook）。
- STYLE-REF prompt 组装。
- `usable_for_n4=true` 翻转 API（仅挂起面人审；本拍不实现）。N4 assemble 成功测用 **test-only** `mark_usable_for_n4_reviewed` 模拟挂起面，**不是**产品缝。

## 怎么验

```bash
pytest tests/drama/test_n3_look_refs.py tests/drama/test_n4_gates.py tests/drama/test_n3_g3.py -q
```

覆盖：has_usable_ref / missing_file / attach-ref-does-not-flip-usable / N4 409。

## 非声称

≠ 绿 N4 · ≠ LOOP-PASS · ≠ 合 main · ≠ 出图已做 · ≠ usable 已翻 · docs≠PASS

— AIV-031-IMPL-BE-001 · ForcePass=never —
