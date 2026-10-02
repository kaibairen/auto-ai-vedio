# 单元剧 D-N5b 出片骨架（门 G5）

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N5b**（Ark Seedance 2.0 tasks client + clips 契约 + 门 G5） |
| 接口权威 | [`openapi/drama-n5b.v0.yaml`](../openapi/drama-n5b.v0.yaml) **0.1.0** |
| 锚 | NOTE-AIV-036-N5B-API-SCOUT-v0 md5 **`a11e4b39460139ef8d4dac78ef86768a`** |
| 状态 | **docs≠PASS** · ForcePass=**never** · **skeleton** · 禁真 Job POST · 禁假像素 · N6 不做 |

本包停在骨架。**不**宣称 LOOP-PASS / 成片 / 合 main。N5a 宫格是并行稿，本 PR **不**实现 generate-grid，只**读** `gate_g4`。

---

## 人怎么走

1. 上游已有 `episodes/EP##/EP##-prompts.jsonl`（N4 assemble）。
2. **门 G4** locked（或 `written_subset` 书面子集）——由 N5a 写入；本包不点 G4。
3. `GET .../drama/n5b/status`：看 mapped / clips / `posted=false`。
4. `POST .../drama/n5b/jobs`：**默认 409**。
   - G4 未过 → `g4_required`
   - 未设 `AIV_N5B_ALLOW_LIVE_JOB` → `live_job_forbidden`（details 含 dry mapped）
   - 标志已设 → 仍 `n5b_impl_hold`（本 ASSIGN 永不 POST create）
5. 人点 `POST .../gates/g5/confirm` `pass|rework`。pass 须已有真 clips+meta。ForcePass → 400。

Mode B look 审（缺 face 文件）**不**挡本骨架 submit 代码。

---

## Bot / CLI

```bash
aiv drama n5b status --project proj_01 --ep EP01
aiv drama n5b submit --project proj_01 --ep EP01 --shot S01 --actor yangzhou
# 期望 409 g4_required 或 live_job_forbidden；stdout JSON；posted=false
aiv drama n5b gate g5 --project proj_01 --ep EP01 --actor yangzhou --verdict rework
aiv drama g5 get --project proj_01 --ep EP01
```

---

## 映射（SCOUT）

| jsonl | Ark |
|-------|-----|
| `prompt` + `negative` | `content[]` `type=text`（负词拼 `\n负面：`） |
| `ref_images[]` | `image_url` + `role=reference_image`（≤9；本地 path 不伪造公网 URL） |
| `duration_s` ∈ {5,8,10} | `duration` |
| `aspect` `2.35:1` | `ratio=21:9` |
| `shot_id` | 落盘名 `clips/<shot_id>.mp4` + `.meta.json` |
| 默认 model | `doubao-seedance-2-0-260128` |

Base `https://ark.cn-beijing.volces.com/api/v3`（`ARK_BASE_URL`）。Auth 名与 N3 同：`ARK_API_KEY` / `ARK_API_KEY_FILE`。evidence 禁 Key 明文。

落盘契约：`write_clip_bytes` / `write_clip_meta` **只写调用方字节**；空/彩条标记 → FAIL。成功 meta 最少 **SKU · job_id · md5**。

---

## 硬

- ForcePass=never
- 零付费 Job（CI / 默认路径）
- 假像素 = FAIL
- ≠ LOOP-PASS · N6 out of scope · ≠ merge
