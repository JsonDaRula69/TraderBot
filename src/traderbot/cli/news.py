"""News commands: news, news-ingest, news-context, backfill, data-points, news-summary."""
from __future__ import annotations

import asyncio
import json as json_lib
import os
import sys
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import err_console


def register_commands(parent_app: typer.Typer) -> None:

    @parent_app.command()
    def news(
        category: Annotated[
            str | None,
            typer.Option(
                "--category",
                help="Filter by category: Economics, Politics, Weather, Culture, Tech, Science",
            ),
        ] = None,
        limit: Annotated[int, typer.Option("--limit", help="Max items to fetch")] = 10,
        source: Annotated[
            str | None,
            typer.Option("--source", help="Filter by source: newsapi, twitter, reddit, open-meteo, coingecko, thesportsdb, openweathermap, fred, google-trends, all"),
        ] = None,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """Fetch and display news for tracked markets."""
        from traderbot.news.cache_paths import get_news_cache_path
        from traderbot.news.classifier import NewsClassifier
        from traderbot.news.models import DataPoint, NewsCategory, NewsItem, NewsSource
        from traderbot.news.sentiment_scorer import SentimentScorer
        from traderbot.news.sources import DataSourcesConfig, NewsAggregator
        from traderbot.profiles.config import (
            resolve_fred_key,
            resolve_newsapi_key,
            resolve_openweather_key,
        )
        from traderbot.profiles.runtime import get_current_profile

        console = Console()

        # Resolve active profile
        profile = get_current_profile()

        # Validate --category
        category_enum: NewsCategory | None = None
        if category is not None:
            try:
                category_enum = NewsCategory(category.lower())
            except ValueError:
                valid = ", ".join(c.value for c in NewsCategory)
                if json_output:
                    json_lib.dump(
                        {"error": f"Invalid category: {category}. Valid: {valid}"}, sys.stdout
                    )
                else:
                    err_console.print(f"[red]Invalid category:[/red] {category}. Valid: {valid}")
                raise typer.Exit(code=1) from None

        # Profile-aware category validation: --category must be in enabled_categories
        if (
            profile is not None
            and category_enum is not None
            and profile.enabled_categories
            and not profile.is_category_enabled(category_enum)
        ):
            if json_output:
                json_lib.dump(
                    {
                        "error": f"Category '{category_enum.value}' not enabled for profile '{profile.name}'"
                    },
                    sys.stdout,
                )
            else:
                err_console.print(
                    f"[red]Category '{category_enum.value}' not enabled for profile '{profile.name}'.[/red]"
                )
            raise typer.Exit(code=1) from None

        # Resolve API keys
        newsapi_key = resolve_newsapi_key(profile)
        openweather_key = resolve_openweather_key(profile)
        fred_key = resolve_fred_key(profile)
        twitter_key = os.environ.get("TWITTER_API_KEY")

        # Set env vars for sources that read from environment
        if newsapi_key:
            os.environ["NEWSAPI_API_KEY"] = newsapi_key
        if openweather_key:
            os.environ["OPENWEATHER_API_KEY"] = openweather_key
        if fred_key:
            os.environ["FRED_API_KEY"] = fred_key

        cache_path = get_news_cache_path(profile)

        # Build category filter
        category_filter: list[NewsCategory] | None = None
        if category_enum is not None:
            category_filter = [category_enum]
        elif profile is not None and profile.enabled_categories:
            category_filter = profile.enabled_categories

        # Build source filter
        source_filter: NewsSource | None = None
        if source is not None:
            try:
                source_filter = NewsSource(source.lower())
            except ValueError:
                valid = ", ".join(s.value for s in NewsSource)
                if json_output:
                    json_lib.dump(
                        {"error": f"Invalid source: {source}. Valid: {valid}"}, sys.stdout
                    )
                else:
                    err_console.print(f"[red]Invalid source:[/red] {source}. Valid: {valid}")
                raise typer.Exit(code=1) from None

        async def _fetch() -> list[NewsItem | DataPoint]:
            async with NewsAggregator(
                newsapi_key=newsapi_key,
                twitter_api_key=twitter_key,
                openweather_key=openweather_key,
                fred_key=fred_key,
                cache_path=cache_path,
            ) as aggregator:
                return await aggregator.fetch_all(limit=limit, source_filter=source_filter)

        try:
            items = asyncio.run(_fetch())
        except Exception:
            if json_output:
                json_lib.dump({"error": "Failed to fetch news"}, sys.stdout)
            else:
                console.print("[red]Failed to fetch news.[/red]")
            return

        classifier = NewsClassifier()
        scorer = SentimentScorer()
        classified_items: list[dict] = []
        datapoints: list[DataPoint] = []
        for item_or_dp in items:
            if isinstance(item_or_dp, DataPoint):
                datapoints.append(item_or_dp)
                continue
            classified = classifier.classify(item_or_dp, category_filter=category_filter)
            if classified is None:
                continue
            if category_enum is not None and classified.category != category_enum:
                continue
            sentiment = scorer.score(item_or_dp.title, item_or_dp.source, item_or_dp.id)
            classified_items.append(
                {
                    "classified": classified,
                    "sentiment": sentiment,
                }
            )

        if json_output:
            output = []
            for entry in classified_items:
                c = entry["classified"]
                s = entry["sentiment"]
                item = c.news_item
                output.append(
                    {
                        "type": "news_item",
                        "id": item.id,
                        "title": item.title,
                        "source": item.source.value,
                        "category": c.category.value,
                        "published_at": item.published_at.isoformat(),
                        "sentiment_score": s.score,
                        "sentiment_confidence": s.confidence,
                        "sentiment_model": s.model,
                        "url": item.url,
                        "ticker_refs": item.ticker_refs,
                    }
                )
            for dp in datapoints:
                output.append(
                    {
                        "type": "data_point",
                        "id": dp.id,
                        "source": dp.source.value,
                        "category": dp.category.value if dp.category else None,
                        "title": dp.title,
                        "data": dp.data,
                        "timestamp": dp.timestamp.isoformat(),
                        "ticker_refs": dp.ticker_refs,
                        "metadata": dp.metadata,
                    }
                )
            json_lib.dump(output, sys.stdout, default=str)
            return

        if not classified_items and not datapoints:
            console.print("No news items found.")
            return

        table = Table(title="News Feed")
        table.add_column("Title", style="white", max_width=50)
        table.add_column("Source", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Sentiment", justify="right")
        table.add_column("Published", style="dim")

        for entry in classified_items:
            c = entry["classified"]
            s = entry["sentiment"]
            item = c.news_item
            title = item.title[:80]
            score_str = f"{s.score:.2f}" if s.score is not None else "—"
            table.add_row(
                title,
                item.source.value,
                c.category.value,
                score_str,
                item.published_at.isoformat()[:10],
            )
        console.print(table)

        if datapoints:
            console.print(f"\n[dim]Data points: {len(datapoints)}[/dim]")

    @parent_app.command()
    def news_ingest(
        limit: Annotated[int, typer.Option("--limit", help="Max items to fetch per run")] = 50,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """Fetch, classify, embed, and store news articles into ChromaDB.

        Runs as a pure data pipeline — no LLM required. Call from cron/timer
        to accumulate news while the agent is offline. Subsequent calls
        automatically deduplicate by URL hash.
        """
        from traderbot.news.ingest import ingest_news
        from traderbot.profiles.config import (
            resolve_fred_key,
            resolve_newsapi_key,
            resolve_openweather_key,
        )
        from traderbot.profiles.runtime import get_current_profile

        console = Console()

        profile = get_current_profile()
        newsapi_key = resolve_newsapi_key(profile)
        openweather_key = resolve_openweather_key(profile)
        fred_key = resolve_fred_key(profile)

        if newsapi_key:
            os.environ["NEWSAPI_API_KEY"] = newsapi_key
        if openweather_key:
            os.environ["OPENWEATHER_API_KEY"] = openweather_key
        if fred_key:
            os.environ["FRED_API_KEY"] = fred_key
        if profile:
            voyage_key = os.environ.get(
                f"VOYAGE_API_KEY_PROFILE_{profile.name.upper()}",
                os.environ.get("VOYAGE_API_KEY", "")
            )
            if voyage_key:
                os.environ["VOYAGE_API_KEY"] = voyage_key

        report = ingest_news(
            limit=limit,
            newsapi_key=newsapi_key,
            openweather_key=openweather_key,
            fred_key=fred_key,
        )

        if json_output:
            json_lib.dump(report.to_dict(), sys.stdout, default=str)
            return

        console.print(f"[green]✓[/green] Ingest report — "
                      f"[bold]{report.new}[/bold] new, "
                      f"{report.duplicates} duplicates, "
                      f"{report.skipped} skipped, "
                      f"{report.signals} signals, "
                      f"{report.errors} errors "
                      f"({report.elapsed_seconds:.1f}s)")
        console.print(f"  News collection: {report.collection_sizes.get('news', 0)} items")
        console.print(f"  Signals collection: {report.collection_sizes.get('news_signals', 0)} items")
        dp_count = report.collection_sizes.get("data_points", 0)
        if dp_count:
            console.print(f"  Data points collection: {dp_count} items")

    @parent_app.command()
    def news_context(
        category: Annotated[str, typer.Argument(help="News/market category (economics, weather, politics, ...)")],
        hours: Annotated[int, typer.Option("--hours", "-h", help="Look back window in hours")] = 24,
        limit: Annotated[int, typer.Option("--limit", "-l", help="Max articles to return")] = 10,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
        include_data: Annotated[bool, typer.Option("--include-data", help="Also include data point readings (weather, economic indicators, etc.)")] = False,
    ) -> None:
        """Get news context for a market category — aggregated sentiment + top articles.

        Queries ChromaDB for news in the given category, computes aggregate
        sentiment, and returns structured data. Use this before trading to
        understand the news landscape for a market category.

        Use --include-data to also fetch quantitative readings (temperature,
        humidity, economic indicators, crypto prices) for the same category.
        """
        from traderbot.news.ingest import get_news_context

        console = Console()
        ctx = get_news_context(category=category, since_hours=hours, max_articles=limit, include_data_points=include_data)

        if json_output:
            json_lib.dump(ctx, sys.stdout, default=str)
            return

        if ctx["article_count"] == 0:
            console.print(f"[yellow]No news articles found for '{category}' in the last {hours}h.[/yellow]")
        else:
            console.print(f"[bold]News Context:[/bold] {category} — last {hours}h")
            console.print(f"  Articles: {ctx['article_count']}")
            console.print(f"  Sentiment: [bold]{ctx['sentiment']}[/bold] "
                          f"(+{ctx['positive_count']}/-{ctx['negative_count']}/{ctx['neutral_count']})")
            console.print()

            table = Table(title="Top Articles")
            table.add_column("Source", style="cyan")
            table.add_column("Sentiment", justify="right")
            table.add_column("Title", style="white")
            for a in ctx["articles"]:
                sent_str = f"{a['sentiment_score']:.2f}" if a["sentiment_score"] is not None else "—"
                table.add_row(a["source"], sent_str, a["title"][:80])
            console.print(table)

        # Show data points when included
        data_pts = ctx.get("data_points")
        if data_pts and data_pts.get("count", 0) > 0:
            console.print()
            console.print(f"[bold]Data Points:[/bold] {data_pts['count']} readings")
            for dp in data_pts["data_points"][:5]:
                title = dp.get("title", "")[:80]
                data_str = "; ".join(f"{k}={v}" for k, v in dp.get("data", {}).items())
                if data_str:
                    console.print(f"  [dim]{dp.get('source','')}[/dim] — {title}: {data_str}")
                else:
                    console.print(f"  [dim]{dp.get('source','')}[/dim] — {title}")

    @parent_app.command()
    def backfill(
        months: Annotated[int, typer.Option("--months", "-m", help="Months of history to backfill")] = 6,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """One-time historical data backfill for weather and economic indicators.

        Fetches 6 months (default) of historical weather data from Open-Meteo
        and economic observations from FRED, storing to the data_points
        ChromaDB collection. Run this once to bootstrap historical context
        before regular news-ingest cycles take over.
        """
        from traderbot.news.ingest import backfill_data

        console = Console()
        if json_output:
            import json as json_lib

        console.print(f"[bold]Backfill:[/bold] fetching {months} months of historical data...")

        counts = backfill_data(months=months)

        if json_output:
            json_lib.dump(counts, sys.stdout)
            print()
        else:
            console.print()
            console.print("[bold green]Backfill complete:[/bold green]")
            for source, count in counts.items():
                console.print(f"  {source}: {count} data points stored")
            total = sum(counts.values())
            console.print(f"  [bold]Total: {total}[/bold]")

    @parent_app.command()
    def data_points(
        category: Annotated[str, typer.Argument(help="Market category (weather, economics, politics, ...)")],
        hours: Annotated[int, typer.Option("--hours", "-h", help="Look back window in hours")] = 48,
        limit: Annotated[int, typer.Option("--limit", "-l", help="Max data points to return")] = 10,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """Query data point readings for a market category.

        Returns structured quantitative data (weather readings, economic
        indicators, crypto prices, sports scores) stored by the offline
        ingestion pipeline. Useful for pre-trade context on weather,
        economics, and other data-driven markets.
        """
        from traderbot.news.ingest import get_data_points

        console = Console()
        ctx = get_data_points(category=category, since_hours=hours, max_items=limit)

        if json_output:
            import json as _json
            _json.dump(ctx, sys.stdout, default=str)
            return

        if ctx["count"] == 0:
            console.print(f"[yellow]No data points found for '{category}' in the last {hours}h.[/yellow]")
            return

        console.print(f"[bold]Data Points:[/bold] {category} — last {hours}h")
        console.print(f"  Readings: {ctx['count']}")
        console.print()

        for dp in ctx["data_points"]:
            console.print(f"[cyan]{dp['source']}[/cyan] — {dp['title']}")
            data_str = "; ".join(f"{k}={v}" for k, v in dp.get("data", {}).items())
            if data_str:
                console.print(f"  [dim]{data_str}[/dim]")

    @parent_app.command()
    def news_summary(
        since: Annotated[
            str | None,
            typer.Option("--since", help="ISO 8601 timestamp — only articles after this time"),
        ] = None,
        category: Annotated[
            str | None,
            typer.Option("--category", help="Filter by category (Economics, Politics, Weather, ...)"),
        ] = None,
        source: Annotated[
            str | None,
            typer.Option("--source", help="Filter by source (newsapi, reddit, coingecko, ...)"),
        ] = None,
        limit: Annotated[int, typer.Option("--limit", help="Max articles to return")] = 30,
        query: Annotated[
            str | None,
            typer.Option("--query", help="Semantic search query (uses VoyageAI embedding)"),
        ] = None,
        signal_only: Annotated[
            bool,
            typer.Option("--signals", help="Only return high-impact signals"),
        ] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    ) -> None:
        """Retrieve accumulated news from ChromaDB.

        Supports time-range filtering, category/source filters, and
        semantic search via VoyageAI. Without --since, returns the
        most recent articles across all time.
        """
        from traderbot.news.ingest import get_news_summary

        console = Console()

        since_dt: datetime | None = None
        if since is not None:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError:
                err_console = Console(stderr=True)
                err_console.print(f"[red]Invalid timestamp:[/red] {since}. Use ISO 8601 format.")
                raise typer.Exit(code=1) from None

        items = get_news_summary(
            since=since_dt,
            category=category,
            source=source,
            limit=limit,
            query=query,
            signal_only=signal_only,
        )

        if json_output:
            json_lib.dump([it.to_dict() for it in items], sys.stdout, default=str)
            return

        if not items:
            console.print("No accumulated news found.")
            return

        table = Table(title="Accumulated News")
        table.add_column("Title", style="white", max_width=50)
        table.add_column("Source", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Sentiment", justify="right")
        table.add_column("Impact", justify="right")
        table.add_column("Published", style="dim")

        for item in items:
            meta = item.metadata
            title = meta.get("title", item.text[:80]) or item.text[:80]
            score_str = meta.get("sentiment_score", "")
            imp_str = meta.get("impact_magnitude", "")
            table.add_row(
                title,
                meta.get("source", ""),
                meta.get("category", ""),
                f"{score_str}" if score_str else "",
                f"{imp_str}" if imp_str else "",
                meta.get("published", "")[:10],
            )
        console.print(table)
