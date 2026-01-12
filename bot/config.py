import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv


@dataclass
class ProxyConfig:
    scheme: str | None
    host: str | None
    port: int | None
    username: str | None
    password: str | None

    def as_url(self) -> str | None:
        if not (self.scheme and self.host and self.port):
            return None
        if self.username and self.password:
            return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"


@dataclass
class Settings:
    bot_token: str
    old_bot_token: str | None
    gemini_api_key: str
    database_url: str
    proxy: ProxyConfig
    admin_ids: list[int]


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    old_bot_token = os.getenv("OLD_BOT_TOKEN", "").strip() or None
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db").strip()

    # Сначала пробуем получить единый URL прокси
    bot_http_proxy = os.getenv("BOT_HTTP_PROXY", "").strip()
    if bot_http_proxy:
        if "://" in bot_http_proxy:
            from urllib.parse import urlparse
            parsed = urlparse(bot_http_proxy)
            proxy = ProxyConfig(
                scheme=parsed.scheme or "http",
                host=parsed.hostname,
                port=parsed.port,
                username=parsed.username,
                password=parsed.password,
            )
        else:
            # Обработка формата host:port:user:pass или host:port
            parts = bot_http_proxy.split(":")
            if len(parts) == 4:
                proxy = ProxyConfig(scheme="http", host=parts[0], port=int(parts[1]), username=parts[2], password=parts[3])
            elif len(parts) == 2:
                proxy = ProxyConfig(scheme="http", host=parts[0], port=int(parts[1]), username=None, password=None)
            else:
                proxy = ProxyConfig(scheme=None, host=None, port=None, username=None, password=None)
    else:
        proxy = ProxyConfig(
            scheme=os.getenv("PROXY_SCHEME", "").strip() or None,
            host=os.getenv("PROXY_HOST", "").strip() or None,
            port=int(os.getenv("PROXY_PORT", "0") or 0) or None,
            username=os.getenv("PROXY_USER", "").strip() or None,
            password=os.getenv("PROXY_PASS", "").strip() or None,
        )

    admin_ids_env = os.getenv("ADMIN_IDS", "").strip()
    admin_ids: List[int] = []
    if admin_ids_env:
        parts = [p.strip() for p in admin_ids_env.replace(";", ",").split(",")]
        for p in parts:
            if not p:
                continue
            try:
                admin_ids.append(int(p))
            except ValueError:
                continue

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required in .env")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required in .env")

    return Settings(
        bot_token=bot_token,
        old_bot_token=old_bot_token,
        gemini_api_key=gemini_api_key,
        database_url=database_url,
        proxy=proxy,
        admin_ids=admin_ids,
    )


