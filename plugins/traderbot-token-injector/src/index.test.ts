import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PluginHookBeforeToolCallEvent, PluginHookHandlerMap, PluginHookToolContext } from "openclaw/plugin-sdk/types";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

import plugin from "./index.js";
import { resolveSecretRefValues } from "openclaw/plugin-sdk/secret-ref-runtime";

vi.mock("openclaw/plugin-sdk/secret-ref-runtime", () => ({
  resolveSecretRefValues: vi.fn(),
}));

type BeforeToolCallHandler = PluginHookHandlerMap["before_tool_call"];

/** Minimal fake API that records the hook handler registered via `api.on`. */
function createFakeApi(pluginConfig: Record<string, unknown>) {
  const on = vi.fn();
  const api = {
    config: {},
    pluginConfig,
    on,
  } as unknown as OpenClawPluginApi;

  plugin.register(api);

  const beforeToolCall = on.mock.calls.find(
    ([hookName]) => hookName === "before_tool_call",
  );
  if (!beforeToolCall) {
    throw new Error("before_tool_call hook was not registered");
  }
  return {
    api,
    handler: beforeToolCall[1] as BeforeToolCallHandler,
    on,
  };
}

const validPluginConfig = {
  agentTokenMap: {
    weather: { source: "exec", provider: "infisical", id: "weather_token" },
  },
};

function event(params: Record<string, unknown>, toolName = "traderbot__health"): PluginHookBeforeToolCallEvent {
  return { toolName, params };
}

function ctx(agentId?: string): PluginHookToolContext {
  return { agentId } as PluginHookToolContext;
}

beforeEach(() => {
  vi.mocked(resolveSecretRefValues).mockReset();
});

describe("traderbot-token-injector before_tool_call hook", () => {
  it("injects the resolved token on the happy path", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "resolved-weather-token"]]),
    );

    const result = await handler(event({}), ctx("weather"));

    expect(result).toEqual({
      params: { token: "resolved-weather-token" },
    });
    expect(resolveSecretRefValues).toHaveBeenCalledWith(
      [validPluginConfig.agentTokenMap.weather],
      { config: {} },
    );
  });

  it("blocks when ctx.agentId is missing", async () => {
    const { handler } = createFakeApi(validPluginConfig);

    const result = await handler(event({}), ctx(undefined));

    expect(result).toEqual({ block: true, blockReason: expect.stringContaining("no agentId") });
    expect(resolveSecretRefValues).not.toHaveBeenCalled();
  });

  it("blocks when the agent has no token mapping", async () => {
    const { handler } = createFakeApi(validPluginConfig);

    const result = await handler(event({}), ctx("sysadmin"));

    expect(result).toEqual({ block: true, blockReason: expect.stringContaining("No token mapping") });
    expect(resolveSecretRefValues).not.toHaveBeenCalled();
  });

  it("is a no-op for non-traderbot tools", async () => {
    const { handler } = createFakeApi(validPluginConfig);

    const result = await handler(
      { toolName: "web_search", params: {} },
      ctx("weather"),
    );

    expect(result).toBeUndefined();
    expect(resolveSecretRefValues).not.toHaveBeenCalled();
  });

  it("preserves existing params while adding the token", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "resolved-weather-token"]]),
    );

    const result = await handler(
      { toolName: "traderbot__market_edge", params: { category: "weather", ticker: "KXWEATHER-26" } },
      ctx("weather"),
    );

    expect(result).toEqual({
      params: { category: "weather", ticker: "KXWEATHER-26", token: "resolved-weather-token" },
    });
  });

  it("registers the hook with priority 100", () => {
    const { on } = createFakeApi(validPluginConfig);

    const call = on.mock.calls.find(([hookName]) => hookName === "before_tool_call");
    expect(call).toBeDefined();
    expect(call?.[2]).toEqual({ priority: 100 });
  });

  it("overwrites a model-provided token with the resolved one", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "resolved-real-token"]]),
    );

    const result = await handler(event({ token: "fake" }), ctx("weather"));

    expect(result).toEqual({ params: { token: "resolved-real-token" } });
  });

  it("extracts the raw token from a 5-field JSON document (Infisical exec provider)", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    const doc = JSON.stringify({
      token: "raw-token-from-infisical",
      profile: "weather",
      agent_id: "weather",
      categories: [],
      permissions: [],
    });
    vi.mocked(resolveSecretRefValues).mockResolvedValue(new Map([["key", doc]]));

    const result = await handler(event({}), ctx("weather"));

    expect(result).toEqual({ params: { token: "raw-token-from-infisical" } });
  });

  it("falls back to the raw string when the resolved value is not JSON", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "plain-raw-token"]]),
    );

    const result = await handler(event({}), ctx("weather"));

    expect(result).toEqual({ params: { token: "plain-raw-token" } });
  });

  it("blocks when the resolved JSON document has no token field", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", JSON.stringify({ profile: "weather", agent_id: "weather" })]]),
    );

    const result = await handler(event({}), ctx("weather"));

    expect(result).toEqual({ block: true, blockReason: expect.stringContaining("Token resolution failed") });
  });

  it("blocks when token resolution fails", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    vi.mocked(resolveSecretRefValues).mockRejectedValue(new Error("infisical down"));

    const result = await handler(event({}), ctx("weather"));

    expect(result).toEqual({ block: true, blockReason: expect.stringContaining("Token resolution failed") });
  });
});
