"""Deterministic, local rule-based review analytics.

Per constitution Principle VI: all analysis here MUST be computed locally from
rule-based dictionaries / regex, MUST NOT call any LLM or external service, and MUST
degrade safely on missing or malformed input (never raise). Nothing in this package
feeds the deduplication ``content_hash``.
"""

from app.analysis.analyzer import ReviewAnalyzer
from app.analysis.problems import ProblemExtractor
from app.analysis.sentiment import SentimentAnalyzer

__all__ = ["ReviewAnalyzer", "ProblemExtractor", "SentimentAnalyzer"]
