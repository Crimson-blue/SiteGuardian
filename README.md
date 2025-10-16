#  SiteGuardian

**SiteGuardian** is a Python desktop application that monitors websites for changes, manages scheduled crawls, and automatically creates backups of page content — all inside a powerful and intuitive GUI built with PySide6.

---

##  Features

- **Automated website monitoring** with customizable crawl schedules  
- **Change detection** that highlights differences between versions  
- **Automatic backups** of downloaded pages for reference and rollback  
- **Scheduler service** for continuous background tasks  
- **In-app logging** displayed in real time  
- **Visual diff viewer** and data plots in a friendly Qt interface  
- **Configurable settings** through simple `.env` or GUI options  

---

##  Architecture Overview

SiteGuardian is built on a **modular architecture** for clarity, testability, and easy extension.

```
SiteGuardian/
├── main.py                # Application entry point
│
├── config/                # Configuration and database setup
│   ├── settings.py        # Settings and project constants
│   ├── database.py        # SQLAlchemy engine and session
│   └── siteguardian.db    # Local SQLite database
│
├── core/                  # Logic and background services
│   ├── crawler.py         # Website crawling engine
│   ├── diff.py            # Page comparison logic
│   ├── backup_manager.py  # Backup handling (stores fetched content snapshots)
│   ├── scheduler.py       # Threaded scheduling service
│   ├── notifier.py        # Notifications for detected changes
│   ├── models.py          # Data models and ORM logic
│   └── utils.py           # Helper functions
│
├── gui/                   # PySide6 GUI components
│   ├── main_window.py     # Primary application window
│   ├── log_handler.py     # GUI-integrated logging
│   ├── diff_viewer.py     # Visual difference viewer
│   ├── plot_widget.py     # Trend visualization widget
│   └── add_edit_dialog.py # Dialog for adding or editing monitored sites
│
└── requirements.txt
```

---

## ⚙️ Setup & Installation

1. Clone the repository  
   ```bash
   git clone https://github.com/your-username/siteguardian.git
   cd siteguardian
   ```

2. Create and activate a virtual environment  
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. Install dependencies  
   ```bash
   pip install -r requirements.txt
   ```

4. (Optional) Create a `.env` file to customize app paths and parameters:
   ```
   APP_NAME=SiteGuardian
   LOG_DIR=logs
   BACKUP_ROOT=backups
   DB_PATH=config/siteguardian.db
   ```

---

##  Run the App

```bash
python main.py
```

Once running, the GUI provides an interface to:

- Add or edit monitored websites  
- Trigger manual crawls  
- Browse detected changes  
- View logs and trends  
- Restore or compare backups  

---

##  Technologies

- **Python 3.10+**  
- **PySide6** — user interface framework  
- **SQLAlchemy + SQLite** — persistent storage  
- **python-dotenv** — configuration management  
- **logging** — console and GUI-integrated logging  

---

##  Developer Quick Start

### Core Code Entry Points
- `main.py` → Application bootstrap logic  
- `core/scheduler.py` → Handles timed background tasks  
- `core/backup_manager.py` → Manages creation and retrieval of backups  
- `gui/main_window.py` → Central GUI controller  

### Adding New GUI Modules
1. Create your new widget or dialog in `gui/`.  
2. Connect it via `main_window.py`.  
3. Send logs to `QtLogHandler` for on-screen updates.

### Adding New Core Services
1. Place the module under `core/`.  
2. Register it in `main.py` or within the `SchedulerService`.  
3. Use `SessionLocal` from the database for persistence when needed.

---

##  Backups Explained

SiteGuardian stores every crawled version of a monitored page in the **backup directory** defined in your environment settings (`BACKUP_ROOT`).

Each backup includes:
- The raw HTML snapshot  
- Metadata (timestamp, URL, checksum) stored in the database  
- Diff compatibility for side-by-side comparison  

This ensures that **no detected change is ever lost**, enabling version history and recovery.

---

## 📝 License

Licensed under the **MIT License** — free for modification, use, and distribution with attribution.
