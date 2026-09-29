# repo-stage — staging tree (awaiting push)

This directory is a **local staging tree** for the user's push plan to `kaibairen/auto-ai-vedio`.

- **Not** a git clone. **Do not** push from here until the user authorizes.
- Layout (per user):
  - `.skill/` — Skill packages for the AI video pipeline
  - `.prompt/` — Prompt / instruction documents
  - `MANIFEST.md` — inventory (KEEP from WF-SPEC v0.5): path, source, category
- Packed snapshot: `/workspace/aiv-learn/repo-stage-v0.tar.gz`

Suggested later push (user/CTO only): branch `skills-base-v0`, PR title `skills-base v0: KEEP 包 + MANIFEST`.
