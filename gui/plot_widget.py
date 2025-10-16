from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objects as go
import plotly.io as pio
from sqlalchemy.orm import Session
from core.models import Website, BackupSnapshot

class PlotWidget(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.view = QWebEngineView()
        self.label = QLabel("Backup size over time")
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.view)

    def update_for_website(self, website_id: int | None):
        if not website_id:
            self.view.setHtml("<h3>No website selected</h3>")
            return
        snaps = (self.session.query(BackupSnapshot)
                 .filter(BackupSnapshot.website_id == website_id)
                 .order_by(BackupSnapshot.created_at.asc())
                 .all())
        if not snaps:
            self.view.setHtml("<i>No snapshots yet.</i>")
            return
        x = [s.created_at for s in snaps]
        y = [s.total_size / 1024.0 for s in snaps]  # KB

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name="Size (KB)"))
        fig.update_layout(
            margin=dict(l=30, r=30, t=30, b=30),
            xaxis_title="Timestamp",
            yaxis_title="Size (KB)",
            template="plotly_white",
            height=250
        )
        html = pio.to_html(fig, include_plotlyjs="cdn", full_html=False)
        self.view.setHtml(html)