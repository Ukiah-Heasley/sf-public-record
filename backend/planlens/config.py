from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/sf-public-record.duckdb")
    raw_dir: Path = Path("data/raw")
    user_agent: str = "SFPublicRecord/0.1 civic research crawler; contact: unset"
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
            db_path=Path(
                _env("SF_PUBLIC_RECORD_DB_PATH", "PLANLENS_DB_PATH", cls.db_path.as_posix())
            ),
            raw_dir=Path(
                _env("SF_PUBLIC_RECORD_RAW_DIR", "PLANLENS_RAW_DIR", cls.raw_dir.as_posix())
            ),
            user_agent=_env("SF_PUBLIC_RECORD_USER_AGENT", "PLANLENS_USER_AGENT", cls.user_agent),
            crawl_delay_seconds=float(
                _env(
                    "SF_PUBLIC_RECORD_CRAWL_DELAY_SECONDS",
                    "PLANLENS_CRAWL_DELAY_SECONDS",
                    str(cls.crawl_delay_seconds),
                )
            ),
            chunk_target_tokens=int(
                _env(
                    "SF_PUBLIC_RECORD_CHUNK_TARGET_TOKENS",
                    "PLANLENS_CHUNK_TARGET_TOKENS",
                    str(cls.chunk_target_tokens),
                )
            ),
            chunk_max_tokens=int(
                _env(
                    "SF_PUBLIC_RECORD_CHUNK_MAX_TOKENS",
                    "PLANLENS_CHUNK_MAX_TOKENS",
                    str(cls.chunk_max_tokens),
                )
            ),
            chunk_overlap_tokens=int(
                _env(
                    "SF_PUBLIC_RECORD_CHUNK_OVERLAP_TOKENS",
                    "PLANLENS_CHUNK_OVERLAP_TOKENS",
                    str(cls.chunk_overlap_tokens),
                )
            ),
            embedding_provider=_env(
                "SF_PUBLIC_RECORD_EMBEDDING_PROVIDER",
                "PLANLENS_EMBEDDING_PROVIDER",
                cls.embedding_provider,
            ),
            embedding_model=_env(
                "SF_PUBLIC_RECORD_EMBEDDING_MODEL",
                "PLANLENS_EMBEDDING_MODEL",
                cls.embedding_model,
            ),
            embedding_dimensions=int(
                _env(
                    "SF_PUBLIC_RECORD_EMBEDDING_DIMENSIONS",
                    "PLANLENS_EMBEDDING_DIMENSIONS",
                    str(cls.embedding_dimensions),
                )
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


def _env(name: str, legacy_name: str, default: str) -> str:
    return os.getenv(name) or os.getenv(legacy_name) or default
