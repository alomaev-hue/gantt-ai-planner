from app.agent.prompt import STATIC_SYSTEM_PROMPT, build_system


def test_both_system_blocks_are_cache_breakpoints():
    # The plan table stays the same for every LLM call of a turn (up to 15 iterations), so it
    # must be cached too, not only the static rules; tools add the third breakpoint (max 4).
    blocks = build_system("id | задача\n1 | Анализ")
    assert blocks[0]["text"] == STATIC_SYSTEM_PROMPT
    assert blocks[1]["text"].endswith("1 | Анализ")
    assert all(b.get("cache_control") == {"type": "ephemeral"} for b in blocks)
