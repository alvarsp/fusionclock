#!/usr/bin/env bash
set -e

echo ""
echo "=== fusionclock setup ==="
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv…"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q
playwright install chromium -q
echo "Dependencies ready."

# ── 2. .env ───────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  read -rp "Your Oracle Fusion URL (e.g. https://xyz.fa.em2.oraclecloud.com): " oracle_url
  sed -i.bak "s|ORACLE_URL=.*|ORACLE_URL=${oracle_url}|" .env && rm .env.bak

  # Pre-fill the known values that are the same for everyone at OLX
  sed -i.bak "s|# TIME_NAV_URL=.*|TIME_NAV_URL=https://gzn.fa.em2.oraclecloud.com/hcmUI/faces/FuseWelcome|" .env && rm .env.bak
  sed -i.bak "s|# SSO_DOMAIN=.*|SSO_DOMAIN=olxgroup.okta-emea.com|" .env && rm .env.bak
fi

# ── 3. Session ────────────────────────────────────────────────────────────────
echo ""
echo "Opening Oracle Fusion in a browser. Approve the Okta push when prompted."
echo ""
python main.py setup

# ── 4. GitHub Actions ─────────────────────────────────────────────────────────
echo ""
read -rp "Your GitHub username (to fork alvarsp/fusionclock): " gh_user

if ! gh auth status &>/dev/null; then
  echo "Logging in to GitHub…"
  gh auth login
fi

# Fork if the user doesn't already own the repo
if ! gh repo view "${gh_user}/fusionclock" &>/dev/null; then
  echo "Forking repo…"
  gh repo fork alvarsp/fusionclock --clone=false
fi

REPO="${gh_user}/fusionclock"

source .env
gh secret set ORACLE_URL   --body "${ORACLE_URL}"   --repo "$REPO"
gh secret set TIME_NAV_URL --body "${TIME_NAV_URL}" --repo "$REPO"
gh secret set SSO_DOMAIN   --body "${SSO_DOMAIN}"   --repo "$REPO"
base64 -i ~/.oracle-clock/session.json | gh secret set SESSION_JSON --repo "$REPO"

echo ""
echo "All done! Your workflow is live at:"
echo "  https://github.com/${REPO}/actions"
echo ""
echo "Clock-in:  weekdays 09:00–09:15 CEST"
echo "Clock-out: weekdays 17:45–18:00 CEST"
echo ""
echo "When your Okta session expires (weeks/months), re-run:"
echo "  python main.py setup"
echo "  base64 -i ~/.oracle-clock/session.json | gh secret set SESSION_JSON --repo ${REPO}"
