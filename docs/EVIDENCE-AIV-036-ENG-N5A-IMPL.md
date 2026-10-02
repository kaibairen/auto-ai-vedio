# EVIDENCE · AIV-036-ENG-N5A-IMPL

| 项 | 值 |
|----|----|
| ASSIGN | **AIV-036-ENG-N5A-IMPL** |
| Base | `main` tip `69eda17`（含 PR#21 AIV-032） |
| 范围 | N5a 最小闭环：真图 API 合同 → `grids/` + 检项 + **门 G4** |
| 状态 | draft PR · **≠合 main** · docs≠PASS · **N5b 不做** |

## 冻结钉落实

| 钉 | 落实 |
|----|------|
| P-CHAR | `usable_for_n4=true` 语义 = 人审合板；本 PR **不翻** usable。见 `look_mode.py` / envelope `p_char`。 |
| Mode B | 无 face/full ref → Mode B；generate **不** 409。测：`test_mode_b_does_not_require_face_file`。 |
| SCENE EXEMPT EP01 | 检 G4 → `N/A·EXEMPT`；G1/G2/G3/G9 仍 hard。测：`test_ep01_scene_exempt_g4_item_na`。 |
| ForcePass=never | generate / G4 / HTTP middleware 拒 `force_pass`/`force`/`skip_gate` → 400。 |
| 禁假像素 | `assert_real_image_bytes`；无钥 → `provider` BLOCK（`blocked=true`,`written=false`）；不写 PNG。 |
| ≥7/9 | `threshold_hard_gated=false`；检项记录 + 文档 only。 |
| 门序 | 无 jsonl → 409；G4 未锁 N5b → 409；G4 已锁 N5b → 404 `n5b_not_implemented`。 |

## 表面

- 包：`packages/drama-n5a-core/`
- CLI：`aiv drama n5a generate-grid` · `aiv drama n5a gate g4`
- API：`POST .../drama/n5a/generate` · `POST .../gates/g4` · `GET .../drama/n5a/status`
- OpenAPI：`openapi/drama-n5a.v0.yaml`
- 测：`tests/drama/test_n5a_gates.py`（合同 + mock 边界；**不要求 live 出图**）

## 无钥 / 无 live 图

CTO：ship contracts + unit tests + mock boundaries。  
Live `ARK_API_KEY` 缺失 → 结构化 **BLOCK**，禁止把 dry-run / 占位格写成 SUCCESS/PASS。

## 协调

- 无已开的 U-033 SCENE-optional draft PR；本 PR **不** 静默合入 033。
- 并行 draft：AIV-031 #19 / #20（look refs）— 不依赖、不合并。
- N5b Job / N6 / 合 main / 翻 usable：**out of scope**。
