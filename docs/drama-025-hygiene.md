# AIV-025 · Class-D 加厚软门 + named_cast 漏网小补丁（工程映射）

| 项 | 值 |
|----|-----|
| BRIEF | BRIEF-AIV-025 · DESIGN-ACCEPT |
| 状态 | **docs≠PASS** · ForcePass=**never** · ≠产品/G2/G3/LOOP-PASS |
| 基线 | PR#15 tip `01f6c7dc`；**不合 main** |

对照冻结：`DESIGN-025-CAM-D-THICKEN` · `DESIGN-025-PRD-A-B` · `DESIGN-025-DIR-CAST-LEAK`。本文只记工程落点，**不是**复评 PASS。

## 轨 A · Class-D

闭集不变：`WHIP_PUSH` `WHIP_PULL` `DOLLY_ZOOM` `ROLL` `HANDHELD` `ORBIT`。`PUSH`/`PULL`/`CRANE_*` **不**计入加厚。

| 检 | 门级 |
|----|------|
| D≥8（有 profile） | **MUST** · `duration_below_camera_floor` error（023 继承） |
| 条数 / 种类 / 单种占比 | **SHOULD** · warn `class_d_count_below_suggest` / `class_d_kinds_below_suggest` / `class_d_monoculture` |

约 12 镜建议 count≥5、kinds≥4；单种不超过 ⌈D_count/2⌉。warn **不**单独改 `valid`、**不**单独挡 `ready_for_n4`。禁 ForcePass / 手改 camera 冒充加厚。

手段：`.skill/writing/动态漫-转分镜` 引导 + N2 LLM rules + validate 软检。

## 轨 B · name 槽

硬扫仅 `characters[].name`（及 merge/sidecar 开行）。**不**因 one_line/大纲含集合头衔删已挂行。

姓名只来自本项目本集预挂人物卡。生成名是该全名加前缀或后缀则折回同一 id；对不上则不硬折。漏库新角色仍按 §5.2 新开 id。已挂 library_ref 行不得因通用头衔分类被丢掉。

扩例（DENY 开 CHAR）：弹窗/双屏/窗口/爽点+头衔；拆穿两位…/吐槽…；屏幕里/弹幕里两位…；半截系统音；裸头衔 fold 至已挂全名。无剧集专名白名单。

SCENE 与 CHAR **分桶**：`is_scene_b_class` 先放行空间短名（`弹窗空间` / `弹窗审判庭` / `…门厅` / `…战场`），再判 system-speaker。CHAR `弹窗将军` / 裸 `弹窗` 仍 DENY（无 library_ref 时）。禁手改 SCENE 名冒充。

— docs≠PASS · ForcePass=never —
