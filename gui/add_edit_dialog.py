from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QPushButton, QMessageBox
)
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from core.models import Website, ScheduleType
from core.utils import domain_from_url

class AddEditWebsiteDialog(QDialog):
    def __init__(self, session: Session, website: Website | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Website")
        self.session = session
        self.website = website

        self.url_edit = QLineEdit()
        self.depth_spin = QSpinBox(); self.depth_spin.setRange(0, 5); self.depth_spin.setValue(1)
        self.images_chk = QCheckBox("Include images"); self.images_chk.setChecked(True)
        self.css_chk = QCheckBox("Include CSS"); self.css_chk.setChecked(True)
        self.js_chk = QCheckBox("Include JS"); self.js_chk.setChecked(True)
        self.retention_spin = QSpinBox(); self.retention_spin.setRange(1, 1000); self.retention_spin.setValue(10)
        self.compress_chk = QCheckBox("Compress older versions"); self.compress_chk.setChecked(True)
        self.max_workers_spin = QSpinBox(); self.max_workers_spin.setRange(1, 64); self.max_workers_spin.setValue(8)

        self.schedule_combo = QComboBox()
        self.schedule_combo.addItems(["interval", "daily", "cron"])
        self.interval_spin = QSpinBox(); self.interval_spin.setRange(1, 1440); self.interval_spin.setValue(60)
        self.daily_time_edit = QLineEdit(); self.daily_time_edit.setPlaceholderText("HH:MM")
        self.cron_edit = QLineEdit(); self.cron_edit.setPlaceholderText("e.g. 0 3 * * *")

        self.email_chk = QCheckBox("Email notify on completion")
        self.email_to_edit = QLineEdit(); self.email_to_edit.setPlaceholderText("recipient@example.com")

        form = QFormLayout()
        form.addRow("Website URL:", self.url_edit)
        form.addRow("Crawl depth:", self.depth_spin)
        form.addRow("", self.images_chk)
        form.addRow("", self.css_chk)
        form.addRow("", self.js_chk)
        form.addRow("Retention (snapshots):", self.retention_spin)
        form.addRow("", self.compress_chk)
        form.addRow("Max workers:", self.max_workers_spin)
        form.addRow("Schedule type:", self.schedule_combo)
        form.addRow("Interval (minutes):", self.interval_spin)
        form.addRow("Daily time:", self.daily_time_edit)
        form.addRow("Cron expr:", self.cron_edit)
        form.addRow("", self.email_chk)
        form.addRow("Email to:", self.email_to_edit)

        btns = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.save_btn)
        btns.addWidget(self.cancel_btn)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(btns)

        self.save_btn.clicked.connect(self.save)
        self.cancel_btn.clicked.connect(self.reject)
        self.schedule_combo.currentTextChanged.connect(self._schedule_changed)
        self._schedule_changed(self.schedule_combo.currentText())

        if website:
            self._load(website)

    def _schedule_changed(self, t: str):
        self.interval_spin.setEnabled(t == "interval")
        self.daily_time_edit.setEnabled(t == "daily")
        self.cron_edit.setEnabled(t == "cron")

    def _load(self, w: Website):
        self.url_edit.setText(w.url)
        self.depth_spin.setValue(w.crawl_depth)
        self.images_chk.setChecked(w.include_images)
        self.css_chk.setChecked(w.include_css)
        self.js_chk.setChecked(w.include_js)
        self.retention_spin.setValue(w.retention_limit)
        self.compress_chk.setChecked(w.compress_old)
        self.max_workers_spin.setValue(w.max_workers or 8)
        self.schedule_combo.setCurrentText(w.schedule_type.value)
        self.interval_spin.setValue(w.interval_minutes or 60)
        self.daily_time_edit.setText(w.daily_time or "")
        self.cron_edit.setText(w.cron_expression or "")
        self.email_chk.setChecked(w.email_notify)
        self.email_to_edit.setText(w.email_to or "")

    def save(self):
        url = self.url_edit.text().strip()
        if not url or not urlparse(url).scheme:
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL, e.g., https://example.com")
            return

        domain = domain_from_url(url)
        if self.website is None:
            w = Website(url=url, domain=domain)
            self.session.add(w)
        else:
            w = self.website
            w.url = url
            w.domain = domain

        w.crawl_depth = self.depth_spin.value()
        w.include_images = self.images_chk.isChecked()
        w.include_css = self.css_chk.isChecked()
        w.include_js = self.js_chk.isChecked()
        w.retention_limit = self.retention_spin.value()
        w.compress_old = self.compress_chk.isChecked()
        w.max_workers = self.max_workers_spin.value()
        stype = self.schedule_combo.currentText()
        w.schedule_type = getattr(ScheduleType, stype)
        w.interval_minutes = self.interval_spin.value() if stype == "interval" else None
        w.daily_time = self.daily_time_edit.text().strip() if stype == "daily" else None
        w.cron_expression = self.cron_edit.text().strip() if stype == "cron" else None
        w.email_notify = self.email_chk.isChecked()
        w.email_to = self.email_to_edit.text().strip() or None
        self.session.commit()
        self.accept()