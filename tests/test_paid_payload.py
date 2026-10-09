import pytest
from live.paid_payload import validate_paid_payload


def payload():
    return {
        "model": "priced",
        "max_tokens": 512,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_paper",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ],
    }


def test_tool_allowlist_and_phase_gate():
    with pytest.raises(RuntimeError, match="authorized"):
        validate_paid_payload(payload(), {"priced"})
    assert validate_paid_payload(payload(), {"priced"}, True) == "generation"
    bad = payload()
    bad["tools"][0]["function"]["name"] = "shell"
    with pytest.raises(RuntimeError, match="local paper"):
        validate_paid_payload(bad, {"priced"}, True)


@pytest.mark.parametrize(
    "field,value",
    [("max_tokens", 513), ("max_tokens", True), ("model", "unknown"), ("n", 2), ("stream", True)],
)
def test_paid_payload_rejects_unbounded_or_unpriced_calls(field, value):
    body = payload()
    body[field] = value
    with pytest.raises(RuntimeError):
        validate_paid_payload(body, {"priced"}, True)
