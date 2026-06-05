"""Validate all Kalshi API endpoint paths in TraderBot source against Dep_Docs.

Scans the ``kalshi/`` module for HTTP method calls (``get``, ``post``,
``delete``) and checks that every endpoint path matches what the Kalshi
V2 API documentation defines in ``Dep_Docs/Kalshi-llms.txt``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KALSHI_DOCS = PROJECT_ROOT / "Dep_Docs" / "Kalshi-llms.txt"
KALSHI_SRC = PROJECT_ROOT / "src" / "traderbot" / "kalshi"

# ---------------------------------------------------------------------------
# Kalshi V2 API endpoints from Dep_Docs/Kalshi-llms.txt
#
# Extracted from the Kalshi V2 API Reference. Path parameters shown as
# {param}. Method is inferred from the endpoint purpose.
# ---------------------------------------------------------------------------

KALSHI_ENDPOINTS: dict[str, set[str]] = {
    # Account
    "/account/api-limits": {"GET"},
    "/account/endpoint-costs": {"GET"},
    # API Keys
    "/api-keys": {"GET", "POST"},
    "/api-keys/{key_id}": {"DELETE"},
    "/api-keys/generate": {"POST"},
    # Communications
    "/communications/id": {"GET"},
    "/communications/rfq": {"POST"},
    "/communications/rfq/{rfq_id}": {"GET", "DELETE"},
    "/communications/rfqs": {"GET"},
    "/communications/quote": {"POST"},
    "/communications/quote/{quote_id}": {"GET"},
    "/communications/quote/{quote_id}/accept": {"POST"},
    "/communications/quote/{quote_id}/confirm": {"POST"},
    "/communications/quote/{quote_id}/delete": {"DELETE"},
    "/communications/quotes": {"GET"},
    # Events
    "/events": {"GET"},
    "/events/{event_ticker}": {"GET"},
    "/events/{event_ticker}/candlesticks": {"GET"},
    "/events/{event_ticker}/forecast-percentile-history": {"GET"},
    "/events/multivariate": {"GET"},
    "/events/{event_ticker}/metadata": {"GET"},
    # Exchange
    "/exchange/announcements": {"GET"},
    "/exchange/schedule": {"GET"},
    "/exchange/status": {"GET"},
    "/exchange/series-fee-changes": {"GET"},
    "/exchange/user-data-timestamp": {"GET"},
    # FCM
    "/fcm/orders": {"GET"},
    "/fcm/positions": {"GET"},
    # Historical
    "/historical/cutoff-timestamps": {"GET"},
    "/historical/fills": {"GET"},
    "/historical/markets/{ticker}": {"GET"},
    "/historical/markets/{ticker}/candlesticks": {"GET"},
    "/historical/markets": {"GET"},
    "/historical/orders": {"GET"},
    "/historical/trades": {"GET"},
    # Incentives
    "/incentives": {"GET"},
    # Live Data
    "/live-data/milestone/{milestone_id}": {"GET"},
    "/live-data/milestone/{milestone_id}/with-type/{type}": {"GET"},
    "/live-data/milestones": {"GET"},
    "/live-data/game-stats/{milestone_id}": {"GET"},
    # Markets
    "/markets": {"GET"},
    "/markets/{ticker}": {"GET"},
    "/markets/{ticker}/candlesticks": {"GET"},
    "/markets/{ticker}/orderbook": {"GET"},
    "/markets/trades": {"GET"},
    "/markets/orderbooks": {"GET"},
    "/series": {"GET"},
    "/series/{ticker}": {"GET"},
    # Milestones
    "/milestones/{milestone_id}": {"GET"},
    "/milestones": {"GET"},
    # Multivariate
    "/multivariate/event-collections": {"GET"},
    "/multivariate/event-collections/{ticker}": {"GET"},
    "/multivariate/event-collections/{ticker}/markets": {"POST"},
    "/multivariate/event-collections/{ticker}/markets/lookup": {"GET"},
    "/multivariate/event-collections/{ticker}/lookup-history": {"GET"},
    # Orders
    "/portfolio/events/orders/v2": {"POST"},
    "/portfolio/events/orders/{order_id}": {"DELETE"},
    "/portfolio/orders": {"GET"},
    "/portfolio/orders/{order_id}": {"GET"},
    "/portfolio/orders/{order_id}/amend": {"PATCH"},
    "/portfolio/orders/{order_id}/amend/v2": {"PATCH"},
    "/portfolio/orders/{order_id}/cancel": {"DELETE"},
    "/portfolio/orders/{order_id}/cancel/v2": {"DELETE"},
    "/portfolio/orders/{order_id}/decrease": {"DELETE"},
    "/portfolio/orders/{order_id}/decrease/v2": {"DELETE"},
    "/portfolio/orders/{order_id}/queue-position": {"GET"},
    "/portfolio/orders/batch-cancel": {"POST"},
    "/portfolio/orders/batch-cancel/v2": {"POST"},
    "/portfolio/orders/batch-create": {"POST"},
    "/portfolio/orders/batch-create/v2": {"POST"},
    "/portfolio/orders/queue-positions": {"GET"},
    # Order Groups
    "/portfolio/order-groups": {"GET", "POST"},
    "/portfolio/order-groups/{group_id}": {"GET", "DELETE"},
    "/portfolio/order-groups/{group_id}/limit": {"PATCH"},
    "/portfolio/order-groups/{group_id}/reset": {"POST"},
    "/portfolio/order-groups/{group_id}/trigger": {"POST"},
    # Portfolio
    "/portfolio/balance": {"GET"},
    "/portfolio/positions": {"GET"},
    "/portfolio/fills": {"GET"},
    "/portfolio/settlements": {"GET"},
    "/portfolio/deposits": {"GET"},
    "/portfolio/withdrawals": {"GET"},
    "/portfolio/resting-order-value": {"GET"},
    # Subaccounts
    "/portfolio/subaccounts": {"POST"},
    "/portfolio/subaccounts/balances": {"GET"},
    "/portfolio/subaccounts/netting": {"GET"},
    "/portfolio/subaccounts/transfers": {"GET"},
    "/portfolio/subaccounts/transfer": {"POST"},
    "/portfolio/subaccounts/{subaccount_id}/netting": {"PATCH"},
    # Search
    "/search/filters/sports": {"GET"},
    "/search/tags/series-categories": {"GET"},
}


def _get_http_method(node: ast.Call) -> str | None:
    """Extract HTTP method from a method call like ``self._client.get(...)``.

    Only matches calls on ``_client``, ``client``, ``self._client``, or
    ``self.client`` — not generic ``.get()`` calls on dicts or responses.
    """
    if not isinstance(node.func, ast.Attribute):
        return None
    method = node.func.attr.lower()
    if method not in ("get", "post", "put", "patch", "delete"):
        return None
    # Check the receiver — must be _client, client, self._client, or self.client
    receiver = node.func.value
    if isinstance(receiver, ast.Attribute):
        # e.g. self._client.get(...), self.client.get(...)
        if receiver.attr in ("_client", "client"):
            return method.upper()
    elif isinstance(receiver, ast.Name):
        # e.g. client.get(...), live_client.get(...)
        if receiver.id in ("client", "live_client", "http_client"):
            return method.upper()
    return None


def _extract_kalshi_endpoints() -> list[dict]:
    """Walk kalshi source and extract all API endpoint paths with HTTP methods."""
    calls: list[dict] = []
    for py_file in sorted(KALSHI_SRC.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            method = _get_http_method(node)
            if method is None:
                continue

            # Get first positional arg (the path)
            if not node.args:
                continue
            path_arg = node.args[0]

            # Handle f-strings: extract the pattern
            path_str: str | None = None
            if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                path_str = path_arg.value
            elif isinstance(path_arg, ast.JoinedStr):
                parts: list[str] = []
                for v in path_arg.values:
                    if isinstance(v, ast.Constant):
                        parts.append(str(v.value))
                    else:
                        parts.append("{param}")
                path_str = "".join(parts) if parts else None

            if path_str is None:
                continue

            calls.append({
                "file": str(py_file.relative_to(PROJECT_ROOT)),
                "line": node.lineno,
                "path": path_str,
                "method": method,
            })

    return calls


def _match_doc_endpoint(pattern: str, doc_endpoints: dict[str, set[str]]) -> str | None:
    """Match a path pattern against doc endpoints, normalizing path params."""
    # Normalize: replace path segments that look like params with {param}
    segments = pattern.strip("/").split("/")
    doc_patterns = list(doc_endpoints.keys())

    for doc_pat in doc_patterns:
        doc_segs = doc_pat.strip("/").split("/")
        if len(segments) != len(doc_segs):
            continue
        match = True
        for s, d in zip(segments, doc_segs):
            if d.startswith("{") and d.endswith("}"):
                continue  # doc has a path param here — any value matches
            if s != d:
                match = False
                break
        if match:
            return doc_pat
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKalshiDocExists:
    """Dep_Docs/Kalshi-llms.txt must exist."""

    def test_doc_exists(self) -> None:
        assert KALSHI_DOCS.is_file(), f"Kalshi doc not found at {KALSHI_DOCS}"
        text = KALSHI_DOCS.read_text(encoding="utf-8")
        assert "/markets" in text, "Dep_Docs missing /markets endpoint"
        assert "Get Balance" in text, "Dep_Docs missing /portfolio/balance (Get Balance)"


class TestKalshiEndpointsAreValid:
    """Every Kalshi endpoint path in source must exist in Dep_Docs."""

    @pytest.fixture(scope="class")
    def kalshi_calls(self) -> list[dict]:
        return _extract_kalshi_endpoints()

    def test_all_endpoints_match_docs(self, kalshi_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in kalshi_calls:
            matched = _match_doc_endpoint(call["path"], KALSHI_ENDPOINTS)
            if matched is None:
                errors.append(
                    f"{call['file']}:{call['line']}: {call['method']} {call['path']} "
                    f"not found in Dep_Docs Kalshi endpoints"
                )
        assert not errors, "\n".join(errors)

    def test_http_methods_match_docs(self, kalshi_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in kalshi_calls:
            matched = _match_doc_endpoint(call["path"], KALSHI_ENDPOINTS)
            if matched is None:
                continue  # already caught by endpoint match test
            valid_methods = KALSHI_ENDPOINTS[matched]
            if call["method"] not in valid_methods:
                errors.append(
                    f"{call['file']}:{call['line']}: {call['method']} {call['path']} "
                    f"not a valid method for {matched} (valid: {valid_methods})"
                )
        assert not errors, "\n".join(errors)


class TestKalshiClientEndpointCalls:
    """Validate that KalshiClient always uses ``self._client`` not raw httpx."""

    @pytest.fixture(scope="class")
    def kalshi_calls(self) -> list[dict]:
        return _extract_kalshi_endpoints()

    def test_client_calls_use_correct_receiver(self, kalshi_calls: list[dict]) -> None:
        """All endpoint calls should go through self._client (or `client`),
        not a raw httpx call."""
        errors: list[str] = []
        py_files = sorted(KALSHI_SRC.rglob("*.py"))
        for py_file in py_files:
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                method = node.func.attr.lower()
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                # Check receiver — should be self._client, client, or self.client
                if isinstance(node.func.value, ast.Attribute):
                    receiver = node.func.value.attr
                    if "httpx" in receiver.lower() or "request" in receiver.lower():
                        errors.append(
                            f"{py_file.relative_to(PROJECT_ROOT)}:{node.lineno}: "
                            f"raw httpx call {receiver}.{method}(), "
                            f"should use self._client.{method}()"
                        )
        assert not errors, "\n".join(errors)