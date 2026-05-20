import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.oracle_url = os.getenv("ORACLE_URL", "")
        if not self.oracle_url:
            raise ValueError("ORACLE_URL is required in .env")

        self.oracle_url = self.oracle_url.rstrip("/")

        home = Path.home()
        data_dir = Path(os.getenv("DATA_DIR", str(home / ".oracle-clock")))
        data_dir.mkdir(parents=True, exist_ok=True)

        self.session_file = str(data_dir / "session.json")
        self.screenshot_dir = data_dir / "screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)
        self.log_file = str(data_dir / "clock.log")

        # Optional direct URL to the time/clock page — much faster than navigating
        self.time_nav_url = os.getenv("TIME_NAV_URL", "").rstrip("/")

        # SSO domain hint for detecting session expiry (e.g. "okta.com")
        self.sso_domain = os.getenv("SSO_DOMAIN", "")

        # Button selectors — override if the defaults don't match your Oracle instance
        self.clock_in_selector = os.getenv("CLOCK_IN_SELECTOR", "text=Clock In")
        self.clock_out_selector = os.getenv("CLOCK_OUT_SELECTOR", "text=Clock Out")

        # Randomized delay windows (minutes)
        self.checkin_delay_min = int(os.getenv("CHECKIN_DELAY_MIN", "0"))
        self.checkin_delay_max = int(os.getenv("CHECKIN_DELAY_MAX", "15"))
        self.checkout_delay_min = int(os.getenv("CHECKOUT_DELAY_MIN", "0"))
        self.checkout_delay_max = int(os.getenv("CHECKOUT_DELAY_MAX", "15"))

        # Notification webhook (Slack, Discord, or any POST endpoint)
        self.notify_webhook = os.getenv("NOTIFY_WEBHOOK_URL", "")

        self.headless = os.getenv("HEADLESS", "true").lower() == "true"
        self.timeout_ms = int(os.getenv("TIMEOUT_MS", "30000"))

        # Path to an existing Chrome user-data-dir (used by the `setup` command)
        self.chrome_profile_dir = os.getenv("CHROME_PROFILE_DIR", "")
