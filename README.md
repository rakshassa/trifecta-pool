# trifecta-pool
Pool League automation

## Running Locally
- Create a subdirectory named "private".  Add a file there named "local_config.py" with contents:
TWILIO_ACCOUNT_SID = "fake"
TWILIO_API_KEY = "fake"
TWILIO_API_KEY_SECRET = "fake"
TWILIO_MESSAGING_SERVICE_SID = "fake"

- Set DRY_RUN=1 to print the texts without sending them (no Twilio credentials needed when running fargorate_sms.py directly).
- Run local_env.py to setup the correct ENV vars and execute fargorate_sms.py

## Configuring target phone numbers/teams/leagues.
- Edit the DIVISIONS dict in fargorate_sms.py (one entry per division: name, team phones, tables).
- Choose the division with the DIVISION env var (`tuesday` default, or `sunday`).

## Payouts (manual)
- `python payouts.py` calculates payouts for "2026 Fall Tuesdays in Paradise": team payout by standings placement (PAYOUT_BY_PLACE), split between players by "Player Points". Prints a per-team breakdown, then a per-person total. Needs no Twilio credentials.

## Github Automation
- Uses a github workflow (cron is UTC, not adjusted for DST):
  - Tuesday league: every Tuesday 8:00 AM MST
  - Sunday league: every Saturday 12:00 PM MST (only texts if the next Sunday match is within 2 days)
  - Both leagues skip sending if the next match is more than 2 days away (see max_days_ahead)
- needs a small commit every 60 days else it gets cancelled
