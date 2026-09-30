"""Cron entry point: python -m monitor crawl | visibility"""
import json
import logging
import sys

from monitor import crawl

logging.basicConfig(level=logging.INFO)
jobs = {"crawl": crawl.crawl_all, "visibility": crawl.visibility_all}
if len(sys.argv) != 2 or sys.argv[1] not in jobs:
    sys.exit("usage: python -m monitor crawl|visibility")
print(json.dumps(jobs[sys.argv[1]](), default=str))
