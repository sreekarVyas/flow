"""HDFC Bank alerts from alerts@hdfcbank.bank.in. Formats taken from real Nov 2026 emails.

HDFC masks most of each VPA in emails (e.g. ******0000@yescred), so names matter more than VPAs.
"""

import re
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.parsers.base import EmailInput, IgnoreRule, ParsedTxn, squash, to_amount

SENDER = "alerts@hdfcbank.bank.in"
IST = ZoneInfo("Asia/Kolkata")
AMT = r"([\d,]+(?:\.\d{1,2})?)"


def _dmy2(s: str) -> date:  # 31-10-26
    return datetime.strptime(s, "%d-%m-%y").date()


class HdfcUpiDebit:
    """Subject: "❗ You have done a UPI txn. Check details!"

    Rs.1500.00 is debited from your account ending 1111 towards VPA ******0000@ybl (Name) on 31-10-26.
    UPI transaction reference no.: 123456789012.
    """

    name = "hdfc_upi_debit"
    senders = (SENDER,)
    pat = re.compile(
        rf"Rs\.\s?{AMT} is debited from your account ending (\d{{4}}) towards "
        r"(?:VPA (\S+) \((.*?)\)|(.*?)) on (\d{2}-\d{2}-\d{2})\.?"
        r"(?: UPI transaction reference no\.?:? (\d+))?"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m:
            return None
        amount, last4, vpa, vpa_name, other, d, ref = m.groups()
        return ParsedTxn(
            institution="HDFC", account_type="bank", last4=last4, amount=to_amount(amount),
            direction="debit", txn_date=_dmy2(d),
            counterparty_name=(vpa_name or other or "").strip() or None,
            vpa_or_merchant=vpa, ref_no=ref,
        )


class HdfcUpiCredit:
    """Subject: "View: Account update for your HDFC Bank A/c"

    Rs.700.00 has been successfully credited to your HDFC Bank account ending in 1111.
    Transaction Details: a. Date: 31-10-26 b. Sender: NAME (VPA: ********00-1@ybl) c. UPI Reference No.: 123
    """

    name = "hdfc_upi_credit"
    senders = (SENDER,)
    pat = re.compile(
        rf"Rs\.\s?{AMT} has been successfully credited to your HDFC Bank account ending in (\d{{4}})\. "
        r"Transaction Details: a\. Date: (\d{2}-\d{2}-\d{2}) b\. Sender: (.*?)(?: \(VPA: (\S+?)\))? "
        r"c\. UPI Reference No\.?:? (\d+)"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m:
            return None
        amount, last4, d, sender, vpa, ref = m.groups()
        return ParsedTxn(
            institution="HDFC", account_type="bank", last4=last4, amount=to_amount(amount),
            direction="credit", txn_date=_dmy2(d),
            counterparty_name=sender.strip(), vpa_or_merchant=vpa, ref_no=ref,
        )


class HdfcCardSpend:
    """Subject: "A payment was made using your Credit Card"

    Rs. 554.00 has been debited from your HDFC Bank Credit Card ending 2222 towards RAZ*SWIGGY
    on 31 Oct, 2026 at 22:40:51 .
    """

    name = "hdfc_card_spend"
    senders = (SENDER,)
    pat = re.compile(
        rf"Rs\.\s?{AMT} has been debited from your HDFC Bank Credit Card ending (\d{{4}}) towards (.*?) "
        r"on (\d{1,2} [A-Za-z]{3}, \d{4})(?: at (\d{2}:\d{2}:\d{2}))?"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m:
            return None
        amount, last4, merchant, d, t = m.groups()
        return ParsedTxn(
            institution="HDFC", account_type="credit_card", last4=last4, amount=to_amount(amount),
            direction="debit", txn_date=datetime.strptime(d, "%d %b, %Y").date(),
            txn_time=time.fromisoformat(t) if t else None,
            counterparty_name=merchant.strip(), vpa_or_merchant=merchant.strip(),
        )


class HdfcEmiDebit:
    """Rs. INR 9,999.00 is deducted from your account ending XX1111 and added to EMI 900000001
    Chq S... account on 07-NOV-2026.
    """

    name = "hdfc_emi_debit"
    senders = (SENDER,)
    pat = re.compile(
        rf"Rs\.\s?(?:INR\s?)?{AMT} is deducted from your account ending X*(\d{{4}}) "
        r"and added to EMI (\d+)\b.*? account on (\d{2}-[A-Za-z]{3}-\d{4})"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m:
            return None
        amount, last4, loan, d = m.groups()
        return ParsedTxn(
            institution="HDFC", account_type="bank", last4=last4, amount=to_amount(amount),
            direction="debit", txn_date=datetime.strptime(d, "%d-%b-%Y").date(),
            counterparty_name="Loan EMI", vpa_or_merchant=f"EMI loan ••{loan[-4:]}",
        )


class HdfcNetbankingCardBill:
    """This is to inform you that an amount of Rs. 7,000.00 has been debited from your Account number
    XX1111 for Credit Card Payment done using HDFC Bank Online Banking.

    The email has no date. Use the email's received date (IST), with lower confidence.
    """

    name = "hdfc_netbanking_card_bill"
    senders = (SENDER,)
    pat = re.compile(
        rf"an amount of Rs\.\s?{AMT} has been debited from your Account number X*(\d{{4}}) "
        r"for Credit Card Payment done using HDFC Bank Online Banking"
    )

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(squash(email.body_text))
        if not m or email.received_at is None:
            return None
        amount, last4 = m.groups()
        return ParsedTxn(
            institution="HDFC", account_type="bank", last4=last4, amount=to_amount(amount),
            direction="debit", txn_date=email.received_at.astimezone(IST).date(),
            counterparty_name="Credit card bill (NetBanking)", vpa_or_merchant="HDFC NetBanking",
            confidence=Decimal("0.90"),
        )


PARSERS = [HdfcUpiDebit(), HdfcUpiCredit(), HdfcCardSpend(), HdfcEmiDebit(), HdfcNetbankingCardBill()]

IGNORE_RULES = [
    IgnoreRule(
        "hdfc_netbanking_terms",
        (SENDER,),
        body=re.compile(r"accepted the terms and conditions of using NetBanking", re.I),
    ),
]
