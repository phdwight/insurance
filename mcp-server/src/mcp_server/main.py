"""Policy Catalog MCP server (streamable HTTP at /mcp, plus /health).

Read-only tools over published policies. See docs/02-ingestion-mcp.md.
"""

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server import queries

# The SDK's DNS-rebinding protection rejects requests (421) unless the Host
# header is allowlisted. Cover the in-cluster name plus local dev by default.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "MCP_ALLOWED_HOSTS",
        "mcp-server:8002,localhost:8002,127.0.0.1:8002",
    ).split(",")
    if host.strip()
]

mcp = FastMCP(
    "policy-catalog",
    instructions=(
        "Read-only catalog of Philippine insurance policies (currency PHP unless "
        "stated). Every policy has a verified_at date — treat stale data with "
        "caution and always surface verified_at and source_url to users."
    ),
    streamable_http_path="/mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(allowed_hosts=ALLOWED_HOSTS),
)


def _json(data: Any) -> str:
    return json.dumps(data, default=str)


@mcp.tool()
def list_product_lines() -> str:
    """List available insurance product lines (life, health, travel, pet) with
    the number of published policies in each."""
    return _json(queries.list_product_lines())


@mcp.tool()
def list_insurers(product_line: str | None = None) -> str:
    """List insurers in the catalog. Optionally filter to those with published
    policies in a product line: one of 'life', 'health', 'travel', 'pet'."""
    return _json(queries.list_insurers(product_line))


@mcp.tool()
def search_policies(
    product_line: str,
    needs_description: str | None = None,
    max_premium: float | None = None,
    premium_frequency: str | None = None,
    age: int | None = None,
    limit: int = 5,
) -> str:
    """Search published policies in one product line, ranked by relevance.

    Args:
        product_line: one of 'life', 'health', 'travel', 'pet'. Required.
        needs_description: free-text description of the user's needs, used for
            semantic ranking (e.g. "2-week trip to Japan, needs COVID cover").
        max_premium: maximum premium in PHP. Filters out policies whose minimum
            premium exceeds this.
        premium_frequency: 'monthly', 'quarterly', 'semi_annual', 'annual', or
            'single' (one-time, common for travel).
        age: age in years of the person to be insured; filters by eligibility.
        limit: max results (default 5, cap 20).

    Returns JSON: {ranking, count, results[]} where each result includes slug
    (use with get_policy/compare_policies), premiums, summary, verified_at.
    """
    return _json(
        queries.search_policies(
            product_line=product_line,
            needs_description=needs_description,
            max_premium=max_premium,
            premium_frequency=premium_frequency,
            age=age,
            limit=limit,
        )
    )


@mcp.tool()
def get_policy(slug: str) -> str:
    """Get the full current version of one policy by slug: coverage details,
    eligibility, exclusions, riders, premiums, verified_at, source_url."""
    result = queries.get_policy(slug)
    return _json(result if result else {"error": f"no published policy with slug '{slug}'"})


@mcp.tool()
def compare_policies(slugs: list[str]) -> str:
    """Compare 2-4 policies attribute-by-attribute (premiums, coverage,
    eligibility, exclusions). Pass policy slugs from search_policies."""
    if not 2 <= len(slugs) <= 4:
        return _json({"error": "provide between 2 and 4 policy slugs"})
    return _json(queries.compare_policies(slugs))


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mcp-server"})


async def product_lines(request: Request) -> JSONResponse:
    """Plain REST mirror of the list_product_lines tool, for the PWA's
    category chips (only lines with published policies are worth showing)."""
    return JSONResponse(queries.list_product_lines())


async def compare(request: Request) -> JSONResponse:
    """Plain REST mirror of the compare_policies tool, for the PWA's
    side-by-side comparison view. GET /compare?slugs=a,b,c"""
    slugs = [s for s in request.query_params.get("slugs", "").split(",") if s]
    if not 2 <= len(slugs) <= 4:
        return JSONResponse(
            {"detail": "provide between 2 and 4 policy slugs"}, status_code=400
        )
    return JSONResponse(json.loads(_json(queries.compare_policies(slugs))))


app = mcp.streamable_http_app()
app.add_route("/health", health)
app.add_route("/product-lines", product_lines)
app.add_route("/compare", compare)
