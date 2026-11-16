# trifecta-pool
Pool League automation

## Running Locally
- Create a subdirectory named "private".  Add a file there named "local_config.py" with contents:
TWILIO_ACCOUNT_SID = "fake"
TWILIO_API_KEY = "fake"
TWILIO_API_KEY_SECRET = "fake"
TWILIO_MESSAGING_SERVICE_SID = "fake"

- Run local_env.py to setup the correct ENV vars and execute fargorate_sms.py

## Configuring target phone numbers/teams/leagues.
- Edit the DIVISIONS dict in fargorate_sms.py (one entry per division: name, team phones, tables).
- Choose the division with the DIVISION env var (`tuesday` default, or `sunday`).

## Github Automation
- Uses a github workflow (cron is UTC, not adjusted for DST):
  - Tuesday league: every Tuesday 8:00 AM MST
  - Sunday league: every Saturday 8:00 PM MST (only texts if the next Sunday match is within 1 day)
- needs a small commit every 60 days else it gets cancelled
