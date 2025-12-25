"""Configuration settings for the debate workflow."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Track running agent processes for manual termination
RUNNING_AGENTS: dict[str, int] = {}  # agent_key -> PID

# Package directory (where this file lives)
_PACKAGE_DIR = Path(__file__).parent.parent


def _default_agent_dir() -> Path:
    """Resolve the default agent directory.

    Priority:
    1. DEBATE_AGENT_DIR environment variable (handled by pydantic)
    2. agent/ folder in the package directory (for repo installs)
    3. ~/.config/opencode/agent (legacy fallback)
    """
    # Check if agent/ exists in package directory
    package_agent_dir = _PACKAGE_DIR / "agent"
    if package_agent_dir.exists():
        return package_agent_dir
    # Fallback to legacy location
    return Path.home() / ".config" / "opencode" / "agent"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    db_host: str = "localhost"
    db_port: int = 15432
    db_name: str = "debate"
    db_user: str = "agent"
    db_password: str = "agent"

    # Paths
    config_dir: Path = Path.home() / ".config" / "opencode"
    agent_dir: Path = _default_agent_dir()

    opencode_api_url: str = "http://localhost:4096"
    opencode_directory: str | None = None

    # Redis
    redis_url: str = "redis://localhost:16379/0"
    redis_rate_limit_enabled: bool = True
    redis_queue_enabled: bool = False
    redis_queue_max_depth: int = 100
    redis_rate_limit_wait_seconds: int = 60

    # Timeouts (seconds)
    agent_timeout: int = 300  # 5 minutes
    round_timeout: int = 720  # 12 minutes
    debate_timeout: int = 1800  # 30 minutes

    # Thresholds
    consensus_threshold: float = 80.0
    max_rounds: int = 3
    max_retries: int = 2
    triage_shadow_mode: bool = True

    # Agent CLI commands
    gemini_cmd: str = "gemini"
    claude_cmd: str = "claude"
    codex_cmd: str = "codex"

    @property
    def database_url(self) -> str:
        """SQLAlchemy database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def async_database_url(self) -> str:
        """Async SQLAlchemy database URL."""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_prefix = "DEBATE_"
        env_file = ".env"


# Global settings instance
settings = Settings()
