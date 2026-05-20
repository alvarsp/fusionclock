# oracle-clock

Automatic weekday clock-in / clock-out for Oracle Fusion HCM.

## How it works

1. **`setup`** (run once on your Mac) — exports your existing Oracle Fusion session
   from a Chrome profile into a portable `session.json` file.
2. **`clock-in` / `clock-out`** — restore that session headlessly, navigate to Oracle
   Fusion, and click the button. A randomized delay (0–15 min by default) is
   applied so the times look natural.
3. **Session expiry** — when Oracle / Okta eventually invalidates the session the
   script detects it, skips the action, and sends you a webhook notification to
   re-run `setup`.

## Local setup (Mac)

```bash
cd oracle-clock

# Create virtualenv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Playwright's Chromium browser
playwright install chromium

# Configure
cp .env.example .env
# Edit .env — set ORACLE_URL and CHROME_PROFILE_DIR at minimum

# Export your session (reuses your existing Chrome profile — no login needed)
python main.py setup
# → Creates ~/.oracle-clock/session.json
```

> If your Chrome profile is locked (Chrome is open), quit Chrome first, or set
> `CHROME_PROFILE_DIR` to the dedicated `chrome-fusion-cdp-profile` directory
> instead of your main profile.

## Test it locally

```bash
# Test without the random delay
python main.py clock-in  --no-delay
python main.py clock-out --no-delay

# Check session validity
python main.py status
```

## Deploy to a remote server

### 1. Copy files

```bash
# On the server, create the deploy directory
ssh user@server "mkdir -p /opt/oracle-clock/data"

# Copy the project and the session
rsync -av --exclude='.venv' --exclude='__pycache__' oracle-clock/ user@server:/opt/oracle-clock/
scp ~/.oracle-clock/session.json user@server:/opt/oracle-clock/data/session.json
```

### 2. Server-side setup (plain Python)

```bash
ssh user@server
cd /opt/oracle-clock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps   # installs system deps too
cp .env.example .env
# Edit .env: set ORACLE_URL, NOTIFY_WEBHOOK_URL, DATA_DIR=/opt/oracle-clock/data
# Leave HEADLESS=true and remove CHROME_PROFILE_DIR (not needed on server)
```

### 3. Schedule with cron

```bash
crontab -e
# Paste from crontab.example (Option A)
```

Make sure the server timezone matches your work timezone:

```bash
sudo timedatectl set-timezone Europe/Madrid
```

### Alternative: Docker

```bash
# On the server
docker build -t oracle-clock /opt/oracle-clock
# Then use Option B from crontab.example
```

## Refreshing the session

When the session expires you'll get a notification like:

> Oracle Clock ACTION NEEDED: session expired. Re-run 'setup' on your Mac.

1. On your Mac: `python main.py setup` (re-exports fresh cookies)
2. Copy the new `session.json` to the server:
   ```bash
   scp ~/.oracle-clock/session.json user@server:/opt/oracle-clock/data/session.json
   ```

## Tuning selectors

If the automation can't find the Clock In/Out button, check the screenshots in
`~/.oracle-clock/screenshots/` (or `/opt/oracle-clock/data/screenshots/` on the
server) to see what was on screen.

Then either:
- Set `TIME_NAV_URL` to the direct URL of your Oracle time-card page, or
- Override `CLOCK_IN_SELECTOR` / `CLOCK_OUT_SELECTOR` in `.env`

You can use browser DevTools to find the right selector, then test with:

```bash
HEADLESS=false python main.py clock-in --no-delay
```
