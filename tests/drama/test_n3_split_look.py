"""Split full-body / heads look generate. Does not route through generate-look."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app, n3_generate_fullbody, n3_generate_heads, n3_generate_look
from aiv_drama.errors import AppError
from aiv_drama_n3.gold_sheet import (
    OUTPUT_SHEET_LINE,
    RECIPE_TURNAROUND_TEMPLATE,
    assemble_gold_a_sheet_prompt,
    load_look_card,
    md5_text,
)
from aiv_drama_n3.look_generate import generate_gold_a_sheet
from aiv_drama_n3.seedream import SEEDREAM_SKU_CHAIN, SEEDREAM_SKU_PRIMARY
from aiv_drama_n3.split_look import (
    FULLBODY_EN_IDENTITY,
    FULLBODY_KIND,
    FULLBODY_OUTPUT_LINE,
    FULLBODY_PROMPT_ORDER,
    FULLBODY_RECIPE,
    FULLBODY_STYLE,
    HEADS_EN_IDENTITY,
    HEADS_KIND,
    HEADS_OUTPUT_LINE,
    HEADS_PROMPT_ORDER,
    HEADS_RECIPE,
    HEADS_STYLE,
    TEMPLATE_BAN_TOKENS,
    assemble_fullbody_prompt,
    assemble_fullbody_sections,
    assemble_heads_prompt,
    assemble_heads_sections,
    generate_split_look,
)

ROOT = Path(__file__).resolve().parents[2]
GOLD_PROMPT = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-doubao-sheet-r1-prompt.txt"
GOLD_CARD = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-card.yaml"
FULLBODY_PROMPT = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-fullbody-prompt.txt"
HEADS_PROMPT = ROOT / "fixtures" / "drama" / "gold-a" / "CHAR-01-heads-prompt.txt"
GOLD_PROMPT_MD5 = "4cd224525bdf108b020756ea665be8dc"
FULLBODY_PROMPT_MD5 = "52a182332951cfbd2c1fd63d7b36cc7d"
HEADS_PROMPT_MD5 = "6868d45c0d5e819686e4f28f9e76c08e"
runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _face(tmp_path: Path, payload: bytes = b"\xff\xd8fake-face-bytes") -> Path:
    path = tmp_path / "CHAR-01-user-ref.jpg"
    path.write_bytes(payload)
    return path


def _gold_card() -> dict:
    return load_look_card(GOLD_CARD)


def _sheet_card() -> dict:
    card = dict(_gold_card())
    card.pop("refs", None)
    return card


class _Resp:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_combined_gold_sheet_fixture_still_matches():
    """Old generate-look 3+6 合板 stays the Gold-A fixture on main."""
    prompt = assemble_gold_a_sheet_prompt(_gold_card())
    expected = GOLD_PROMPT.read_text(encoding="utf-8")
    assert prompt == expected
    assert md5_text(prompt) == GOLD_PROMPT_MD5
    assert RECIPE_TURNAROUND_TEMPLATE in prompt
    assert OUTPUT_SHEET_LINE in prompt
    assert "2×3 网格六张头部小图" in prompt
    assert "全身正视站姿" in prompt
    assert "全身90°侧视站姿" in prompt
    assert "全身90°背视站姿" in prompt


def test_fullbody_assemble_matches_fixture_and_layout():
    prompt = assemble_fullbody_prompt(_gold_card())
    expected = FULLBODY_PROMPT.read_text(encoding="utf-8")
    assert prompt == expected
    assert md5_text(prompt) == FULLBODY_PROMPT_MD5
    assert FULLBODY_STYLE in prompt
    assert FULLBODY_RECIPE in prompt
    assert "从左到右并排三张完整全身站姿：正面、侧面、背面" in prompt
    assert "从头顶到脚底完整入画" in prompt
    assert "禁止裁切脚踝或脚" in prompt
    assert FULLBODY_OUTPUT_LINE in prompt
    assert "do not crop the feet" in FULLBODY_EN_IDENTITY
    assert "2×3" not in prompt
    assert "2x3" not in prompt
    assert "六张头" not in prompt
    assert "头部小图" not in prompt
    names = [n for n, _ in assemble_fullbody_sections(_gold_card())]
    assert names == list(FULLBODY_PROMPT_ORDER)
    assert prompt.index("角色穿着：") < prompt.index("不可变：")
    assert prompt.index("人物身高1.75米") < prompt.index("禁令：")


def test_heads_assemble_matches_fixture_and_layout():
    prompt = assemble_heads_prompt(_gold_card())
    expected = HEADS_PROMPT.read_text(encoding="utf-8")
    assert prompt == expected
    assert md5_text(prompt) == HEADS_PROMPT_MD5
    assert HEADS_STYLE in prompt
    assert HEADS_RECIPE in prompt
    assert "2×3" in prompt
    assert "正、背、左45、右45、笑、生气" in prompt
    assert HEADS_OUTPUT_LINE in prompt
    assert "3×3" not in prompt
    assert "3x3" not in prompt
    assert "九" not in prompt
    assert "全身正视" not in prompt
    assert "全身90°" not in prompt
    assert "三张全身" not in prompt
    names = [n for n, _ in assemble_heads_sections(_gold_card())]
    assert names == list(HEADS_PROMPT_ORDER)


def test_templates_do_not_hardcode_episode_or_costume():
    blobs = (
        FULLBODY_STYLE,
        FULLBODY_RECIPE,
        FULLBODY_EN_IDENTITY,
        FULLBODY_OUTPUT_LINE,
        HEADS_STYLE,
        HEADS_RECIPE,
        HEADS_EN_IDENTITY,
        HEADS_OUTPUT_LINE,
    )
    for blob in blobs:
        for token in TEMPLATE_BAN_TOKENS:
            assert token not in blob
        assert "3×3" not in blob
        assert "九" not in blob


def test_split_prompts_take_card_appearance_same_as_generate_look():
    card = _gold_card()
    gold = assemble_gold_a_sheet_prompt(card)
    fullbody = assemble_fullbody_prompt(card)
    heads = assemble_heads_prompt(card)
    wardrobe = "角色穿着：灰色连帽卫衣"
    immutable = "不可变：圆框黑边眼镜"
    height = "人物身高1.75米"
    for prompt in (gold, fullbody, heads):
        assert wardrobe in prompt
        assert immutable in prompt
        assert height in prompt
    other = dict(card)
    other["wardrobe"] = "蓝色外套与深色长裤"
    other["immutable"] = "黑框眼镜"
    other["height"] = "1.80米"
    filled = assemble_fullbody_prompt(other)
    assert "角色穿着：蓝色外套与深色长裤" in filled
    assert "不可变：黑框眼镜" in filled
    assert "人物身高1.80米" in filled
    assert "灰色连帽卫衣" not in filled


def test_split_assemble_does_not_invent_wardrobe():
    exc = _err(lambda: assemble_fullbody_prompt({"id": "CHAR-02", "kind": "character"}))
    assert exc.code == "look_card_incomplete"
    exc2 = _err(lambda: assemble_heads_prompt({"id": "CHAR-02", "kind": "character"}))
    assert exc2.code == "look_card_incomplete"


def test_split_prompts_are_not_the_combined_sheet():
    gold = GOLD_PROMPT.read_text(encoding="utf-8")
    fullbody = FULLBODY_PROMPT.read_text(encoding="utf-8")
    heads = HEADS_PROMPT.read_text(encoding="utf-8")
    assert fullbody != gold
    assert heads != gold
    assert RECIPE_TURNAROUND_TEMPLATE not in fullbody
    assert RECIPE_TURNAROUND_TEMPLATE not in heads
    assert OUTPUT_SHEET_LINE not in fullbody
    assert OUTPUT_SHEET_LINE not in heads
    assert "turnaround sheet image" not in fullbody
    assert "turnaround sheet image" not in heads


def test_generate_split_does_not_call_generate_look(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not route through generate_gold_a_sheet")

    monkeypatch.setattr("aiv_drama_n3.look_generate.generate_gold_a_sheet", boom)
    monkeypatch.setattr("aiv_drama_n3.split_look.generate_gold_a_sheet", boom, raising=False)
    face = _face(tmp_path)
    for kind in ("fullbody", "heads"):
        look = generate_split_look(
            kind=kind,
            card=_sheet_card(),
            face_ref=face,
            out_dir=tmp_path / kind,
            api_key=None,
            dry_run=True,
        )
        assert look["dry_run"] is True
        assert Path(look["prompt_path"]).is_file()
        assert look["sheet_path"] is None
        assert look["sku_chain"] == list(SEEDREAM_SKU_CHAIN)
        assert look["sku_chain"][0] == SEEDREAM_SKU_PRIMARY


def test_dry_run_writes_prompt_not_sheet_and_skips_api(tmp_path, monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on dry-run")

    monkeypatch.setattr("aiv_drama_n3.split_look.generate_seedream_sheet", boom)
    face = _face(tmp_path)
    look = generate_split_look(
        kind="fullbody",
        card=_sheet_card(),
        face_ref=face,
        out_dir=tmp_path / "out",
        api_key="sk-should-not-be-used",
        dry_run=True,
    )
    assert called["n"] == 0
    written = Path(look["prompt_path"]).read_text(encoding="utf-8")
    assert written == FULLBODY_PROMPT.read_text(encoding="utf-8")
    assert look["kind"] == FULLBODY_KIND
    assert not (tmp_path / "out" / "CHAR-01-fullbody-sheet.jpg").exists()
    recorded = json.loads(Path(look["recorded_path"]).read_text(encoding="utf-8"))
    assert recorded["sku_chain"][0] == SEEDREAM_SKU_PRIMARY
    assert "sk-" not in json.dumps(look)


def test_face_md5_gate_before_split_generate(tmp_path, monkeypatch):
    face = _face(tmp_path)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Ark must not run on bind fail")

    monkeypatch.setattr("aiv_drama_n3.split_look.generate_seedream_sheet", boom)
    exc = _err(
        lambda: generate_split_look(
            kind="heads",
            card=_sheet_card(),
            face_ref=face,
            expected_md5="0" * 32,
            out_dir=tmp_path / "out",
            api_key="sk-should-not-be-used",
            dry_run=False,
        )
    )
    assert exc.code == "material_bind"
    assert called["n"] == 0
    assert not (tmp_path / "out" / "CHAR-01-heads-sheet.jpg").exists()


def test_live_generate_uses_flash_first_chain(tmp_path):
    face = _face(tmp_path)
    jpeg = b"\xff\xd8\xff" + b"sheet" * 20
    posts = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        posts.append(json["model"])
        assert json["model"] == SEEDREAM_SKU_PRIMARY
        assert "sequential_image_generation" not in json
        return _Resp(200, payload={"data": [{"url": "https://cdn.example/s.jpg"}]})

    def fake_get(url, timeout=None):
        return _Resp(200, content=jpeg)

    look = generate_split_look(
        kind="heads",
        card=_sheet_card(),
        face_ref=face,
        out_dir=tmp_path / "out",
        api_key="not-a-real-key",
        dry_run=False,
        post=fake_post,
        get=fake_get,
    )
    assert look["kind"] == HEADS_KIND
    assert look["model"] == SEEDREAM_SKU_PRIMARY
    assert posts == [SEEDREAM_SKU_PRIMARY]
    assert Path(look["sheet_path"]).read_bytes() == jpeg
    written = Path(look["prompt_path"]).read_text(encoding="utf-8")
    assert written == HEADS_PROMPT.read_text(encoding="utf-8")
    assert "not-a-real-key" not in json.dumps(look)


def test_split_generate_has_no_model_override():
    params = inspect.signature(generate_split_look).parameters
    assert "models" not in params
    assert "model" not in params
    assert "skip_flash" not in params
    assert "sku" not in params


def test_cli_commands_have_no_model_or_skip_flash():
    for fn in (n3_generate_fullbody, n3_generate_heads):
        names = set(inspect.signature(fn).parameters)
        assert "model" not in names
        assert "skip_flash" not in names
        assert {"card", "face_ref", "expected_md5", "out", "dry_run"} <= names
    look_names = set(inspect.signature(n3_generate_look).parameters)
    assert "card" in look_names
    assert "face_ref" in look_names


def test_cli_help_lists_split_commands_not_as_generate_look():
    listing = runner.invoke(app, ["drama", "n3", "--help"])
    assert listing.exit_code == 0, listing.output
    assert "generate-look" in listing.output
    assert "generate-fullbody" in listing.output
    assert "generate-heads" in listing.output
    for cmd in ("generate-fullbody", "generate-heads"):
        help_res = runner.invoke(app, ["drama", "n3", cmd, "--help"])
        assert help_res.exit_code == 0, help_res.output
        assert "--card" in help_res.output
        assert "--face-ref" in help_res.output
        assert "--expected-md5" in help_res.output
        assert "--out" in help_res.output
        assert "--dry-run" in help_res.output
        assert "--model" not in help_res.output
        assert "--skip-flash" not in help_res.output
        assert "Not generate-look" in help_res.output


def test_cli_standalone_dry_run_each_command(tmp_path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    face = _face(tmp_path)
    digest = hashlib.md5(face.read_bytes()).hexdigest()
    card_path = tmp_path / "CHAR-01-card.yaml"
    card_path.write_text(
        GOLD_CARD.read_text(encoding="utf-8").replace("refs:\n", "refs_unused:\n"),
        encoding="utf-8",
    )
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("generate-look must not run")

    monkeypatch.setattr("aiv_cli.cli.generate_gold_a_sheet", boom)
    expected = {
        "generate-fullbody": (FULLBODY_PROMPT, FULLBODY_KIND, FULLBODY_PROMPT_MD5),
        "generate-heads": (HEADS_PROMPT, HEADS_KIND, HEADS_PROMPT_MD5),
    }
    for cmd, (fixture, kind, digest_prompt) in expected.items():
        out = tmp_path / cmd
        res = runner.invoke(
            app,
            [
                "drama",
                "n3",
                cmd,
                "--card",
                str(card_path),
                "--face-ref",
                str(face),
                "--expected-md5",
                digest,
                "--out",
                str(out),
                "--dry-run",
            ],
        )
        assert res.exit_code == 0, res.output
        payload = json.loads(res.output)
        assert payload["dry_run"] is True
        assert payload["kind"] == kind
        written = Path(payload["prompt_path"]).read_text(encoding="utf-8")
        assert written == fixture.read_text(encoding="utf-8")
        assert md5_text(written) == digest_prompt
        assert payload["sku_chain"][0] == SEEDREAM_SKU_PRIMARY
        assert "sk-" not in res.output
    assert called["n"] == 0
