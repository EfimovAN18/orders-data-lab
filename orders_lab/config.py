import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    warehouse: Path
    raw_dir: Path
    report_dir: Path


def get_settings() -> Settings:
    # Читаем только .env текущего проекта; переменные окружения имеют приоритет.
    load_dotenv(Path.cwd() / ".env", override=False)
    return Settings(
        database_url=os.getenv("APP_DATABASE_URL", "sqlite:///data/orders.db"),
        warehouse=Path(os.getenv("WAREHOUSE_PATH", "data/warehouse.db")),
        raw_dir=Path(os.getenv("RAW_DIR", "data/raw")),
        report_dir=Path(os.getenv("REPORT_DIR", "reports")),
    )
