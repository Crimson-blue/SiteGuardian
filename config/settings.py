from dataclasses import dataclass
import os

@dataclass
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "SiteGuardian")
    BACKUP_ROOT: str = os.getenv("BACKUP_ROOT", "backups")
    DB_PATH: str = os.getenv("DB_PATH", "config/siteguardian.db")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "8"))
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    EMAIL_TO: str = os.getenv("EMAIL_TO", "")
    DESKTOP_NOTIFICATIONS: bool = os.getenv("DESKTOP_NOTIFICATIONS", "true").lower() == "true"

settings = Settings()