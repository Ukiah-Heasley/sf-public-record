from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/planlens.duckdb")
    raw_dir: Path = Path("data/raw")
    user_agent: str = "PlanLensSF/0.1 civic research crawler; contact: local-dev"
    crawl_delay_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=Path(os.getenv("PLANLENS_DB_PATH", cls.db_path.as_posix())),
            raw_dir=Path(os.getenv("PLANLENS_RAW_DIR", cls.raw_dir.as_posix())),
            user_agent=os.getenv("PLANLENS_USER_AGENT", cls.user_agent),
            crawl_delay_seconds=float(
                os.getenv("PLANLENS_CRAWL_DELAY_SECONDS", str(cls.crawl_delay_seconds))
            ),
        )

    @property
    def html_dir(self) -> Path:
        return self.raw_dir / "html"

    @property
    def pdf_dir(self) -> Path:
        return self.raw_dir / "pdfs"
