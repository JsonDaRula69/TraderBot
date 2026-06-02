"""Market commands: scan, signals, sentiment."""
from __future__ import annotations

import asyncio
import json as json_lib
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import err_console

logger = logging.getLogger(__name__)


def register_commands(parent_app: typer.Typer) -> None:

    @parent_app.command()
    def scan(
        limit: Annotated[int, typer.Option("--limit", help="Max markets to return")] = 500,
        category: Annotated[str | None, typer.Option("--category", help="Filter by category")] = None,
        continuous: Annotated[
            bool, typer.Option("--continuous", help="Continuous polling mode for agent service (re-scans every 5min)")
        ] = False,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        """List open markets from Kalshi. Use --continuous for agent service polling."""
        from traderbot.kalshi.markets import MarketService

        console = Console()

        async def _scan_once() -> list[dict[str, object]]:
            for attempt in range(3):
                try:
                    from traderbot.kalshi.client import KalshiClient

                    client = KalshiClient()
                    service = MarketService(client)
                    if category is not None:
                        result = await service.list_markets_by_category(category=category, limit=limit)
                    else:
                        result = await service.list_markets(limit=limit)
                    if result.markets or attempt == 2:
                        return [m.model_dump(mode="json") for m in result.markets]
                    logger.warning("Scan returned empty, retrying (attempt %d/3)", attempt + 1)
                    await asyncio.sleep(5)
                except Exception:
                    if attempt == 2:
                        return []
                    await asyncio.sleep(5)
            return []

        if continuous:
            import time
            while True:
                markets = asyncio.run(_scan_once())
                if json_output:
                    json_lib.dump(markets, sys.stdout, default=str)
                    sys.stdout.flush()
                else:
                    console.print(f"[{datetime.now(UTC).isoformat()}] Scan complete: {len(markets)} markets")
                # time.sleep() is safe here — this runs in a dedicated sync thread from typer
                time.sleep(300)  # 5-minute polling interval to match decision loop cadence

        markets = asyncio.run(_scan_once())

        if json_output:
            json_lib.dump(markets, sys.stdout, default=str)
            return

        table = Table(title="Open Markets")
        table.add_column("Ticker", style="cyan")
        table.add_column("Question", style="white")
        table.add_column("Volume", justify="right")
        table.add_column("State", style="green")
        for m in markets:
            table.add_row(m["ticker"], m["question"], str(m["volume"]), m["status"])
        console.print(table)

    @parent_app.command()
    def signals(
        category: Annotated[
            str | None, typer.Option("--category", help="Filter by market category")
        ] = None,
        limit: Annotated[int, typer.Option("--limit", help="Max markets to scan")] = 10,
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
    ) -> None:
        """Compute and display trading signals across open markets."""
        from traderbot.analysis.odds import implied_probability
        from traderbot.analysis.signals import generate_signal
        from traderbot.kalshi.models import MarketCategory

        console = Console()

        category_enum: MarketCategory | None = None
        if category is not None:
            try:
                category_enum = MarketCategory(category.lower())
            except ValueError:
                valid = ", ".join(c.value for c in MarketCategory)
                if json_output:
                    json_lib.dump({"error": f"Invalid category: {category}. Valid: {valid}"}, sys.stdout)
                else:
                    err_console.print(f"[red]Invalid category:[/red] {category}. Valid: {valid}")
                raise typer.Exit(code=1) from None

        try:
            from traderbot.kalshi.client import KalshiClient
            from traderbot.kalshi.markets import MarketService

            client = KalshiClient()
            service = MarketService(client)
            if category_enum is not None:
                result = asyncio.run(service.list_markets_by_category(category=category, limit=limit))
            else:
                result = asyncio.run(service.list_markets(limit=limit))
            markets = result.markets
        except Exception:
            if json_output:
                json_lib.dump({"note": "Signal generation requires API connection"}, sys.stdout)
            else:
                console.print("[yellow]Signal generation requires API connection.[/yellow]")
            return

        if category_enum is not None:
            cat_val = category_enum.value
            markets = [m for m in markets if m.market_category == category_enum or (m.category and m.category.lower() in (cat_val, f"climate and {cat_val}"))]

        if not markets:
            if json_output:
                json_lib.dump([], sys.stdout)
            else:
                console.print("[yellow]No open markets found.[/yellow]")
            return

        news_context: dict | None = None
        if category is not None:
            try:
                from traderbot.news.ingest import get_news_context
                news_context = get_news_context(category=category.lower())
            except Exception:
                pass
        news_context = news_context or {}

        results = []
        for mkt in markets:
            try:
                signal = generate_signal(mkt, news_context)
                results.append({
                    "ticker": mkt.ticker,
                    "question": mkt.question,
                    "signal": signal.value,
                    "confidence": signal.confidence,
                    "category": mkt.market_category.value if mkt.market_category else mkt.category or "",
                })
            except Exception:
                pass

        if json_output:
            json_lib.dump(results, sys.stdout, default=str)
            return

        table = Table(title="Trading Signals")
        table.add_column("Ticker", style="cyan")
        table.add_column("Question", style="white", max_width=50)
        table.add_column("Signal", style="bold")
        table.add_column("Confidence", justify="right")
        table.add_column("Category", style="green")
        for r in results:
            signal_color = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}.get(r["signal"], "")
            table.add_row(r["ticker"], r["question"], f"[{signal_color}]{r['signal']}[/{signal_color}]",
                          f"{r['confidence']:.2f}", r["category"])
        console.print(table)

    @parent_app.command()
    def sentiment(
        ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BTC, SPX)")],
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """Analyze market sentiment from news and social for a ticker."""
        from traderbot.news.cache_paths import get_news_cache_path
        from traderbot.news.classifier import NewsClassifier
        from traderbot.news.impact_assessor import ImpactAssessor
        from traderbot.news.models import NewsCategory, NewsItem
        from traderbot.news.sentiment_scorer import SentimentScorer
        from traderbot.news.sources import NewsAggregator
        from traderbot.profiles.config import resolve_newsapi_key
        from traderbot.profiles.runtime import get_current_profile

        console = Console()

        profile = get_current_profile()

        newsapi_key = resolve_newsapi_key(profile)
        twitter_key = os.environ.get("TWITTER_API_KEY")

        category_filter: list[NewsCategory] | None = None
        if profile is not None and profile.enabled_categories:
            category_filter = profile.enabled_categories

        cache_path = get_news_cache_path(profile)
        logger.debug("News cache path: %s", cache_path)

        async def _fetch() -> list[NewsItem]:
            async with NewsAggregator(
                newsapi_key=newsapi_key, twitter_api_key=twitter_key
            ) as aggregator:
                return await aggregator.fetch_all(limit=50)

        try:
            items = asyncio.run(_fetch())
        except Exception:
            if json_output:
                json_lib.dump({"error": "Failed to fetch news"}, sys.stdout)
            else:
                console.print("[red]Failed to fetch news.[/red]")
            return

        # Filter items that reference the ticker (case-insensitive)
        ticker_upper = ticker.upper()
        ticker_refs_items = [
            item
            for item in items
            if any(t.upper() == ticker_upper for t in item.ticker_refs)
            or ticker_upper in item.title.upper()
        ]

        if not ticker_refs_items and not items:
            if json_output:
                json_lib.dump({"ticker": ticker_upper, "error": "No news found"}, sys.stdout)
            else:
                console.print(
                    f"[yellow]No news found for [/yellow]{ticker_upper}[yellow]. Check API keys.[/yellow]"
                )
            return

        # Fall back to all items if none have ticker refs
        items_to_analyze = ticker_refs_items if ticker_refs_items else items[:10]

        classifier = NewsClassifier()
        scorer = SentimentScorer()
        assessor = ImpactAssessor()

        classified_items: list[dict] = []
        for item in items_to_analyze:
            classified = classifier.classify(item, category_filter=category_filter)
            if classified is None:
                continue
            if category_filter is not None and classified.category not in category_filter:
                continue
            sentiment = scorer.score(item.title, item.source, item.id)
            impact = assessor.assess(item, classified, sentiment)
            classified_items.append({
                "news_item": item,
                "category": classified.category,
                "sentiment_score": sentiment.score,
                "sentiment_confidence": sentiment.confidence,
                "sentiment_model": sentiment.model,
                "impact": impact,
            })

        if json_output:
            output = []
            for entry in classified_items:
                item = entry["news_item"]
                impact = entry["impact"]
                output.append({
                    "ticker": ticker_upper,
                    "id": item.id,
                    "title": item.title,
                    "source": item.source.value,
                    "category": entry["category"].value,
                    "sentiment_score": entry["sentiment_score"],
                    "sentiment_confidence": entry["sentiment_confidence"],
                    "sentiment_model": entry["sentiment_model"],
                    "impact": {
                        "magnitude": impact.magnitude,
                        "direction": impact.direction,
                        "timeframe": impact.timeframe,
                        "confidence": impact.confidence,
                    },
                    "url": item.url,
                    "published_at": item.published_at.isoformat(),
                })
            json_lib.dump(output, sys.stdout, default=str)
            return

        if not classified_items:
            console.print(f"[yellow]No classified news found for [/yellow]{ticker_upper}")
            return

        console.print(f"[bold]Sentiment Analysis:[/bold] {ticker_upper}")
        table = Table(title="News Articles")
        table.add_column("Source", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Sentiment", justify="right")
        table.add_column("Impact", justify="right")
        table.add_column("Title", style="white", max_width=60)

        for entry in classified_items:
            item = entry["news_item"]
            impact = entry["impact"]
            sent_str = f"{entry['sentiment_score']:.2f}" if entry["sentiment_score"] is not None else "—"
            table.add_row(
                item.source.value,
                entry["category"].value,
                sent_str,
                f"{impact.magnitude:.2f}",
                item.title[:80],
            )
        console.print(table)
