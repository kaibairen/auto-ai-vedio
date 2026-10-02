# AIV-032 · 金样 A 3:2 CHAR 合板 look-generate

| 项 | 值 |
|----|----|
| BRIEF | `BRIEF-AIV-032-GOLD-SHEET-HARDEN-v0` |
| ASSIGN | AIV-032-ENG-001 |
| 金样 | ENG-031 / `RUN-AIV-031-DOUBAO-SHEET-ENG-001` SUCCESS |
| 状态 | docs≠PASS · ForcePass=never · ≠合 main · ≠绿 N4 |
| 共用函数 | `aiv_drama_n3.look_generate.generate_gold_a_sheet` + `assemble_gold_a_sheet_prompt` |

工作台 Screen H「合板 generate-look」与 CLI **同一** assemble+Ark 函数。无平行孤儿脚本。

## 契约（与 eng-031 对齐）

| 项 | 值 |
|----|----|
| API | `POST https://ark.cn-beijing.volces.com/api/v3/images/generations` |
| SKU 主 | `doubao-seedream-5-0-flash-260915` |
| SKU 备 | `doubao-seedream-5-0-pro-260628` → `doubao-seedream-4-5-251128` → `wan2.7-image` |
| body | `model` + `prompt` + `size=2048x1365` + `watermark=false` + `response_format=url` + `image`=face data-URL |
| 禁 | `sequential_image_generation`；拆 CU/LS 多图冒充合板 |
| Prompt 序 | STYLE终句（ADDENDUM 一字不改）→ RECIPE§4 合板正文（一字不改）→ 厚卡 wardrobe/immutable → 身高句（若有）→ negatives → EN identity 锚句 →「输出单张3:2横版合板」 |
| 门 | 脸 ref **md5 核验先于** generate |
| usable | 合板记录 `usable_for_n4=false`；**不**自翻集级 usable；不把 sheet 写成 face/full |

wardrobe / immutable / height **只**从厚卡字段读取。缺服装字段 → `look_card_incomplete`，禁助手自写合板正文。

## CLI

### 无人值守狗粮（卡路径 + 脸 ref）

```bash
# 无 Key / CI：dry-run 落盘 prompt + recorded Ark 请求（无像素、无 Key）
aiv drama n3 generate-look \
  --card fixtures/drama/gold-a/CHAR-01-card.yaml \
  --face-ref /path/to/CHAR-01-user-ref.jpg \
  --expected-md5 a8c70f3b4cb7855284d3d4d2bd3c906d \
  --out ./looks/CHAR-01 \
  --dry-run

# 盒上有 Key（只读 env 或 ~/.config/aiv/ARK_API_KEY；禁 echo / 禁入仓）
# export ARK_API_KEY=...     # do not print
aiv drama n3 generate-look \
  --card fixtures/drama/gold-a/CHAR-01-card.yaml \
  --face-ref /path/to/CHAR-01-user-ref.jpg \
  --expected-md5 a8c70f3b4cb7855284d3d4d2bd3c906d \
  --out ./looks/CHAR-01
```

产物：`{id}-doubao-sheet-prompt.txt`（全文 + md5）· `{id}-turnaround-sheet-3x2.jpg`（live）· `{id}-ark-request.recorded.json`（dry-run）。新 sheet md5 可异于金样 `a46b88eb54508c8240381afcf1d78241`。

### 本集 N3 路径（与 HTTP / 工作台相同）

```bash
aiv drama n3 generate-look \
  --project proj_01 --ep EP01 --id CHAR-01 \
  --face-ref /path/to/CHAR-01-user-ref.jpg \
  --dry-run
```

前置：G2 已锁 + 本集 CHAR 已 materialize，且厚卡有 `appearance`/`wardrobe` + `immutable`。不自动绿 N4。

## HTTP / 工作台

`POST /api/v0/projects/{id}/episodes/{ep}/drama/n3/cards/generate-look`

```json
{ "id": "CHAR-01", "face_ref": "/path/to/face.jpg", "expected_md5": "…", "dry_run": true }
```

Screen H：选 CHAR、填 face ref、默认 dry-run 勾选后点「合板 generate-look」。

## Key

- 环境变量 `ARK_API_KEY` 或 `AIV_ARK_API_KEY`，或文件 `ARK_API_KEY_FILE` / `~/.config/aiv/ARK_API_KEY`
- **禁止**写入 git、evidence、prompt、日志、信封 JSON
- 无 Key 且非 dry-run → `422 provider`（诚实失败，不造像素）

## 指针

- STYLE：`ADDENDUM-AIV-031-STYLE-BANANA-PHOTOREAL-v0`
- RECIPE：`RECIPE-AIV-031-BANANA-LOCAL-v0` §4；实测参数见 `docs/APPEND-AIV-031-RECIPE-EXEC-v0.md`
- BIND：`NOTE-AIV-031-BANANA-MATERIAL-BIND-v0`
- 金样 prompt：`fixtures/drama/gold-a/CHAR-01-doubao-sheet-r1-prompt.txt`

— AIV-032-ENG-001 · ≠合 main · ≠绿 N4 —
