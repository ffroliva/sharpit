from __future__ import annotations


def _recognizer():
    try:
        from sharpit.engine.collectors.ai import recognizer
    except ImportError:
        recognizer = None
    assert recognizer is not None, "AI span recognizer is missing"
    return recognizer


def test_ai_recognizer_fallback_keys():
    recognizer = _recognizer()
    attributes = {
        "gen_ai.operation.name": "chat",
        "gen_ai.system": "openai",
        "gen_ai.request.model_name": "gpt-4o-mini",
        "gen_ai.usage.prompt_tokens": 7,
        "gen_ai.usage.completion_tokens": 5,
        "gen_ai.response.finish_reasons": ["STOP"],
    }
    assert recognizer.operation(attributes, "chat") == "chat"
    assert recognizer.provider(attributes) == "openai"
    assert recognizer.request_model(attributes) == "gpt-4o-mini"
    assert recognizer.input_tokens(attributes) == 7
    assert recognizer.output_tokens(attributes) == 5
    assert recognizer.finish_reason(attributes) == "STOP"
    assert recognizer.operation({}, "spring.ai.tool search") == "tool"
    assert recognizer.operation({"spring.ai.kind": "vector_store"}, "query") == "retrieval"
    assert recognizer.tool_name({"spring.ai.tool.definition.name": "search"}, "tool search") == "search"
    assert recognizer.vector_collection({"db.namespace": "docs"}) == "docs"
