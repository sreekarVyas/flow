"""Real-format parser tests. Fixtures copy the real email layout with fake names and numbers."""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import classify_email
from app.parsers.base import EmailInput, infer_kind

FIX = Path(__file__).parent / "fixtures"
HDFC = "alerts@hdfcbank.bank.in"
SBI = "onlinesbicard@sbicard.com"
RECEIVED = datetime(2026, 11, 17, 14, 23, tzinfo=UTC)  # 19:53 IST


def run(fixture: str, sender: str = HDFC, subject: str = "s"):
    return classify_email(EmailInput(sender, subject, (FIX / fixture).read_text(), RECEIVED))


CASES = [
    ("hdfc_upi_debit.txt", HDFC, "hdfc_upi_debit",
     dict(institution="HDFC", account_type="bank", last4="1111", amount=Decimal("1500.00"), direction="debit",
          txn_date=date(2026, 10, 31), counterparty_name="Test Payee Name", vpa_or_merchant="******0000@ybl",
          ref_no="100000000001"), "expense"),
    ("hdfc_upi_debit_paren_name.txt", HDFC, "hdfc_upi_debit",
     dict(amount=Decimal("40.00"), counterparty_name="Sri Test tea stall 2", txn_date=date(2026, 11, 5)), "expense"),
    ("hdfc_upi_credit.txt", HDFC, "hdfc_upi_credit",
     dict(last4="1111", amount=Decimal("700.00"), direction="credit", txn_date=date(2026, 10, 31),
          counterparty_name="TEST FRIEND NAME", vpa_or_merchant="********00-1@ybl", ref_no="100000000003"), None),
    ("hdfc_card_spend.txt", HDFC, "hdfc_card_spend",
     dict(account_type="credit_card", last4="2222", amount=Decimal("554.00"), direction="debit",
          txn_date=date(2026, 10, 31), txn_time=time(22, 40, 51), counterparty_name="RAZ*SWIGGY"), "expense"),
    ("hdfc_emi_debit.txt", HDFC, "hdfc_emi_debit",
     dict(last4="1111", amount=Decimal("9999.00"), direction="debit", txn_date=date(2026, 11, 7),
          counterparty_name="Loan EMI", vpa_or_merchant="EMI loan ••0001"), "expense"),
    ("hdfc_netbanking_card_bill.txt", HDFC, "hdfc_netbanking_card_bill",
     dict(last4="1111", amount=Decimal("7000.00"), direction="debit", txn_date=date(2026, 11, 17),
          confidence=Decimal("0.90")), "transfer"),
    ("sbicard_spend.txt", SBI, "sbicard_spend",
     dict(institution="SBI Card", account_type="credit_card", last4="3333", amount=Decimal("1500.00"),
          direction="debit", txn_date=date(2026, 10, 31), counterparty_name="TESTFILLINGSTATION"), "expense"),
]


@pytest.mark.parametrize(("fixture", "sender", "parser", "expected", "kind"), CASES, ids=[c[0] for c in CASES])
def test_parser(fixture, sender, parser, expected, kind):
    r = run(fixture, sender)
    assert (r.status, r.parser_name) == ("txn", parser), r.error
    for field, value in expected.items():
        assert getattr(r.txn, field) == value, field
    assert infer_kind(r.txn) == kind


def test_netbanking_terms_ignored():
    r = run("hdfc_netbanking_terms.txt")
    assert (r.status, r.parser_name) == ("ignored", "hdfc_netbanking_terms")


def test_hdfc_format_from_wrong_sender_not_parsed():
    assert run("hdfc_upi_debit.txt", sender=SBI).status == "unknown"
