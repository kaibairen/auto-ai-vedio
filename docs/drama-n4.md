# 单元剧 D-N4 按镜提示词确定性拼装

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N4**（`episodes/EP##/EP##-prompts.jsonl` 一镜一行） |
| 接口权威 | [`openapi/drama-n4.v0.yaml`](../openapi/drama-n4.v0.yaml) **0.1.0** |
| 基线 | main **`9477302b`**（PR#16 025 已合） |
| 状态 | **docs≠PASS** · ForcePass=**never** · 非 LLM · 不做 N5 / 补图 / FE |

本包停在拼装。不自动开 D-N5。`usable_for_n4=false` **不写盘**。

---

## 人怎么走

1. 先走完 D-N2 **G2 pass**（须已选 `tool_profile`，`ready_for_n4=true`）和 D-N3 **G3 pass**。未锁 → **409 `upstream_unlocked`**。
2. 每张 CHAR/SCENE 须有真实 ref（path+md5，文件存在）**且** `usable_for_n4=true`（仅挂起面人审可翻；挂 ref ≠ 自绿）。否则 assemble **409** `usable_for_n4_false`，不写 jsonl。
3. 未选工具 / `ready_for_n4=false` → assemble **409 `not_ready_for_n4`**。
4. **POST** `.../drama/n4/validate`：软校验，不写盘，返回 `missing_refs` / issues / `first_shot_review`。
5. **POST** `.../drama/n4/assemble`：DIR `join_nonempty` 填槽。成功写 jsonl + `EP##-prompts.v{n}.jsonl`；`n4-consumer.started=true`。
6. 入参 `seedance_2_0` → 落盘 `seedance_2`。覆盖写 `assemble_version++`。stale 态须 `--force-reassemble` 或先消 stale。
7. 裸 `/n4` → 404，改走 `/drama/n4/...`。

---

## Bot / CLI

```bash
aiv drama n4 validate --project proj_01 --ep EP01 --tool-profile seedance_2_0
aiv drama n4 assemble --project proj_01 --ep EP01 --tool-profile seedance_2_0 --actor yangzhou
aiv drama n4 assemble --project proj_01 --ep EP01 --force-reassemble --actor yangzhou
aiv drama n4 get --project proj_01 --ep EP01
aiv drama n4 status --project proj_01 --ep EP01
```

---

## DESIGN 对齐（PRD 契约 + ENG adapter 优先）

- 写盘门：`G2 locked ∧ G3 locked ∧ ready_for_n4 ∧ usable_for_n4`。usable 假 → **409** + 缺图列表，不造假 ref。
- DIR 槽：`slot_ref_lead` → 主体特征块 → 场锚 → 光色（无则空，不造平光）→ action → 微表情 → 景别 → 运镜 → 约 N 秒。对白不进正词。
- CAM 词表：N2 码 → DESIGN-026-CAM 中文短语；一镜一主运镜；Class-D ≥8s。
- Adapter：`seedance_2`（别名 `seedance_2_0`）；时长 {5,8,10}；画幅 9:16|16:9|2.35:1；`max_prompt_len=800`；ref≤9。
- jsonl 行含 `char_ids` / `scene_id` / `card_versions` / `card_fingerprint` / `g2_fingerprint` / `assemble_version`。
- D11：`first_shot_review` 软建议。无独立 G-N4。无 LLM 主链。无 FE。
