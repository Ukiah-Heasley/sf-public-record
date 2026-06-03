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
    chunk_target_tokens: int = 1000
    chunk_max_tokens: int = 1200
    chunk_overlap_tokens: int = 120
    embedding_provider: str = "local_hash"
    embedding_model: str = "local-hash-v1"
    embedding_dimensions: int = 384
    openai_api_key: str | None = None
    google_api_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=Path(os.getenv("PLANLENS_DB_PATH", cls.db_path.as_posix())),
            raw_dir=Path(os.getenv("PLANLENS_RAW_DIR", cls.raw_dir.as_posix())),
            user_agent=os.getenv("PLANLENS_USER_AGENT", cls.user_agent),
            crawl_delay_seconds=float(
                os.getenv("PLANLENS_CRAWL_DELAY_SECONDS", str(cls.crawl_delay_seconds))
            ),
            chunk_target_tokens=int(
                os.getenv("PLANLENS_CHUNK_TARGET_TOKENS", str(cls.chunk_target_tokens))
            ),
            chunk_max_tokens=int(
                os.getenv("PLANLENS_CHUNK_MAX_TOKENS", str(cls.chunk_max_tokens))
            ),
            chunk_overlap_tokens=int(
                os.getenv("PLANLENS_CHUNK_OVERLAP_TOKENS", str(cls.chunk_overlap_tokens))
            ),
            embedding_provider=os.getenv(
                "PLANLENS_EMBEDDING_PROVIDER",
                cls.embedding_provider,
            ),
            embedding_model=os.getenv("PLANLENS_EMBEDDING_MODEL", cls.embedding_model),
            embedding_dimensions=int(
                os.getenv("PLANLENS_EMBEDDING_DIMENSIONS", str(cls.embedding_dimensions))
            ),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            google_api_key=os.getenv("GOOGLE_API_KEY") or None,
        )

    @property
    def html_dir(self) -> Path:
        return self.raw_dir / "html"

    @property
    def pdf_dir(self) -> Path:
        return self.raw_dir / "pdfs"
