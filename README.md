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
- Edit constants in fargorate_sms.py

## Github Automation
- Uses a github workflow every tuesday at noon MST (not adjusted for DST)
- needs a small commit every 60 days else it gets cancelled
