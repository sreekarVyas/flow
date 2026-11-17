"""Pure unit tests: no DB, no Gmail."""

import base64
from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.api.transactions import month_bounds
from app.gmail.client import html_to_text, parse_message
from app.ingest.poller import build_query
from app.ingest.store import account_name, resolve_ts
from app.ingest.survey import mask_digits, subject_shape
from app.parsers.base import EmailInput, IgnoreRule, ParsedTxn, classify, infer_kind

IST = ZoneInfo("Asia/Kolkata")
BANK = "alerts@hdfcbank.bank.in"


def txn(**kw) -> ParsedTxn:
    base = dict(
        institution="HDFC", account_type="bank", last4="1234", amount=Decimal("336.00"),
        direction="debit", txn_date=date(2026, 11, 5),
    )
    return ParsedTxn(**(base | kw))


class FakeParser:
    name = "fake"
    senders = (BANK,)

    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def parse(self, email):
        if self.exc:
            raise self.exc
        return self.result


OTP_RULE = IgnoreRule("otp", (BANK,), subject=__import__("re").compile("OTP"))


# ---------- classify ----------


def test_txn_parser_wins():
    r = classify(EmailInput(BANK, "OTP", "x"), [FakeParser(txn())], [OTP_RULE])
    assert r.status == "txn" and r.parser_name == "fake" and r.txn.amount == Decimal("336.00")


def test_ignore_rule():
    r = classify(EmailInput(BANK, "Your OTP", "use 1234"), [FakeParser(None)], [OTP_RULE])
    assert (r.status, r.parser_name) == ("ignored", "otp")


def test_ignore_rule_cannot_hide_money_movement():
    body = "Rs.500.00 has been debited from your account"
    r = classify(EmailInput(BANK, "Your OTP", body), [FakeParser(None)], [OTP_RULE])
    assert r.status == "unknown"


def test_unknown_and_parser_errors_recorded():
    r = classify(EmailInput(BANK, "hello", "x"), [FakeParser(exc=ValueError("bad amount"))], [OTP_RULE])
    assert r.status == "unknown" and "bad amount" in r.error


def test_parser_skipped_for_other_sender():
    r = classify(EmailInput("x@other.com", "s", "b"), [FakeParser(txn())], [])
    assert r.status == "unknown"


def test_parsed_txn_validation():
    with pytest.raises(ValueError):
        txn(last4="12")
    with pytest.raises(ValueError):
        txn(amount=Decimal("0"))


# ---------- kind ----------


@pytest.mark.parametrize(
    ("kw", "kind"),
    [
        ({"counterparty_name": "CRED CLUB", "vpa_or_merchant": "cred.club@axisb"}, "transfer"),
        ({"counterparty_name": "TEST SELF NAME", "vpa_or_merchant": "x@yescred"}, "transfer"),
        ({"counterparty_name": "SOME FRIEND", "vpa_or_merchant": "friend@yescred"}, "expense"),
        ({"counterparty_name": "GOOD FLIPPIN BURGERS"}, "expense"),
        ({"direction": "credit", "counterparty_name": "ACME SERVICES PVT LTD SALARY"}, "income"),
        ({"direction": "credit", "counterparty_name": "ACME SERVICES PVT LTD"}, "income"),
        ({"direction": "credit", "counterparty_name": "JASTI NIKHIL"}, None),
        ({"account_type": "credit_card", "institution": "SBI Card"}, "expense"),
        ({"account_type": "credit_card", "institution": "SBI Card", "direction": "credit"}, None),
    ],
)
def test_infer_kind(kw, kind):
    assert infer_kind(txn(**kw), self_names=["test self name"], salary_payers=["ACME SERVICES"]) == kind


def test_infer_kind_without_personal_config():
    assert infer_kind(txn(counterparty_name="TEST SELF NAME")) == "expense"


# ---------- ts / names / query / month ----------


def test_resolve_ts_uses_email_time_on_same_day():
    received = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)  # 13:30 IST
    assert resolve_ts(txn(), received, IST) == received


def test_resolve_ts_other_day_and_explicit_time():
    received = datetime(2026, 11, 6, 8, 0, tzinfo=UTC)
    assert resolve_ts(txn(), received, IST) == datetime(2026, 11, 5, 0, 0, tzinfo=IST)
    assert resolve_ts(txn(txn_time=time(21, 15)), received, IST) == datetime(2026, 11, 5, 21, 15, tzinfo=IST)


def test_account_name():
    assert account_name("HDFC", "bank", "1234") == "HDFC ••1234"
    assert account_name("HDFC", "credit_card", "9876") == "HDFC Card ••9876"
    assert account_name("SBI Card", "credit_card", "5678") == "SBI Card ••5678"


def test_build_query():
    after = datetime(2026, 10, 31, tzinfo=IST)
    q = build_query(["a@b.in", "c@d.com"], after)
    assert q == f"from:(a@b.in OR c@d.com) after:{int(after.timestamp())}"


def test_month_bounds_ist_and_december():
    s, e = month_bounds("2026-11")
    assert (s, e) == (datetime(2026, 11, 1, tzinfo=IST), datetime(2026, 12, 1, tzinfo=IST))
    assert month_bounds("2026-12")[1] == datetime(2027, 1, 1, tzinfo=IST)


def test_survey_helpers():
    assert mask_digits("ref 123456789012 a/c 1234") == "ref XXXXXXXX9012 a/c 1234"
    assert subject_shape("Rs.500 debited 05-11") == "Rs.### debited ##-##"


# ---------- MIME ----------


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_parse_message_prefers_html_and_extracts_fields():
    html = "<html><head><style>p{}</style></head><body><p>Rs.336.00 debited</p><p>  to VPA x@ybl </p></body></html>"
    msg = {
        "id": "m1", "threadId": "t1", "historyId": "99", "internalDate": "1762300800000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "HDFC Bank InstaAlerts <Alerts@HDFCBank.bank.in>"},
                {"name": "Subject", "value": "UPI txn"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("stub")}},
                {"mimeType": "text/html", "headers": [{"name": "Content-Type", "value": 'text/html; charset="UTF-8"'}],
                 "body": {"data": _b64(html)}},
            ],
        },
    }
    fe = parse_message(msg)
    assert fe.sender == "alerts@hdfcbank.bank.in"
    assert fe.subject == "UPI txn" and fe.history_id == 99
    assert fe.body_text == "Rs.336.00 debited\nto VPA x@ybl"
    assert fe.received_at == datetime.fromtimestamp(1762300800, tz=UTC)


def test_html_to_text_drops_blank_lines():
    assert html_to_text("<div>a</div>\n\n<div> <b>b</b> </div>") == "a\nb"
