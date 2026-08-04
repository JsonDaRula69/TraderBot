import { buildPluginConfigSchema, definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { resolveSecretRefValues } from "openclaw/plugin-sdk/secret-ref-runtime";
import type { PluginHookBeforeToolCallEvent, PluginHookBeforeToolCallResult, PluginHookToolContext } from "openclaw/plugin-sdk/types";
import { z } from "openclaw/plugin-sdk/zod";

/** Shape of a single agent's SecretRef in the plugin config. */
const agentTokenRefSchema = z.object({
  source: z.enum(["env", "file", "exec"]),
  provider: z.string(),
  id: z.string(),
});

/** Plugin config: maps agent id -> full SecretRef for that agent's TraderBot token. */
const pluginConfigSchema = z.object({
  agentTokenMap: z.record(z.string(), agentTokenRefSchema),
});

type PluginConfig = z.infer<typeof pluginConfigSchema>;

const TRADERBOT_TOOL_PREFIX = "traderbot__";

/**
 * Host-side token injection for TraderBot MCP tools.
 *
 * Runs at priority 100 so the injected `token` param is not discarded by a
 * later hook that freezes params for a different plugin. Fails closed whenever
 * the agent is unrecognized or the Vault SecretRef cannot be resolved.
 */
export default definePluginEntry({
  id: "traderbot-token-injector",
  name: "TraderBot Token Injector",
  description: "Injects per-agent TraderBot profile tokens via before_tool_call hook",
  configSchema: buildPluginConfigSchema(pluginConfigSchema),
  register(api) {
    api.on(
      "before_tool_call",
      async (
        event: PluginHookBeforeToolCallEvent,
        ctx: PluginHookToolContext,
      ): Promise<PluginHookBeforeToolCallResult | undefined> => {
        if (!event.toolName.startsWith(TRADERBOT_TOOL_PREFIX)) {
          return undefined;
        }

        const agentId = ctx.agentId;
        if (!agentId) {
          return { block: true, blockReason: "Unrecognized agent: no agentId" };
        }

        // Config was validated against pluginConfigSchema at plugin load time.
        const pluginConfig = api.pluginConfig as PluginConfig | undefined;
        const secretRef = pluginConfig?.agentTokenMap?.[agentId];
        if (!secretRef) {
          return { block: true, blockReason: `No token mapping for agent: ${agentId}` };
        }

        let resolved: Map<string, unknown>;
        try {
          resolved = await resolveSecretRefValues([secretRef], { config: api.config });
        } catch {
          return { block: true, blockReason: `Token resolution failed for agent: ${agentId}` };
        }

        const resolvedToken = resolved.values().next().value;
        if (resolvedToken === undefined || resolvedToken === null || resolvedToken === "") {
          return { block: true, blockReason: `Token resolution failed for agent: ${agentId}` };
        }

        // Phase 1.5: the Infisical exec provider returns profile tokens as
        // 5-field JSON documents ({"token", "profile", "agent_id",
        // "categories", "permissions"}) per DD-037 §4. Extract the raw token
        // field; fall back to the raw string for env/file providers (Phase
        // 1.1) whose value is the token itself.
        let tokenValue = String(resolvedToken);
        try {
          const parsed: unknown = JSON.parse(tokenValue);
          if (typeof parsed === "object" && parsed !== null) {
            if (typeof (parsed as Record<string, unknown>).token === "string") {
              tokenValue = (parsed as Record<string, unknown>).token as string;
            } else {
              // Malformed secret: JSON object without a string `token` field.
              return { block: true, blockReason: `Token resolution failed for agent: ${agentId}` };
            }
          }
        } catch {
          // Not JSON — raw token string (env/file provider mode).
        }
        if (tokenValue === "") {
          return { block: true, blockReason: `Token resolution failed for agent: ${agentId}` };
        }

        return { params: { ...event.params, token: tokenValue } };
      },
      { priority: 100 },
    );
  },
});