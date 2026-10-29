"""Second search provider (the Claude API's web search tool) and the outreach rewording guard (29 Oct 2026)."""
from __future__ import annotations

import pytest

from app import config
from app.ai import outreach
from app.connectors import search as ws


def test_anthropic_provider_uses_the_ai_key_and_only_the_tool_results():
    s = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "key-not-real"})
    assert ws.available(s) is None and s.search_api_key == "key-not-real"
    hits = ws.parse_anthropic_results({"content": [
        {"type": "text", "text": "Here are some people I know of: Jane Doe, CEO."},      # model prose: never used
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": "https://a.example/cargo", "title": "Cargo"},
            {"type": "web_search_result", "url": "javascript:alert(1)", "title": "bad"},
            {"type": "web_search_result", "url": "https://a.example/cargo", "title": "duplicate"}]}]}, 5)
    assert [h.url for h in hits] == ["https://a.example/cargo"]
    assert ws.available(config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "anthropic"})) == "ANTHROPIC_API_KEY is not set"
    with pytest.raises(config.ConfigError):
        config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "bing"})


def test_reworded_outreach_may_not_add_facts():
    template = "Dear Jane Wanjiru,\n\nI am writing because of RFP EXA-GSSA-2026-301. Kind regards,\n[your name]\nWorld Freight Company"
    basis = ["name and title as recorded: Jane Wanjiru, Procurement Manager at Example Air"]
    assert outreach.adds_facts("Dear Jane Wanjiru, I am reaching out about RFP EXA-GSSA-2026-301. Kind regards, [your name], World Freight Company",
                               template, basis) == []
    added = outreach.adds_facts("Dear Jane, following our meeting in Nairobi with Peter Otieno about 40 tonnes of flowers...", template, basis)
    assert "Nairobi" in added and "Peter" in added and "40" in added
    assert outreach.drops_substance('{"language": "en", "claims": []}', template, ["Jane Wanjiru", "World Freight Company"]).startswith("reworded text drops")
    assert outreach.drops_substance("Dear Jane Wanjiru, World Freight Company [your name]", template, ["Jane Wanjiru"]) == "reworded text is much shorter than the draft"
    assert outreach.drops_substance(template, template, ["Jane Wanjiru", "[your name]"]) is None
