from pydantic import BaseModel

from traderbot.mcp.tools import (
    TOOL_DEFINITIONS,
    AuthCheckInput,
    HealthInput,
    MarketEdgeInput,
    ProfileListInput,
)


def test_pydantic_matches_input_schema() -> None:
    models: dict[str, type[BaseModel]] = {
        "health": HealthInput,
        "auth_check": AuthCheckInput,
        "profile_list": ProfileListInput,
        "market_edge": MarketEdgeInput,
    }

    names = {str(definition["name"]) for definition in TOOL_DEFINITIONS}
    assert names == set(models)
    for definition in TOOL_DEFINITIONS:
        name = definition["name"]
        input_schema = definition["inputSchema"]
        assert isinstance(name, str)
        assert isinstance(input_schema, dict)
        model_properties = models[name].model_json_schema()["properties"]
        definition_properties = input_schema["properties"]
        assert set(model_properties) == set(definition_properties)
