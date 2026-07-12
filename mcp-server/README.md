# mcp-server

Read-only MCP server over the policy catalog (streamable HTTP at `:8002/mcp`).

Tools: `list_product_lines`, `list_insurers`, `search_policies` (hybrid: SQL filters + pgvector semantic ranking when `VOYAGE_API_KEY` is set, premium-sorted fallback otherwise), `get_policy`, `compare_policies`.

Only `published`, non-superseded policy versions are visible. See [`docs/02-ingestion-mcp.md`](../docs/02-ingestion-mcp.md).

Try it with MCP Inspector: `npx @modelcontextprotocol/inspector` → connect to `http://localhost:8002/mcp`.
