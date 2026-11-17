"""Parser registry. Formats come from real alert samples (`uv run python -m app.ingest.survey`)."""

from app.parsers import hdfc, sbicard
from app.parsers.base import ClassifyResult, EmailInput, IgnoreRule, TxnParser, classify

TXN_PARSERS: list[TxnParser] = [*hdfc.PARSERS, *sbicard.PARSERS]
IGNORE_RULES: list[IgnoreRule] = [*hdfc.IGNORE_RULES, *sbicard.IGNORE_RULES]


def classify_email(email: EmailInput) -> ClassifyResult:
    return classify(email, TXN_PARSERS, IGNORE_RULES)
