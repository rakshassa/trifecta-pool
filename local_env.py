"""
Set local environment variables and run the Twilio SMS test.

Works on Windows and Ubuntu/Linux.

The private/ directory should be excluded from Git.
"""

import os
import subprocess
import sys

from private import local_config


# ---------------------------------------------------------------------------
# Set environment variables
# ---------------------------------------------------------------------------

os.environ["TWILIO_ACCOUNT_SID"] = local_config.TWILIO_ACCOUNT_SID
os.environ["TWILIO_API_KEY"] = local_config.TWILIO_API_KEY
os.environ["TWILIO_API_KEY_SECRET"] = local_config.TWILIO_API_KEY_SECRET
os.environ["TWILIO_MESSAGING_SERVICE_SID"] = (
    local_config.TWILIO_MESSAGING_SERVICE_SID
)


# ---------------------------------------------------------------------------
# Run the test script
# ---------------------------------------------------------------------------

subprocess.run(
    [sys.executable, "fargorate_sms.py"],
    check=True,
)
