from __future__ import annotations

import json

from orbit.data.ms_swift_dataset import build_ms_swift_dataset, normalize_record_for_ms_swift


def test_normalize_record_for_ms_swift_packs_tool_calls():
    record = {
        "env": "LIVEWEB",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "goto",
                            "arguments": "{\"url\": \"https://example.com\"}",
                        }
                    }
                ],
            },
            {"role": "tool", "content": "{\"status\": \"ok\"}"},
        ],
    }

    normalized = normalize_record_for_ms_swift(record, default_env_name="LIVEWEB")

    assert list(normalized.keys()) == ["messages"]
    assert normalized["messages"][0]["role"] == "system"
    assert "# Tools" in normalized["messages"][0]["content"]
    assert "<tool_call>" in normalized["messages"][1]["content"]
    assert normalized["messages"][2]["role"] == "user"
    assert "<tool_response>" in normalized["messages"][2]["content"]


def test_build_ms_swift_dataset_writes_uniform_messages_only(tmp_path):
    game = tmp_path / "game.jsonl"
    game.write_text(
        json.dumps(
            {
                "env": "GAME",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"},
                ],
                "score": 1.0,
                "seed": 1,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    liveweb = tmp_path / "liveweb.jsonl"
    liveweb.write_text(
        json.dumps(
            {
                "env": "LIVEWEB",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "u"},
                ],
                "tools": [{"type": "function", "function": {"name": "goto", "parameters": {"type": "object"}}}],
                "metadata": {"source": "demo"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    output = tmp_path / "train.jsonl"
    manifest = tmp_path / "manifest.json"
    report = build_ms_swift_dataset(
        input_paths=[game, liveweb],
        output_path=output,
        manifest_path=manifest,
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert report["total"] == 2
    assert len(rows) == 2
    assert all(sorted(row.keys()) == ["messages"] for row in rows)
