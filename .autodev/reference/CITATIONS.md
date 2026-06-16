# AutoDev Reference Citations

Source of truth for all dependency documentation seeded into the knowledge base.
Each entry tracks the origin, version/commit, date fetched, and local path.

## OpenClaw

- **Source**: GitHub repo `openclaw/openclaw` docs/ folder
- **Version**: commit `568f2d56314478ba48877648bdcb0b1e4a4278e2` (2026-06-16)
- **URL**: https://github.com/openclaw/openclaw/tree/568f2d56314478ba48877648bdcb0b1e4a4278e2/docs
- **Files**: 670 `.md` files (excluding `.generated/` and `.i18n/`)
- **Local path**: `.autodev/reference/openclaw/`
- **Notes**: Authoritative source; ~3 weeks newer than `Openclaw-llms-full.txt` (May 2026). Includes `providers/ollama-cloud.md`, `gateway/external-apps.md`, `tools/goal.md`, `tools/permission-modes.md` not in the llms snapshot.

## Kalshi API Docs

- **Source**: `docs.kalshi.com` individual `.md` pages + OpenAPI/AsyncAPI specs
- **Version**: Fetched 2026-06-16
- **URL**: https://docs.kalshi.com/llms.txt (index); individual pages at `https://docs.kalshi.com/<path>.md`
- **Files**: 210 `.md` pages + 5 YAML specs (`openapi.yaml`, `perps_openapi.yaml`, `perps_scm_openapi.yaml`, `asyncapi.yaml`, `perps_asyncapi.yaml`)
- **Local path**: `.autodev/reference/kalshi/`
- **Notes**: Full individual `.md` pages (6x more detail than `llms-full.txt` summaries). Includes complete OpenAPI request/response schemas. No GitHub source available; Mintlify-hosted only.

## VoyageAI

- **API Docs**: `docs.voyageai.com` individual `.md` pages
  - Version: Fetched 2026-06-16
  - URL: https://docs.voyageai.com/llms.txt (index); individual pages at `https://docs.voyageai.com/<path>.md`
  - Files: 39 `.md` pages (26 guides + 13 API reference)
  - Local path: `.autodev/reference/voyageai/docs/` and `.autodev/reference/voyageai/reference/`

- **OpenAPI Spec**: GitHub `voyage-ai/openapi`, commit `d638a2a` (2025-04-01)
  - URL: https://github.com/voyage-ai/openapi
  - Local path: `.autodev/reference/voyageai/voyage-openapi.yml`

- **Python SDK**: GitHub `voyage-ai/voyageai-python`, commit `3afd321` (2026-06-05)
  - URL: https://github.com/voyage-ai/voyageai-python
  - Local path: `.autodev/reference/voyageai/repos/voyageai-python/`

- **TypeScript SDK**: GitHub `voyage-ai/typescript-sdk`, commit `32450b4` (2026-06-15)
  - URL: https://github.com/voyage-ai/typescript-sdk
  - Local path: `.autodev/reference/voyageai/repos/typescript-sdk/`

## TraderBot v2 (Immutable Source of Truth)

- **v2roadmap.md**: `.autodev/reference/v2roadmap.md` — immutable design roadmap
- **v2docs/**: `.autodev/reference/v2docs/` — immutable design documentation
- **Status**: These files are never modified by AutoDev; they are the authority for all development decisions.

---

## CRITICAL: Kalshi API Versioning

The Kalshi API has undergone a major migration to V2 with fixed-point pricing (_dollars suffix for prices, _fp suffix for contract counts). The legacy /portfolio/orders endpoint (V1) will be deprecated no earlier than May 6, 2026.

AutoDev MUST ONLY implement against the V2 API spec. Key differences:

- V2 uses /portfolio/events/orders (not /portfolio/orders)
- V2 uses side: bid/ask (not action: buy/sell)
- V2 uses fixed-point dollar strings for prices (price_dollars: "0.1200")
- V2 uses fixed-point strings for contract counts (count_fp: "10.00")
- WebSocket base URLs changed: wss://external-api-ws.kalshi.com/trade-api/ws/v2

No legacy SDK code is included in the reference. The OpenAPI spec at .autodev/reference/kalshi/specs/openapi.yaml (version 3.21.0) is the authoritative contract. When in doubt, always defer to the latest docs in .autodev/reference/kalshi/.
