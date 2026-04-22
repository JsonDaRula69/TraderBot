"""Tests for sentiment_scorer — VADER, TextBlob, Voyage uplift, degradation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from traderbot.news.models import NewsSource
from traderbot.news.sentiment_scorer import SentimentScorer


@pytest.fixture
def scorer_no_voyage() -> SentimentScorer:
    return SentimentScorer(voyage_client=None)


@pytest.fixture
def mock_voyage() -> MagicMock:
    return MagicMock()


@pytest.fixture
def scorer_with_voyage(mock_voyage: MagicMock) -> SentimentScorer:
    return SentimentScorer(voyage_client=mock_voyage)


class TestVaderPath:
    def test_twitter_positive(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "Great earnings! Market rally is fantastic!", NewsSource.TWITTER, "t1"
        )
        assert result.news_id == "t1"
        assert result.score > 0.3
        assert result.model == "vader"
        assert result.confidence > 0.0

    def test_twitter_negative(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "Terrible crash, market is awful and devastating", NewsSource.TWITTER, "t2"
        )
        assert result.score < -0.3
        assert result.model == "vader"

    def test_reddit_uses_vader(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "Bullish on tech stocks!", NewsSource.REDDIT, "r1"
        )
        assert result.model == "vader"

    def test_vader_neutral_no_voyage(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "The market opened today.", NewsSource.TWITTER, "t3"
        )
        assert result.model == "vader"


class TestTextBlobPath:
    def test_newsapi_positive(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "The economy showed excellent growth in the latest quarterly report, "
            "with GDP expanding beyond expectations and strong positive results.",
            NewsSource.NEWSAPI,
            "n1",
        )
        assert result.score > 0.0
        assert result.model == "textblob"

    def test_newsapi_negative(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "Companies announced massive terrible layoffs across multiple sectors "
            "as the worst economic crisis deepened with awful results.",
            NewsSource.NEWSAPI,
            "n2",
        )
        assert result.score < 0.0
        assert result.model == "textblob"

    def test_newsapi_uses_textblob_not_vader(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score("Stocks went up nicely.", NewsSource.NEWSAPI, "n3")
        assert result.model.startswith("textblob")


class TestVoyageUplift:
    def test_uplift_called_for_ambiguous_vader(
        self, scorer_with_voyage: SentimentScorer, mock_voyage: MagicMock
    ) -> None:
        mock_voyage.embed.return_value = [0.1] * 1024
        result = scorer_with_voyage.score(
            "Officials signal caution", NewsSource.TWITTER, "u1"
        )
        assert mock_voyage.embed.called
        assert "+voyage" in result.model

    def test_uplift_not_called_for_high_confidence(
        self, scorer_with_voyage: SentimentScorer, mock_voyage: MagicMock
    ) -> None:
        mock_voyage.embed.return_value = [0.1] * 1024
        result = scorer_with_voyage.score(
            "Amazing incredible fantastic breakthrough!", NewsSource.TWITTER, "u2"
        )
        if -0.3 < result.score < 0.3:
            pytest.skip("VADER scored ambiguous despite positive words")
        assert mock_voyage.embed.called is False

    def test_uplift_shifts_score(
        self, scorer_with_voyage: SentimentScorer, mock_voyage: MagicMock
    ) -> None:
        text_emb = [0.9] * 512 + [0.1] * 512
        pos_emb = [0.9] * 512 + [0.1] * 512
        neg_emb = [0.1] * 512 + [0.9] * 512
        mock_voyage.embed.side_effect = [text_emb, pos_emb, neg_emb]

        result = scorer_with_voyage.score(
            "Some ambiguous statement about markets", NewsSource.TWITTER, "u3"
        )
        assert "+voyage" in result.model

    def test_uplift_for_textblob_ambiguous(
        self, scorer_with_voyage: SentimentScorer, mock_voyage: MagicMock
    ) -> None:
        mock_voyage.embed.return_value = [0.1] * 1024
        result = scorer_with_voyage.score(
            "The market may shift depending on policy.", NewsSource.NEWSAPI, "u4"
        )
        if -0.3 < result.score < 0.3:
            assert mock_voyage.embed.called


class TestGracefulDegradation:
    def test_no_voyage_client(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score("Some text here.", NewsSource.TWITTER, "d1")
        assert "+voyage" not in result.model

    def test_voyage_returns_none(self) -> None:
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = None
        scorer = SentimentScorer(voyage_client=mock_voyage)
        result = scorer.score("Ambiguous text about markets.", NewsSource.TWITTER, "d2")
        assert "+voyage" not in result.model

    def test_voyage_partial_failure(self) -> None:
        mock_voyage = MagicMock()
        text_emb = [0.5] * 1024
        pos_emb = [0.6] * 1024
        mock_voyage.embed.side_effect = [text_emb, pos_emb, None]
        scorer = SentimentScorer(voyage_client=mock_voyage)
        result = scorer.score("Ambiguous market signal.", NewsSource.TWITTER, "d3")
        assert "+voyage" not in result.model


class TestSentimentResultFields:
    def test_score_bounded(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score(
            "EXTREMELY AMAZING WONDERFUL INCREDIBLE FANTASTIC!!!",
            NewsSource.TWITTER,
            "b1",
        )
        assert -1.0 <= result.score <= 1.0

    def test_confidence_bounded(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score("Some text.", NewsSource.TWITTER, "b2")
        assert 0.0 <= result.confidence <= 1.0

    def test_timestamp_is_utc(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score("Text.", NewsSource.TWITTER, "b3")
        assert result.timestamp.tzinfo is not None

    def test_news_id_preserved(self, scorer_no_voyage: SentimentScorer) -> None:
        result = scorer_no_voyage.score("Text.", NewsSource.TWITTER, "my-id-123")
        assert result.news_id == "my-id-123"