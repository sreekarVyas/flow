from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://flow:flow_local@127.0.0.1:5432/flow"

    # Only mail from these exact addresses is stored. Lower case.
    alert_senders: list[str] = ["alerts@hdfcbank.bank.in", "onlinesbicard@sbicard.com"]

    gmail_client_secret: Path = BACKEND_DIR / "secrets" / "client_secret.json"
    gmail_token: Path = BACKEND_DIR / "secrets" / "token.json"

    # First poll reads mail from this date (minus one day of margin).
    backfill_start: date = date(2026, 11, 1)
    poll_enabled: bool = True
    poll_interval_seconds: int = 600

    timezone: str = "Asia/Kolkata"

    # Personal patterns for kind rules. Set in .env (git-ignored), upper case, as banks print them.
    self_names: list[str] = []  # your own name: UPI debits to it are self-transfers
    salary_payers: list[str] = []  # employer names: credits from them are income

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
