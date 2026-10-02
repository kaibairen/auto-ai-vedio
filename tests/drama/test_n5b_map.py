"""AIV-036 N5b mapping: aspect / duration / jsonl → content[]. No HTTP."""

from __future__ import annotations

import pytest

from aiv_drama.errors import AppError
from aiv_drama_n5b.constants import NEGATIVE_JOIN, SEEDANCE_SKU_PRIMARY
from aiv_drama_n5b.map import (
    compose_text,
    jsonl_to_content,
    map_aspect,
    map_duration,
    map_jsonl_line_to_task_body,
    map_jsonl_lines,
)


def test_aspect_235_maps_to_21_9():
    assert map_aspect("2.35:1") == "21:9"
    assert map_aspect("9:16") == "9:16"
    assert map_aspect("16:9") == "16:9"
    with pytest.raises(AppError) as exc:
        map_aspect("4:3")
    assert exc.value.status_code == 422


def test_duration_closed_set():
    assert map_duration(5) == 5
    assert map_duration(8) == 8
    assert map_duration(10) == 10
    with pytest.raises(AppError) as exc:
        map_duration(4)
    assert exc.value.code == "duration_out_of_profile"


def test_jsonl_to_content_joins_negative_and_refs():
    line = {
        "prompt": "林晚推门",
        "negative": "面部变形",
        "ref_images": ["/data/refs/CHAR-01.png", "https://cdn.example/ref.jpg"],
        "duration_s": 5,
        "aspect": "2.35:1",
        "tool_profile": "seedance_2",
        "shot_id": "S01",
    }
    content, notes = jsonl_to_content(line)
    assert content[0]["type"] == "text"
    assert content[0]["text"] == f"林晚推门{NEGATIVE_JOIN}面部变形"
    assert compose_text("林晚推门", "面部变形") == content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["role"] == "reference_image"
    assert content[1]["image_url"]["url"] == "/data/refs/CHAR-01.png"
    assert notes[0]["hosted"] is False
    assert notes[1]["hosted"] is True


def test_task_body_shape_and_default_sku():
    body = map_jsonl_line_to_task_body(
        {
            "prompt": "边关夜雨",
            "negative": "低清",
            "duration_s": 8,
            "aspect": "2.35:1",
            "tool_profile": "seedance_2",
            "ref_images": [],
        }
    )
    assert body["model"] == SEEDANCE_SKU_PRIMARY
    assert body["duration"] == 8
    assert body["ratio"] == "21:9"
    assert body["resolution"] == "720p"
    assert body["watermark"] is False
    assert body["generate_audio"] is False
    assert body["content"][0]["type"] == "text"
    assert "2.35:1" not in str(body["ratio"])


def test_map_lines_shot_filter_and_clip_names():
    lines = [
        {
            "shot_id": "S01",
            "prompt": "一",
            "negative": "低清",
            "duration_s": 5,
            "aspect": "9:16",
            "tool_profile": "seedance_2",
        },
        {
            "shot_id": "S02",
            "prompt": "二",
            "negative": "低清",
            "duration_s": 10,
            "aspect": "16:9",
            "tool_profile": "seedance_2",
        },
    ]
    mapped = map_jsonl_lines(lines, shot_id="S02")
    assert len(mapped) == 1
    assert mapped[0]["shot_id"] == "S02"
    assert mapped[0]["clip_relpath"] == "clips/S02.mp4"
    assert mapped[0]["meta_relpath"] == "clips/S02.meta.json"
    assert mapped[0]["duration"] == 10
    with pytest.raises(AppError) as exc:
        map_jsonl_lines(lines, shot_id="S99")
    assert exc.value.status_code == 404
