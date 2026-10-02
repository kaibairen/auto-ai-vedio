# EVIDENCE · AIV-036-ENG-033-IMPL · U-033

| 项 | 值 |
|----|----|
| ASSIGN | AIV-036-ENG-033-IMPL |
| 基线 tip | `69eda17c778e2bb1b4b004b5647a788ffe68e283` |
| 分支 | `cursor/u-033-scene-look-optional-a1c6` |
| 本拍 tip | `1fd201426a801ee9b2663ed6adc6e19b3db7a35b` |
| PR | https://github.com/kaibairen/auto-ai-vedio/pull/22 (**draft** · ≠ merge) |
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

## pytest（本拍）

命令：`python3 -m pytest tests/drama/test_n3_g3.py tests/drama/test_n3_api.py tests/drama/test_n3_thicken.py tests/drama/test_n4_gates.py tests/drama/test_n4_api.py tests/drama/test_n4_assemble.py tests/drama/test_n4_scene_look_exempt.py tests/drama/test_n4_char_look_mode.py tests/drama/test_n3_look_generate.py tests/drama/test_021b_workbench.py tests/drama/test_copy_contract.py -q`

**结果：86 passed.**

| 测试 | 结果 |
|------|------|
| `test_n4_scene_look_exempt.py::test_policy_pin_is_proj_01_ep01_not_global` | PASS |
| `test_n4_scene_look_exempt.py::test_char_only_usable_true_on_exempt_false_off_scope` | PASS |
| `test_n4_scene_look_exempt.py::test_scene_missing_plus_char_missing_face_still_409` | PASS |
| `test_n4_scene_look_exempt.py::test_assemble_expands_thick_scene_text_without_plate` | PASS |
| `test_n4_scene_look_exempt.py::test_char_only_assemble_writes_jsonl_on_ep01` | PASS |
| `test_n4_scene_look_exempt.py::test_char_missing_face_still_409_on_exempt_assemble` | PASS |
| `test_n4_scene_look_exempt.py::test_force_pass_still_400_on_exempt_path` | PASS |
| `test_n4_char_look_mode.py::test_mode_b_reviewed_sheet_usable_without_face_file` | PASS |
| `test_n4_char_look_mode.py::test_mode_b_does_not_409_on_missing_face_file_when_sheet_reviewed` | PASS |
| `test_n4_char_look_mode.py::test_mode_b_without_reviewed_sheet_still_blocks_but_not_as_missing_face` | PASS |
| `test_n4_char_look_mode.py::test_mode_a_missing_face_still_409` | PASS |
| `test_n4_char_look_mode.py::test_generate_look_does_not_self_green_sheet` | PASS |
| `test_n4_char_look_mode.py::test_mode_b_assemble_writes_jsonl_without_face` | PASS |
| `test_n4_gates.py::test_force_pass_forbidden_on_assemble` | PASS |
| `test_n4_api.py::test_http_force_pass_forbidden` | PASS |
| `test_n4_api.py::test_http_char_only_assemble_when_scene_exempt` | PASS |
| `test_n3_g3.py::test_usable_for_n4_true_with_char_refs_only_when_exempt` | PASS |
| 同批其余 n3/n4/g3/look/workbench/copy | PASS |

## 禁项核对

- ≠自绿：`generate-look` 仍 `usable_for_n4=false`；不写 USABLE*.md。
- ≠翻 dogfood 盘上 `usable_for_n4` 旗。
- T0–T5 全文门未做（本拍 P0 改门）。
- Mode B LOOK 真狗粮 / 明早人审 **不挡** 本 PR。
- **≠ merge.**
