# 短剧 D-N2 分镜表运行时（门 G2）

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N2**（分镜表） |
| 门 | **G2**（唯一锁入口 `POST .../gates/g2/confirm`） |
| 接口权威 | [`openapi/drama-n2.v0.yaml`](../openapi/drama-n2.v0.yaml) **0.1.0** |
| 存储 | API/DB（`drama_storyboard` + `drama_storyboard_shot` 逻辑表，JsonStore 承载）为读写源；盘为投影 |
| 状态 | **docs≠PASS** · ForcePass=**never** · 实施 PR ≠ 产品 PASS |
| 命名 | 短剧 **D-N2 / G2**；禁止裸「N2」；≠ **koubo-N1** |

本包停在 G2。`next_edges: ["D-N3"]` **只是候选**，**不**自动开 D-N3、不写制卡/提示词/宫格/出片。

薄 FE 分镜表页：**018c 已升到日用最低可用**（Screen E 表 + 芯片 + F/G 门态）。不做 CastId 高级编辑 / D-N3 定妆 / Seedance 出片台。docs≠PASS。

---

## 冻结 O1–O9（DESIGN-ACCEPT · 不可再摇摆）

| ID | 口径 |
|----|------|
| **O1** | 无独立剧本硬门；大纲+cast → 直出分镜 |
| **O2** | `storyboard_skill: borrowed_dongman`；只读借用 `.skill/writing/动态漫-转分镜`；禁注入 Seedance 出片 Skill |
| **O3 / O8** | NODE-SPEC 最低列 + 必填 `bridge_id`；`angle` / `camera_speed` 默认 `notes` 前缀，不加死列 |
| **O4** | API/DB 权威 + 盘投影 `EP##-分镜.csv` + `EP##-分镜.md` |
| **O5** | 未知具名 CHAR/SCENE 硬拒 `cast_id_unknown`；空镜/群杂允许 `NONE` 或 `[]` |
| **017a O1=A** | generate 后自动入表具名对戏主体并回填 `char_ids` |
| **017a O2** | 侧车加角不拆 G1b；cast 升 version + hint；禁静默改锁态大纲正文 |
| **017a O5** | 默认 `named_cast_check=warn`；G2 pass 若仍有 `named_cast_*` → `named_cast_gate` |
| **O6** | `shot_cap` 继承 outline；硬上限 **≤12**；超限 `shot_cap_exceeded` |
| **O7** | 景别/运镜 **英文短码**入库/落盘；中文标签仅 UI（本批无薄 FE） |
| **O9** | `tool_profile` 可空不挡 G2；未选禁 `ready_for_n4` |
| **020 P0-A** | B 档（`【系统音】`/弹窗/旁白/广播半截/动词短语/脏前缀）**不得**开 CHAR；姓名只来自本集预挂人物卡，前缀/后缀折回同一 id；「两位将军」解析到已挂个体槽 |
| **020 P0-B** | generate 时长默认吸附到 **{5,8,10}**（profile 空也吸附，bucket 仍 null）；选 `tool_profile` 后硬吸附且 duration↔bucket 同秒 |
| **020 P0-C** | generate/GET/validate 落盘 `skill_paths` + `skill_excerpt` + `skill_trace`；`n2_request` 备证 |
| **023 P0-A** | Banlist B-ACT/TAG/FRAG/GEN **不得**开 CHAR。无剧集专名白名单。已挂行不因通用头衔分类被丢掉。清零= classifier/merge，≠事后手删卡 |
| **023 P1-3** | 类 D 运镜（HANDHELD/WHIP_*/ORBIT/DOLLY_ZOOM/ROLL）生成默认+吸附 **duration_s≥8**；有 profile 仍低于 8 → `duration_below_camera_floor` |
| **025 A** | Class-D 闭集不变；D≥8 **不回退**。条数/种类加厚为 **SHOULD** warn（`class_d_count_below_suggest` / `class_d_kinds_below_suggest` / `class_d_monoculture`），**不**单独挡 `ready_for_n4`，不可 ForcePass |
| **025 B** | named_cast **name 槽**：姓名只来自本集预挂卡；前缀/后缀折回同一 id；对不上则不硬折；漏库新角色仍按 §5.2 新开 id。one_line/大纲散文里的头衔**不**当 name 拒 |

---

## 人怎么走

1. 先走完 D-N0 / D-N1，**门 G1b pass**（outline+cast 均 `locked`）。未锁时 generate / GET 分镜 → **409 `upstream_unlocked`**（`node=D-N1`, `gate=g1b`）。
2. **POST** `.../drama/storyboard/generate`。`provider=fixture`（默认 / 无密钥）走确定性草稿；`provider=llm` 走 **真实** OpenAI 兼容 Chat（与 D-N1 同一套 `AIV_OPENAI_*`）。无密钥却要 llm → **422 `provider`**，**不会**静默回落 fixture。Skill 元数据 `borrowed_dongman`。无独立 `script_draft`。
3. 锁前可 **PUT** 整表、**POST validate / reorder / reset**。
4. 未知具名 ID → **422 `cast_id_unknown`**；空镜用 `NONE`。镜数 > `shot_cap` → **422 `shot_cap_exceeded`**。表内完整出片提示词 → **422 `prompt_forbidden`**（无 prompt 列）。
5. **门 G2**：`{ decision: pass|reject, actor, note? }`。
   - pass → storyboard `locked=true`，`confirmed_by=actor`，`next_edges=["D-N3"]`，**不**创建 D-N3 job。
   - reject → 保持可编辑，记 note。
   - `force_pass` / `force` / `skip_gate` → **400 `force_pass_forbidden`**。
   - `stale=true`（上游 unlock 未刷新）→ **409 `stale_upstream`**。
   - 未选 `tool_profile` 可通过；`ready_for_n4` 必须 false。
   - 仍有 `named_cast_*`（017a O5）→ **422 `named_cast_gate`**。默认 warn 不改 validate `valid`，但挡 G2 pass。
6. 锁后改表须 `unlock_edit=true` → version++、清 locked、下游 **D-N3 stale**。静默 PUT → **409 `locked`**。

---

## Bot / CLI 怎么调

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
export AIV_LLM_PROVIDER=fixture
# 先走 D-N1 / G1b
aiv --fixture --pretty drama demo --ep EP01 --lane female
# D-N2 fixture（无密钥）
aiv drama storyboard generate --project proj_01 --ep EP01 --provider fixture
# D-N2 真 LLM（须 AIV_OPENAI_API_KEY；DeepSeek 兼容基址示例）
# export AIV_OPENAI_API_KEY=...
# export AIV_OPENAI_BASE_URL=https://api.deepseek.com/v1
# export AIV_OPENAI_MODEL=deepseek-chat
aiv drama storyboard generate --project proj_01 --ep EP01 --provider llm
# 侧车加角（不拆 G1b / 不改大纲正文）
aiv drama cast sidecar-add --project proj_01 --ep EP01 --name 预挂丙将军 --one-line 侧车配角
aiv drama storyboard validate --project proj_01 --ep EP01
aiv drama g2 confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
aiv drama storyboard get --project proj_01 --ep EP01
```

`provider` 分支：`fixture` / `skill` → `FixtureStoryboardProvider`；`llm`（及 `openai` / `openai_compat`）→ `LlmStoryboardProvider`。llm 注入锁态大纲+cast + 只读借用 `.skill/writing/动态漫-转分镜` 摘录，**不**注入 Seedance 出片 Skill。

---

## LLM 环境（与 D-N1 相同）

| 变量 | 作用 |
|------|------|
| `AIV_OPENAI_API_KEY` 或 `OPENAI_API_KEY` | 必填才会打真模型 |
| `AIV_OPENAI_BASE_URL` / `OPENAI_BASE_URL` | 默认 `https://api.openai.com/v1`；DeepSeek 用其兼容 `/v1` |
| `AIV_OPENAI_MODEL` / `OPENAI_MODEL` | 默认 `gpt-4o-mini` |
| `AIV_LLM_PROVIDER` | 进程默认；`fixture` 或 `llm`。CLI `--provider` 覆盖单次 generate |

无密钥时请用 `--provider fixture`。密钥禁止写入 `episodes/**`。

等价 REST（根路径 `/api/v0`）：

```
GET|PUT  /projects/{id}/episodes/{ep}/drama/storyboard
POST     .../drama/storyboard/generate    {provider: fixture|llm|skill, tool_profile?, actor?}
POST     .../drama/cast/sidecar-add       {name, one_line?, actor?}   # O2 不拆 G1b
POST     .../drama/storyboard/validate
POST     .../drama/storyboard/reorder     {shot_ids: ["S02","S01",...]}
POST     .../drama/storyboard/reset       {unlock_edit?}
GET      .../gates/g2
POST     .../gates/g2/confirm             {decision: pass|reject, actor, note?}
```

写接口可带 `Idempotency-Key`、`If-Match`（storyboard version）。

OpenAPI 拷贝：`GET /openapi/drama-n2.v0.yaml`。

---

## 盘投影（API 为源）

相对 `{AIV_DATA_DIR}/projects/{project_id}/episodes/EP{NN}/`：

```
EP{NN}-brief.yaml          # D-N0
EP{NN}-大纲.md             # D-N1
EP{NN}-cast.yaml           # D-N1
EP{NN}-分镜.csv            # D-N2 机读投影（英文 shot_size/camera；无 prompt 列）
EP{NN}-分镜.md             # D-N2 人读投影（可按 bridge_id 分组）
.aiv/episode.json          # versions.storyboard · gates.g2 · stale.d_n2/d_n3 · storyboard_meta
```

密钥禁止进入 `episodes/**`。人手改盘 **不视为提交**；下次 API 写覆盖投影。写盘失败标 `projection_dirty`，**不以旧盘盖 API**。

---

## 与 D-N0 / D-N1 / koubo 隔离

| | 短剧 D-N2 | 上游 D-N1 | 口播 koubo-N1 |
|--|-----------|-----------|----------------|
| 门 | `gates/g2` | `gates/g1b` | `gates/g1` |
| 路径 | `/drama/storyboard` | `/drama/outline` · `/drama/cast` | `/n1` · `/nodes/n1` |
| 定稿 | `EP##-分镜.csv\|md` | `EP##-大纲.md` + cast | `N1-口播定稿.md` |
| Skill | 只读借用动态漫-转分镜 | 女/男频编剧 | `.prompt/koubo-*` |

本进程对 `/n1`、`/nodes/n1`、`/gates/g1` 以及裸 `/n2`、`/nodes/n2` 返回 **404**。短剧分镜只走 `/drama/storyboard` + `/gates/g2`。

G1b pass 的 `next_edges: ["D-N2"]` 与 G2 pass 的 `["D-N3"]` 都只是导航候选，不自动开下游 job。

---

## 错误码（主路径）

| code | HTTP | 场景 |
|------|------|------|
| `force_pass_forbidden` | 400 | force/skip 门字段 |
| `upstream_unlocked` | 409 | G1b 未锁却进 D-N2 有意义读写 |
| `stale_upstream` | 409 | storyboard.stale 未处理却 G2 pass |
| `locked` | 409 | 锁后未 `unlock_edit` |
| `version_conflict` | 409 | If-Match 不符 |
| `shot_cap_exceeded` | 422 | 行数 > shot_cap（PUT 空表亦此码） |
| `storyboard_empty` | 422 | G2 pass 时空表 |
| `prompt_forbidden` | 422 | 完整出片提示词入表 / 禁列 |
| `cast_id_unknown` | 422 | 具名 CHAR/SCENE ∉ cast |
| `named_cast_gate` | 422 | G2 pass 时仍有 `named_cast_*`（017a O5 产品门） |
| `named_cast_missing` | 422 | `named_cast_check=error` 时具名未入表抬 HTTP |
| `bridge_id_missing` | 422 | 缺 bridge_id |
| `cam_enum_invalid` | 422 | shot_size/camera 非 CAM 英文闭集 |
| `duration_bucket_mismatch` | 422 | 已选 tool_profile 且 duration↔bucket 不一致 |
| `ready_for_n4_requires_tool_profile` | 422 | 未选工具却标记可出片（evaluate overlay） |
| `tool_profile_unset` | warn | 未选工具；不挡 G2，挡 ready_for_n4 |
| `wrong_profile` | 422 | pipeline_profile≠drama |

景别跳变 J1–J2：**warn**，不硬拒。

---

## 非目标

- D-N3 制卡、N4 提示词、宫格、出片、Seedance 工作流
- 口播 koubo-N1 运行时
- 改 `.skill` / `.prompt` 教材正文
- 自动开 D-N3；跨短剧线
- 薄 FE 分镜表页（本批债）
- 把 docs 齐套当成产品 PASS

CONTRACT-BE §8 矩阵见 `tests/drama/test_n2_contract.py` 与 `tests/drama/test_n2_api.py`。
