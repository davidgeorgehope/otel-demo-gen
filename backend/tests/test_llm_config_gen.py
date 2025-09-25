import json

from llm_config_gen import _select_content_from_blocks


def test_select_content_prefers_non_empty_tool_payload():
    tool_payload = {
        "services": ["checkout"],
        "telemetry": {
            "trace_rate": 1,
            "error_rate": 0.05,
            "metrics_interval": 10,
            "include_logs": True,
        },
    }

    content, empty_tool = _select_content_from_blocks([
        {"type": "tool_use", "name": "emit_config", "input": tool_payload},
        {"type": "text", "text": "{}"},
    ])

    assert empty_tool is False
    assert json.loads(content) == tool_payload


def test_select_content_falls_back_to_text_when_tool_empty():
    fallback_text = (
        '{"services": ["checkout"], "telemetry": '
        '{"trace_rate": 1, "error_rate": 0.05, "metrics_interval": 10, "include_logs": true}}'
    )

    content, empty_tool = _select_content_from_blocks([
        {"type": "tool_use", "name": "emit_config", "input": {}},
        {"type": "text", "text": f"  {fallback_text}   "},
    ])

    assert empty_tool is True
    assert json.loads(content) == json.loads(fallback_text)
