"""SBI Card alerts from onlinesbicard@sbicard.com. Format taken from real Nov 2026 emails."""

import re
from datetime import datetime

from app.parsers.base import EmailInput, ParsedTxn, squash, to_amount

SENDER = "onlinesbicard@sbicard.com"


class SbiCardSpend:
    """Subject: "Transaction Alert from BPCL Octane Card"

    Rs.1,500.00 spent on your SBI Credit Card ending 3333 at TESTFILLINGSTATION on 31/10/26.
    """

    name = "sbicard_spend"
    senders = (SENDER,)
    pat = re.compile(
        r"Rs\.\s?([\d,]+(?:\.\d{1,2})?) spent on your SBI Credit Card ending (\d{4}) at (.*?) "
        r"on (\d{2}/\d{2}/\d{2})\b"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m:
            return None
        amount, last4, merchant, d = m.groups()
        return ParsedTxn(
            institution="SBI Card", account_type="credit_card", last4=last4, amount=to_amount(amount),
            direction="debit", txn_date=datetime.strptime(d, "%d/%m/%y").date(),
            counterparty_name=merchant.strip(), vpa_or_merchant=merchant.strip(),
        )


PARSERS = [SbiCardSpend()]
IGNORE_RULES: list = []
