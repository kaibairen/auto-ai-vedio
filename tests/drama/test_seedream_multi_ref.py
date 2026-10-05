"""AIV-041 PR1 — multi-ref Ark body + single-model Seedream (no network)."""

from __future__ import annotations

import json

import pytest

from aiv_drama.errors import AppError
from aiv_drama_n3.seedream import (
    ARK_IMAGES_URL,
    DEFAULT_MAX_REFS,
    SEEDREAM_SKU_CHAIN,
    SEEDREAM_SKU_PRIMARY,
    SHEET_SIZE,
    build_ark_body,
    generate_seedream_single_model,
)

PRIMARY = "data:image/jpeg;base64,QQ=="
EXTRA_A = "data:image/png;base64,QUE="
EXTRA_B = "data:image/png;base64,QUI="
EXTRA_C = "data:image/png;base64,QUM="
TEST_KEY = "unit-test-placeholder"


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


def _legacy_body() -> dict:
    """Exact body shape on main before extra_image_data_urls existed."""
    return {
        "model": SEEDREAM_SKU_PRIMARY,
        "prompt": "p",
        "size": SHEET_SIZE,
        "watermark": False,
        "response_format": "url",
        "image": PRIMARY,
    }


def test_zero_extra_body_byte_identical_to_legacy():
    expected = json.dumps(_legacy_body(), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    omitted = build_ark_body(model=SEEDREAM_SKU_PRIMARY, prompt="p", image_data_url=PRIMARY)
    none_extras = build_ark_body(
        model=SEEDREAM_SKU_PRIMARY,
        prompt="p",
        image_data_url=PRIMARY,
        extra_image_data_urls=None,
    )
    empty_extras = build_ark_body(
        model=SEEDREAM_SKU_PRIMARY,
        prompt="p",
        image_data_url=PRIMARY,
        extra_image_data_urls=[],
    )
    for body in (omitted, none_extras, empty_extras):
        assert isinstance(body["image"], str)
        assert body["image"] == PRIMARY
        dumped = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        assert dumped == expected
    assert omitted == none_extras == empty_extras == _legacy_body()


def test_two_refs_image_is_array_in_order():
    body = build_ark_body(
        model=SEEDREAM_SKU_PRIMARY,
        prompt="p",
        image_data_url=PRIMARY,
        extra_image_data_urls=[EXTRA_A],
    )
    assert body["image"] == [PRIMARY, EXTRA_A]
    assert list(body.keys()) == list(_legacy_body().keys())


def test_three_refs_image_is_array_in_order():
    body = build_ark_body(
        model=SEEDREAM_SKU_PRIMARY,
        prompt="p",
        image_data_url=PRIMARY,
        extra_image_data_urls=[EXTRA_A, EXTRA_B],
    )
    assert body["image"] == [PRIMARY, EXTRA_A, EXTRA_B]
    assert DEFAULT_MAX_REFS == 3


def test_four_refs_rejected():
    with pytest.raises(ValueError, match="at most 3"):
        build_ark_body(
            model=SEEDREAM_SKU_PRIMARY,
            prompt="p",
            image_data_url=PRIMARY,
            extra_image_data_urls=[EXTRA_A, EXTRA_B, EXTRA_C],
        )


def test_single_model_posts_once_and_never_falls_back_on_400():
    posts: list[str] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        assert url == ARK_IMAGES_URL
        posts.append(json["model"])
        assert json["model"] == SEEDREAM_SKU_PRIMARY
        assert json["size"] == "2048x1365"
        assert TEST_KEY not in str(json)
        return _Resp(400, text="model rejected")

    def fake_get(url, timeout=None):
        raise AssertionError("GET must not run after a non-200 POST")

    with pytest.raises(AppError) as caught:
        generate_seedream_single_model(
            api_key=TEST_KEY,
            prompt="p",
            image_data_url=PRIMARY,
            extra_image_data_urls=[EXTRA_A],
            post=fake_post,
            get=fake_get,
        )
    exc = caught.value
    assert exc.code == "provider"
    assert exc.details.get("http") == 400
    assert exc.details.get("model") == SEEDREAM_SKU_PRIMARY
    assert len(posts) == 1
    assert posts == [SEEDREAM_SKU_PRIMARY]
    for other in SEEDREAM_SKU_CHAIN[1:]:
        assert other not in posts
    blob = f"{exc} {exc.message} {exc.details}"
    assert TEST_KEY not in blob
    assert "Bearer " not in blob or "Bearer ***" in blob


def test_single_model_success_records_model_http_bytes():
    posts: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        posts.append(json)
        assert url == ARK_IMAGES_URL
        assert json["image"] == [PRIMARY, EXTRA_A, EXTRA_B]
        assert json["model"] == SEEDREAM_SKU_PRIMARY
        return _Resp(200, payload={"data": [{"url": "https://cdn.example/out.jpg"}]})

    def fake_get(url, timeout=None):
        assert url == "https://cdn.example/out.jpg"
        return _Resp(200, content=b"jpeg-bytes")

    out = generate_seedream_single_model(
        api_key=TEST_KEY,
        prompt="p",
        image_data_url=PRIMARY,
        extra_image_data_urls=[EXTRA_A, EXTRA_B],
        post=fake_post,
        get=fake_get,
    )
    assert out["model"] == SEEDREAM_SKU_PRIMARY
    assert out["http"] == 200
    assert out["bytes"] == b"jpeg-bytes"
    assert out["size"] == SHEET_SIZE
    assert len(posts) == 1
    assert TEST_KEY not in json.dumps(out, default=str)
