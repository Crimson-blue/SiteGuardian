import logging
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
from sqlalchemy.orm import Session
from datetime import datetime

from core.models import Website, BackupSnapshot, BackupFile
from core.crawler import crawl_website
from core.utils import domain_from_url, timestamp_str
from config.settings import settings
from core.notifier import Notifier

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, session: Session):
        self.session = session
        self.notifier = Notifier()

    def _snapshot_dir(self, domain: str, ts: str) -> Path:
        return Path(settings.BACKUP_ROOT) / domain / ts

    def run_backup(self, website_id: int, progress_cb=None) -> BackupSnapshot | None:
        website = self.session.get(Website, website_id)
        if not website or not website.active:
            return None

        domain = website.domain
        ts = timestamp_str()
        snap_dir = self._snapshot_dir(domain, ts)
        snap_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting backup: {website.url} -> {snap_dir}")
        total_size = 0
        try:
            files_meta, url_map = crawl_website(
                base_url=website.url,
                dest_root=snap_dir,
                depth=website.crawl_depth,
                include_assets={"images": website.include_images, "css": website.include_css, "js": website.include_js},
                max_workers=website.max_workers or settings.MAX_WORKERS,
                progress_cb=progress_cb
            )

            # Save metadata
            meta = {
                "website": website.url,
                "domain": domain,
                "timestamp": ts,
                "files": files_meta,
            }
            meta_path = snap_dir / "metadata.json"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

            for f in files_meta:
                total_size += f["size"]

            # Create DB snapshot
            snapshot = BackupSnapshot(
                website_id=website.id, timestamp=ts, path=str(snap_dir), file_count=len(files_meta),
                total_size=total_size, compressed=False
            )
            self.session.add(snapshot)
            self.session.flush()

            # Add files entries
            bf_objs = [
                BackupFile(
                    snapshot_id=snapshot.id, url=f["url"], rel_path=f["rel_path"], size=f["size"],
                    sha256=f.get("sha256"), content_type=f.get("content_type")
                )
                for f in files_meta
            ]
            self.session.add_all(bf_objs)
            self.session.commit()

            website.last_run_at = datetime.utcnow()
            website.last_status = f"OK ({len(files_meta)} files, {total_size} bytes)"
            self.session.commit()
            logger.info(f"Backup complete: {website.url} ({len(files_meta)} files, {total_size} bytes)")

            # Enforce retention
            self.enforce_retention(website)

            # Notify
            self.notifier.desktop("SiteGuardian", f"Backup complete: {website.domain}")
            if website.email_notify:
                self.notifier.email(
                    subject=f"SiteGuardian backup complete: {website.domain}",
                    body=f"Completed at {website.last_run_at}.\nFiles: {len(files_meta)}\nSize: {total_size} bytes",
                    to_addr=website.email_to
                )
            return snapshot

        except Exception as e:
            website.last_status = f"ERROR: {e}"
            self.session.commit()
            logger.exception(f"Backup failed for {website.url}: {e}")
            self.notifier.desktop("SiteGuardian - Backup Failed", f"{website.domain}: {e}")
            if website.email_notify:
                self.notifier.email(
                    subject=f"SiteGuardian backup FAILED: {website.domain}",
                    body=f"Error: {e}",
                    to_addr=website.email_to
                )
            return None

    def enforce_retention(self, website: Website):
        """
        - Compress older snapshots (except most recent 2) if compress_old=True
        - Retain only last retention_limit snapshots (zipped or unzipped), delete older
        """
        snaps = list(sorted(website.snapshots, key=lambda s: s.created_at, reverse=True))
        if not snaps:
            return

        # Compress older snapshots except most recent 2
        if website.compress_old:
            for s in snaps[2:]:
                if not s.compressed:
                    self._zip_snapshot(Path(s.path))
                    s.compressed = True
                    self.session.commit()
                    logger.info(f"Compressed snapshot {s.timestamp} for {website.domain}")

        # Prune beyond retention limit
        limit = max(1, website.retention_limit or 10)
        for s in snaps[limit:]:
            self._delete_snapshot(s)

    def _zip_snapshot(self, snap_dir: Path):
        zip_path = snap_dir.with_suffix(".zip")
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
            for p in snap_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=p.relative_to(snap_dir))
        # remove original directory
        for p in sorted(snap_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            else:
                try:
                    p.rmdir()
                except Exception:
                    pass
        snap_dir.rmdir()

    def _delete_snapshot(self, snapshot: BackupSnapshot):
        path = Path(snapshot.path)
        zip_path = path.with_suffix(".zip")
        try:
            if path.exists():
                for p in sorted(path.rglob("*"), reverse=True):
                    if p.is_file():
                        p.unlink(missing_ok=True)
                    else:
                        try:
                            p.rmdir()
                        except Exception:
                            pass
                path.rmdir()
            if zip_path.exists():
                zip_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Failed to delete snapshot {snapshot.id}: {e}")
        self.session.delete(snapshot)
        self.session.commit()
        logger.info(f"Deleted snapshot {snapshot.timestamp}")