import sys
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from config.settings import settings
from config.database import init_db, SessionLocal
from gui.main_window import MainWindow
from core.scheduler import SchedulerService
from gui.log_handler import QtLogHandler

def setup_dirs():
    Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.BACKUP_ROOT).mkdir(parents=True, exist_ok=True)
    Path(Path(settings.DB_PATH).parent).mkdir(parents=True, exist_ok=True)

def setup_logging():
    log_file = Path(settings.LOG_DIR) / "siteguardian.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
  
def main():
    load_dotenv(override=True)
    setup_dirs()
    setup_logging()
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)

    # GUI log handler bridge
    qt_log_handler = QtLogHandler()
    logging.getLogger().addHandler(qt_log_handler)

    session = SessionLocal()
    scheduler_service = SchedulerService(session=session)
    scheduler_service.start()

    window = MainWindow(session=session, scheduler_service=scheduler_service, qt_log_handler=qt_log_handler)
    window.resize(1200, 780)
    window.show()

    ret = app.exec()
    scheduler_service.shutdown()
    session.close()
    sys.exit(ret)

if __name__ == "__main__":
    main()