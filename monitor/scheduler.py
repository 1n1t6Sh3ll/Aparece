"""In-process scheduler, on only when MONITOR_ENABLED=1: daily crawl (03:00 UTC), weekly visibility (Mon 04:00 UTC).
For cron instead: python -m monitor crawl | visibility."""
import logging
import os

from monitor import crawl

log = logging.getLogger("monitor")
_sched = None


def start():
    global _sched
    if os.environ.get("MONITOR_ENABLED") != "1" or _sched:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    _sched = BackgroundScheduler(timezone="UTC")
    _sched.add_job(crawl.crawl_all, "cron", hour=3, id="daily_crawl", max_instances=1, coalesce=True)
    _sched.add_job(crawl.visibility_all, "cron", day_of_week="mon", hour=4, id="weekly_visibility",
                   max_instances=1, coalesce=True)
    _sched.start()
    log.info("monitor scheduler started")
    return _sched


def stop():
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None
