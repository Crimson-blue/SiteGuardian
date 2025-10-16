from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView
from sqlalchemy.orm import Session
from core.models import Website, BackupSnapshot, BackupFile
from core.diff import generate_html_diff
from pathlib import Path
import zipfile
import tempfile
import shutil

class DiffViewer(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Diff Viewer")

        # Make this a real window even if a parent is passed
        self.setWindowFlag(Qt.Window, True)
        # Ensure resources are freed when closed
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # Track temporary extraction directories so we can clean them up
        self._temp_dirs: list[Path] = []

        self.website_combo = QComboBox()
        self.snap_a_combo = QComboBox()
        self.snap_b_combo = QComboBox()
        self.page_combo = QComboBox()
        self.view = QWebEngineView()

        top = QHBoxLayout()
        top.addWidget(QLabel("Website:")); top.addWidget(self.website_combo)
        top.addWidget(QLabel("Snapshot A:")); top.addWidget(self.snap_a_combo)
        top.addWidget(QLabel("Snapshot B:")); top.addWidget(self.snap_b_combo)
        top.addWidget(QLabel("Page:")); top.addWidget(self.page_combo)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Load Pages")
        swap_btn = QPushButton("Swap A/B")
        export_btn = QPushButton("Export HTML...")
        open_ext_btn = QPushButton("Open in Browser")
        close_btn = QPushButton("Close")
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(swap_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(open_ext_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(btn_layout)
        layout.addWidget(self.view)

        self.website_combo.currentIndexChanged.connect(self._website_changed)
        self.snap_a_combo.currentIndexChanged.connect(self._snap_changed)
        self.snap_b_combo.currentIndexChanged.connect(self._snap_changed)
        self.page_combo.currentIndexChanged.connect(self._render_diff)
        refresh_btn.clicked.connect(self._populate_pages)
        swap_btn.clicked.connect(self._swap_snaps)
        export_btn.clicked.connect(self._export_html)
        open_ext_btn.clicked.connect(self._open_in_browser)
        close_btn.clicked.connect(self.close)

        self._populate_websites()
        self.resize(1000, 700)

    def closeEvent(self, event):
        # Cleanup any temporary extracted files
        for d in self._temp_dirs:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        self._temp_dirs.clear()
        super().closeEvent(event)

    def _populate_websites(self):
        self.website_combo.clear()
        websites = self.session.query(Website).order_by(Website.domain.asc()).all()
        for w in websites:
            self.website_combo.addItem(w.domain, w.id)
        self._website_changed()

    def _website_changed(self):
        self.snap_a_combo.clear(); self.snap_b_combo.clear(); self.page_combo.clear()
        website_id = self.website_combo.currentData()
        if not website_id:
            self.view.setHtml("<i>No website selected.</i>")
            return
        snaps = (self.session.query(BackupSnapshot)
                 .filter(BackupSnapshot.website_id == website_id)
                 .order_by(BackupSnapshot.created_at.desc())
                 .all())
        if not snaps:
            self.view.setHtml("<i>No snapshots for this website yet.</i>")
            return
        for s in snaps:
            label = f"{s.timestamp}{' (zip)' if s.compressed else ''}"
            self.snap_a_combo.addItem(label, s.id)
            self.snap_b_combo.addItem(label, s.id)
        self._populate_pages()

    def _populate_pages(self):
        self.page_combo.clear()
        a_id = self.snap_a_combo.currentData()
        b_id = self.snap_b_combo.currentData()
        if not a_id or not b_id:
            self.view.setHtml("<i>Select two snapshots to compare.</i>")
            return
        # Intersect pages present in both snapshots
        a_files = self.session.query(BackupFile).filter(
            BackupFile.snapshot_id == a_id,
            BackupFile.content_type.like("%html%")
        ).all()
        b_files = self.session.query(BackupFile).filter(
            BackupFile.snapshot_id == b_id,
            BackupFile.content_type.like("%html%")
        ).all()
        a_set = {f.rel_path for f in a_files}
        b_set = {f.rel_path for f in b_files}
        common = sorted(a_set.intersection(b_set))
        if not common:
            self.view.setHtml("<i>No common HTML pages between these snapshots.</i>")
            return
        for rel in common:
            self.page_combo.addItem(rel, rel)
        self._render_diff()

    def _ensure_file_path(self, snap: BackupSnapshot, rel: str) -> Path | None:
        """
        Return a local filesystem path for the requested file.
        - If snapshot folder exists: return path directly.
        - If snapshot is compressed (zip exists): extract only that file to a temp dir and return the extracted path.
        """
        candidate = Path(snap.path) / rel
        if candidate.exists():
            return candidate

        # Try zip file next to the original snapshot path
        zip_path = Path(snap.path).with_suffix(".zip")
        if zip_path.exists():
            rel_posix = Path(rel).as_posix()
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    # Quick membership test
                    names = set(zf.namelist())
                    if rel_posix not in names:
                        return None
                    tempdir = Path(tempfile.mkdtemp(prefix=f"siteguardian_diff_{snap.timestamp}_"))
                    self._temp_dirs.append(tempdir)
                    zf.extract(rel_posix, tempdir)
                    return tempdir / rel_posix
            except Exception:
                return None
        return None

    def _render_diff(self):
        a_id = self.snap_a_combo.currentData()
        b_id = self.snap_b_combo.currentData()
        rel = self.page_combo.currentData()
        if not (a_id and b_id and rel):
            self.view.setHtml("<i>Select snapshots and a page to diff.</i>")
            return

        a_snap = self.session.get(BackupSnapshot, a_id)
        b_snap = self.session.get(BackupSnapshot, b_id)

        a_path = self._ensure_file_path(a_snap, rel)
        b_path = self._ensure_file_path(b_snap, rel)

        if not a_path or not b_path or not a_path.exists() or not b_path.exists():
            self.view.setHtml("<i>One of the files is missing. If the snapshot is zipped, it will be extracted temporarily. Try again.</i>")
            return

        diff_html = generate_html_diff(a_path, b_path, title=f"{rel}")
        self.view.setHtml(diff_html)

    def _snap_changed(self):
        self._populate_pages()

    def _swap_snaps(self):
        # Swap current selection between A and B
        a_idx = self.snap_a_combo.currentIndex()
        b_idx = self.snap_b_combo.currentIndex()
        if a_idx != -1 and b_idx != -1:
            self.snap_a_combo.setCurrentIndex(b_idx)
            self.snap_b_combo.setCurrentIndex(a_idx)
            self._populate_pages()

    def _export_html(self):
        # Export the currently displayed diff HTML
        def _save(content: str):
            path, _ = QFileDialog.getSaveFileName(self, "Save Diff HTML", "diff.html", "HTML Files (*.html)")
            if path:
                Path(path).write_text(content or "", encoding="utf-8")
        self.view.page().toHtml(_save)

    def _open_in_browser(self):
        # Open the current diff in the system browser (writes a temp HTML file)
        def _open(content: str):
            if not content:
                return
            tmp_dir = Path(tempfile.mkdtemp(prefix="siteguardian_diffview_"))
            self._temp_dirs.append(tmp_dir)
            out = tmp_dir / "diff.html"
            out.write_text(content, encoding="utf-8")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        self.view.page().toHtml(_open)