# 单元剧 D-N5a 宫格 + 门 G4

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N5a**（`episodes/EP##/grids/EP##_grid_{9\|16}_vN.png`） |
| 产品门 | **门 G4** `pass` \| `rework`（≠ 检 G1–G10） |
| 接口 | [`openapi/drama-n5a.v0.yaml`](../openapi/drama-n5a.v0.yaml) **0.1.0** |
| 状态 | **docs≠PASS** · ForcePass=**never** · 禁假像素 · **N5b 本 PR 不做** |

狗粮默认 **9** 格。≥7/9 为 CAM 建议，**未硬钉**。

---

## 冻结钉

1. **P-CHAR**：进镜 CHAR `usable_for_n4=true` = 人审 **look 合板**，不是必须有 face 文件。本包 **不翻** usable。
2. **Mode B**：厚卡 `appearance`+`immutable` 即可出格；**禁止**把「缺 face 文件」写成 N5a 硬挡。Mode A 有 face 时才带 img2img。
3. **SCENE EXEMPT (EP01)**：检 G4 场项 = **N/A·EXEMPT**；检 G1–G3 / G9 身份项仍硬。
4. **ForcePass=never**：`force_pass` / `force` / `skip_gate` → **400**.
5. **无假像素**：无钥 / API 全败 → 结构化 **BLOCK**（`provider`，`blocked=true`，`written=false`）。不写彩条、不写占位格、不记 PASS。
6. 门序：非空 `EP##-prompts.jsonl` → `generate-grid` → **门 G4** → N5b（锁前 409；本 PR submit = 404 `n5b_not_implemented`）。

---

## 人怎么走

1. 本集已有非空 `episodes/EP##/EP##-prompts.jsonl`。缺/空 → generate **409** `missing_prompts_jsonl`。
2. `POST .../drama/n5a/generate` 或 `aiv drama n5a generate-grid`。无 `ARK_API_KEY` 且非 `--dry-run` → **422 BLOCK**。`--dry-run` 只记 Ark 合同，**不写 PNG**，不得点 G4 pass。
3. 产物：`grids/EP##_grid_9_vN.png` + `grids/EP##_g4-checklist.yaml` + evidence（SKU / attempts / md5；无 Key 明文）。
4. 人点 `POST .../gates/g4` `{verdict: pass|rework, actor}`。无真格 → 409 `missing_grid`。
5. 裸 `/n5a` `/n5b` → 404，走 `/drama/n5a/...`。

```bash
aiv drama n5a generate-grid --project proj_01 --ep EP01 --layout 9 --actor yangzhou
aiv drama n5a generate-grid --project proj_01 --ep EP01 --dry-run
aiv drama n5a gate g4 --project proj_01 --ep EP01 --actor yangzhou --verdict pass
aiv drama n5a status --project proj_01 --ep EP01
```

---

## 非声称

- ≠ N5b Job / clips / 门 G5
- ≠ N6 / LOOP-PASS / 成片交付
- ≠ 翻 `usable_for_n4`
- ≠ 合 main（未经书面）
- ≠ 无钥却绿宫格
