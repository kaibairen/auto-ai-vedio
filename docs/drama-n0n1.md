# 短剧 D-N0 / D-N1 运行时（门 G1b）

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N0**（题材入口）· **D-N1**（编剧扩场） |
| 门 | **G1b**（唯一锁入口 `POST .../gates/g1b/confirm`） |
| 接口权威 | [`openapi/drama-n0n1.v0.yaml`](../openapi/drama-n0n1.v0.yaml) **0.1.0** |
| 状态 | **docs≠PASS** · ForcePass=never · 实施 PR ≠ 产品 PASS |
| 命名 | 短剧 **D-N0 / D-N1**；口播 **koubo-N1**。禁止裸写「N1」 |

本包停在 G1b。`next_edges: ["D-N2"]` **只是候选**，**不**自动开 D-N2。D-N2 运行时见 [`docs/drama-n2.md`](drama-n2.md)（须显式 generate；本包不写分镜）。

---

## 人怎么走

1. 建项目 stub → 建集 `episode_id=EP01` 且 `pipeline_profile=drama`。
2. **D-N0**：PUT brief。`title_intent` 或非空 `pin` 至少其一；`lane_preference=unset` **可以保存**。主角身份句须落 `hero_one_line`（brief）或预挂/薄 cast，不可仅会话草稿。
3. 可选：把 project 内角色 `CHAR@version` attach 到本集（D12：出项目 → 404）。OpenAPI **没有**库 list/search，本批不实现搜索；attach 只接受显式 id@version。狗粮入库：`aiv drama library put` 或 `PUT /api/v0/projects/{id}/library/characters/{character_id}`（扩展，不是 list/search）。
4. **A2 意图确认（018a）**：`POST .../drama/intent/confirm` 写入集级 `intent.confirmed` + `intent.fingerprint`（投影 `.aiv/episode.json`）。未确认正式 generate → **422 `intent_unconfirmed`**；MUST 变更后未再确认 → **422 `intent_stale`**；lane×预挂冲突禁确认 → **422 `intent_lane_conflict`**（一键跟预挂改 lane，不上 `lane_cast_mismatch`）。`POST .../drama/intent/clear` 清确认。确认≠G1b。
5. **D-N1**：POST generate。须先意图确认。请求 `lane` 或 brief `lane_preference` 必须是 `female|male`，否则 **422 `lane_required`**。无 `dual_skill_preview`（C1 已关）。默认 `provider=fixture`（无密钥）。
6. 锁前可 PUT outline / cast / attach / detach。CHAR/SCENE **新行不要自造 id**（省略则后端发号；自造 → 422）。
7. **门 G1b**：`{ decision: pass|reject, actor, note? }`。
   - pass → outline+cast `locked=true`，`confirmed_by=actor`，`next_edges=["D-N2"]`，**不**创建 D-N2 job。
   - reject → 保持可编辑，记 note，不写通过态 `confirmed_by`。
   - 请求带 `force_pass` / `force` / `skip_gate` / `skip_intent` → **400 `force_pass_forbidden`**。
8. 锁后写必须 `unlock_edit=true` → 升 version、清 locked、`stale_downstream` 含 **D-N2**。静默 PUT → **409 `locked`**。
   **例外（017a O2）**：`POST .../drama/cast/sidecar-add` 锁后可加具名 CHAR，**不**拆 G1b、**不**改大纲正文，只 bump `cast.version` 并回 `cast_changed` hint。
9. 未锁时下游读 `GET .../drama/downstream` → **409 `upstream_unlocked`**。该路径是 D-N2 **只读消费面**（OpenAPI 未列；不启动 D-N2）。

薄 UI（可选）：`aiv serve` 后打开 `/` 或 `/workbench`。无 force 控件。

---

## Bot / CLI 怎么调

安装（fixture 模式，无需 API key）：

```bash
python3 -m pip install -e ".[dev]"
export AIV_DATA_DIR=./data
export AIV_LLM_PROVIDER=fixture
pytest
aiv --fixture --pretty drama demo --ep EP01 --lane female
aiv serve   # :8000  REST + 薄向导
```

CLI 与 REST 走同一 `DramaService`（API 为源，盘为投影）。禁止手改 `episodes/**` 冒充锁定。

```bash
aiv drama project create --name 短剧狗粮-01
aiv drama library put --project proj_01 --character-id CHAR-01 --version 1 --name 林晚 --one-line 重生女主
aiv drama episode create --project proj_01 --ep EP01
aiv drama brief put --project proj_01 --ep EP01 --title-intent "被流放的庶女在边关翻盘" --lane female --hero-one-line 重生女主
aiv drama cast attach --project proj_01 --ep EP01 --character-id CHAR-01 --version 1
aiv drama intent confirm --project proj_01 --ep EP01 --actor eng-018a
aiv drama outline generate --project proj_01 --ep EP01 --lane female --provider fixture
aiv drama gate confirm --project proj_01 --ep EP01 --decision pass --actor yangzhou
aiv drama downstream get --project proj_01 --ep EP01
```

等价 REST（根路径 `/api/v0`）：

```
POST /projects
POST /projects/{project_id}/episodes          {episode_id, pipeline_profile: drama}
PUT  /projects/{id}/episodes/{ep}/drama/brief
GET|POST .../drama/intent[/check]
POST .../drama/intent/confirm
POST .../drama/intent/clear
POST /projects/{id}/episodes/{ep}/drama/outline   {lane: female|male, provider: fixture}
PUT  /projects/{id}/episodes/{ep}/drama/outline
POST /projects/{id}/episodes/{ep}/drama/outline/reset
GET|PUT .../drama/cast
POST .../drama/cast/attach   {character_id, version}
POST .../drama/cast/detach   {character_id}
POST .../drama/cast/sidecar-add {name, one_line?}  # O2 不拆 G1b
GET  .../gates/g1b
POST .../gates/g1b/confirm   {decision, actor, note?}
GET  .../drama/downstream    # 扩展：未锁 409；pass 后只读；started=false
```

写接口可带 `Idempotency-Key`、`If-Match`（资源 version）。

LLM：`provider=llm` 且设置 `AIV_OPENAI_API_KEY`。无密钥时请用 fixture。女/男频 Skill **只读**引用：

- `.skill/writing/女频短剧编剧/SKILL.md`
- `.skill/writing/男频短剧编剧/SKILL.md`

不改教材正文。

---

## 盘投影（API 为源）

相对 `{AIV_DATA_DIR}/projects/{project_id}/`：

```
episodes/EP01/
  EP01-brief.yaml
  EP01-大纲.md
  EP01-cast.yaml
  .aiv/episode.json
libraries/characters/CHAR-01/v1/character.yaml   # 不在 episodes/** 下
```

密钥禁止进入 `episodes/**`。人手改盘 **不视为提交**；下次 API 写会覆盖投影。

---

## 与 koubo-N1 隔离

| | 短剧 D-N1 | 口播 koubo-N1 |
|--|-----------|----------------|
| 门 | `gates/g1b` | `gates/g1` |
| 定稿 | `EP##-大纲.md` + `EP##-cast.yaml` | `N1-口播定稿.md` |
| Skill | 女/男频编剧 | `.prompt/koubo-*` |
| 本 PR | **本运行时** | **不迁入**（`feature/koubo` 另轨） |

本进程对 `/n1`、`/nodes/n1`、`/gates/g1` 返回 404，并说明应走 D-N0 / D-N1 / g1b。

---

## Provisional（实施取向 · 不替用户终选）

| ID | 取向 |
|----|------|
| D3 | 生成前必选 `female\|male`；unset→422；无 dual Skill |
| D12 | 仅 project 内库；无 list/search |
| D13–D15 | 无 promote/fork；`library_ref` 预留 |
| shot_cap | 硬上限 **12** |

---

## 错误码（主路径）

| code | HTTP | 场景 |
|------|------|------|
| `force_pass_forbidden` | 400 | force/skip 门字段 |
| `lane_required` | 422 | 确认/生成前赛道 unset |
| `brief_incomplete` | 422 | title 与 pin 皆空 |
| `intent_unconfirmed` | 422 | 未确认却正式 generateOutline |
| `intent_stale` | 422 | 已确认但 MUST 指纹漂移 |
| `intent_lane_conflict` | 422 | lane×预挂冲突，禁确认 |
| `locked` | 409 | 锁后未 `unlock_edit` |
| `upstream_unlocked` | 409 | 下游读时 G1b 未锁 |
| `downstream_locked` | 409 | 改 brief 时大纲仍锁且未 `confirm_stale_outline` |
| `version_conflict` | 409 | If-Match 不符 |
| `outline_contains_prompts` | 422 | 正文含宫格/提示词 |
| `cast_incomplete` | 422 | pass 时缺人/缺场 |
| `shot_cap_exceeded` | 422 | 超 12 |

018d 中英目录：`GET /api/v0/drama/error-catalog`。出片档机检：`POST .../drama/copy-contract/evaluate`（不改 generate）。
OpenAPI 仍标 **0.1.0**（诚实增量，非 0.2.0）。契约 CI：`tests/contract/test_error_codes_sync.py`。
docs≠PASS；ForcePass=never。

CONTRACT-BE §8 测试矩阵见 `tests/drama/test_contract_matrix.py`。
