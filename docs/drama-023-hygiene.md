# AIV-023 · named_cast Acc#3 / SCENE / Class-D（工程映射）

| 项 | 值 |
|----|----|
| BRIEF | BRIEF-AIV-023 · DESIGN-ACCEPT |
| 状态 | **docs≠PASS** · ForcePass=**never** · ≠产品/G2/G3/LOOP-PASS |
| 基线 | PR#14 tip `39ce9c10`；**不合 main** |

对照冻结：`DESIGN-023-PRD-BANLIST` · `DESIGN-023-DIR-IDENTITY` · `DESIGN-023-CAM-FLOOR`。本文只记工程落点，**不是**复评 PASS。

## CHAR banlist（开表 / auto_merge）

命中则 **不** 新建 CHAR、不入镜。姓名只来自本项目本集预挂人物卡。生成名是该全名加前缀或后缀则折回同一 id；对不上则不硬折。漏库的真正新角色仍按 DRAMA-N0N1-PRD §5.2 新开 id。已挂行不得因通用头衔分类被丢掉。

| 类 | DENY 锚 |
|----|---------|
| B-ACT | `吐槽两位将军` 及吐槽/端水/争宠+角色 |
| B-TAG | `弹窗将军` / 双屏·窗口·爽点+头衔 |
| B-FRAG | 半截台词 / 句级大纲切片（020 已冻） |
| B-GEN | `幕里两位将军` · `两位将军` · `两侧将军` · 幕里…头衔族 |

无剧集专名白名单，也无品牌硬折。

## SCENE

CHAR / SCENE **分桶**。空间短名不出 `b_class_skipped`。生成侧可吸附事件 `时刻`→`空间`、`入口`→`门厅`。禁止把狗粮 cast 名手补丁当 G3 解。

## 类 D 时长

`HANDHELD` `WHIP_*` `ORBIT` `DOLLY_ZOOM` `ROLL`：默认+吸附 **≥8**。有 `tool_profile` 仍 &lt;8 → 硬 `duration_below_camera_floor`；未选 profile → 薄 warn。

025 加厚软门与漏网扩表示例见 [`drama-025-hygiene.md`](drama-025-hygiene.md)。

— docs≠PASS · ForcePass=never —
