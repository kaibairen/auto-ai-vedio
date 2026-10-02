# 单元剧 D-N3 工作副本卡（门 G3）+ 资产库薄挂点

| 项 | 值 |
|----|----|
| pipeline_profile | **drama**（本拍 unit 语义） |
| 节点 | **D-N3**（本集 `cards/` CHAR/SCENE 工作副本 + 故事板裁剪投影） |
| 门 | **G3**（唯一锁入口 `POST .../gates/g3/confirm`） |
| 接口权威 | [`openapi/drama-n3.v0.yaml`](../openapi/drama-n3.v0.yaml) **0.1.0** |
| 基线 | main **`2b6385ad`**（PR#13 GAP-COPY 已合；本包不重做 banners/catalog） |
| 状态 | **docs≠PASS** · ForcePass=**never** · ≠产品/G2/G3 PASS · 021b Screen H 最小卡表（非产品 PASS） |

本包停在 G3。`next_edges: ["D-N4"]` **只是候选**，**不**自动开 D-N4。

---

## 冻结条 F1–F3（ACCEPT）

| ID | 口径 |
|----|------|
| **F1** | G3 允许无图薄确认。缺 ref → warn「视觉弱绑定 · 下游一致性自负」，**不挡** confirm/reject。`usable_for_n4` 才是缺 CHAR/SCENE ref 的硬门。G3 pass ≠ usable_for_n4。 |
| **F2** | SCENE materialize = thin stub / `one_line`。不发明虚假 KEEP SCENE 模板路径。thicken 用 **provisional_inline**。 |
| **F3** | N3 用 `template_paths` / `prompt_paths`。**.prompt 不得写入** D-N1/D-N2 `skill_paths`。可选人物小传只进 `thicken_skill_paths`。不重开 018b。 |

KEEP（仓内若存在）：`.prompt/consistency/人物卡模板/*`、`.prompt/consistency/故事板-臭猫参考/臭猫故事板提示词参考.txt`。臭猫 Seedance 参数文不作 N3 卡模板。

---

## 人怎么走

1. 先走完 D-N2，**门 G2 pass**。未锁时物化/attach/GET N3 → **409 `upstream_unlocked`**。
2. **POST** `.../drama/n3/cards/materialize`：只从本集 cast 的 CHAR-*/SCENE-* 挂出工作副本。系统音/群杂/CHAR 脏名不开 CHAR。SCENE 与 CHAR **分桶**：合法空间短名（含 侧边栏奶茶时刻 / 开源避难所入口 / **弹窗审判庭**）不得因 CHAR `弹窗*` 半截规则 `b_class_skipped`。裸 `弹窗` / `系统音` 仍跳过。禁以 cast 名手补丁当 G3 产品解。
3. **POST** `.../drama/n3/cards/thicken`（029 · 文字加厚）：`provider=llm` 填 CHAR `appearance`+`immutable`、SCENE 空间 `appearance`+`light_anchor`。KEEP 人物卡模板进 `prompt_paths`。可选 `--include-bio-skill` 进 `thicken_skill_paths`（**不**写回 N1/N2 `skill_paths`）。SCENE 模板 `provisional_inline`。CAM 扩展槽软并入 appearance/light_anchor。`refs` 可仍空；**不**翻转 `usable_for_n4`；**不** assemble N4。狗粮默认 **G3 锁前** thicken。
4. 故事板裁剪 **GET** `.../drama/n3/storyboard-crop` = 既有 D-N2 列只读投影（seq/shot_id/duration/shot_size/camera/action/char_ids/scene_id/dialogue/notes）。不扩 N2 schema。
5. **门 G3**：`{ decision: pass|reject, actor, note? }`。
   - pass → cards `locked=true`，`next_edges=["D-N4"]`，**不**创建 D-N4 job。
   - reject → 回改。
   - `force_pass` / `force` / `skip_gate` → **400 `force_pass_forbidden`**。
   - 同名 SCENE → warn `duplicate_scene_name`（ID 权威）；**不**硬挡 G3；禁静默并 ID。
6. **attach** `CHAR@version` / `SCENE@version` → 本集 cards 工作副本；**仍须 G3**。
6b. **attach-ref**（031 BE）`POST .../drama/n3/cards/attach-ref`：本地 fixture 落入 `episodes/<ep>/n3/looks/{char|scene}/<id>/face_<view>.png`（SCENE `plate_`），写 `refs[{path,md5,role}]`。禁热链。`has_usable_ref`（CHAR `face|full`）**不**推导 `usable_for_n4`。缺 MUST face → `missing_ref`/`weak_binding`。ForcePass=never。不接 Ark/DashScope。
7. **promote** 显式 stub：写入 `libraries/` 新 version；**不**自动标 G3 pass。
8. D12–D15：`GET .../library/policy` 只挂起面；`project_scope` 默认可覆盖假设 `project`，`chosen=null`。

---

## Bot / CLI

```bash
aiv drama n3 materialize --project proj_01 --ep EP01 --actor yangzhou
aiv drama n3 thicken --project proj_01 --ep EP01 --provider llm --actor eng-dogfood-029
aiv drama n3 get --project proj_01 --ep EP01
aiv drama n3 attach --project proj_01 --ep EP01 --id CHAR-01 --version 3
aiv drama n3 attach-ref --project proj_01 --ep EP01 --id CHAR-01 --role face --source ./fixtures/face.png
aiv drama n3 promote --project proj_01 --ep EP01 --id CHAR-01
aiv drama g3 confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
```

## eng-029 狗粮（文字加厚 · SUCCESS ≠ 绿 N4）

对照谱系：与 eng-027 **一字不改** `title_intent`，intent fingerprint 应对上 `05091fb5…c8ef1`。链：

`N0 → N2 → G2 → N3 materialize → thicken（G3 锁前）→ 导出加厚卡样例`

钉：

```bash
export AIV_LLM_PROVIDER=llm
export AIV_OPENAI_BASE_URL=https://api.deepseek.com/v1
export AIV_OPENAI_MODEL=deepseek-chat
# AIV_OPENAI_API_KEY from env — never echo
```

| SUCCESS | 非 SUCCESS |
|---------|------------|
| CHAR/SCENE PRD MUST 非空可评；`prompt_paths` 含 P-CHAR-*；`fixture_hits=0`；薄→厚对照落盘 | `usable_for_n4=true`；写 jsonl；look 图；ForcePass；助手代写卡正文当成品 |

工作台 Screen H：CHAR/SCENE 卡表（id / name / ref chip）+ 弱绑定 warn 横幅（不挡 G3）+ 分列 G3 locked / `usable_for_n4` 徽章。JSON dump 仅次要。**docs≠PASS**。
