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

1. 先走完 D-N3，**门 G3 pass**。未锁 → **409 `upstream_unlocked`**。
2. 每张 CHAR/SCENE 工作副本须有真实 ref（path+md5，文件存在）。否则 `usable_for_n4=false`。
3. **POST** `.../drama/n4/validate`：软校验，不写盘，返回 `missing_refs` / issues。
4. **POST** `.../drama/n4/assemble`：按 DIR 槽序填槽。成功写 jsonl；`n4-consumer.started=true`。
5. 入参 `seedance_2_0` → 落盘 `seedance_2`。覆盖写 `assemble_version++`，history 可追溯。
6. 上游 cards/分镜/cast 升版 → N4 `stale`（对齐 N3）。stale cards 写路径 **409**；重新拼装可覆盖。
7. 裸 `/n4` → 404，改走 `/drama/n4/...`。

---

## Bot / CLI

```bash
aiv drama n4 validate --project proj_01 --ep EP01 --tool-profile seedance_2_0
aiv drama n4 assemble --project proj_01 --ep EP01 --tool-profile seedance_2_0 --actor yangzhou
aiv drama n4 get --project proj_01 --ep EP01
aiv drama n4 status --project proj_01 --ep EP01
```

---

## DESIGN 偏差（本环境 uploads/ 未挂载）

- DIR 槽序取仓内 KEEP Seedance 核心公式（风格/主体/场景/动作/镜头/光影），不是上传 DESIGN 原文逐行照抄。
- CAM 词表 = N2 英文字段闭集 → 中文一词；一镜只填一个主运镜。
- 无 G4。N5 / Skill·MCP / FE **DEFER**。
