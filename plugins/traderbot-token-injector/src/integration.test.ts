import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PluginHookBeforeToolCallEvent, PluginHookHandlerMap, PluginHookToolContext } from "openclaw/plugin-sdk/types";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

import plugin from "./index.js";
import { resolveSecretRefValues } from "openclaw/plugin-sdk/secret-ref-runtime";

vi.mock("openclaw/plugin-sdk/secret-ref-runtime", () => ({
  resolveSecretRefValues: vi.fn(),
}));

type BeforeToolCallHandler = PluginHookHandlerMap["before_tool_call"];

/**
 * Stand-in for the TraderBot MCP transport. The real hook never talks to the
 * MCP server directly — it rewrites tool-call params that the OpenClaw runtime
 * then forwards to the server. This fake records the params that WOULD be sent
 * so the integration test can assert the token reached the transport boundary
 * without touching a live server or Vault.
 */
function createMCPTransportFake() {
  const calls: Array<{ toolName: string; params: Record<string, unknown> }> = [];
  return {
    calls,
    call(toolName: string, params: Record<string, unknown>) {
      calls.push({ toolName, params });
    },
  };
}

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
    weather: { source: "exec", provider: "vault", id: "traderbot/weather/token" },
  },
};

function ctx(agentId?: string): PluginHookToolContext {
  return { agentId } as PluginHookToolContext;
}

beforeEach(() => {
  vi.mocked(resolveSecretRefValues).mockReset();
});

describe("traderbot-token-injector integration (MCP token injection)", () => {
  it("injects the resolved Vault token into a health tool call with empty params", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    const transport = createMCPTransportFake();
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "resolved-weather-token"]]),
    );

    const event: PluginHookBeforeToolCallEvent = {
      toolName: "traderbot__health",
      params: {},
    };
    const result = await handler(event, ctx("weather"));

    // The hook returns the params that the runtime forwards to the MCP server.
    expect(result).toEqual({ params: { token: "resolved-weather-token" } });
    if (result === undefined || result.block || result.params === undefined) {
      throw new Error("expected token-injected params");
    }
    transport.call(event.toolName, result.params);

    // The transport boundary receives the resolved Vault token, not any model input.
    expect(transport.calls).toEqual([
      { toolName: "traderbot__health", params: { token: "resolved-weather-token" } },
    ]);
    expect(resolveSecretRefValues).toHaveBeenCalledWith(
      [validPluginConfig.agentTokenMap.weather],
      { config: {} },
    );
  });

  it("preserves existing params and adds the token for a market_edge tool call", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    const transport = createMCPTransportFake();
    vi.mocked(resolveSecretRefValues).mockResolvedValue(
      new Map([["key", "resolved-weather-token"]]),
    );

    const event: PluginHookBeforeToolCallEvent = {
      toolName: "traderbot__market_edge",
      params: { category: "weather", ticker: "KXWEATHER-26" },
    };
    const result = await handler(event, ctx("weather"));

    expect(result).toEqual({
      params: { category: "weather", ticker: "KXWEATHER-26", token: "resolved-weather-token" },
    });
    if (result === undefined || result.block || result.params === undefined) {
      throw new Error("expected token-injected params");
    }
    transport.call(event.toolName, result.params);

    expect(transport.calls).toEqual([
      {
        toolName: "traderbot__market_edge",
        params: { category: "weather", ticker: "KXWEATHER-26", token: "resolved-weather-token" },
      },
    ]);
  });

  it("blocks the tool call for an unknown agent", async () => {
    const { handler } = createFakeApi(validPluginConfig);
    const transport = createMCPTransportFake();

    const result = await handler(
      { toolName: "traderbot__health", params: {} },
      ctx("sysadmin"),
    );

    expect(result).toEqual({
      block: true,
      blockReason: expect.stringContaining("No token mapping"),
    });
    expect(resolveSecretRefValues).not.toHaveBeenCalled();
    // A blocked call is never forwarded to the MCP transport.
    expect(transport.calls).toEqual([]);
  });
});
