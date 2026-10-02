# APPEND · RECIPE 工程可执行 · 本拍实测（禁 Key）

| 项 | 值 |
|----|----|
| 上游 | `RECIPE-AIV-031-BANANA-LOCAL-v0.md` §6 出图参数（教材缺 size/SKU/endpoint） |
| 实测 | `RUN-AIV-031-DOUBAO-SHEET-ENG-001` SUCCESS · 2026-10-03 |
| 硬化 | BRIEF-AIV-032 / `aiv_drama_n3.seedream` |

教材 Banana/IMAGE-2 未写 API。本拍金样 A 工程主路径 = **Ark Seedream**（≠ Banana 配额）。

| 参数 | 本拍实测 |
|------|----------|
| endpoint | `POST https://ark.cn-beijing.volces.com/api/v3/images/generations` |
| SKU 主 | `doubao-seedream-5-0-flash-260915`（第 1 档即中） |
| SKU 备 | `doubao-seedream-5-0-pro-260628` → `doubao-seedream-4-5-251128` → `wan2.7-image` |
| size | 请求 `2048x1365`（3:2）；回片 **2048×1365** |
| watermark | `false` |
| response_format | `url` |
| image | 脸 ref data-URL（图生图） |
| 未发 | `sequential_image_generation` · `output_format` |
| seed | API 未回（seed=null） |

禁：Key 入仓 / 日志明文。新狗粮 sheet md5 可异于 `a46b88eb54508c8240381afcf1d78241`。

— APPEND-AIV-031-RECIPE-EXEC-v0 · LEARN/ENG 对照 RUN · 禁 Key —
