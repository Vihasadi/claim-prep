"""Settings, read from environment variables and an optional `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """A required setting is missing or a value is invalid."""


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"
    model: str = ""
    api_key: str = "unused"
    context_tokens: int = 32_000
    reply_tokens: int = 2_000
    concurrency: int = 4
    timeout_s: float = 180.0

    @property
    def prompt_budget(self) -> int:
        """Tokens a prompt may use. Token counts are estimates, so 10% is held back."""
        return int((self.context_tokens - self.reply_tokens) * 0.9)


@dataclass(frozen=True)
class Settings:
    crm_db: Path = Path("data/crm.sqlite3")
    replay_db: Path = Path("data/replays.sqlite3")      # ClaimReplay's output (optional)
    playbook_db: Path = Path("data/playbooks.sqlite3")  # ClaimScout's output (optional)
    cache_db: Path = Path("data/call_briefs.sqlite3")
    api_keys: tuple[str, ...] = ()                      # empty: no key required (local use)
    llm: LLMConfig = field(default_factory=LLMConfig)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or Path(".env"), override=False)
    problems: list[str] = []

    def number(name: str, default: int) -> int:
        try:
            return int(_env(name, str(default)))
        except ValueError:
            problems.append(f"{name} must be a whole number")
            return default

    llm = LLMConfig(
        base_url=_env("LLM_BASE_URL", LLMConfig.base_url),
        model=_env("LLM_MODEL"),
        api_key=_env("LLM_API_KEY", LLMConfig.api_key),
        context_tokens=number("LLM_CONTEXT_TOKENS", LLMConfig.context_tokens),
        reply_tokens=number("LLM_REPLY_TOKENS", LLMConfig.reply_tokens),
        concurrency=number("LLM_CONCURRENCY", LLMConfig.concurrency),
    )
    if not llm.model:
        problems.append("LLM_MODEL is not set")
    if llm.prompt_budget < 4_000:
        problems.append("LLM_CONTEXT_TOKENS is too small: a brief needs about 4k tokens of prompt room")
    if problems:
        raise ConfigError("; ".join(problems))
    return Settings(
        crm_db=Path(_env("CRM_DB_PATH", str(Settings.crm_db))),
        replay_db=Path(_env("REPLAY_DB_PATH", str(Settings.replay_db))),
        playbook_db=Path(_env("PLAYBOOK_DB_PATH", str(Settings.playbook_db))),
        cache_db=Path(_env("CALL_BRIEFS_DB_PATH", str(Settings.cache_db))),
        api_keys=tuple(k.strip() for k in _env("API_KEYS").split(",") if k.strip()),
        llm=llm,
    )
