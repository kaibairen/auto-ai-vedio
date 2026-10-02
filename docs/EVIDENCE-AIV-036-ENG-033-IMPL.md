# EVIDENCE · AIV-036-ENG-033-IMPL · U-033

| 项 | 值 |
|----|----|
| ASSIGN | AIV-036-ENG-033-IMPL |
| 基线 tip | `69eda17c778e2bb1b4b004b5647a788ffe68e283` |
| 分支 | `cursor/u-033-scene-look-optional-a1c6` |
| PR | *(draft — filled after open)* |
| ForcePass | never |
| 合 main | **否** |

## 行为 before / after

| 场景 | 改门前 | 改门后 |
|------|--------|--------|
| `proj_01`/`EP01` · CHAR face/full 齐 · SCENE 无 plate | `usable_for_n4=false` → assemble **409** | `scene_look=exempt` · usable 可 true · **写** `EP01-prompts.jsonl` |
| 同上 · CHAR 缺 face（Mode A） | 409 | 仍 **409**（`usable_for_n4_false` / CHAR missing_ref） |
| Mode B · 人审合板 `look.usable_for_n4=true` · 无 face 文件 | 409 missing_file/missing_ref | **不**因缺 face 文件 409；P-CHAR=合板 usable |
| Mode B · 合板未人审 | 409 missing_ref | 409 `look_usable_for_n4_false`（**不是** missing_file） |
| `proj_01`/`EP02` 或 `proj_02`/`EP01` · 缺 SCENE plate | 409 | 仍 409（非钉集） |
| ForcePass 键 | 400 | 仍 **400** `force_pass_forbidden` |

## 测试（待本拍 pytest 回填）

| 测试 | 结果 |
|------|------|
| *(run pending)* | |

## 禁项核对

- ≠自绿：`generate-look` 仍 `usable_for_n4=false`；不写 USABLE*.md。
- ≠翻 dogfood 盘上 `usable_for_n4` 旗。
- T0–T5 全文门未做（本拍 P0 改门）。
- Mode B LOOK 真狗粮 / 明早人审 **不挡** 本 PR。
