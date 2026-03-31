from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # --- Supabase ---
    supabase_url: str
    supabase_key: str  # service-role key (server-side only)

    # --- OpenAI ---
    openai_api_key: str

    # --- Alpha Vantage ---
    alpha_vantage_api_key: str

    # --- App ---
    api_secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173"
    environment: str = "development"

    # --- Agent ---
    agent_schedule_hours: int = 4
    tracked_crypto: str = "BTC,ETH,SOL"
    tracked_forex: str = "EUR/USD,GBP/USD,USD/JPY"

    # --- Risk defaults ---
    max_position_pct: float = 5.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 3
    default_stop_loss_pct: float = 2.0
    default_take_profit_pct: float = 4.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def crypto_symbols(self) -> list[str]:
        return [s.strip() for s in self.tracked_crypto.split(",")]

    @property
    def forex_pairs(self) -> list[str]:
        return [s.strip() for s in self.tracked_forex.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]
