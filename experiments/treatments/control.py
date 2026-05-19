"""ControlTreatment — production-mirroring control that calls generate_signal()."""

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface
from traderbot.analysis.signals import generate_signal
from traderbot.kalshi.models import OrderBook, OrderBookLevel


class ControlTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "control"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        try:
            signal = self._compute_signal(ctx)
        except Exception:
            return self._build_fallback_prompt(ctx)

        return self._format_signal_prompt(ctx, signal)

    def validate_response(self, response: dict) -> bool:
        decision = response.get("decision")
        if decision not in ("buy_yes", "buy_no", "skip"):
            return False

        prob = response.get("estimated_prob")
        if not isinstance(prob, (int, float)) or prob < 0 or prob > 1:
            return False

        confidence = response.get("confidence")
        return isinstance(confidence, (int, float))

    def _compute_signal(self, ctx: TreatmentContext):
        yes_cents = int(ctx.prices.yes_price * 100)
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=yes_cents, size=100)],
            no_bids=[OrderBookLevel(price=100 - yes_cents, size=100)],
        )
        prices = self._build_price_series(ctx)
        return generate_signal(
            ticker=ctx.market.ticker,
            prices=prices,
            orderbook=orderbook,
            estimated_prob=ctx.prices.implied_prob,
        )

    def _build_price_series(self, ctx: TreatmentContext) -> list[int]:
        base = int(ctx.prices.yes_price * 100)
        variations = [0, 1, -1, 2, -2, 1, -1, 3, -3, 0]
        return [max(1, min(99, base + v)) for v in variations]

    def _format_signal_prompt(self, ctx: TreatmentContext, signal) -> str:
        lines = [
            f"Market: {ctx.market.ticker} — {ctx.market.city}",
            f"Strike: {ctx.market.strike_type} {ctx.market.threshold}",
            f"Resolution: {ctx.market.resolution_date}",
            "",
            f"YES price: {ctx.prices.yes_price:.2f}  |  NO price: {ctx.prices.no_price:.2f}",
            f"Implied probability: {ctx.prices.implied_prob:.2f}",
            f"Trade count: {ctx.prices.trade_count}  |  Open interest: {ctx.prices.open_interest}",
            "",
            "Technical indicators:",
            f"  RSI(14): {ctx.technicals.rsi:.1f}",
            f"  Bollinger position: {ctx.technicals.bollinger_position:.2f}",
            f"  EMA(5): {ctx.technicals.ema5:.1f}",
            f"  EMA(20): {ctx.technicals.ema20:.1f}",
            "",
            f"Signal direction: {signal.direction}",
            f"Signal confidence: {signal.confidence:.2f}",
            f"Edge: {signal.edge_cents}¢",
        ]
        return "\n".join(lines)

    def _build_fallback_prompt(self, ctx: TreatmentContext) -> str:
        lines = [
            f"Market: {ctx.market.ticker} — {ctx.market.city}",
            f"Strike: {ctx.market.strike_type} {ctx.market.threshold}",
            f"Resolution: {ctx.market.resolution_date}",
            "",
            f"YES price: {ctx.prices.yes_price:.2f}  |  NO price: {ctx.prices.no_price:.2f}",
            f"Implied probability: {ctx.prices.implied_prob:.2f}",
            "",
            "Technical indicators (from context):",
            f"  RSI(14): {ctx.technicals.rsi:.1f}",
            f"  Bollinger position: {ctx.technicals.bollinger_position:.2f}",
            f"  EMA(5): {ctx.technicals.ema5:.1f}",
            f"  EMA(20): {ctx.technicals.ema20:.1f}",
            f"  Signal direction: {ctx.technicals.signal_direction}",
            f"  Signal confidence: {ctx.technicals.signal_confidence:.2f}",
        ]
        return "\n".join(lines)
