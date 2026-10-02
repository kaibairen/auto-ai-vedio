# RUN-NOTES · AIV-031 LOOK dogfood（skeleton）

| 项 | 值 |
|----|----|
| BRIEF | BRIEF-AIV-031-LOOK-IMPL · AIV-031-IMPL-ENG-001 |
| 性质 | 工程狗粮笔记骨架 · **≠PASS** · **≠绿 N4** · ForcePass=never |
| tip | `4bd1aa2` (look impl) · pytest green on this branch |

## 环境（密钥隔离）

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
export AIV_REPO_ROOT=.

# N1/N2/N3 thicken 仍走 DeepSeek（可选）
# export AIV_OPENAI_API_KEY=...          # 禁止当看出图 Key
# export AIV_OPENAI_BASE_URL=https://api.deepseek.com/v1

# Look 出图（硬隔离）
export ARK_API_KEY=...                   # 方舟 Seedream · 主
# export DASHSCOPE_API_KEY=...           # 百炼 wan · 备（北京域）
# export AIV_LOOK_SKU=doubao-seedream-5-0-flash-260915
# export AIV_LOOK_STYLE_REF=             # 整句替换 STYLE-REF；换则全员重抽
```

| 钉 | 值 |
|----|----|
| 默认 SKU | `doubao-seedream-5-0-flash-260915` |
| 水印 | OFF |
| seed | 同 CHAR 同 seed；SCENE 分种 |
| SEED_REPLAY | _ok / partial（对照官方是否回放 seed）_ |

## 链（SUCCESS ≠ 绿 N4）

```text
N0 → N2 → G2 → N3 materialize → thicken（G3 锁前）
  → look generate CHAR-01 (face_front)
  → look generate SCENE-01 (plate_empty)
  → 确认 refs 有 path+md5+role
  → 确认 usable_for_n4=false
  → POST n4/assemble 仍 409（未挂起面 / 未齐卡）
```

```bash
aiv drama look generate --project <pid> --ep EP01 --id CHAR-01 --actor eng-031
aiv drama look generate --project <pid> --ep EP01 --id SCENE-01 --actor eng-031
```

## 检查清单

| 检 | 期望 |
|----|------|
| 落盘 | `data/projects/<pid>/episodes/EP01/n3/looks/char/CHAR-01/face_front.png` |
| refs[].path | `episodes/EP01/n3/looks/char/CHAR-01/face_front.png`（非 URL） |
| md5 | 与文件 bytes 一致；非空 |
| role | CHAR `face`；SCENE `plate` |
| usable_for_n4 | **false** |
| N4 assemble | **409** `usable_for_n4_false` · 不写 `EP##-prompts.jsonl` |
| Key | 请求走 Ark/DashScope host，不带 `AIV_OPENAI_API_KEY` |
| 升档 | 仅 identity_drift / api_fail / quality_gate；meta.json 记 sku_from/to/reason |

## 非声称

≠ 出图观感 PASS · ≠ 挂起面三轴已翻 usable · ≠ 绿 N4 · ≠ 合 main · ≠ N5 · docs≠PASS
