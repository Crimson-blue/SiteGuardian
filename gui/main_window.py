import logging
import os
import sys
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QSplitter, QPlainTextEdit, QLabel, QMessageBox
)
from sqlalchemy.orm import Session

from config.settings import settings
from core.models import Website, BackupSnapshot
from core.backup_manager import BackupManager
from gui.add_edit_dialog import AddEditWebsiteDialog
from gui.plot_widget import PlotWidget
from gui.diff_viewer import DiffViewer

logger = logging.getLogger(__name__)

class BackupWorker(QThread):
    progressed = Signal(str, str, int)  # url, type, count
    finished_ok = Signal(int)           # website_id
    finished_err = Signal(int, str)

    def __init__(self, backup_mgr: BackupManager, website_id: int):
        super().__init__()
        self.backup_mgr = backup_mgr
        self.website_id = website_id

    def run(self):
        try:
            def cb(url, kind, count):
                self.progressed.emit(url, kind, count)
            snap = self.backup_mgr.run_backup(self.website_id, progress_cb=cb)
            if snap:
                self.finished_ok.emit(self.website_id)
            else:
                self.finished_err.emit(self.website_id, "Unknown error")
        except Exception as e:
            self.finished_err.emit(self.website_id, str(e))

class MainWindow(QMainWindow):
    def __init__(self, session: Session, scheduler_service, qt_log_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SiteGuardian")
        self.session = session
        self.scheduler_service = scheduler_service
        self.backup_mgr = BackupManager(session=self.session)
        self.qt_log_handler = qt_log_handler

        # Track child windows/threads
        self._diff_viewer = None
        self._workers: list[BackupWorker] = []

        # UI components
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Domain", "URL", "Schedule", "Next Run", "Last Run", "Last Status", "Snapshots"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.run_btn = QPushButton("Run Now")
        self.diff_btn = QPushButton("Diff Viewer")
        self.open_btn = QPushButton("Open Backups...")
        self.refresh_btn = QPushButton("Refresh")

        top_bar = QHBoxLayout()
        for b in [self.add_btn, self.edit_btn, self.delete_btn, self.run_btn, self.diff_btn, self.open_btn, self.refresh_btn]:
            top_bar.addWidget(b)
        top_bar.addStretch()

        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        self.status_label = QLabel("Ready")
        self.progress_label = QLabel("")
        log_layout = QVBoxLayout(); log_layout.addWidget(QLabel("Logs")); log_layout.addWidget(self.log_view)

        self.plot = PlotWidget(session=self.session)

        left = QWidget(); left_l = QVBoxLayout(left); left_l.addLayout(top_bar); left_l.addWidget(self.table); left_l.addWidget(self.progress_label)
        right = QWidget(); right_l = QVBoxLayout(right); right_l.addWidget(self.plot); right_l.addLayout(log_layout)

        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)
        container = QWidget(); layout = QVBoxLayout(container); layout.addWidget(splitter); layout.addWidget(self.status_label)
        self.setCentralWidget(container)

        # Connections
        self.add_btn.clicked.connect(self.add_site)
        self.edit_btn.clicked.connect(self.edit_site)
        self.delete_btn.clicked.connect(self.delete_site)
        self.run_btn.clicked.connect(self.run_now)
        self.diff_btn.clicked.connect(self.open_diff)
        self.open_btn.clicked.connect(self.open_backups_dir)
        self.refresh_btn.clicked.connect(self.refresh_table)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.qt_log_handler.log_signal.connect(self._append_log)

        # Refresh timer
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_table); self.timer.start(3000)
        self.refresh_table()

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def add_site(self):
        dlg = AddEditWebsiteDialog(session=self.session, website=None, parent=self)
        if dlg.exec():
            self.scheduler_service.load_jobs()
            self.refresh_table()

    def edit_site(self):
        w = self._current_website()
        if not w:
            return
        dlg = AddEditWebsiteDialog(session=self.session, website=w, parent=self)
        if dlg.exec():
            self.scheduler_service.reschedule(w.id)
            self.refresh_table()

    def delete_site(self):
        w = self._current_website()
        if not w:
            return
        if QMessageBox.question(self, "Confirm", f"Delete {w.domain}? This does not delete backup files.") == QMessageBox.Yes:
            # Unschedule
            if w.job_id:
                try:
                    self.scheduler_service.scheduler.remove_job(w.job_id)
                except Exception:
                    pass
            self.session.delete(w)
            self.session.commit()
            self.refresh_table()

    def run_now(self):
        w = self._current_website()
        if not w:
            return
        self.status_label.setText(f"Running backup for {w.domain}...")
        worker = BackupWorker(backup_mgr=self.backup_mgr, website_id=w.id)
        worker.progressed.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished_ok)
        worker.finished_err.connect(self._on_finished_err)
        # Cleanup when done
        worker.finished_ok.connect(lambda _: self._cleanup_worker(worker))
        worker.finished_err.connect(lambda *_: self._cleanup_worker(worker))
        worker.start()
        # Keep reference to avoid GC
        self._workers.append(worker)

    def _cleanup_worker(self, worker: BackupWorker):
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def open_diff(self):
        # Open Diff Viewer as a separate top-level window (closable)
        if self._diff_viewer and self._diff_viewer.isVisible():
            self._diff_viewer.raise_()
            self._diff_viewer.activateWindow()
            return
        viewer = DiffViewer(session=self.session)  # no parent => real window with titlebar
        viewer.setAttribute(Qt.WA_DeleteOnClose, True)
        viewer.resize(1000, 700)
        viewer.show()
        self._diff_viewer = viewer
        viewer.destroyed.connect(lambda: setattr(self, "_diff_viewer", None))

    def open_backups_dir(self):
        w = self._current_website()
        if not w:
            return
        path = Path(settings.BACKUP_ROOT) / w.domain
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("darwin"):
            subprocess.call(["open", str(path)])
        elif os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.call(["xdg-open", str(path)])

    def _current_website(self) -> Website | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        ridx = rows[0].row()
        w_id = self.table.item(ridx, 0).data(Qt.UserRole)
        return self.session.get(Website, int(w_id)) if w_id else None

    def refresh_table(self):
        websites = self.session.query(Website).order_by(Website.created_at.desc()).all()
        self.table.setRowCount(len(websites))
        for i, w in enumerate(websites):
            next_run = self.scheduler_service.get_job_next_run(w.job_id)
            next_run_str = next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "-"
            last_run_str = w.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if w.last_run_at else "-"
            schedule_str = self._schedule_str(w)
            snapshots_count = self.session.query(BackupSnapshot).filter(BackupSnapshot.website_id == w.id).count()

            items = [
                QTableWidgetItem(w.domain),
                QTableWidgetItem(w.url),
                QTableWidgetItem(schedule_str),
                QTableWidgetItem(next_run_str),
                QTableWidgetItem(last_run_str),
                QTableWidgetItem(w.last_status or "-"),
                QTableWidgetItem(str(snapshots_count)),
            ]
            for col, item in enumerate(items):
                if col == 0:
                    item.setData(Qt.UserRole, w.id)
                self.table.setItem(i, col, item)
        self._selection_changed()

    def _selection_changed(self):
        w = self._current_website()
        self.plot.update_for_website(w.id if w else None)

    def _schedule_str(self, w: Website) -> str:
        if w.schedule_type.name == "interval":
            return f"Every {w.interval_minutes} min"
        elif w.schedule_type.name == "daily":
            return f"Daily at {w.daily_time}"
        else:
            return f"Cron: {w.cron_expression}"

    def _on_progress(self, url: str, kind: str, count: int):
        self.progress_label.setText(f"Fetched {count} items... last: {url}")

    def _on_finished_ok(self, website_id: int):
        w = self.session.get(Website, website_id)
        self.status_label.setText(f"Backup completed: {w.domain}")
        self.refresh_table()

    def _on_finished_err(self, website_id: int, err: str):
        w = self.session.get(Website, website_id)
        self.status_label.setText(f"Backup failed: {w.domain}: {err}")
        self.refresh_table()