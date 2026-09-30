# 单元剧 D-N3 工作副本卡（门 G3）+ 资产库薄挂点

| 项 | 值 |
|----|----|
| pipeline_profile | **drama**（本拍 unit 语义） |
| 节点 | **D-N3**（本集 `cards/` CHAR/SCENE 工作副本 + 故事板裁剪投影） |
| 门 | **G3**（唯一锁入口 `POST .../gates/g3/confirm`） |
| 接口权威 | [`openapi/drama-n3.v0.yaml`](../openapi/drama-n3.v0.yaml) **0.1.0** |
| 基线 | main **`2b6385ad`**（PR#13 GAP-COPY 已合；本包不重做 banners/catalog） |
| 状态 | **docs≠PASS** · ForcePass=**never** · ≠产品/G2/G3 PASS · 021b FE 未宣称 |

本包停在 G3。`next_edges: ["D-N4"]` **只是候选**，**不**自动开 D-N4。

---

## 冻结条 F1–F3（ACCEPT）

| ID | 口径 |
|----|------|
| **F1** | G3 允许无图薄确认。缺 ref → warn「视觉弱绑定 · 下游一致性自负」，**不挡** confirm/reject。`usable_for_n4` 才是缺 CHAR/SCENE ref 的硬门。G3 pass ≠ usable_for_n4。 |
| **F2** | SCENE = thin stub / `one_line`。不发明虚假 KEEP SCENE 模板路径。 |
| **F3** | N3 用 `template_paths` / `prompt_paths`。**.prompt 不得写入** D-N1/D-N2 `skill_paths`。不重开 018b。 |

KEEP（仓内若存在）：`.prompt/consistency/人物卡模板/*`、`.prompt/consistency/故事板-臭猫参考/臭猫故事板提示词参考.txt`。臭猫 Seedance 参数文不作 N3 卡模板。

---

## 人怎么走

1. 先走完 D-N2，**门 G2 pass**。未锁时物化/attach/GET N3 → **409 `upstream_unlocked`**。
2. **POST** `.../drama/n3/cards/materialize`：只从本集 cast 的 CHAR-*/SCENE-* 挂出工作副本。系统音/群杂不开 CHAR。
3. 故事板裁剪 **GET** `.../drama/n3/storyboard-crop` = 既有 D-N2 列只读投影（seq/shot_id/duration/shot_size/camera/action/char_ids/scene_id/dialogue/notes）。不扩 N2 schema。
4. **门 G3**：`{ decision: pass|reject, actor, note? }`。
   - pass → cards `locked=true`，`next_edges=["D-N4"]`，**不**创建 D-N4 job。
   - reject → 回改。
   - `force_pass` / `force` / `skip_gate` → **400 `force_pass_forbidden`**。
5. **attach** `CHAR@version` / `SCENE@version` → 本集 cards 工作副本；**仍须 G3**。
6. **promote** 显式 stub：写入 `libraries/` 新 version；**不**自动标 G3 pass。
7. D12–D15：`GET .../library/policy` 只挂起面；`project_scope` 默认可覆盖假设 `project`，`chosen=null`。

---

## Bot / CLI

```bash
aiv drama n3 materialize --project proj_01 --ep EP01 --actor yangzhou
aiv drama n3 get --project proj_01 --ep EP01
aiv drama n3 attach --project proj_01 --ep EP01 --id CHAR-01 --version 3
aiv drama n3 promote --project proj_01 --ep EP01 --id CHAR-01
aiv drama g3 confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
```

工作台 Screen H 仅为 JSON dump 狗粮钩子；**021b FE 未宣称 PASS**。
