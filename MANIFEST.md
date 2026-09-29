# MANIFEST — skills-base staging inventory (KEEP per WF-SPEC v0.5)

Staging root: `/workspace/aiv-learn/repo-stage/`  
Built: 2026-09-29 (Asia/Shanghai)  
Sources: `local-mirror/`, `local-mirror-txt/`, `kou_shui_full.txt`, `chang_wen_kou_bo_full.txt`, `WF-SPEC-v0.5.md`  
Policy: md/txt preferred; when source is only `.docx`, use already-extracted text under `local-mirror-txt`. No videos/png/jpg/xlsx/zip; skip Coze giant tutorials (>2MB) and multi-industry junk prompts. Do not push from this tree.

---

## Layout summary

| Dest root | Role |
|-----------|------|
| `.skill/` | Skill packages (each folder keeps its own `SKILL.md` + refs) |
| `.prompt/` | Prompt / instruction documents for koubo, generation, consistency, seedance |
| `MANIFEST.md` | This inventory (KEEP) |
| `README-STAGE.md` | Staging note awaiting user push |

---

## `.skill/` — writing / generation

| Dest path | Source path | Category | Why |
|-----------|-------------|----------|-----|
| `.skill/writing/女频短剧编剧/` (SKILL.md + references/*) | `local-mirror/6【Skill包】女频男频短剧编剧skill/女频短剧编剧-skill/` | writing | KEEP 女频短剧编剧 Skill；含 references |
| `.skill/writing/男频短剧编剧/` (SKILL.md + references/*) | `local-mirror/6【Skill包】女频男频短剧编剧skill/男频短剧编剧-skill/` | writing | KEEP 男频短剧编剧 Skill；含 references |
| `.skill/writing/动态漫-人物小传/` | `local-mirror/7【Skill包】动态漫剧本skill合集/动态漫人物小传写作skill/` | writing | KEEP 动态漫人物小传 |
| `.skill/writing/动态漫-节奏爽点/` | `local-mirror/7【Skill包】动态漫剧本skill合集/动态漫剧情爽点-节奏设计skill/` | writing | KEEP 动态漫剧情爽点-节奏设计 |
| `.skill/writing/动态漫-详细写作/` | `local-mirror/7【Skill包】动态漫剧本skill合集/动态漫剧本详细写作skill/` | writing | KEEP 动态漫剧本详细写作 |
| `.skill/writing/动态漫-转分镜/` | `local-mirror/7【Skill包】动态漫剧本skill合集/动态漫剧本转分镜skill/` | writing | KEEP 动态漫剧本转分镜 |
| `.skill/generation/Seedance2.0-分镜/` | `local-mirror/7【Skill包】动态漫剧本skill合集/Seedance2.0分镜生成skill/` | generation | KEEP Seedance2.0 分镜生成 Skill（SKILL.md + seedance2.0.md） |

Notes: Skill folders copied as-is from `local-mirror` (already `.md`). Parent「使用教程」and 附：分镜头表格模板 (docx-only / non-Skill) not included. `1，漫剧影视编剧skill包` extras not in KEEP map — skipped.

### File-level `.skill/`

| Dest file | Source | Category |
|-----------|--------|----------|
| `.skill/writing/女频短剧编剧/SKILL.md` | `…/女频短剧编剧-skill/SKILL.md` | writing |
| `.skill/writing/女频短剧编剧/references/jiegou-kuangjia.md` | same under skill | writing |
| `.skill/writing/女频短剧编剧/references/luoji-jiaoyan-qingdan.md` | same | writing |
| `.skill/writing/女频短剧编剧/references/shuangdian-sheji.md` | same | writing |
| `.skill/writing/女频短剧编剧/references/ticai-yurenshe.md` | same | writing |
| `.skill/writing/男频短剧编剧/SKILL.md` | `…/男频短剧编剧-skill/SKILL.md` | writing |
| `.skill/writing/男频短剧编剧/references/jiegou-kuangjia.md` | same | writing |
| `.skill/writing/男频短剧编剧/references/luoji-jiaoyan-qingdan.md` | same | writing |
| `.skill/writing/男频短剧编剧/references/shuangdian-sheji.md` | same | writing |
| `.skill/writing/男频短剧编剧/references/ticai-yurenshe.md` | same | writing |
| `.skill/writing/动态漫-人物小传/SKILL.md` | `…/动态漫人物小传写作skill/SKILL.md` | writing |
| `.skill/writing/动态漫-人物小传/动态漫人物小传写作指南.md` | same folder | writing |
| `.skill/writing/动态漫-节奏爽点/SKILL.md` | `…/动态漫剧情爽点-节奏设计skill/SKILL.md` | writing |
| `.skill/writing/动态漫-节奏爽点/剧情爽点节奏设计指南.md` | same folder | writing |
| `.skill/writing/动态漫-详细写作/SKILL.md` | `…/动态漫剧本详细写作skill/SKILL.md` | writing |
| `.skill/writing/动态漫-详细写作/动态漫剧本写作规范.md` | same folder | writing |
| `.skill/writing/动态漫-转分镜/SKILL.md` | `…/动态漫剧本转分镜skill/SKILL.md` | writing |
| `.skill/writing/动态漫-转分镜/动态漫剧本转分镜生成指南.md` | same folder | writing |
| `.skill/generation/Seedance2.0-分镜/SKILL.md` | `…/Seedance2.0分镜生成skill/SKILL.md` | generation |
| `.skill/generation/Seedance2.0-分镜/seedance2.0.md` | same folder | generation |

---

## `.prompt/` — koubo / generation / consistency / seedance

| Dest path | Source path | Category | Why |
|-----------|-------------|----------|-----|
| `.prompt/koubo-口水话.md` | `/workspace/aiv-learn/kou_shui_full.txt` | koubo | KEEP 口水话指令全文（N1 路径 A） |
| `.prompt/koubo-长文章.md` | `/workspace/aiv-learn/chang_wen_kou_bo_full.txt` (+ one-line defect header) | koubo | KEEP 长文口播；header notes 缺第3步、框架7/8串 |
| `.prompt/generation/优化提示词.md` | `local-mirror-txt/优化提示词.docx.txt` ← `local-mirror/优化提示词.docx` | generation | KEEP N4 优化（反推→二创→细节） |
| `.prompt/generation/提示词拼接.md` | `local-mirror-txt/提示词拼接.docx.txt` ← `local-mirror/提示词拼接.docx` | generation | KEEP N4 拼接（短正文，extract 即全文） |
| `.prompt/generation/负面提示词.md` | `local-mirror-txt/负面提示词基于自己的应用场景修改.docx.txt` | generation | KEEP N4 负面 |
| `.prompt/generation/宫格-9.md` | `local-mirror-txt/生成9宫格分镜提示词.docx.txt` | generation | KEEP N5 9 宫格 |
| `.prompt/generation/宫格-16.md` | `local-mirror-txt/生成16宫格分镜提示词.docx.txt` | generation | KEEP N5 16 宫格 |
| `.prompt/generation/宫格-25.md` | `local-mirror-txt/生成25宫格分镜提示词.docx.txt` | generation | KEEP N5 25 宫格 |
| `.prompt/consistency/人物卡模板/复杂角色信息一致性角色卡--提示词模板.md` | `local-mirror-txt/5【AI故事板】…/…/复杂角色信息一致性角色卡--提示词模板.docx.txt` | consistency | KEEP 人物卡模板 |
| `.prompt/consistency/人物卡模板/角色一致性提示词-附使用方法.md` | `local-mirror-txt/5【AI故事板】…/…/角色一致性提示词-附使用方法.docx.txt` | consistency | KEEP 人物卡用法 |
| `.prompt/consistency/故事板-臭猫参考/臭猫故事板提示词参考.txt` | `local-mirror/5【AI故事板】…/故事板--臭猫系列案例/臭猫故事板提示词参考.txt` | consistency | KEEP 臭猫故事板参考（原 txt） |
| `.prompt/consistency/故事板-臭猫参考/臭猫系列seedance2.0视频提示词与参数.md` | `local-mirror-txt/5【AI故事板】…/臭猫系列seedance2.0视频提示词与参数.docx.txt` | consistency | KEEP 臭猫 Seedance 参数（docx→txt） |
| `.prompt/seedance/seedance2.0分镜提示词模板.txt` | `local-mirror/4【提示词指令】…/1，分镜提示词合集/seedance2.0分镜提示词模板.txt` | generation | KEEP Seedance2.0 分镜提示词模板 |

Duplicate BYTE_IDENTICAL tree `ai短剧人物&场景一致性保证故事版/` not staged (same as `5【AI故事板】…` per WF-SPEC).

---

## Intentionally skipped (per brief / WF-SPEC)

| Item | Reason |
|------|--------|
| Coze 反推二创 docx (~1.5MB) / 米核对接教程 (~2MB) | Coze giant tutorials >2MB; tiny txt extracts only; not KEEP core pack |
| `2x2/3x3/3x4/4x4宫格代码块.docx` | Extra grid code blocks; KEEP map asked 9/16/25 prompt docs |
| `一键生成4、9、12、16全能分镜.docx` | Extract nearly empty; skip |
| `【coze工作流代码】一键生成91625宫格…txt` | Coze workflow code; not in .prompt KEEP list |
| `6，多行业提示词（大模型通用）/` | multi-industry junk prompts |
| Videos / png / jpg / xlsx / zip / 附：分镜头表格模板 docx | binary / non-text KEEP |
| `故事板万能公式+提示词模版.doc` | WF-SPEC: 未拷 / not in mirror |
| 场景卡独立模板 | WF-SPEC gap（场景卡模板见缺口） |
| 微表情 PDF / 运镜 docx 全集 | not listed in this KEEP push map |

---

## Counts

- `.skill/` files: 20 (7 Skill packages)
- `.prompt/` files: 13
- Plus: `MANIFEST.md`, `README-STAGE.md`
