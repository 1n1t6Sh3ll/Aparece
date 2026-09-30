"""Cron entry point for retries: python -m webhooks deliver"""
import json
import logging
import sys

from webhooks import core

logging.basicConfig(level=logging.INFO)
if sys.argv[1:] != ["deliver"]:
    sys.exit("usage: python -m webhooks deliver")
print(json.dumps(core.deliver_due()))
