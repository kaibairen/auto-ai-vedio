# 单元剧 D-N3 look 落盘（AIV-031）

| 项 | 值 |
|----|----|
| pipeline_profile | **drama** |
| 节点 | **D-N3 look**（`episodes/<ep>/n3/looks/`） |
| 接口权威 | [`openapi/drama-look.v0.yaml`](../openapi/drama-look.v0.yaml) **0.1.0** |
| SoT | `DESIGN-AIV-031-LOOK-v0` · `DESIGN-AIV-031-ENG-v0` |
| 状态 | **docs≠PASS** · ForcePass=**never** · ≠绿 N4 · ≠翻 usable |

工程只挂图：写 `looks/` + `refs[{path,md5,role}]`。**不**自动 `usable_for_n4=true`。缺合格 face / usable=false → N4 assemble 仍 **409**。

## 人怎么走

1. N2 G2 pass → N3 materialize → **文字 thicken**（`appearance`/`immutable`/`light_anchor`）。
2. **POST** `.../drama/n3/looks/generate` 一次一张卡：CHAR → `face_front`（CU）；SCENE → `plate_empty`（空镜 LS）。
3. 落盘 `episodes/<ep>/n3/looks/{char|scene}/<card_id>/`，算 md5，挂 refs。水印 OFF。
4. `usable_for_n4` 仍为 false（挂起面三轴另拍）。N4 assemble 在缺图/未翻 usable 时 **409**。
5. `force_pass` → **400**。热链 URL 当 path → **400** `hotlink_url_forbidden`。

## Bot / CLI

```bash
# Keys isolated from DeepSeek / AIV_OPENAI_API_KEY
export ARK_API_KEY=...
# optional backup
# export DASHSCOPE_API_KEY=...

aiv drama look generate --project proj_01 --ep EP01 --id CHAR-01 --actor eng-031
aiv drama look generate --project proj_01 --ep EP01 --id SCENE-01 --actor eng-031
```

默认 SKU `doubao-seedream-5-0-flash-260915`。升档须书面 reason∈{identity_drift,api_fail,quality_gate}（`--upgrade-reason`），**≠更好看**。

狗粮步骤见 [`RUN-NOTES-AIV-031-LOOK.md`](RUN-NOTES-AIV-031-LOOK.md)。
