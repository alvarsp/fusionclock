import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from config import Config
from notify import Notifier

logger = logging.getLogger(__name__)

# How long to wait for the user to complete SSO login during `setup` (3 min)
SETUP_TIMEOUT_MS = 180_000


class OracleClock:
    def __init__(self, config: Config):
        self.config = config
        self.notifier = Notifier(config)

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------

    def setup(self):
        """
        Export a portable session from an existing Chrome profile or by
        opening a headed browser for manual SSO login.
        """
        profile = self.config.chrome_profile_dir

        if profile and Path(profile).exists():
            print(f"Loading existing Chrome profile: {profile}")
            self._export_from_profile(profile)
        else:
            print("No CHROME_PROFILE_DIR set — opening a headed browser for manual login.")
            self._interactive_login()

    def clock_in(self, no_delay: bool = False):
        delay = self._random_delay(
            self.config.checkin_delay_min,
            self.config.checkin_delay_max,
            skip=no_delay,
        )
        if delay:
            logger.info("Clock-in: waiting %dm %ds", delay // 60, delay % 60)
            time.sleep(delay)
        self._perform_action("clock-in")

    def clock_out(self, no_delay: bool = False):
        delay = self._random_delay(
            self.config.checkout_delay_min,
            self.config.checkout_delay_max,
            skip=no_delay,
        )
        if delay:
            logger.info("Clock-out: waiting %dm %ds", delay // 60, delay % 60)
            time.sleep(delay)
        self._perform_action("clock-out")

    def discover(self):
        """Open the HCM home page and capture the URL after you click Web Clock."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(
                storage_state=self.config.session_file,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.goto(self.config.time_nav_url or self.config.oracle_url)
            page.wait_for_load_state("networkidle", timeout=self.config.timeout_ms)

            print("\nBrowser is open. Click the 'Web Clock' tile now.")
            print("Waiting for navigation…\n")

            start_url = page.url
            # Wait until the URL changes from the current page
            page.wait_for_function(
                f"() => window.location.href !== {repr(start_url)}",
                timeout=60_000,
            )
            page.wait_for_load_state("networkidle", timeout=15_000)

            # Strip dynamic ADF state params — keep only the stable base path
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(page.url)
            clean = urlunparse(parsed._replace(query="", fragment=""))

            print(f"Detected URL: {page.url}")
            print(f"\nAdd this to your .env:\n  TIME_NAV_URL={clean}\n")
            ctx.close()
            browser.close()

    def status(self):
        if self._session_valid():
            print("Session is valid.")
        else:
            print("Session has expired. Run 'setup' to re-authenticate.")

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _export_from_profile(self, profile_dir: str):
        """
        Launch Chromium with the existing Chrome user-data-dir, navigate to
        the HCM clock page, complete any SSO flow, then export the session.
        """
        # Navigate to the actual clock page so the HCM SAML session is established.
        target = self.config.time_nav_url or self.config.oracle_url

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                args=["--profile-directory=Default"],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            try:
                print(f"Navigating to {target}")
                page.goto(target, timeout=self.config.timeout_ms)
                page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)

                if self._is_login_page(page):
                    print(
                        "\nBrowser redirected to Okta — please approve the push "
                        "notification on your phone.\n"
                        "The script will continue automatically once you're in."
                    )
                    self._wait_for_login(page)
                else:
                    print("Session still valid — no login needed.")

                ctx.storage_state(path=self.config.session_file)
                print(f"\nSession saved → {self.config.session_file}")
                print("Setup complete. Deploy session.json to your remote server.")
            finally:
                ctx.close()

    def _interactive_login(self):
        """Open a headed browser and wait for the user to complete SSO."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()

            print(f"Navigating to {self.config.oracle_url}")
            print("Complete the SSO + MFA flow, then wait for Oracle Fusion to load.")
            page.goto(self.config.oracle_url, timeout=self.config.timeout_ms)

            try:
                self._wait_for_login(page)
                ctx.storage_state(path=self.config.session_file)
                print(f"Session saved → {self.config.session_file}")
            finally:
                browser.close()

    def _wait_for_login(self, page):
        oracle_domain = _domain(self.config.oracle_url)
        sso = self.config.sso_domain

        # Wait until the browser is back on the Oracle domain AND no longer
        # on the SSO provider's domain. Oracle's own /sso paths are fine.
        conditions = [f"window.location.href.includes('{oracle_domain}')"]
        if sso:
            conditions.append(f"!window.location.href.includes('{sso}')")

        logger.info("Waiting for Oracle Fusion to load (up to 3 min)…")
        page.wait_for_function(
            "() => " + " && ".join(conditions),
            timeout=SETUP_TIMEOUT_MS,
        )
        page.wait_for_load_state("networkidle", timeout=30_000)
        print("Login detected.")

    # ------------------------------------------------------------------
    # Core clock action
    # ------------------------------------------------------------------

    def _perform_action(self, action: str):
        if not Path(self.config.session_file).exists():
            msg = "No session.json found. Run 'setup' first."
            logger.error(msg)
            self.notifier.send(f"Oracle Clock ERROR: {msg}")
            sys.exit(1)

        selector = (
            self.config.clock_in_selector
            if action == "clock-in"
            else self.config.clock_out_selector
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.config.headless)
            ctx = browser.new_context(
                storage_state=self.config.session_file,
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()

            try:
                target = self.config.time_nav_url or self.config.oracle_url
                logger.info("Navigating to %s", target)
                page.goto(target, timeout=self.config.timeout_ms)
                page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)

                if self._is_login_page(page):
                    msg = (
                        "Oracle Fusion session expired. "
                        "Re-run 'setup' on your Mac to refresh the session."
                    )
                    logger.warning(msg)
                    self._screenshot(page, f"{action}-session-expired")
                    self.notifier.send(f"Oracle Clock ACTION NEEDED: {msg}")
                    return

                # Refresh the persisted session so it stays warm
                ctx.storage_state(path=self.config.session_file)

                self._click_clock_button(page, action, selector)

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg = f"{'Clocked in' if action == 'clock-in' else 'Clocked out'} at {ts}"
                logger.info(msg)
                self._screenshot(page, f"{action}-success")
                self.notifier.send(f"Oracle Clock: {msg}")

            except PWTimeout as exc:
                msg = f"Timeout during {action}: {exc}"
                logger.error(msg)
                self._screenshot(page, f"{action}-timeout")
                self.notifier.send(f"Oracle Clock ERROR: {msg}")
                sys.exit(1)
            except Exception as exc:
                msg = f"Error during {action}: {exc}"
                logger.error(msg)
                self._screenshot(page, f"{action}-error")
                self.notifier.send(f"Oracle Clock ERROR: {msg}")
                sys.exit(1)
            finally:
                ctx.close()
                browser.close()

    def _click_clock_button(self, page, action: str, selector: str):
        # Web Clock is a panel inside FuseWelcome — always open the tile first.
        self._open_web_clock_tile(page)

        logger.info("Looking for button: %s", selector)

        text = selector[5:] if selector.startswith("text=") else selector
        # Wait for the Clock In/Out button to appear inside the panel
        btn = page.get_by_role("button", name=text, exact=False).first

        try:
            btn.wait_for(state="visible", timeout=self.config.timeout_ms)
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            self._screenshot(page, f"button-not-found-{action}")
            raise RuntimeError(
                f"Button '{selector}' not found after opening Web Clock panel. "
                f"Screenshot saved to {self.config.screenshot_dir}."
            )

    def _open_web_clock_tile(self, page):
        """Click the Web Clock tile using a JS dispatch so Oracle ADF registers it."""
        logger.info("Opening Web Clock tile…")

        # Use JS to find the nearest clickable ancestor of the 'Web Clock' text node.
        clicked = page.evaluate("""() => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT
            );
            let node;
            while ((node = walker.nextNode())) {
                if (node.nodeValue && node.nodeValue.trim() === 'Web Clock') {
                    const el = node.parentElement.closest(
                        'a, button, [role="link"], [role="button"], [onclick]'
                    ) || node.parentElement;
                    el.dispatchEvent(
                        new MouseEvent('click', {bubbles: true, cancelable: true})
                    );
                    return true;
                }
            }
            return false;
        }""")

        if not clicked:
            logger.warning("Web Clock tile not found via JS; proceeding anyway.")
            return

        logger.info("Web Clock tile clicked.")
        # The panel opens asynchronously — wait for the Clock In/Out button to appear
        # rather than waiting for networkidle (which may never fire for a panel).
        try:
            clock_text = (
                self.config.clock_in_selector[5:]
                if self.config.clock_in_selector.startswith("text=")
                else self.config.clock_in_selector
            )
            page.get_by_role("button", name=clock_text, exact=False).first.wait_for(
                state="visible", timeout=15_000
            )
        except PWTimeout:
            # Button might already have different text (e.g. already clocked in → shows Clock Out)
            pass

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _session_valid(self) -> bool:
        if not Path(self.config.session_file).exists():
            return False
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=self.config.session_file)
            page = ctx.new_page()
            try:
                page.goto(self.config.oracle_url, timeout=self.config.timeout_ms)
                page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)
                return not self._is_login_page(page)
            except Exception:
                return False
            finally:
                ctx.close()
                browser.close()

    def _is_login_page(self, page) -> bool:
        url = page.url.lower()
        oracle_domain = _domain(self.config.oracle_url).lower()

        # Only consider it a login page if the browser left the Oracle domain entirely.
        # Oracle itself uses /sso and /auth paths during normal authenticated navigation,
        # so we must not key off those path fragments.
        if oracle_domain not in url:
            logger.info("Session check: left Oracle domain → %s", page.url)
            return True

        # Belt-and-suspenders: if we're still on Oracle's domain but the page title
        # looks like a login screen, something went wrong.
        try:
            title = page.title().lower()
            if any(w in title for w in ["sign in", "log in", "login"]):
                logger.info("Session check: login title detected → %s", title)
                return True
        except Exception:
            pass

        return False

    def _screenshot(self, page, label: str):
        try:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self.config.screenshot_dir / f"{ts}-{label}.png"
            page.screenshot(path=str(path))
            logger.info("Screenshot: %s", path)
        except Exception as exc:
            logger.warning("Could not save screenshot: %s", exc)

    @staticmethod
    def _random_delay(min_min: int, max_min: int, skip: bool = False) -> int:
        if skip or max_min == 0:
            return 0
        return random.randint(min_min * 60, max_min * 60)


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc
