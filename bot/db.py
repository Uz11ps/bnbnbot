import aiosqlite
from typing import Optional
import logging

logger = logging.getLogger(__name__)


CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    accepted_terms INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    referrer_id INTEGER,
    language TEXT NOT NULL DEFAULT 'ru',
    trial_used INTEGER NOT NULL DEFAULT 0,
    balance INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SUBSCRIPTION_PLANS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subscription_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ru TEXT NOT NULL,
    name_en TEXT NOT NULL,
    name_vi TEXT NOT NULL,
    description_ru TEXT,
    description_en TEXT,
    description_vi TEXT,
    price INTEGER NOT NULL,          -- Цена в рублях
    duration_days INTEGER NOT NULL,
    daily_limit INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
"""

CREATE_SUBSCRIPTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id INTEGER,                 -- Ссылка на план (может быть NULL для триала)
    plan_type TEXT NOT NULL,         -- 'trial', 'custom', или название из плана
    expires_at TIMESTAMP NOT NULL,
    daily_limit INTEGER NOT NULL,
    daily_usage INTEGER NOT NULL DEFAULT 0,
    last_usage_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    individual_api_key TEXT,         -- Индивидуальный ключ для 4K планов
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(plan_id) REFERENCES subscription_plans(id)
);
"""

CREATE_PAYMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id INTEGER,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'RUB',
    status TEXT DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

CREATE_GENERATION_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid TEXT UNIQUE NOT NULL,         -- PID000000000
    user_id INTEGER NOT NULL,
    category TEXT,
    params TEXT,                     -- JSON с параметрами
    input_photos TEXT,               -- JSON с file_id входящих фото
    result_photo_id TEXT,            -- file_id результата
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

UPDATE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
  UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""

CREATE_PROMPTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL
);
"""

CREATE_MODELS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    cloth TEXT NOT NULL,
    name TEXT NOT NULL,
    prompt_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    photo_file_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(prompt_id) REFERENCES prompts(id)
);
"""

CREATE_API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    daily_usage INTEGER NOT NULL DEFAULT 0,
    total_usage INTEGER NOT NULL DEFAULT 0,
    last_usage_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_API_USAGE_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(key_id) REFERENCES api_keys(id)
);
"""

CREATE_API_ERRORS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_key_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER,
    api_key_preview TEXT,  -- Первые 10 символов ключа для идентификации
    error_type TEXT NOT NULL,  -- '429', 'quota', 'proxy', etc.
    error_message TEXT,
    status_code INTEGER,
    is_proxy_error INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(key_id) REFERENCES api_keys(id)
);
"""

CREATE_OWN_VARIANT_API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS own_variant_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_OWN_VARIANT_RATE_LIMIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS own_variant_rate_limit (
    key_id INTEGER NOT NULL,
    date DATE NOT NULL,
    minute_start INTEGER NOT NULL,
    requests_count INTEGER NOT NULL DEFAULT 0,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, date, minute_start),
    FOREIGN KEY(key_id) REFERENCES own_variant_api_keys(id)
);
"""

CREATE_OWN_VARIANT_RATE_LIMIT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_own_variant_rate_limit_date ON own_variant_rate_limit(key_id, date);
"""

CREATE_APP_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CREATE_TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    type TEXT NOT NULL,           -- 'topup' | 'spend' | 'adjust'
    reason TEXT,                  -- 'generation' | 'edit_generation' | 'admin_add' | 'admin_remove' | ...
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PROMPT_TEMPLATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS prompt_templates (
    key TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    description TEXT
);
"""


CREATE_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    name_ru TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    order_index INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_STEPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    step_key TEXT NOT NULL,          -- ключ для сохранения в state (например 'age', 'size')
    question_text TEXT NOT NULL,     -- текст вопроса
    input_type TEXT NOT NULL,        -- 'text', 'buttons', 'photo'
    is_optional INTEGER NOT NULL DEFAULT 0,
    order_index INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(category_id) REFERENCES categories(id)
);
"""

CREATE_STEP_OPTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS step_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    option_value TEXT NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(step_id) REFERENCES steps(id)
);
"""


class Database:
    def __init__(self, db_path: str = "bot.db") -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(CREATE_USERS_TABLE_SQL)
            await db.execute(CREATE_SUBSCRIPTION_PLANS_TABLE_SQL)
            await db.execute(UPDATE_TRIGGER_SQL)
            await db.execute(CREATE_PROMPTS_TABLE_SQL)
            await db.execute(CREATE_MODELS_TABLE_SQL)
            await db.execute(CREATE_API_KEYS_TABLE_SQL)
            await db.execute(CREATE_API_USAGE_LOG_TABLE_SQL)
            await db.execute(CREATE_API_ERRORS_TABLE_SQL)
            await db.execute(CREATE_OWN_VARIANT_API_KEYS_TABLE_SQL)
            await db.execute(CREATE_OWN_VARIANT_RATE_LIMIT_TABLE_SQL)
            await db.execute(CREATE_OWN_VARIANT_RATE_LIMIT_INDEX_SQL)
            await db.execute(CREATE_APP_SETTINGS_TABLE_SQL)
            await db.execute(CREATE_TRANSACTIONS_TABLE_SQL)
            await db.execute(CREATE_PAYMENTS_TABLE_SQL)
            await db.execute(CREATE_SUBSCRIPTIONS_TABLE_SQL)
            await db.execute(CREATE_GENERATION_HISTORY_TABLE_SQL)
            await db.execute(CREATE_PROMPT_TEMPLATES_TABLE_SQL)
            await db.execute(CREATE_CATEGORIES_TABLE_SQL)
            await db.execute(CREATE_STEPS_TABLE_SQL)
            await db.execute(CREATE_STEP_OPTIONS_TABLE_SQL)
            await db.commit()
        
        # Миграция для описаний планов
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("PRAGMA table_info(subscription_plans)") as cur:
                cols = [row[1] for row in await cur.fetchall()]
            if "description_ru" not in cols:
                await db.execute("ALTER TABLE subscription_plans ADD COLUMN description_ru TEXT")
                await db.execute("ALTER TABLE subscription_plans ADD COLUMN description_en TEXT")
                await db.execute("ALTER TABLE subscription_plans ADD COLUMN description_vi TEXT")
                await db.commit()

        await self._seed_prompts()
        await self._seed_templates()
        await self._seed_subscription_plans()
        await self._seed_app_settings() # Добавляем сид настроек
        await self._seed_categories() # Добавляем сид категорий и шагов
        
        # Добавляем токен для nano-banano модели для "Свой вариант" если его еще нет
        try:
            existing_keys = await self.list_own_variant_api_keys()
            nano_banano_token = "AIzaSyCFJPf6oFYfIZGxrYrOL79379OMV_KKyVs"
            # Проверяем, есть ли уже этот токен
            if not any(tok == nano_banano_token for _kid, tok, _active in existing_keys):
                await self.add_own_variant_api_key(nano_banano_token, priority=100)  # Высокий приоритет
                logger.info("Добавлен токен nano-banano для категории 'Свой вариант'")
        except Exception as e:
            logger.warning(f"Не удалось добавить токен nano-banano при инициализации: {e}")

        # Ensure new columns exist
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("PRAGMA table_info(users)") as cur:
                cols = [row[1] for row in await cur.fetchall()]
            if "trial_used" not in cols:
                await db.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0")
            if "balance" not in cols:
                await db.execute("ALTER TABLE users ADD COLUMN balance INTEGER NOT NULL DEFAULT 0")
            
            async with db.execute("PRAGMA table_info(api_keys)") as cur:
                cols = [row[1] for row in await cur.fetchall()]
            if "daily_usage" not in cols:
                await db.execute("ALTER TABLE api_keys ADD COLUMN daily_usage INTEGER NOT NULL DEFAULT 0")
            if "total_usage" not in cols:
                await db.execute("ALTER TABLE api_keys ADD COLUMN total_usage INTEGER NOT NULL DEFAULT 0")
            if "last_usage_reset" not in cols:
                # SQLite doesn't allow CURRENT_TIMESTAMP as a default for new columns in ALTER TABLE
                await db.execute("ALTER TABLE api_keys ADD COLUMN last_usage_reset TIMESTAMP")
                await db.execute("UPDATE api_keys SET last_usage_reset = CURRENT_TIMESTAMP")
            
            async with db.execute("PRAGMA table_info(subscriptions)") as cur:
                cols = [row[1] for row in await cur.fetchall()]
            if "plan_id" not in cols:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN plan_id INTEGER")
            if "individual_api_key" not in cols:
                await db.execute("ALTER TABLE subscriptions ADD COLUMN individual_api_key TEXT")

            await db.commit()

    # API keys management
    async def list_api_keys(self) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, token, is_active, priority, daily_usage, total_usage, last_usage_reset, created_at, updated_at FROM api_keys ORDER BY is_active DESC, priority DESC, id"
            ) as cur:
                return await cur.fetchall()

    async def list_active_api_keys(self) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT token FROM api_keys WHERE is_active=1 ORDER BY priority DESC, id"
            ) as cur:
                rows = await cur.fetchall()
                return [str(r[0]) for r in rows]

    async def add_api_key(self, token: str, priority: int = 0) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO api_keys (token, priority) VALUES (?, ?)",
                (token.strip(), int(priority)),
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                row = await cur.fetchone()
                return int(row[0])

    # Transactions (balance history)
    async def add_transaction(self, user_id: int, amount: int, type: str, reason: str | None = None) -> None:
        safe_type = (type or "adjust").strip()
        safe_reason = (reason or "").strip() or None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO transactions (user_id, amount, type, reason) VALUES (?,?,?,?)",
                (int(user_id), int(amount), safe_type, safe_reason),
            )
            await db.commit()

    async def list_user_transactions(self, user_id: int, offset: int, limit: int) -> list[tuple[int, int, str, str | None, str]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, amount, type, reason, datetime(created_at, 'localtime') "
                "FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (int(user_id), int(limit), int(offset)),
            ) as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), int(r[1]), str(r[2]), (str(r[3]) if r[3] is not None else None), str(r[4])) for r in rows]

    async def update_api_key(self, key_id: int, *, token: str | None = None, is_active: int | None = None, priority: int | None = None) -> None:
        fields = []
        values = []
        if token is not None:
            fields.append("token=?")
            values.append(token.strip())
        if is_active is not None:
            fields.append("is_active=?")
            values.append(1 if is_active else 0)
        if priority is not None:
            fields.append("priority=?")
            values.append(int(priority))
        if not fields:
            return
        values.append(int(key_id))
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(f"UPDATE api_keys SET {', '.join(fields)} WHERE id=?", tuple(values))
            await db.commit()

    async def delete_api_key(self, key_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM api_keys WHERE id=?", (int(key_id),))
            await db.commit()

    # Own Variant API keys management
    async def list_own_variant_api_keys(self) -> list[tuple[int, str, int]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, token, is_active FROM own_variant_api_keys ORDER BY is_active DESC, priority DESC, id"
            ) as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), str(r[1]), int(r[2])) for r in rows]

    async def list_active_own_variant_api_keys(self) -> list[str]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT token FROM own_variant_api_keys WHERE is_active=1 ORDER BY priority DESC, id"
            ) as cur:
                rows = await cur.fetchall()
                return [str(r[0]) for r in rows]

    async def add_own_variant_api_key(self, token: str, priority: int = 0) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO own_variant_api_keys (token, priority) VALUES (?, ?)",
                (token.strip(), int(priority)),
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                row = await cur.fetchone()
                return int(row[0])

    async def update_own_variant_api_key(self, key_id: int, *, token: str | None = None, is_active: int | None = None, priority: int | None = None) -> None:
        fields = []
        values = []
        if token is not None:
            fields.append("token=?")
            values.append(token.strip())
        if is_active is not None:
            fields.append("is_active=?")
            values.append(1 if is_active else 0)
        if priority is not None:
            fields.append("priority=?")
            values.append(int(priority))
        if not fields:
            return
        values.append(int(key_id))
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(f"UPDATE own_variant_api_keys SET {', '.join(fields)} WHERE id=?", tuple(values))
            await db.commit()

    async def delete_own_variant_api_key(self, key_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM own_variant_api_keys WHERE id=?", (int(key_id),))
            await db.commit()

    # Own Variant Rate Limiting
    async def check_own_variant_rate_limit(self, key_id: int, tokens_needed: int = 2) -> tuple[bool, str]:
        """
        Проверяет rate limits для own_variant API ключа:
        - 20 запросов в минуту
        - 100 токенов в день
        - 250 запросов в день
        
        Returns: (is_allowed, error_message)
        """
        from datetime import datetime, timedelta
        import time
        
        now = datetime.now()
        today = now.date()
        current_minute = int(time.time() // 60)
        
        async with aiosqlite.connect(self._db_path) as db:
            # Проверка: 20 запросов в минуту
            async with db.execute(
                "SELECT SUM(requests_count) FROM own_variant_rate_limit WHERE key_id=? AND minute_start=?",
                (int(key_id), current_minute)
            ) as cur:
                row = await cur.fetchone()
                minute_requests = int(row[0]) if row and row[0] else 0
                if minute_requests >= 20:
                    return False, "Превышен лимит: 20 запросов в минуту"
            
            # Проверка: 100 токенов в день
            async with db.execute(
                "SELECT SUM(tokens_used) FROM own_variant_rate_limit WHERE key_id=? AND date=?",
                (int(key_id), today.isoformat())
            ) as cur:
                row = await cur.fetchone()
                daily_tokens = int(row[0]) if row and row[0] else 0
                if daily_tokens + tokens_needed > 100:
                    return False, f"Превышен лимит: 100 токенов в день (использовано: {daily_tokens}, нужно: {tokens_needed})"
            
            # Проверка: 250 запросов в день
            async with db.execute(
                "SELECT SUM(requests_count) FROM own_variant_rate_limit WHERE key_id=? AND date=?",
                (int(key_id), today.isoformat())
            ) as cur:
                row = await cur.fetchone()
                daily_requests = int(row[0]) if row and row[0] else 0
                if daily_requests >= 250:
                    return False, "Превышен лимит: 250 запросов в день"
            
            return True, ""

    async def record_own_variant_usage(self, key_id: int, tokens_used: int = 2) -> None:
        """Записывает использование API ключа для rate limiting"""
        from datetime import datetime
        import time
        
        now = datetime.now()
        today = now.date()
        current_minute = int(time.time() // 60)
        
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO own_variant_rate_limit (key_id, date, minute_start, requests_count, tokens_used)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(key_id, date, minute_start) DO UPDATE SET
                       requests_count = requests_count + 1,
                       tokens_used = tokens_used + excluded.tokens_used""",
                (int(key_id), today.isoformat(), current_minute, int(tokens_used))
            )
            await db.commit()

    # Maintenance flag
    async def get_maintenance(self) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='maintenance'") as cur:
                row = await cur.fetchone()
                return (str(row[0]) == '1') if row else False

    async def set_maintenance(self, enabled: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            # Получаем текущий статус
            current = await self.get_maintenance()
            if current == enabled:
                return

            from datetime import datetime
            now_str = datetime.now().isoformat()
            
            if enabled:
                # Включаем: записываем время начала
                await db.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('maintenance_start', ?)\n                     ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (now_str,),
                )
            else:
                # Выключаем: считаем сколько длились техработы и продлеваем подписки
                async with db.execute("SELECT value FROM app_settings WHERE key='maintenance_start'") as cur:
                    row = await cur.fetchone()
                    if row:
                        start_time = datetime.fromisoformat(row[0])
                        duration = datetime.now() - start_time
                        duration_seconds = int(duration.total_seconds())
                        
                        if duration_seconds > 0:
                            # Продлеваем все активные подписки
                            await db.execute(
                                "UPDATE subscriptions SET expires_at = datetime(expires_at, '+' || ? || ' seconds') WHERE expires_at > CURRENT_TIMESTAMP",
                                (str(duration_seconds),)
                            )

            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('maintenance', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ('1' if enabled else '0',),
            )
            await db.commit()

    # Prompt Templates
    async def get_prompt_template(self, key: str) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT template FROM prompt_templates WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None

    async def set_prompt_template(self, key: str, template: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO prompt_templates (key, template) VALUES (?, ?)\n                 ON CONFLICT(key) DO UPDATE SET template=excluded.template",
                (key, template),
            )
            await db.commit()

    async def list_prompt_templates(self) -> list[tuple[str, str, str | None]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT key, template, description FROM prompt_templates") as cur:
                rows = await cur.fetchall()
                return [(str(r[0]), str(r[1]), r[2]) for r in rows]

    async def _seed_app_settings(self) -> None:
        """Начальные настройки приложения"""
        settings = [
            ("required_channel_id", ""), # Например: -100123456789
            ("required_channel_url", "https://t.me/bnbslow"),
            ("agreement_text", "Пожалуйста, ознакомьтесь и примите условия пользовательского соглашения перед использованием бота."),
        ]
        async with aiosqlite.connect(self._db_path) as db:
            for key, val in settings:
                await db.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                    (key, val)
                )
            await db.commit()

    async def _seed_templates(self) -> None:
        templates = [
            ("template_female", "Манекен {Пол}, одежда {Стиль}, длина {Длина}, рукав {Рукав}, ракурс {Ракурс}", "Шаблон для женщин"),
            ("template_male", "Манекен {Пол}, одежда {Стиль}, длина {Длина}, рукав {Рукав}, ракурс {Ракурс}", "Шаблон для мужчин"),
            ("template_child", "Манекен {Пол}, одежда {Стиль}, возраст {Возраст}, ракурс {Ракурс}", "Шаблон для детей"),
            ("template_own_variant", "Photo 1: model reference. Photo 2: clothing. \nReproduce Photo 2 on the model from Photo 1. \nDetails: Length {Длина}, Sleeve {Рукав}, View {Ракурс}", "Шаблон для 'Свой вариант'"),
        ]
        async with aiosqlite.connect(self._db_path) as db:
            for key, tmpl, desc in templates:
                await db.execute(
                    "INSERT OR IGNORE INTO prompt_templates (key, template, description) VALUES (?, ?, ?)",
                    (key, tmpl, desc)
                )
            await db.commit()

    # Base prompts storage (single prompt per key)
    async def get_whitebg_prompt(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='whitebg_prompt'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None

    async def set_whitebg_prompt(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('whitebg_prompt', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()

    async def get_random_prompt(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='random_prompt'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None

    async def set_random_prompt(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('random_prompt', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()
    # Own prompts (3 steps)
    async def get_own_prompt1(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='own_prompt1'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None
    async def set_own_prompt1(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('own_prompt1', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()
    async def get_own_prompt2(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='own_prompt2'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None
    async def set_own_prompt2(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('own_prompt2', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()
    async def get_own_prompt3(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='own_prompt3'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None
    async def set_own_prompt3(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('own_prompt3', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()

    # Own Variant prompt storage
    async def get_own_variant_prompt(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='own_variant_prompt'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None

    async def set_own_variant_prompt(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('own_variant_prompt', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()

    # Category prices (in tenths of tokens, e.g., 10 = 1 token, 12 = 1.2 tokens, 20 = 2 tokens)
    async def get_category_price(self, category: str) -> int:
        """Возвращает цену категории в десятых долях токена (по умолчанию: 10 = 1 токен)"""
        # Значения по умолчанию
        defaults = {
            "female": 10,
            "male": 10,
            "child": 10,
            "storefront": 10,
            "whitebg": 10,
            "random": 10,
            "own": 12,  # 1.2 токена
            "own_variant": 20,  # 2 токена - фиксированная цена
        }
        default_price = defaults.get(category, 10)
        
        # Для "свой вариант" всегда возвращаем 2 токена (20 tenths)
        if category == "own_variant":
            return 20
        
        key = f"category_price_{category}"
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                if row:
                    try:
                        return int(row[0])
                    except Exception:
                        return default_price
                return default_price

    async def set_category_price(self, category: str, price_tenths: int) -> None:
        """Устанавливает цену категории в десятых долях токена"""
        key = f"category_price_{category}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(price_tenths)),
            )
            await db.commit()

    async def list_category_prices(self) -> dict[str, int]:
        """Возвращает словарь всех цен категорий"""
        categories = ["female", "male", "child", "storefront", "whitebg", "random", "own", "own_variant"]
        result = {}
        for cat in categories:
            result[cat] = await self.get_category_price(cat)
        return result

    @staticmethod
    def add_ai_room_branding(prompt: str) -> str:
        """Добавляет требование об использовании брендинга AI-ROOM ко всем промптам"""
        branding_text = "\n\nWhenever the user asks to write or display the name of the AI model on an image, always use AI-ROOM. Never write or reveal real model names (such as Gemini, GPT, or any others). For any request involving text on an image, the only model name that may appear is AI-ROOM."
        if prompt and prompt.strip():
            return prompt.strip() + branding_text
        return prompt

    # Category enable/disable
    async def get_category_enabled(self, name: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key=?", (name,)) as cur:
                row = await cur.fetchone()
                # По умолчанию категории включены, если нет записи '0'
                if not row:
                    return True
                return str(row[0]) != '0'

    async def set_category_enabled(self, name: str, enabled: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (name, '1' if enabled else '0'),
            )
            await db.commit()

    async def list_categories_enabled(self) -> dict[str, bool]:
        names = ["female", "male", "child", "storefront", "whitebg", "random", "random_other", "own", "own_variant", "infographic_clothing", "infographic_other"]
        result: dict[str, bool] = {}
        for n in names:
            result[n] = await self.get_category_enabled(n)
        return result

    # Fractional token support (store tenths remainder per user)
    async def get_user_fraction(self, user_id: int) -> int:
        key = f"user_frac_{int(user_id)}"
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                try:
                    return int(row[0]) if row else 0
                except Exception:
                    return 0

    async def set_user_fraction(self, user_id: int, fraction_tenths: int) -> None:
        # fraction in [0..9]
        value = max(0, min(9, int(fraction_tenths)))
        key = f"user_frac_{int(user_id)}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            await db.commit()

    # How-to text
    async def get_howto_text(self) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='howto_text'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else None

    async def set_howto_text(self, text: str) -> None:
        safe = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('howto_text', ?)\n                 ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (safe,),
            )
            await db.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        referrer_id: Optional[int] = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO users (id, username, first_name, last_name, referrer_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name
                """,
                (user_id, username, first_name, last_name, referrer_id),
            )
            await db.commit()

    async def set_terms_acceptance(self, user_id: int, accepted: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE users SET accepted_terms=? WHERE id=?",
                (1 if accepted else 0, user_id),
            )
            await db.commit()

    async def get_user_accepted_terms(self, user_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT accepted_terms FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return bool(int(row[0])) if row else False

    async def get_user_blocked(self, user_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT blocked FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return bool(int(row[0])) if row else False

    async def set_user_blocked(self, user_id: int, blocked: bool) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE users SET blocked=? WHERE id=?", (1 if blocked else 0, user_id))
            await db.commit()

    async def set_user_language(self, user_id: int, lang: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE users SET language=? WHERE id=?", (lang, user_id))
            await db.commit()

    async def get_user_language(self, user_id: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT language FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else "ru"

    async def get_user_balance(self, user_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT balance FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0

    async def increment_user_balance(self, user_id: int, amount: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
            await db.commit()

    async def add_generation_history(self, pid: str, user_id: int, category: str, params: str, input_photos: str, result_photo_id: str, input_paths: str = None, result_path: str = None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO generation_history (pid, user_id, category, params, input_photos, result_photo_id, input_paths, result_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, user_id, category, params, input_photos, result_photo_id, input_paths, result_path)
            )
            await db.commit()

    async def get_generation_by_pid(self, pid: str) -> tuple | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT * FROM generation_history WHERE pid=?", (pid,)) as cur:
                return await cur.fetchone()

    async def list_user_generations(self, user_id: int, limit: int = 20) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT pid, result_photo_id, created_at FROM generation_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ) as cur:
                return await cur.fetchall()

    async def get_user_subscription(self, user_id: int) -> tuple | None:
        async with aiosqlite.connect(self._db_path) as db:
            # Используем максимально надежное сравнение дат для SQLite (UTC)
            sql = """
                SELECT id, plan_type, expires_at, daily_limit, daily_usage, last_usage_reset, individual_api_key 
                FROM subscriptions 
                WHERE user_id=? AND datetime(expires_at) > CURRENT_TIMESTAMP
                ORDER BY expires_at DESC LIMIT 1
            """
            async with db.execute(sql, (user_id,)) as cur:
                sub = await cur.fetchone()
                if not sub:
                    # Попробуем найти любую последнюю подписку для лога
                    async with db.execute("SELECT expires_at FROM subscriptions WHERE user_id=? ORDER BY expires_at DESC LIMIT 1", (user_id,)) as cur_l:
                        last_exp = await cur_l.fetchone()
                        if last_exp:
                            logger.info(f"Subscription expired for user {user_id} at {last_exp[0]}")
                    return None
                
                sub_id, plan_type, expires_at, daily_limit, daily_usage, last_reset, ind_key = sub
                
                # Автоматический сброс лимита при наступлении нового дня (UTC)
                # last_reset хранится как 'YYYY-MM-DD HH:MM:SS'
                async with db.execute("SELECT date('now'), date(?)", (last_reset,)) as cur_d:
                    row_d = await cur_d.fetchone()
                    if row_d and row_d[0] != row_d[1]:
                        await db.execute(
                            "UPDATE subscriptions SET daily_usage=0, last_usage_reset=CURRENT_TIMESTAMP WHERE id=?",
                            (sub_id,)
                        )
                        await db.commit()
                        daily_usage = 0
                
                return plan_type, expires_at, daily_limit, daily_usage, ind_key

    async def update_daily_usage(self, user_id: int) -> bool:
        """Инкрементирует использование за день. Возвращает False, если лимит исчерпан."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, daily_limit, daily_usage, last_usage_reset FROM subscriptions WHERE user_id=? AND datetime(expires_at) > CURRENT_TIMESTAMP",
                (user_id,)
            ) as cur:
                sub = await cur.fetchone()
                if not sub:
                    return False
                sub_id, limit, usage, last_reset = sub
                
                # Сброс если новый день (UTC)
                async with db.execute("SELECT date('now'), date(?)", (last_reset,)) as cur_d:
                    row_d = await cur_d.fetchone()
                    if row_d and row_d[0] != row_d[1]:
                        await db.execute("UPDATE subscriptions SET daily_usage=1, last_usage_reset=CURRENT_TIMESTAMP WHERE id=?", (sub_id,))
                        await db.commit()
                        return True
                
                if usage >= limit:
                    return False
                
                await db.execute("UPDATE subscriptions SET daily_usage = daily_usage + 1 WHERE id=?", (sub_id,))
                await db.commit()
                return True

    async def get_referral_stats(self, user_id: int) -> tuple[int, int]:
        """Возвращает (кол-во рефералов, заработок)"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,)) as cur:
                count = (await cur.fetchone())[0]
            return count, 0

    async def user_exists(self, user_id: int) -> bool:
        """Проверяет, существует ли пользователь в базе"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT id FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row is not None
    
    async def get_stats(self) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            stats = {}
            # Пользователи
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                stats["total_users"] = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')") as cur:
                stats["today_users"] = (await cur.fetchone())[0]
            
            # Генерации
            async with db.execute("SELECT COUNT(*) FROM generation_history") as cur:
                stats["total_generations"] = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM generation_history WHERE date(created_at) = date('now')") as cur:
                stats["today_generations"] = (await cur.fetchone())[0]

            return stats

    async def list_users_page(self, offset: int, limit: int) -> list[tuple[int, str | None, int, int]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, username, blocked FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
                # Возвращаем 0 в качестве баланса для совместимости с интерфейсом, если нужно
                return [(int(r[0]), r[1], 0, int(r[2])) for r in rows]

    async def list_all_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT id FROM users") as cur:
                rows = await cur.fetchall()
                return [int(r[0]) for r in rows]

    async def _seed_prompts(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM prompts") as cur:
                row = await cur.fetchone()
                count = int(row[0]) if row else 0
            if count == 0:
                await db.executemany(
                    "INSERT INTO prompts (title, text) VALUES (?, ?)",
                    [
                        ("Студийный свет", "studio lighting, neutral background, soft shadows, fashion photography"),
                        ("Уличный стиль", "street style, natural light, urban background, candid fashion"),
                        ("Каталог", "ecommerce catalog photo, clean background, centered model, sharp focus"),
                    ],
                )
                await db.commit()

    # Models CRUD and queries
    async def add_model(self, category: str, cloth: str, name: str, prompt_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            # position = max(position)+1
            async with db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM models WHERE category=? AND cloth=?",
                (category, cloth),
            ) as cur:
                row = await cur.fetchone()
                position = int(row[0]) if row else 0
            await db.execute(
                "INSERT INTO models (category, cloth, name, prompt_id, position) VALUES (?,?,?,?,?)",
                (category, cloth, name, prompt_id, position),
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                row = await cur.fetchone()
                return int(row[0])

    async def delete_model(self, model_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM models WHERE id=?", (model_id,))
            await db.commit()

    async def set_model_prompt(self, model_id: int, prompt_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE models SET prompt_id=? WHERE id=?", (prompt_id, model_id))
            await db.commit()

    async def rename_model(self, model_id: int, name: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE models SET name=? WHERE id=?", (name, model_id))
            await db.commit()

    async def set_model_photo(self, model_id: int, file_id: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE models SET photo_file_id=? WHERE id=?", (file_id, model_id))
            await db.commit()

    async def list_models_page(self, category: str, cloth: str, offset: int, limit: int) -> list[tuple[int, str, int, int]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, name, prompt_id, position FROM models WHERE category=? AND cloth=? AND is_active=1 ORDER BY position, id LIMIT ? OFFSET ?",
                (category, cloth, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), str(r[1]), int(r[2]), int(r[3])) for r in rows]

    async def list_all_models_with_photo(self) -> list[tuple[int, str | None]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT id, photo_file_id FROM models WHERE is_active=1 AND photo_file_id IS NOT NULL") as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), (str(r[1]) if r[1] is not None else None)) for r in rows]

    async def count_models(self, category: str, cloth: str | None = None) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            if cloth and cloth != "all":
                # Для конкретного подтипа (например boy/girl) показываем и его, и универсальные 'all'
                async with db.execute(
                    "SELECT COUNT(*) FROM models WHERE category=? AND (cloth=? OR cloth='all') AND is_active=1",
                    (category, cloth),
                ) as cur:
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0
            else:
                # Если cloth="all" или None — показываем абсолютно всё в этой категории
                async with db.execute(
                    "SELECT COUNT(*) FROM models WHERE category=? AND is_active=1",
                    (category,),
                ) as cur:
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0

    async def list_prompts_page(self, offset: int, limit: int) -> list[tuple[int, str]]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT id, title FROM prompts ORDER BY id LIMIT ? OFFSET ?", (limit, offset)) as cur:
                rows = await cur.fetchall()
                return [(int(r[0]), str(r[1])) for r in rows]

    async def get_prompt_title(self, prompt_id: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT title FROM prompts WHERE id=?", (prompt_id,)) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else "—"

    async def add_prompt(self, title: str, text: str) -> int:
        # Страхуемся от пустых значений
        safe_title = (title or "Untitled").strip() or "Untitled"
        safe_text = (text or "").strip()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("INSERT INTO prompts (title, text) VALUES (?, ?)", (safe_title, safe_text))
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                row = await cur.fetchone()
                return int(row[0])

    async def get_prompt_text(self, prompt_id: int) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT text FROM prompts WHERE id=?", (prompt_id,)) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else ""

    async def get_model_by_index(self, category: str, cloth: str | None, index: int) -> tuple[int, str, int, str | None] | None:
        async with aiosqlite.connect(self._db_path) as db:
            if cloth and cloth != "all":
                sql = "SELECT id, name, prompt_id, photo_file_id FROM models WHERE category=? AND (cloth=? OR cloth='all') AND is_active=1 ORDER BY position, id LIMIT 1 OFFSET ?"
                params = (category, cloth, index)
            else:
                sql = "SELECT id, name, prompt_id, photo_file_id FROM models WHERE category=? AND is_active=1 ORDER BY position, id LIMIT 1 OFFSET ?"
                params = (category, index)
                
            async with db.execute(sql, params) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return int(row[0]), str(row[1]), int(row[2]), (str(row[3]) if row[3] is not None else None)

    # Subscription Plans CRUD
    async def _seed_subscription_plans(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM subscription_plans") as cur:
                if (await cur.fetchone())[0] == 0:
                    plans = [
                        ("2 ДНЯ", "2 DAYS", "2 NGÀY", 
                         "Доступ на 48 часов.\nДо 15 фото в день.\nПодходит для теста сервиса и разовых задач", 
                         "Access for 48 hours.\nUp to 15 photos per day.\nSuitable for testing the service and one-time tasks", 
                         "Truy cập trong 48 giờ.\nTối đa 15 ảnh mỗi ngày.\nPhù hợp để thử nghiệm dịch vụ và các nhiệm vụ một lần", 
                         849, 2, 15),
                        ("7 ДНЕЙ", "7 DAYS", "7 NGÀY", 
                         "Доступ на неделю.\nДо 12 фото в день.\nОптимально для небольших каталогов и регулярных генераций.", 
                         "Access for a week.\nUp to 12 photos per day.\nOptimal for small catalogs and regular generations.", 
                         "Truy cập trong một tuần.\nTối đa 12 ảnh mỗi ngày.\nTối ưu cho các danh mục nhỏ и tạo ảnh thường xuyên.", 
                         1990, 7, 12),
                        ("PRO", "PRO", "PRO", 
                         "Полный доступ на 30 дней.\nДо 30 фото в день.\nРазрешение 1K (1024×1024).\nДля активной работы с товарами и маркетплейсами.", 
                         "Full access for 30 days.\nUp to 30 photos per day.\n1K resolution (1024×1024).\nFor active work with products and marketplaces.", 
                         "Truy cập đầy đủ trong 30 ngày.\nTối đa 30 ảnh mỗi ngày.\nĐộ phân giải 1K (1024×1024).\nĐể làm việc tích cực với các sản phẩm và thị trường.", 
                         6490, 30, 30),
                        ("MAX", "MAX", "MAX", 
                         "Максимальная нагрузка без ограничений по сценариям.\nДо 60 фото в день.\nРазрешение 1K (1024×1024).\nДля продавцов с большим ассортиментом.", 
                         "Maximum load without scenario limitations.\nUp to 60 photos per day.\n1K resolution (1024×1024).\nFor sellers with a large assortment.", 
                         "Tải tối đa không giới hạn kịch bản.\nTối đa 60 ảnh mỗi ngày.\nĐộ phân giải 1K (1024×1024).\nDành cho người bán có danh mục hàng hóa lớn.", 
                         9990, 30, 60),
                        ("ULTRA 4K", "ULTRA 4K", "ULTRA 4K", 
                         "До 25 фото в день.\nРазрешение 4K (Ultra High Definition).\nМаксимальная резкость, детализация и фотореализм.\nДля премиальных карточек товаров и коммерческого использования.", 
                         "Up to 25 photos per day.\n4K resolution (Ultra High Definition).\nMaximum sharpness, detail, and photorealism.\nFor premium product cards and commercial use.", 
                         "Tối đa 25 ảnh mỗi ngày.\nĐộ phân giải 4K (Ultra High Definition).\nĐộ sắc nét, chi tiết и tính chân thực của ảnh tối đa.\nDành cho thẻ sản phẩm cao cấp и mục đích thương mại.", 
                         15990, 30, 25),
                        ("ULTRA BUSINESS 4K", "ULTRA BUSINESS 4K", "ULTRA BUSINESS 4K", 
                         "До 100 фото в день.\nРазрешение 4K (Ultra High Definition).\nМаксимальная резкость, детализация и фотореализм.\nПодходит для агентств, брендов и студий с высокой нагрузкой.", 
                         "Up to 100 photos per day.\n4K resolution (Ultra High Definition).\nMaximum sharpness, detail, and photorealism.\nSuitable for agencies, brands, and studios with high load.", 
                         "Tối đa 100 ảnh mỗi ngày.\nĐộ phân giải 4K (Ultra High Definition).\nĐộ sắc nét, chi tiết и tính chân thực của ảnh tối đa.\nPhù hợp với các đại lý, thương hiệu и studio có tải lượng cao.", 
                         44990, 30, 100),
                        ("ULTRA ENTERPRISE 4K", "ULTRA ENTERPRISE 4K", "ULTRA ENTERPRISE 4K", 
                         " • 250 фото в день\n • 4K Разрешение \n • максимальный приоритет поддержки\n • Выделенная линия генерации.", 
                         " • 250 photos per day\n • 4K Resolution \n • maximum support priority\n • Dedicated generation line.", 
                         " • 250 ảnh mỗi ngày\n • Độ phân giải 4K \n • ưu tiên hỗ trợ tối đa\n • Đường truyền tạo ảnh riêng biệt.", 
                         89990, 30, 250),
                    ]
                    await db.executemany(
                        "INSERT INTO subscription_plans (name_ru, name_en, name_vi, description_ru, description_en, description_vi, price, duration_days, daily_limit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        plans
                    )
                    await db.commit()

    async def list_subscription_plans(self) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT * FROM subscription_plans WHERE is_active=1") as cur:
                return await cur.fetchall()

    async def get_subscription_plan(self, plan_id: int) -> tuple | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT * FROM subscription_plans WHERE id=?", (plan_id,)) as cur:
                return await cur.fetchone()

    # Subscription Management
    async def grant_subscription(self, user_id: int, plan_id: int | None, plan_type: str, duration_days: int, daily_limit: int, amount: int = 0) -> None:
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(days=duration_days)
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self._db_path) as db:
            # Если оформляется платная подписка, триал сгорает (хотя он и так перекроется)
            await db.execute(
                "INSERT INTO subscriptions (user_id, plan_id, plan_type, expires_at, daily_limit) VALUES (?, ?, ?, ?, ?)",
                (user_id, plan_id, plan_type, expires_str, daily_limit)
            )
            
            # Записываем платеж
            if amount > 0:
                await db.execute(
                    "INSERT INTO payments (user_id, plan_id, amount) VALUES (?, ?, ?)",
                    (user_id, plan_id, amount)
                )

            # Если это не триал, помечаем что триал использован
            if plan_type != 'trial':
                await db.execute("UPDATE users SET trial_used=1 WHERE id=?", (user_id,))
            await db.commit()

    async def get_user_trial_status(self, user_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT trial_used FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return bool(row[0]) if row else True

    # PID Generation
    async def generate_pid(self) -> str:
        import random
        import string
        while True:
            pid = "PID" + "".join(random.choices(string.digits, k=8))
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute("SELECT 1 FROM generation_history WHERE pid=?", (pid,)) as cur:
                    if not await cur.fetchone():
                        return pid

    # History cleanup
    async def cleanup_old_generations(self, days: int = 7) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            # В реальности мы тут должны еще удалять файлы из TG, если нужно,
            # но пока просто удалим записи или пометим их
            # Для простоты просто возвращаем кол-во старых записей
            async with db.execute(
                "SELECT COUNT(*) FROM generation_history WHERE created_at < datetime('now', '-' || ? || ' days')",
                (days,)
            ) as cur:
                return (await cur.fetchone())[0]

    # API Key usage tracking
    async def check_api_key_limits(self, key_id: int) -> tuple[bool, str]:
        from datetime import datetime
        MAX_TOTAL_USAGE = 235  # Жесткий общий лимит на ключ
        MAX_DAILY_USAGE = 235  # Лимит в день (согласно запросу)
        MAX_MINUTE_USAGE = 20  # Лимит в минуту (согласно запросу)
        
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT daily_usage, total_usage, last_usage_reset FROM api_keys WHERE id=?", (key_id,)) as cur:
                row = await cur.fetchone()
                if not row: return False, "Key not found"
                daily_usage, total_usage, last_reset = row
                
                # Проверка общего лимита (235 фото)
                if total_usage is not None and total_usage >= MAX_TOTAL_USAGE:
                    # Автоматически деактивируем ключ при достижении лимита
                    await db.execute("UPDATE api_keys SET is_active=0 WHERE id=?", (key_id,))
                    await db.commit()
                    return False, f"Total limit {MAX_TOTAL_USAGE} reached"
                
                # Reset daily if needed
                if not last_reset or (isinstance(last_reset, str) and last_reset[:10] != datetime.now().isoformat()[:10]):
                    await db.execute("UPDATE api_keys SET daily_usage=0, last_usage_reset=CURRENT_TIMESTAMP WHERE id=?", (key_id,))
                    await db.commit()
                    daily_usage = 0
                
                # Проверка дневного лимита (235 фото в день)
                if daily_usage >= MAX_DAILY_USAGE:
                    return False, f"Daily limit {MAX_DAILY_USAGE} reached"
                
                # Проверка минутного лимита (20 в минуту)
                async with db.execute(
                    "SELECT COUNT(*) FROM api_usage_log WHERE key_id=? AND timestamp > datetime('now', '-1 minute')",
                    (key_id,)
                ) as cur_log:
                    minute_usage = (await cur_log.fetchone())[0]
                    if minute_usage >= MAX_MINUTE_USAGE:
                        return False, f"Minute limit {MAX_MINUTE_USAGE} reached"
            
            return True, ""

    async def record_api_usage(self, key_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("INSERT INTO api_usage_log (key_id) VALUES (?)", (key_id,))
            await db.execute("UPDATE api_keys SET daily_usage = daily_usage + 1, total_usage = total_usage + 1 WHERE id=?", (key_id,))
            await db.commit()

    async def record_api_error(self, key_id: int | None, api_key_preview: str, error_type: str, error_message: str, status_code: int | None = None, is_proxy_error: bool = False) -> None:
        """Записывает ошибку API ключа в базу данных"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO api_key_errors (key_id, api_key_preview, error_type, error_message, status_code, is_proxy_error) VALUES (?, ?, ?, ?, ?, ?)",
                (key_id, api_key_preview[:20], error_type, error_message[:500], status_code, 1 if is_proxy_error else 0)
            )
            await db.commit()

    async def get_recent_api_errors(self, limit: int = 10) -> list[tuple]:
        """Получает последние ошибки API ключей"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT key_id, api_key_preview, error_type, error_message, status_code, is_proxy_error, created_at FROM api_key_errors ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ) as cur:
                return await cur.fetchall()

    async def get_proxy_errors_count(self, hours: int = 24) -> int:
        """Получает количество ошибок прокси за последние N часов"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM api_key_errors WHERE is_proxy_error=1 AND created_at > datetime('now', '-' || ? || ' hours')",
                (hours,)
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0

    # Agreement and Instructions
    async def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else default

    async def get_all_app_settings(self) -> dict[str, str]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT key, value FROM app_settings") as cur:
                rows = await cur.fetchall()
                return {row[0]: row[1] for row in rows}

    async def get_agreement_text(self) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT value FROM app_settings WHERE key='agreement_text'") as cur:
                row = await cur.fetchone()
                return str(row[0]) if row else "Пользовательское соглашение не задано."

    async def set_agreement_text(self, text: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO app_settings (key, value) VALUES ('agreement_text', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (text,)
            )
            await db.commit()

    # Category and Steps Management
    async def list_categories(self, only_active: bool = False) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            sql = "SELECT id, key, name_ru, is_active, order_index FROM categories"
            if only_active:
                sql += " WHERE is_active=1"
            sql += " ORDER BY order_index, id"
            async with db.execute(sql) as cur:
                return await cur.fetchall()

    async def get_category_by_key(self, key: str) -> tuple | None:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT id, key, name_ru, is_active, order_index FROM categories WHERE key=?", (key,)) as cur:
                return await cur.fetchone()

    async def list_steps(self, category_id: int) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, step_key, question_text, input_type, is_optional, order_index FROM steps WHERE category_id=? ORDER BY order_index, id",
                (category_id,)
            ) as cur:
                return await cur.fetchall()

    async def list_step_options(self, step_id: int) -> list[tuple]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, option_text, option_value, order_index FROM step_options WHERE step_id=? ORDER BY order_index, id",
                (step_id,)
            ) as cur:
                return await cur.fetchall()

    async def add_category(self, key: str, name_ru: str, is_active: int = 1, order_index: int = 0) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO categories (key, name_ru, is_active, order_index) VALUES (?, ?, ?, ?)",
                (key, name_ru, is_active, order_index)
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                return (await cur.fetchone())[0]

    async def add_step(self, category_id: int, step_key: str, question_text: str, input_type: str, is_optional: int = 0, order_index: int = 0) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO steps (category_id, step_key, question_text, input_type, is_optional, order_index) VALUES (?, ?, ?, ?, ?, ?)",
                (category_id, step_key, question_text, input_type, is_optional, order_index)
            )
            await db.commit()
            async with db.execute("SELECT last_insert_rowid()") as cur:
                return (await cur.fetchone())[0]

    async def add_step_option(self, step_id: int, text: str, value: str, order_index: int = 0) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO step_options (step_id, option_text, option_value, order_index) VALUES (?, ?, ?, ?)",
                (step_id, text, value, order_index)
            )
            await db.commit()

    async def delete_step(self, step_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM step_options WHERE step_id=?", (step_id,))
            await db.execute("DELETE FROM steps WHERE id=?", (step_id,))
            await db.commit()

    async def update_step(self, step_id: int, question_text: str, input_type: str, is_optional: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE steps SET question_text=?, input_type=?, is_optional=? WHERE id=?",
                (question_text, input_type, is_optional, step_id)
            )
            await db.commit()

    async def _seed_categories(self) -> None:
        """Предзаполнение категорий и шагов текущей логикой"""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM categories") as cur:
                if (await cur.fetchone())[0] > 0:
                    return

        # 1. Готовые пресеты (общая база для female/male/child)
        cat_id = await self.add_category("presets", "👗 Пресеты (Готовые)", order_index=1)
        # Для пресетов мы сначала выбираем пол (внешний шаг), затем:
        s1 = await self.add_step(cat_id, "age", "🎂 Выберите возраст модели:", "buttons", order_index=1)
        await self.add_step_option(s1, "20-26 лет", "20_26", 1)
        await self.add_step_option(s1, "30-38 лет", "30_38", 2)
        await self.add_step_option(s1, "40-48 лет", "40_48", 3)
        await self.add_step_option(s1, "55-60 лет", "55_60", 4)
        
        s2 = await self.add_step(cat_id, "size", "📏 Выберите телосложение:", "buttons", order_index=2)
        # Опции размера зависят от пола, в динамике можно просто сделать текстовым или общим
        await self.add_step_option(s2, "Худощавое", "slender", 1)
        await self.add_step_option(s2, "Спортивное", "sporty", 2)
        await self.add_step_option(s2, "Среднее", "medium", 3)
        await self.add_step_option(s2, "Плотное", "large", 4)

        await self.add_step(cat_id, "height", "📏 Введите рост модели числом (например: 170):", "text", order_index=3)
        
        s3 = await self.add_step(cat_id, "pants_style", "👖 Выберите тип кроя штанов:", "buttons", is_optional=1, order_index=4)
        await self.add_step_option(s3, "Зауженные", "skinny", 1)
        await self.add_step_option(s3, "Классические", "classic", 2)
        await self.add_step_option(s3, "Свободные", "oversize", 3)

        s4 = await self.add_step(cat_id, "sleeve", "🧥 Выберите тип рукавов:", "buttons", is_optional=1, order_index=5)
        await self.add_step_option(s4, "Короткий", "short", 1)
        await self.add_step_option(s4, "Длинный", "long", 2)
        await self.add_step_option(s4, "Без рукавов", "none", 3)

        await self.add_step(cat_id, "length", "📏 Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать.", "buttons", is_optional=1, order_index=6)
        # Опции длины обычно с картинками, в БД храним текст/значение
        
        s5 = await self.add_step(cat_id, "pose", "💃 Выберите тип позы:", "buttons", order_index=7)
        await self.add_step_option(s5, "Обычная", "normal", 1)
        await self.add_step_option(s5, "Нестандартная", "unusual", 2)
        await self.add_step_option(s5, "Вульгарная", "vulgar", 3)

        s6 = await self.add_step(cat_id, "dist", "👁️ Выберите ракурс фотографии:", "buttons", is_optional=1, order_index=8)
        await self.add_step_option(s6, "Близкий", "close", 1)
        await self.add_step_option(s6, "Средний", "medium", 2)
        await self.add_step_option(s6, "Дальний", "far", 3)

        s7 = await self.add_step(cat_id, "view", "📸 Выберите вид фотографии:", "buttons", order_index=9)
        await self.add_step_option(s7, "Спереди", "front", 1)
        await self.add_step_option(s7, "Сзади", "back", 2)

        s8 = await self.add_step(cat_id, "season", "🍂 Выберите сезон:", "buttons", is_optional=1, order_index=10)
        await self.add_step_option(s8, "Лето", "summer", 1)
        await self.add_step_option(s8, "Зима", "winter", 2)
        await self.add_step_option(s8, "Осень", "autumn", 3)
        await self.add_step_option(s8, "Весна", "spring", 4)

        await self.add_step(cat_id, "photo", "📸 Пожалуйста пришлите фотографию вашего товара:", "photo", order_index=11)
        await self.add_step(cat_id, "aspect", "📐 Выберите формат (соотношение сторон):", "buttons", order_index=12)

        # 2. Одежда и обувь РАНДОМ
        cat_id = await self.add_category("random", "🎲 Одежда и обувь РАНДОМ", order_index=2)
        await self.add_step(cat_id, "rand_loc_group", "📍 Выберите тип локации:", "buttons", order_index=1)
        await self.add_step(cat_id, "rand_gender", "👤 Выберите пол модели:", "buttons", order_index=2)
        # Далее шаги как в пресетах (age, size, height, body_type_num, pants, sleeve, length, pose, dist, view, season, holiday, photo, aspect)
        # Для простоты сида добавлю только ключевые отличия
        
        # 3. Рандом прочие категории
        cat_id = await self.add_category("random_other", "📦 Рандом · Прочие категории", order_index=3)
        s_hp = await self.add_step(cat_id, "has_person", "👤 Присутствует ли человек на фото?", "buttons", order_index=1)
        await self.add_step_option(s_hp, "Да", "yes", 1)
        await self.add_step_option(s_hp, "Нет", "no", 2)
        
        await self.add_step(cat_id, "gender", "👤 Выберите пол:", "buttons", order_index=2)
        await self.add_step(cat_id, "info_load", "📊 Введите нагруженность фотографии (1-10):", "text", order_index=3)
        await self.add_step(cat_id, "product_name", "🏷️ Введите название продукта:", "text", order_index=4)
        await self.add_step(cat_id, "angle", "📐 Выберите угол камеры (Спереди/Сзади):", "buttons", order_index=5)
        await self.add_step(cat_id, "dist", "👁️ Выберите ракурс (Дальний/Средний/Близкий):", "buttons", order_index=6)
        await self.add_step(cat_id, "rand_height", "📏 Введите высоту (см):", "text", is_optional=1, order_index=7)
        await self.add_step(cat_id, "rand_width", "📏 Введите ширину (см):", "text", is_optional=1, order_index=8)
        await self.add_step(cat_id, "rand_length", "📏 Введите длину (см):", "text", is_optional=1, order_index=9)
        await self.add_step(cat_id, "season", "🍂 Выберите сезон:", "buttons", is_optional=1, order_index=10)
        await self.add_step(cat_id, "style", "🎨 Выберите стиль:", "buttons", is_optional=1, order_index=11)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=12)

        # 4. Инфографика одежда
        cat_id = await self.add_category("infographic_clothing", "👕 Инфогр: Одежда и обувь", order_index=4)
        await self.add_step(cat_id, "info_gender", "👤 Выберите пол:", "buttons", order_index=1)
        await self.add_step(cat_id, "age", "🔢 Введите возраст модели числом:", "text", order_index=2)
        await self.add_step(cat_id, "info_load", "📊 Введите нагруженность инфографики (1-10):", "text", order_index=3)
        
        s_lang = await self.add_step(cat_id, "info_lang", "🌐 Выберите язык для инфографики:", "buttons", is_optional=1, order_index=4)
        await self.add_step_option(s_lang, "Русский", "Russian", 1)
        await self.add_step_option(s_lang, "English", "English", 2)
        await self.add_step_option(s_lang, "Вьетнамский", "Vietnamese", 3)
        await self.add_step_option(s_lang, "Китайский", "Chinese", 4)
        await self.add_step_option(s_lang, "Свой вариант", "custom", 5)

        await self.add_step(cat_id, "info_brand", "🏷️ Название товара/бренда (до 50 симв):", "text", order_index=5)
        await self.add_step(cat_id, "info_adv1", "✨ Преимущество 1 (до 100 симв):", "text", is_optional=1, order_index=6)
        await self.add_step(cat_id, "info_adv2", "✨ Преимущество 2 (до 100 симв):", "text", is_optional=1, order_index=7)
        await self.add_step(cat_id, "info_adv3", "✨ Преимущество 3 (до 100 симв):", "text", is_optional=1, order_index=8)
        await self.add_step(cat_id, "info_extra", "➕ Доп. текст (до 65 симв):", "text", is_optional=1, order_index=9)
        
        await self.add_step(cat_id, "size", "📏 Телосложение модели:", "buttons", order_index=10)
        await self.add_step(cat_id, "height", "📏 Рост модели (числом):", "text", order_index=11)
        await self.add_step(cat_id, "body_type", "⚖️ Телосложение (от 1 до 10):", "text", order_index=12)
        await self.add_step(cat_id, "pants_style", "👖 Тип кроя штанов:", "buttons", is_optional=1, order_index=13)
        await self.add_step(cat_id, "sleeve", "🧥 Тип рукавов:", "buttons", is_optional=1, order_index=14)
        await self.add_step(cat_id, "info_angle", "📐 Угол камеры (Спереди/Сзади):", "buttons", order_index=15)
        await self.add_step(cat_id, "info_dist", "👁️ Ракурс (Дальний/Средний/Близкий):", "buttons", order_index=16)
        await self.add_step(cat_id, "info_pose", "💃 Поза модели:", "buttons", order_index=17)
        await self.add_step(cat_id, "length", "📏 Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать.", "buttons", is_optional=1, order_index=18)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=19)
        await self.add_step(cat_id, "aspect", "📐 Выбор формата:", "buttons", order_index=20)

        # 5. Инфографика прочее
        cat_id = await self.add_category("infographic_other", "📦 Инфогр: Остальные товары", order_index=5)
        s_hp2 = await self.add_step(cat_id, "has_person", "👤 Присутствует ли человек на фото?", "buttons", order_index=1)
        await self.add_step_option(s_hp2, "Да", "yes", 1)
        await self.add_step_option(s_hp2, "Нет", "no", 2)
        
        await self.add_step(cat_id, "info_gender", "👤 Выберите пол:", "buttons", order_index=2)
        await self.add_step(cat_id, "age", "🔢 Возраст модели:", "text", order_index=3)
        await self.add_step(cat_id, "info_pose", "🧘 Поза модели:", "buttons", order_index=4)
        await self.add_step(cat_id, "info_load", "📊 Нагруженность (1-10):", "text", order_index=5)
        
        s_lang2 = await self.add_step(cat_id, "info_lang", "🌐 Язык для инфографики:", "buttons", is_optional=1, order_index=6)
        await self.add_step_option(s_lang2, "Русский", "Russian", 1)
        await self.add_step_option(s_lang2, "English", "English", 2)
        
        await self.add_step(cat_id, "info_brand", "🏷️ Название товара/бренда:", "text", order_index=7)
        await self.add_step(cat_id, "info_adv1", "✨ Преимущества:", "text", is_optional=1, order_index=8)
        await self.add_step(cat_id, "info_extra", "➕ Доп. текст:", "text", is_optional=1, order_index=9)
        await self.add_step(cat_id, "info_angle", "📐 Угол камеры:", "buttons", order_index=10)
        await self.add_step(cat_id, "info_dist", "👁️ Ракурс:", "buttons", order_index=11)
        await self.add_step(cat_id, "info_season", "🍂 Сезон:", "buttons", is_optional=1, order_index=12)
        await self.add_step(cat_id, "info_holiday", "🎉 Праздник:", "buttons", is_optional=1, order_index=13)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=14)
        
        # 6. Витринное фото
        cat_id = await self.add_category("storefront", "📸 Витринное фото", order_index=6)
        await self.add_step(cat_id, "angle", "📐 Угол камеры (Спереди/Сзади):", "buttons", order_index=1)
        await self.add_step(cat_id, "dist", "👁️ Ракурс (Дальний/Средний/Близкий):", "buttons", order_index=2)
        await self.add_step(cat_id, "length", "📏 Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать.", "buttons", is_optional=1, order_index=3)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=4)

        # 7. На белом фоне
        cat_id = await self.add_category("whitebg", "⬜ На белом фоне", order_index=7)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=1)
        await self.add_step(cat_id, "aspect", "📐 Выберите формат:", "buttons", order_index=2)

        # 8. Свой вариант модели
        cat_id = await self.add_category("own", "💃 Свой вариант модели", order_index=8)
        await self.add_step(cat_id, "length", "📏 Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать.", "buttons", order_index=1)
        await self.add_step(cat_id, "sleeve", "🧥 Тип рукавов:", "buttons", is_optional=1, order_index=2)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=3)

        # 9. Свой вариант фона
        cat_id = await self.add_category("own_variant", "🖼️ Свой вариант фона", order_index=9)
        await self.add_step(cat_id, "bg_photo", "📸 Пришлите фото фона:", "photo", order_index=1)
        await self.add_step(cat_id, "photo", "📸 Пришлите фото товара:", "photo", order_index=2)
        await self.add_step(cat_id, "sleeve", "🧥 Длина рукава:", "buttons", order_index=3)
        await self.add_step(cat_id, "length", "📏 Выберите длину изделия. Внимание! если ваш продукт Костюм 2-к, 3-к то длину можно не указывать.", "buttons", order_index=4)
        await self.add_step(cat_id, "aspect", "📐 Выбор формата:", "buttons", order_index=5)



