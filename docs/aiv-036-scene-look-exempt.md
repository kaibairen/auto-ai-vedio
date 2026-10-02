# AIV-036 · SCENE-LOOK-EXEMPT + CHAR Mode A/B（工程钉）

| 项 | 值 |
|----|----|
| ASSIGN | AIV-036-ENG-033-IMPL · U-033 |
| 钉集 | `proj_01` / `EP01` |
| ForcePass | never |
| 合 main | **否**（须另书面） |

## SCENE

书面豁免：`NOTE-AIV-036-SCENE-EXEMPT-EP01`（md5 `3c58b933f94633bfde9b5a323b916132`）。

- 仅 `(proj_01, EP01)` 默认 EXEMPT；`episode.scene_look=required` 可回滚。
- SCENE 卡不计入 `usable_for_n4` 硬与，不进硬 `missing_refs`。
- 缺 plate → warn + 信封 `scene_look=exempt` / `SCENE-LOOK-EXEMPT=EP01`。**不**因此 409。
- 不翻 SCENE 卡 `usable_for_n4=true`。

## CHAR

| 模式 | P-CHAR | 缺 face 文件 |
|------|--------|----------------|
| **Mode A**（默认） | `role=face\|full` + path+md5 且文件存在 | **409** |
| **Mode B**（`look_mode=B` 或已有人审合板） | 合板 `look.usable_for_n4=true`（人审） | **不**单独 409 |

`generate-look` 仍写 `usable_for_n4=false`。工程不自绿合板。
