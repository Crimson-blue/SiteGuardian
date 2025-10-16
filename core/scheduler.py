import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, time
from sqlalchemy.orm import Session
from core.models import Website
from core.backup_manager import BackupManager

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, session: Session):
        self.session = session
        self.scheduler = BackgroundScheduler()
        self.backup_mgr = BackupManager(session=self.session)

    def start(self):
        self.scheduler.start()
        self.load_jobs()

    def shutdown(self):
        self.scheduler.shutdown(wait=False)

    def load_jobs(self):
        # Clear any existing jobs and re-add from DB
        self.scheduler.remove_all_jobs()
        websites = self.session.query(Website).filter_by(active=True).all()
        for w in websites:
            self._add_job_for_website(w)

    def _add_job_for_website(self, w: Website):
        trigger = None
        if w.schedule_type.name == "interval":
            minutes = max(1, w.interval_minutes or 60)
            trigger = IntervalTrigger(minutes=minutes)
        elif w.schedule_type.name == "daily":
            hh, mm = (w.daily_time or "02:00").split(":")
            trigger = CronTrigger(hour=int(hh), minute=int(mm))
        elif w.schedule_type.name == "cron":
            cron_expr = w.cron_expression or "0 3 * * *"
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            return

        job = self.scheduler.add_job(
            func=self._run_backup_job,
            trigger=trigger,
            args=[w.id],
            id=f"backup_{w.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        w.job_id = job.id
        self.session.commit()
        logger.info(f"Scheduled {w.domain}: {w.schedule_type.name} -> job_id {job.id}")

    def _run_backup_job(self, website_id: int):
        try:
            self.backup_mgr.run_backup(website_id=website_id)
        except Exception as e:
            logger.exception(f"Scheduled backup failed for {website_id}: {e}")

    def reschedule(self, website_id: int):
        w = self.session.get(Website, website_id)
        if not w:
            return
        if w.job_id:
            try:
                self.scheduler.remove_job(w.job_id)
            except Exception:
                pass
        if w.active:
            self._add_job_for_website(w)

    def get_job_next_run(self, job_id: str | None):
        if not job_id:
            return None
        job = self.scheduler.get_job(job_id)
        return job.next_run_time if job else None