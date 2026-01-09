from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def terms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Принять.", callback_data="accept_terms")]
        ]
    )


def subscription_check_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=channel_url)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data="check_subscription")]
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Для маркетплейсов", callback_data="menu_market")],
            [InlineKeyboardButton(text="Профиль", callback_data="menu_profile")],
            [InlineKeyboardButton(text="Инструкция", callback_data="menu_howto")],
            [InlineKeyboardButton(text="Настройки", callback_data="menu_settings")]
        ]
    )


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Баланс", callback_data="menu_balance")],
            [InlineKeyboardButton(text="Подписка", callback_data="menu_subscription")],
            [InlineKeyboardButton(text="История генерации", callback_data="menu_history")],
            [InlineKeyboardButton(text="Заработать вместе с нами", callback_data="menu_referral")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")]
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Выбор языка", callback_data="settings_lang")],
            [InlineKeyboardButton(text="Выбор качества", callback_data="settings_quality")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")]
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="lang:ru")],
            [InlineKeyboardButton(text="English", callback_data="lang:en")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_settings")]
        ]
    )


def marketplace_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пресеты для одежды", callback_data="menu_create")],
            [InlineKeyboardButton(text="Одежда и обувь", callback_data="create_random")],
            [InlineKeyboardButton(text="Свой вариант модели", callback_data="create_own_variant")],
            [InlineKeyboardButton(text="Свой вариант фона", callback_data="create_own_bg")],
            [InlineKeyboardButton(text="Генерация для всех продуктов", callback_data="create_all_products")],
            [InlineKeyboardButton(text="Инфографика", callback_data="create_infographics")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_main")]
        ]
    )


def plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="2 дня — 649 ₽", callback_data="buy_plan:2days")],
            [InlineKeyboardButton(text="7 дней — 1990 ₽", callback_data="buy_plan:7days")],
            [InlineKeyboardButton(text="PRO — 5490 ₽", callback_data="buy_plan:pro")],
            [InlineKeyboardButton(text="MAX — 9990 ₽", callback_data="buy_plan:max")],
            [InlineKeyboardButton(text="ULTRA 4K — 15990 ₽", callback_data="buy_plan:ultra_4k")],
            [InlineKeyboardButton(text="ULTRA BUSINESS 4K — 44990 ₽", callback_data="buy_plan:ultra_business_4k")],
            [InlineKeyboardButton(text="ULTRA ENTERPRISE 4K — 89990 ₽", callback_data="buy_plan:ultra_enterprise_4k")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_profile")]
        ]
    )


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="Пользователи", callback_data="admin_users_page:0"), InlineKeyboardButton(text="Поиск по ID", callback_data="admin_user_search")],
            [InlineKeyboardButton(text="Модели", callback_data="admin_models")],
            [InlineKeyboardButton(text="Категории", callback_data="admin_categories")],
            [InlineKeyboardButton(text="💰 Цены категорий", callback_data="admin_category_prices")],
            [InlineKeyboardButton(text="Промты 'Пробовать своё'", callback_data="admin_own_prompts")],
            [InlineKeyboardButton(text="Промт 'Свой вариант'", callback_data="admin_own_variant_prompts")],
            [InlineKeyboardButton(text="Текст помощи", callback_data="admin_howto_edit")],
            [InlineKeyboardButton(text="API ключи Gemini", callback_data="admin_api_keys")],
            [InlineKeyboardButton(text="API ключи 'Свой вариант'", callback_data="admin_own_variant_api_keys")],
            [InlineKeyboardButton(text="📋 Логи сервера", callback_data="admin_logs"), InlineKeyboardButton(text="🌐 Состояние прокси", callback_data="admin_proxy_status")],
            [InlineKeyboardButton(text="Включить техработы", callback_data="admin_maint_on"), InlineKeyboardButton(text="Выключить техработы", callback_data="admin_maint_off")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="16 Токенов — 500 ₽", callback_data="buy_tokens:16")],
            [InlineKeyboardButton(text="35 Токенов — 1000 ₽", callback_data="buy_tokens:35")],
            [InlineKeyboardButton(text="215 Токенов — 4990 ₽", callback_data="buy_tokens:215")],
            [InlineKeyboardButton(text="525 Токенов — 9990 ₽ (Выгодно)", callback_data="buy_tokens:525")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_profile")],
        ]
    )


def referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пригласить друга", callback_data="ref_invite")],
            [InlineKeyboardButton(text="Статистика", callback_data="ref_stats")],
            [InlineKeyboardButton(text="Вывод", callback_data="ref_withdraw")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_profile")],
        ]
    )


def withdraw_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Запросить вывод", callback_data="ref_withdraw_request")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_referral")],
        ]
    )


def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Стандарт (HD)", callback_data="quality:hd")],
            [InlineKeyboardButton(text="Премиум (2K)", callback_data="quality:2k")],
            [InlineKeyboardButton(text="Ультра (4K)", callback_data="quality:4k")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_settings")],
        ]
    )


def admin_api_keys_keyboard(keys: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key_id, token, is_active in keys:
        masked = (token[:4] + "…" + token[-4:]) if len(token) > 8 else ("…" + token)
        status = "✅" if is_active else "⛔"
        rows.append([
            InlineKeyboardButton(text=f"{status} #{key_id} {masked}", callback_data="noop"),
            InlineKeyboardButton(text="Показать", callback_data=f"api_key_show:{key_id}"),
            InlineKeyboardButton(text="Изм.", callback_data=f"api_key_edit:{key_id}"),
        ])
        rows.append([
            InlineKeyboardButton(text=("Откл" if is_active else "Вкл"), callback_data=f"api_key_toggle:{key_id}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"api_key_delete:{key_id}"),
        ])
    rows.append([InlineKeyboardButton(text="Добавить ключ", callback_data="api_key_add")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_users_keyboard(users: list[tuple[int, str | None, int, int]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for uid, username, balance, blocked in users:
        uname = f"@{username}" if username else "—"
        status = "⛔" if blocked else "✅"
        rows.append([
            InlineKeyboardButton(text=f"{status} ID {uid} {uname} • {balance}", callback_data=f"admin_user:{uid}")
        ])
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_users_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"admin_users_page:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_user_history_keyboard(user_id: int, page: int, has_next: bool) -> InlineKeyboardMarkup:
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_user_history:{user_id}:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_user_history:{user_id}:{page+1}"))
    rows: list[list[InlineKeyboardButton]] = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_user:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_categories_keyboard(status: dict[str, bool]) -> InlineKeyboardMarkup:
    def label(name: str, ru: str) -> str:
        return ("✅ " if status.get(name, True) else "⛔ ") + ru
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label("female", "Женская"), callback_data="admin_toggle_cat:female"), InlineKeyboardButton(text=label("male", "Мужская"), callback_data="admin_toggle_cat:male")],
            [InlineKeyboardButton(text=label("child", "Детская"), callback_data="admin_toggle_cat:child")],
            [InlineKeyboardButton(text=label("storefront", "Витринное фото"), callback_data="admin_toggle_cat:storefront"), InlineKeyboardButton(text=label("whitebg", "На белом фоне"), callback_data="admin_toggle_cat:whitebg")],
            [InlineKeyboardButton(text=label("random", "Одежда и обувь"), callback_data="admin_toggle_cat:random")],
            [InlineKeyboardButton(text=label("own", "Пробовать своё"), callback_data="admin_toggle_cat:own")],
            [InlineKeyboardButton(text=label("own_variant", "Свой вариант"), callback_data="admin_toggle_cat:own_variant")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_main")],
        ]
    )


def admin_category_prices_keyboard(prices: dict[str, int]) -> InlineKeyboardMarkup:
    """Клавиатура для управления ценами категорий"""
    def format_price(tenths: int) -> str:
        """Форматирует цену в десятых долях токена в читаемый вид"""
        if tenths % 10 == 0:
            return f"{tenths // 10} токен"
        else:
            return f"{tenths / 10:.1f} токена"
    
    category_names = {
        "female": "Женская",
        "male": "Мужская",
        "child": "Детская",
        "storefront": "Витринное фото",
        "whitebg": "На белом фоне",
        "random": "Одежда и обувь",
        "own": "Пробовать своё",
        "own_variant": "Свой вариант",
    }
    
    rows: list[list[InlineKeyboardButton]] = []
    for cat_key, cat_name in category_names.items():
        price = prices.get(cat_key, 10)
        price_str = format_price(price)
        rows.append([
            InlineKeyboardButton(text=f"{cat_name}: {price_str}", callback_data=f"admin_price_edit:{cat_key}")
        ])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_models_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Список по категории", callback_data="admin_models_browse")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )

def admin_own_prompts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Шаг 1 — Описание модели", callback_data="admin_own_prompt_edit:1")],
            [InlineKeyboardButton(text="Шаг 3 — Финальная генерация", callback_data="admin_own_prompt_edit:3")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_main")],
        ]
    )


def admin_own_variant_prompts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Просмотреть текущий промт", callback_data="admin_own_variant_prompt_view")],
            [InlineKeyboardButton(text="Редактировать промт 'Свой вариант'", callback_data="admin_own_variant_prompt_edit")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_main")],
        ]
    )


def admin_own_variant_api_keys_keyboard(keys: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key_id, token, is_active in keys:
        masked = (token[:4] + "…" + token[-4:]) if len(token) > 8 else ("…" + token)
        status = "✅" if is_active else "⛔"
        rows.append([
            InlineKeyboardButton(text=f"{status} #{key_id} {masked}", callback_data="noop"),
            InlineKeyboardButton(text="Показать", callback_data=f"own_variant_api_key_show:{key_id}"),
            InlineKeyboardButton(text="Изм.", callback_data=f"own_variant_api_key_edit:{key_id}"),
        ])
        rows.append([
            InlineKeyboardButton(text=("Откл" if is_active else "Вкл"), callback_data=f"own_variant_api_key_toggle:{key_id}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"own_variant_api_key_delete:{key_id}"),
        ])
    rows.append([InlineKeyboardButton(text="Добавить ключ", callback_data="own_variant_api_key_add")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_models_category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👱‍♀️ Женская", callback_data="admin_cat:female"), InlineKeyboardButton(text="👨 Мужская", callback_data="admin_cat:male")],
            [InlineKeyboardButton(text="🧒 Детская", callback_data="admin_cat:child")],
            [InlineKeyboardButton(text="🏬 Витринное фото", callback_data="admin_cat:storefront"), InlineKeyboardButton(text="⚪ На белом фоне", callback_data="admin_cat:whitebg")],
            [InlineKeyboardButton(text="👕 Одежда и обувь", callback_data="admin_cat:random")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_models")],
        ]
    )


def admin_models_cloth_keyboard(category: str) -> InlineKeyboardMarkup:
    if category in ("whitebg",):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Загрузить промт (белый фон)", callback_data="admin_base_prompt:whitebg")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
            ]
        )
    if category == "random":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Загрузить промт (рандом)", callback_data="admin_base_prompt:random")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
            ]
        )
    if category == "storefront":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Фон витрины", callback_data=f"admin_cloth:{category}:bg")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
            ]
        )
    # Для женской категории показываем полный набор как в пользовательском меню
    if category == "female":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Куртка (Пальто)", callback_data=f"admin_cloth:{category}:coat"), InlineKeyboardButton(text="Платье", callback_data=f"admin_cloth:{category}:dress")],
                [InlineKeyboardButton(text="Штаны", callback_data=f"admin_cloth:{category}:pants"), InlineKeyboardButton(text="Шорты", callback_data=f"admin_cloth:{category}:shorts")],
                [InlineKeyboardButton(text="Верхняя одежда", callback_data=f"admin_cloth:{category}:top"), InlineKeyboardButton(text="Домашняя одежда", callback_data=f"admin_cloth:{category}:loungewear")],
                [InlineKeyboardButton(text="Костюм", callback_data=f"admin_cloth:{category}:suit"), InlineKeyboardButton(text="Комбинезон", callback_data=f"admin_cloth:{category}:overall")],
                [InlineKeyboardButton(text="Юбка", callback_data=f"admin_cloth:{category}:skirt"), InlineKeyboardButton(text="Обувь", callback_data=f"admin_cloth:{category}:shoes")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
            ]
        )
    # Иначе — общий список
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Куртка (Пальто)", callback_data=f"admin_cloth:{category}:coat"), InlineKeyboardButton(text="Платье" if category in ("female","child") else "Штаны", callback_data=f"admin_cloth:{category}:{'dress' if category in ('female','child') else 'pants'}")],
            [InlineKeyboardButton(text="Шорты", callback_data=f"admin_cloth:{category}:shorts"), InlineKeyboardButton(text="Костюм", callback_data=f"admin_cloth:{category}:suit")],
            [InlineKeyboardButton(text="Верхняя одежда", callback_data=f"admin_cloth:{category}:top"), InlineKeyboardButton(text="Домашняя одежда", callback_data=f"admin_cloth:{category}:loungewear")],
            [InlineKeyboardButton(text="Комбинезон", callback_data=f"admin_cloth:{category}:overall"), InlineKeyboardButton(text="Обувь" if category != 'female' else "Юбка", callback_data=f"admin_cloth:{category}:{'shoes' if category != 'female' else 'skirt'}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
        ]
    )


def admin_models_actions_keyboard(category: str, cloth: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить модель", callback_data=f"admin_model_add:{category}:{cloth}")],
            [InlineKeyboardButton(text="Список моделей", callback_data=f"admin_model_list:{category}:{cloth}:0")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_models_browse")],
        ]
    )


def admin_model_list_keyboard(category: str, cloth: str, items: list[tuple[int, str, str]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for model_id, name, prompt_title in items:
        rows.append([InlineKeyboardButton(text=f"#{model_id} {name} • {prompt_title}", callback_data=f"admin_model_edit:{model_id}")])
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_model_list:{category}:{cloth}:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_model_list:{category}:{cloth}:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_models_actions:{category}:{cloth}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_model_edit_keyboard(model_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить промт", callback_data=f"admin_model_prompt:{model_id}:0")],
            [InlineKeyboardButton(text="Переименовать", callback_data=f"admin_model_rename:{model_id}")],
            [InlineKeyboardButton(text="Обновить фото", callback_data=f"admin_model_setphoto:{model_id}")],
            [InlineKeyboardButton(text="Удалить", callback_data=f"admin_model_delete:{model_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"admin_model_backlist")],
        ]
    )


def admin_prompt_pick_keyboard(model_id: int, prompts: list[tuple[int, str]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for pid, title in prompts:
        rows.append([InlineKeyboardButton(text=f"#{pid} {title}", callback_data=f"admin_model_setprompt:{model_id}:{pid}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_model_prompt:{model_id}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_model_prompt:{model_id}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_model_edit:{model_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_add_prompt_pick_keyboard(category: str, cloth: str, prompts: list[tuple[int, str]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for pid, title in prompts:
        rows.append([InlineKeyboardButton(text=f"#{pid} {title}", callback_data=f"admin_model_add_setprompt:{category}:{cloth}:{pid}")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_model_add_prompt:{category}:{cloth}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_model_add_prompt:{category}:{cloth}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_models_actions:{category}:{cloth}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_model_created_keyboard(category: str, cloth: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать ещё одну модель для этого типа одежды", callback_data=f"admin_model_add:{category}:{cloth}")],
            [InlineKeyboardButton(text="В главное меню администратора", callback_data="admin_main")],
        ]
    )


def admin_user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="+10", callback_data=f"admin_add:{user_id}:10"),
                InlineKeyboardButton(text="+50", callback_data=f"admin_add:{user_id}:50"),
                InlineKeyboardButton(text="+100", callback_data=f"admin_add:{user_id}:100"),
            ],
            [
                InlineKeyboardButton(text="-10", callback_data=f"admin_add:{user_id}:-10"),
                InlineKeyboardButton(text="-50", callback_data=f"admin_add:{user_id}:-50"),
                InlineKeyboardButton(text="-100", callback_data=f"admin_add:{user_id}:-100"),
            ],
            [
                InlineKeyboardButton(text="Заблокировать", callback_data=f"admin_block:{user_id}:1"),
                InlineKeyboardButton(text="Разблокировать", callback_data=f"admin_block:{user_id}:0"),
            ],
            [InlineKeyboardButton(text="📜 История", callback_data=f"admin_user_history:{user_id}:0")],
            [InlineKeyboardButton(text="⤴️ К списку", callback_data="admin_users_page:0")],
        ]
    )


def create_product_keyboard(prices: dict[str, int] | None = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора категории с ценами из БД или значениями по умолчанию"""
    def format_price(cat: str, default: int) -> str:
        if prices:
            price_tenths = prices.get(cat, default)
        else:
            price_tenths = default
        if price_tenths % 10 == 0:
            return f"{price_tenths // 10} токен"
        else:
            return f"{price_tenths / 10:.1f} токена"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"👱‍♀️ Женская • {format_price('female', 10)}", callback_data="create_cat:female"),
                InlineKeyboardButton(text=f"👨 Мужская • {format_price('male', 10)}", callback_data="create_cat:male"),
            ],
            [InlineKeyboardButton(text=f"🧒 Детская одежда • {format_price('child', 10)}", callback_data="create_cat:child")],
            [
                InlineKeyboardButton(text=f"🏬 Витринное фото • {format_price('storefront', 10)}", callback_data="create_cat:storefront"),
                InlineKeyboardButton(text=f"⚪ На белом фоне • {format_price('whitebg', 10)}", callback_data="create_cat:whitebg"),
            ],
            [InlineKeyboardButton(text=f"👕 Одежда и обувь • {format_price('random', 10)}", callback_data="create_random")],
            [InlineKeyboardButton(text=f"🧪 Попробовать своё • {format_price('own', 12)}", callback_data="create_own")],
            [InlineKeyboardButton(text=f"✨ Свой вариант • {format_price('own_variant', 20)}", callback_data="create_own_variant")],
        ]
    )


def create_product_keyboard_dynamic(enabled: dict[str, bool], prices: dict[str, int] | None = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора категории с учетом отключенных разделов и цен из БД"""
    def format_price(cat: str, default: int) -> str:
        if prices:
            price_tenths = prices.get(cat, default)
        else:
            price_tenths = default
        if price_tenths % 10 == 0:
            return f"{price_tenths // 10} токен"
        else:
            return f"{price_tenths / 10:.1f} токена"
    
    rows: list[list[InlineKeyboardButton]] = []
    row1: list[InlineKeyboardButton] = []
    # Проверяем что категория есть в словаре и включена (по умолчанию True если ключа нет)
    if enabled.get("female") is not False:
        row1.append(InlineKeyboardButton(text=f"👱‍♀️ Женская • {format_price('female', 10)}", callback_data="create_cat:female"))
    if enabled.get("male") is not False:
        row1.append(InlineKeyboardButton(text=f"👨 Мужская • {format_price('male', 10)}", callback_data="create_cat:male"))
    if row1:
        rows.append(row1)
    if enabled.get("child") is not False:
        rows.append([InlineKeyboardButton(text=f"🧒 Детская одежда • {format_price('child', 10)}", callback_data="create_cat:child")])
    row3: list[InlineKeyboardButton] = []
    if enabled.get("storefront") is not False:
        row3.append(InlineKeyboardButton(text=f"🏬 Витринное фото • {format_price('storefront', 10)}", callback_data="create_cat:storefront"))
    if enabled.get("whitebg") is not False:
        row3.append(InlineKeyboardButton(text=f"⚪ На белом фоне • {format_price('whitebg', 10)}", callback_data="create_cat:whitebg"))
    if row3:
        rows.append(row3)
    if enabled.get("random") is not False:
        rows.append([InlineKeyboardButton(text=f"👕 Одежда и обувь • {format_price('random', 10)}", callback_data="create_random")])
    if enabled.get("own") is not False:
        rows.append([InlineKeyboardButton(text=f"🧪 Попробовать своё • {format_price('own', 12)}", callback_data="create_own")])
    if enabled.get("own_variant") is not False:
        rows.append([InlineKeyboardButton(text=f"✨ Свой вариант • {format_price('own_variant', 20)}", callback_data="create_own_variant")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Главное меню", callback_data="back_main")]]
    )


def model_select_keyboard(category: str, cloth: str, index: int, total: int = 31) -> InlineKeyboardMarkup:
    prev_idx = index - 1
    next_idx = index + 1
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"model_nav:{category}:{cloth}:{prev_idx}"),
                InlineKeyboardButton(text="✅", callback_data=f"model_pick:{category}:{cloth}:{index}"),
                InlineKeyboardButton(text="➡️", callback_data=f"model_nav:{category}:{cloth}:{next_idx}"),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def form_age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="20-26", callback_data="form_age:20_26"), InlineKeyboardButton(text="30-38", callback_data="form_age:30_38")],
            [InlineKeyboardButton(text="40-48", callback_data="form_age:40_48"), InlineKeyboardButton(text="55-60", callback_data="form_age:55_60")],
        ]
    )


def form_size_keyboard(category: str | None = None) -> InlineKeyboardMarkup:
    # Для детской одежды убираем кнопку 'Вульгарный' (которая здесь соответствует Пышная/Очень пышная в некоторых контекстах)
    # По ТЗ просто удаляем кнопку 'Вульгарный', если она была.
    rows = []
    if category == "child":
        rows.append([InlineKeyboardButton(text="Обычное", callback_data="form_size:normal")])
    elif category == "male":
        rows.append([InlineKeyboardButton(text="Худой", callback_data="form_size:thin"), InlineKeyboardButton(text="Пышный", callback_data="form_size:curvy")])
        rows.append([InlineKeyboardButton(text="Очень пышный", callback_data="form_size:plus")])
    else:
        rows.append([InlineKeyboardButton(text="Худая", callback_data="form_size:thin"), InlineKeyboardButton(text="Пышная", callback_data="form_size:curvy")])
        rows.append([InlineKeyboardButton(text="Очень пышная", callback_data="form_size:plus")])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def form_length_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="form_len:skip")]])


def own_variant_length_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="own_variant_length:skip")]])


def own_variant_product_view_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора части товара на фото"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Передняя", callback_data="own_variant_view:front")],
            [InlineKeyboardButton(text="Задняя", callback_data="own_variant_view:back")],
            [InlineKeyboardButton(text="Боковая", callback_data="own_variant_view:side")],
            [InlineKeyboardButton(text="Пропустить", callback_data="own_variant_view:skip")],
        ]
    )


def garment_length_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора длины изделия на основе изображения-гайда"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Короткий топ", callback_data="garment_len:short_top")],
            [InlineKeyboardButton(text="Обычный топ", callback_data="garment_len:regular_top")],
            [InlineKeyboardButton(text="До талии", callback_data="garment_len:to_waist")],
            [InlineKeyboardButton(text="Ниже талии", callback_data="garment_len:below_waist")],
            [InlineKeyboardButton(text="До середины бедра", callback_data="garment_len:mid_thigh")],
            [InlineKeyboardButton(text="До колен", callback_data="garment_len:to_knees")],
            [InlineKeyboardButton(text="Ниже колен", callback_data="garment_len:below_knees")],
            [InlineKeyboardButton(text="Миди", callback_data="garment_len:midi")],
            [InlineKeyboardButton(text="До щиколоток", callback_data="garment_len:to_ankles")],
            [InlineKeyboardButton(text="До пола", callback_data="garment_len:to_floor")],
            [InlineKeyboardButton(text="Пропустить", callback_data="own_variant_length:skip")],
        ]
    )


def sleeve_length_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Обычный", callback_data="form_sleeve:normal"), InlineKeyboardButton(text="Длинные", callback_data="form_sleeve:long")],
            [InlineKeyboardButton(text="Три четверти", callback_data="form_sleeve:three_quarter"), InlineKeyboardButton(text="До локтей", callback_data="form_sleeve:elbow")],
            [InlineKeyboardButton(text="Короткие", callback_data="form_sleeve:short"), InlineKeyboardButton(text="Без рукав", callback_data="form_sleeve:none")],
            [InlineKeyboardButton(text="Пропустить", callback_data="form_sleeve:skip")],
        ]
    )


def form_view_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сзади", callback_data="form_view:back"), InlineKeyboardButton(text="Передняя часть", callback_data="form_view:front")],
        ]
    )


def whitebg_view_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сзади", callback_data="form_view:back"),
                InlineKeyboardButton(text="Передняя часть", callback_data="form_view:front"),
                InlineKeyboardButton(text="Сбоку", callback_data="form_view:side"),
            ]
        ]
    )


def storefront_options_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📏 Длина изделия", callback_data="storefront_len")],
            [InlineKeyboardButton(text="👀 Ракурс: Сзади", callback_data="form_view:back"), InlineKeyboardButton(text="👀 Ракурс: Спереди", callback_data="form_view:front")],
        ]
    )


def pants_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Свободный крой", callback_data="pants_style:relaxed"), InlineKeyboardButton(text="Зауженный", callback_data="pants_style:slim")],
            [InlineKeyboardButton(text="Бананы", callback_data="pants_style:banana"), InlineKeyboardButton(text="Клеш от колен", callback_data="pants_style:flare_knee")],
            [InlineKeyboardButton(text="Багги", callback_data="pants_style:baggy"), InlineKeyboardButton(text="Мом", callback_data="pants_style:mom")],
            [InlineKeyboardButton(text="Прямые", callback_data="pants_style:straight"), InlineKeyboardButton(text="Пропустить", callback_data="pants_style:skip")],
        ]
    )


def own_view_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сзади", callback_data="own_view:back"), InlineKeyboardButton(text="Спереди", callback_data="own_view:front")],
        ]
    )


def cut_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Приталенный", callback_data="cut_type:fitted"), InlineKeyboardButton(text="Прямой", callback_data="cut_type:straight")],
            [InlineKeyboardButton(text="Оверсайз", callback_data="cut_type:oversize"), InlineKeyboardButton(text="А-силуэт", callback_data="cut_type:a_line")],
            [InlineKeyboardButton(text="Пропустить", callback_data="cut_type:skip")],
        ]
    )


def confirm_generation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать фото", callback_data="form_generate")],
            [InlineKeyboardButton(text="Отмена", callback_data="form_cancel")],
        ]
    )


def result_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить для след фото", callback_data="result_repeat")],
            [InlineKeyboardButton(text="Внести правки", callback_data="result_edit")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )

def result_actions_own_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Внести правки", callback_data="result_edit")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )

def broadcast_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="broadcast_skip")]]
    )

def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить", callback_data="broadcast_send"), InlineKeyboardButton(text="Отмена", callback_data="broadcast_cancel")]
        ]
    )


def random_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мужчина", callback_data="rand_gender:male"), InlineKeyboardButton(text="Женщина", callback_data="rand_gender:female")],
            [InlineKeyboardButton(text="Детский мальчик", callback_data="rand_gender:boy"), InlineKeyboardButton(text="Детская девочка", callback_data="rand_gender:girl")],
        ]
    )


def random_loc_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="На улице", callback_data="rand_locgroup:outdoor"), InlineKeyboardButton(text="В помещении", callback_data="rand_locgroup:indoor")],
        ]
    )


def random_location_keyboard(group: str) -> InlineKeyboardMarkup:
    if group == "indoor":
        items = [
            ("inside_restaurant", "Внутри ресторана"),
            ("photo_studio", "В фотостудии"),
            ("coffee_shop", "У кофейни (внутри)"),
        ]
    else:
        items = [
            ("city", "В городе"),
            ("building", "У здания"),
            ("wall", "У стены"),
            ("park", "В парке"),
            ("coffee_shop_out", "У кофейни (снаружи)"),
            ("forest", "В лесу"),
            ("car", "У машины"),
        ]
    rows: list[list[InlineKeyboardButton]] = []
    for k, label in items:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"rand_location:{k}")])
    # Кнопка для собственного варианта
    rows.append([InlineKeyboardButton(text="✏️ Свой вариант", callback_data="rand_location_custom")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def random_vibe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лето", callback_data="rand_vibe:summer"), InlineKeyboardButton(text="Зима", callback_data="rand_vibe:winter")],
            [InlineKeyboardButton(text="Осень", callback_data="rand_vibe:autumn"), InlineKeyboardButton(text="Весна", callback_data="rand_vibe:spring")],
            [InlineKeyboardButton(text="Новый год", callback_data="rand_vibe:newyear")],
        ]
    )


def random_decor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="С декором", callback_data="rand_decor:decor"), InlineKeyboardButton(text="Без декора", callback_data="rand_decor:plain")],
        ]
    )


def random_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="rand_age:skip")]]
    )

def own_view_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сзади", callback_data="own_view:back"), InlineKeyboardButton(text="Спереди", callback_data="own_view:front")],
        ]
    )

def cut_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Приталенный", callback_data="cut_type:fitted"), InlineKeyboardButton(text="Прямой", callback_data="cut_type:straight")],
            [InlineKeyboardButton(text="Оверсайз", callback_data="cut_type:oversize"), InlineKeyboardButton(text="А-силуэт", callback_data="cut_type:a_line")],
            [InlineKeyboardButton(text="Пропустить", callback_data="cut_type:skip")],
        ]
    )

def random_shot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="В полный рост", callback_data="rand_shot:full"), InlineKeyboardButton(text="Близкий ракурс", callback_data="rand_shot:close")],
        ]
    )


def plus_location_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="На улице", callback_data="plus_loc:outdoor")],
            [InlineKeyboardButton(text="Возле стены", callback_data="plus_loc:wall")],
            [InlineKeyboardButton(text="Возле машины", callback_data="plus_loc:car")],
            [InlineKeyboardButton(text="В парке", callback_data="plus_loc:park")],
            [InlineKeyboardButton(text="У лавочки", callback_data="plus_loc:bench")],
            [InlineKeyboardButton(text="Возле ресторана", callback_data="plus_loc:restaurant")],
            [InlineKeyboardButton(text="Фотостудия", callback_data="plus_loc:studio")],
        ]
    )


def plus_season_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зима", callback_data="plus_season:winter"), InlineKeyboardButton(text="Лето", callback_data="plus_season:summer")],
            [InlineKeyboardButton(text="Весна", callback_data="plus_season:spring"), InlineKeyboardButton(text="Осень", callback_data="plus_season:autumn")],
        ]
    )


def plus_vibe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="С декором элементами", callback_data="plus_vibe:decor"), InlineKeyboardButton(text="Без декора", callback_data="plus_vibe:plain")],
            [InlineKeyboardButton(text="Новый год", callback_data="plus_vibe:newyear"), InlineKeyboardButton(text="Обычный", callback_data="plus_vibe:normal")],
        ]
    )


def aspect_ratio_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="4:3", callback_data="form_aspect:4x3"), InlineKeyboardButton(text="3:4", callback_data="form_aspect:3x4")],
            [InlineKeyboardButton(text="16:9", callback_data="form_aspect:16x9"), InlineKeyboardButton(text="9:16", callback_data="form_aspect:9x16")],
        ]
    )


def plus_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👱‍♀️ Женское", callback_data="plus_gender:female"), InlineKeyboardButton(text="👨 Мужское", callback_data="plus_gender:male")],
        ]
    )


def boy_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Модель (фон)", callback_data="child_mode:model_bg")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def girl_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Модель (фон)", callback_data="child_mode:model_bg")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def child_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👦 Мальчик", callback_data="child_gender:boy"), InlineKeyboardButton(text="👧 Девочка", callback_data="child_gender:girl")],
        ]
    )


def girl_clothes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 Куртка (Пальто)", callback_data="child_cloth:coat"), InlineKeyboardButton(text="👗 Платье", callback_data="child_cloth:dress")],
            [InlineKeyboardButton(text="👖 Штаны", callback_data="child_cloth:pants"), InlineKeyboardButton(text="🩳 Шорты", callback_data="child_cloth:shorts")],
            [InlineKeyboardButton(text="🥼 Костюм", callback_data="child_cloth:suit"), InlineKeyboardButton(text="👚 Верхняя одежда", callback_data="child_cloth:top")],
            [InlineKeyboardButton(text="🏠 Домашняя одежда", callback_data="child_cloth:loungewear"), InlineKeyboardButton(text="🦺 Комбинезон", callback_data="child_cloth:overall")],
            [InlineKeyboardButton(text="👗 Юбка", callback_data="child_cloth:skirt"), InlineKeyboardButton(text="👠 Обувь", callback_data="child_cloth:shoes")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
        ]
    )


def boy_clothes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 Куртка (Пальто)", callback_data="child_cloth:coat"), InlineKeyboardButton(text="👖 Штаны", callback_data="child_cloth:pants")],
            [InlineKeyboardButton(text="🩳 Шорты", callback_data="child_cloth:shorts"), InlineKeyboardButton(text="🥼 Костюм", callback_data="child_cloth:suit")],
            [InlineKeyboardButton(text="👕 Верхняя одежда", callback_data="child_cloth:top"), InlineKeyboardButton(text="🏠 Домашняя одежда", callback_data="child_cloth:loungewear")],
            [InlineKeyboardButton(text="🦺 Комбинезон", callback_data="child_cloth:overall"), InlineKeyboardButton(text="👟 Обувь", callback_data="child_cloth:shoes")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
        ]
    )


def female_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Модель (фон)", callback_data="female_mode:model_bg")],
            [InlineKeyboardButton(text="Большой размер", callback_data="female_mode:plus")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def female_clothes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 Куртка (Пальто)", callback_data="female_cloth:coat"), InlineKeyboardButton(text="👗 Платье", callback_data="female_cloth:dress")],
            [InlineKeyboardButton(text="👖 Штаны", callback_data="female_cloth:pants"), InlineKeyboardButton(text="🩳 Шорты", callback_data="female_cloth:shorts")],
            [InlineKeyboardButton(text="👚 Верхняя одежда", callback_data="female_cloth:top"), InlineKeyboardButton(text="🏠 Домашняя одежда", callback_data="female_cloth:loungewear")],
            [InlineKeyboardButton(text="🥼 Костюм", callback_data="female_cloth:suit"), InlineKeyboardButton(text="🦺 Комбинезон", callback_data="female_cloth:overall")],
            [InlineKeyboardButton(text="👗 Юбка", callback_data="female_cloth:skirt"), InlineKeyboardButton(text="👠 Обувь", callback_data="female_cloth:shoes")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
        ]
    )


def male_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Модель (фон)", callback_data="male_mode:model_bg")],
            [InlineKeyboardButton(text="Большой размер", callback_data="male_mode:plus")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_main")],
        ]
    )


def male_clothes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 Куртка (Пальто)", callback_data="male_cloth:coat"), InlineKeyboardButton(text="👖 Штаны", callback_data="male_cloth:pants")],
            [InlineKeyboardButton(text="🩳 Шорты", callback_data="male_cloth:shorts"), InlineKeyboardButton(text="🥼 Костюм", callback_data="male_cloth:suit")],
            [InlineKeyboardButton(text="👕 Верхняя одежда", callback_data="male_cloth:top"), InlineKeyboardButton(text="🏠 Домашняя одежда", callback_data="male_cloth:loungewear")],
            [InlineKeyboardButton(text="🦺 Комбинезон", callback_data="male_cloth:overall"), InlineKeyboardButton(text="👟 Обувь", callback_data="male_cloth:shoes")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
        ]
    )


def own_variant_category_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора категории товара в 'Свой вариант'"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨 Мужская", callback_data="own_variant_cat:male"), InlineKeyboardButton(text="👱‍♀️ Женская", callback_data="own_variant_cat:female")],
            [InlineKeyboardButton(text="👦 Мальчик", callback_data="own_variant_cat:boy"), InlineKeyboardButton(text="👧 Девочка", callback_data="own_variant_cat:girl")],
            [InlineKeyboardButton(text="Другое", callback_data="own_variant_cat:other")],
        ]
    )


def own_variant_male_subcategory_keyboard() -> InlineKeyboardMarkup:
    """Подкатегории для мужской одежды"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Верхняя одежда", callback_data="own_variant_subcat:male:outerwear")],
            [InlineKeyboardButton(text="Одежда для верха", callback_data="own_variant_subcat:male:top")],
            [InlineKeyboardButton(text="Одежда для низа", callback_data="own_variant_subcat:male:bottom")],
            [InlineKeyboardButton(text="Нижнее бельё", callback_data="own_variant_subcat:male:underwear")],
            [InlineKeyboardButton(text="Спортивная одежда", callback_data="own_variant_subcat:male:sport")],
            [InlineKeyboardButton(text="Одежда для сна", callback_data="own_variant_subcat:male:sleepwear")],
            [InlineKeyboardButton(text="Плавание", callback_data="own_variant_subcat:male:swimwear")],
            [InlineKeyboardButton(text="Обувь", callback_data="own_variant_subcat:male:shoes")],
            [InlineKeyboardButton(text="Аксессуары", callback_data="own_variant_subcat:male:accessories")],
            [InlineKeyboardButton(text="Носки", callback_data="own_variant_subcat:male:socks")],
            [InlineKeyboardButton(text="Другое", callback_data="own_variant_subcat:male:other")],
        ]
    )


def own_variant_female_subcategory_keyboard() -> InlineKeyboardMarkup:
    """Подкатегории для женской одежды"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Верхняя одежда", callback_data="own_variant_subcat:female:outerwear")],
            [InlineKeyboardButton(text="Одежда для верха", callback_data="own_variant_subcat:female:top")],
            [InlineKeyboardButton(text="Одежда для низа", callback_data="own_variant_subcat:female:bottom")],
            [InlineKeyboardButton(text="Платья и комбинезоны", callback_data="own_variant_subcat:female:dresses")],
            [InlineKeyboardButton(text="Нижнее бельё", callback_data="own_variant_subcat:female:underwear")],
            [InlineKeyboardButton(text="Спортивная одежда", callback_data="own_variant_subcat:female:sport")],
            [InlineKeyboardButton(text="Одежда для сна", callback_data="own_variant_subcat:female:sleepwear")],
            [InlineKeyboardButton(text="Плавание", callback_data="own_variant_subcat:female:swimwear")],
            [InlineKeyboardButton(text="Обувь", callback_data="own_variant_subcat:female:shoes")],
            [InlineKeyboardButton(text="Аксессуары", callback_data="own_variant_subcat:female:accessories")],
            [InlineKeyboardButton(text="Носки", callback_data="own_variant_subcat:female:socks")],
            [InlineKeyboardButton(text="Другое", callback_data="own_variant_subcat:female:other")],
        ]
    )


def own_variant_boy_subcategory_keyboard() -> InlineKeyboardMarkup:
    """Подкатегории для одежды мальчиков"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Верхняя одежда", callback_data="own_variant_subcat:boy:outerwear")],
            [InlineKeyboardButton(text="Одежда для верха", callback_data="own_variant_subcat:boy:top")],
            [InlineKeyboardButton(text="Одежда для низа", callback_data="own_variant_subcat:boy:bottom")],
            [InlineKeyboardButton(text="Нижнее бельё", callback_data="own_variant_subcat:boy:underwear")],
            [InlineKeyboardButton(text="Спортивная одежда", callback_data="own_variant_subcat:boy:sport")],
            [InlineKeyboardButton(text="Одежда для сна", callback_data="own_variant_subcat:boy:sleepwear")],
            [InlineKeyboardButton(text="Плавание", callback_data="own_variant_subcat:boy:swimwear")],
            [InlineKeyboardButton(text="Обувь", callback_data="own_variant_subcat:boy:shoes")],
            [InlineKeyboardButton(text="Аксессуары", callback_data="own_variant_subcat:boy:accessories")],
            [InlineKeyboardButton(text="Носки", callback_data="own_variant_subcat:boy:socks")],
            [InlineKeyboardButton(text="Другое", callback_data="own_variant_subcat:boy:other")],
        ]
    )


def own_variant_girl_subcategory_keyboard() -> InlineKeyboardMarkup:
    """Подкатегории для одежды девочек"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Верхняя одежда", callback_data="own_variant_subcat:girl:outerwear")],
            [InlineKeyboardButton(text="Одежда для верха", callback_data="own_variant_subcat:girl:top")],
            [InlineKeyboardButton(text="Одежда для низа", callback_data="own_variant_subcat:girl:bottom")],
            [InlineKeyboardButton(text="Платья и сарафаны", callback_data="own_variant_subcat:girl:dresses")],
            [InlineKeyboardButton(text="Нижнее бельё", callback_data="own_variant_subcat:girl:underwear")],
            [InlineKeyboardButton(text="Спортивная одежда", callback_data="own_variant_subcat:girl:sport")],
            [InlineKeyboardButton(text="Одежда для сна", callback_data="own_variant_subcat:girl:sleepwear")],
            [InlineKeyboardButton(text="Плавание", callback_data="own_variant_subcat:girl:swimwear")],
            [InlineKeyboardButton(text="Обувь", callback_data="own_variant_subcat:girl:shoes")],
            [InlineKeyboardButton(text="Аксессуары", callback_data="own_variant_subcat:girl:accessories")],
            [InlineKeyboardButton(text="Носки", callback_data="own_variant_subcat:girl:socks")],
            [InlineKeyboardButton(text="Другое", callback_data="own_variant_subcat:girl:other")],
        ]
    )


def get_own_variant_items_map() -> dict:
    """Возвращает словарь товаров для всех подкатегорий"""
    return {
        ("male", "outerwear"): ["Пальто", "Куртки", "Пуховики", "Парки", "Бомберы", "Ветровки", "Жилеты"],
        ("male", "top"): ["Футболки", "Поло", "Рубашки", "Лонгсливы", "Свитеры", "Худи", "Кардиганы", "Толстовки", "Жакеты"],
        ("male", "bottom"): ["Брюки", "Джинсы", "Спортивные штаны", "Шорты", "Чиносы"],
        ("male", "underwear"): ["Трусы", "Боксеры", "Майки"],
        ("male", "sport"): ["Спортивные брюки", "Шорты", "Майки", "Компрессионные вещи"],
        ("male", "sleepwear"): ["Пижамы", "Домашние штаны", "Майки"],
        ("male", "swimwear"): ["Плавки", "Шорты для плавания"],
        ("male", "shoes"): ["Кроссовки", "Ботинки", "Сапоги", "Дерби", "Оксфорды", "Лоферы", "Сандалии", "Сланцы"],
        ("male", "accessories"): ["Ремни", "Шарфы", "Шапки", "Перчатки", "Бейсболки", "Рюкзаки", "Сумки"],
        ("male", "socks"): ["Носки"],
        ("female", "outerwear"): ["Пальто", "Пуховики", "Парки", "Плащи", "Тренчи", "Куртки", "Бомберы", "Жилеты"],
        ("female", "top"): ["Топы", "Футболки", "Блузки", "Рубашки", "Свитеры", "Кардиганы", "Худи", "Толстовки", "Жакеты"],
        ("female", "bottom"): ["Брюки", "Джинсы", "Юбки (мини/миди/макси)", "Шорты", "Леггинсы"],
        ("female", "dresses"): ["Платья всех фасонов", "Сарафаны", "Комбинезоны", "Ромперы"],
        ("female", "underwear"): ["Трусы разных типов", "Бюстгальтеры", "Топы", "Майки", "Комплекты"],
        ("female", "sport"): ["Леггинсы", "Шорты", "Топы", "Майки", "Спортивные куртки"],
        ("female", "sleepwear"): ["Пижамы", "Ночные сорочки"],
        ("female", "swimwear"): ["Купальники", "Слитные", "Раздельные", "Пляжные шорты"],
        ("female", "shoes"): ["Кроссовки", "Кеды", "Туфли", "Босоножки", "Сапоги", "Ботильоны", "Лоферы", "Балетки", "Сандалии", "Сланцы"],
        ("female", "accessories"): ["Ремни", "Шарфы", "Платки", "Шапки", "Головные уборы", "Сумки", "Рюкзаки", "Украшения"],
        ("female", "socks"): ["Носки"],
        ("boy", "outerwear"): ["Куртки", "Пуховики", "Жилеты", "Ветровки", "Пальто"],
        ("boy", "top"): ["Футболки", "Лонгсливы", "Рубашки", "Свитеры", "Худи", "Толстовки"],
        ("boy", "bottom"): ["Брюки", "Джинсы", "Спортивные штаны", "Шорты"],
        ("boy", "underwear"): ["Трусы", "Майки"],
        ("boy", "sport"): ["Спортивные штаны", "Шорты", "Майки"],
        ("boy", "sleepwear"): ["Пижамы"],
        ("boy", "swimwear"): ["Шорты для плавания"],
        ("boy", "shoes"): ["Кроссовки", "Ботинки", "Сандалии", "Сланцы"],
        ("boy", "accessories"): ["Шапки", "Шарфы", "Перчатки", "Рюкзаки"],
        ("boy", "socks"): ["Носки"],
        ("girl", "outerwear"): ["Куртки", "Пуховики", "Жилеты", "Плащи", "Пальто"],
        ("girl", "top"): ["Футболки", "Блузки", "Лонгсливы", "Свитеры", "Худи", "Кардиганы"],
        ("girl", "bottom"): ["Брюки", "Джинсы", "Юбки", "Леггинсы", "Шорты"],
        ("girl", "dresses"): ["Повседневные", "Нарядные", "Летние"],
        ("girl", "underwear"): ["Трусы", "Топы для девочек", "Майки"],
        ("girl", "sport"): ["Леггинсы", "Шорты", "Майки", "Спортивные костюмы"],
        ("girl", "sleepwear"): ["Пижамы", "Ночнушки"],
        ("girl", "swimwear"): ["Купальники"],
        ("girl", "shoes"): ["Кроссовки", "Ботинки", "Сандалии", "Балетки", "Сланцы"],
        ("girl", "accessories"): ["Шапки", "Шарфы", "Заколки", "Рюкзаки", "Сумочки"],
        ("girl", "socks"): ["Короткие", "Длинные", "Декоративные", "Спортивные"],
    }


def own_variant_subcategory_items_keyboard(category: str, subcategory: str) -> InlineKeyboardMarkup:
    """Клавиатура с конкретными товарами для подкатегории"""
    items_map = get_own_variant_items_map()
    items = items_map.get((category, subcategory), [])
    rows: list[list[InlineKeyboardButton]] = []
    
    # Если товары не найдены для данной подкатегории, добавляем кнопку "Другое"
    if not items:
        rows.append([InlineKeyboardButton(text="Другое", callback_data=f"own_variant_item:{category}:{subcategory}:-1")])
    else:
        # Разбиваем на строки по 2 кнопки
        # Используем индекс товара вместо названия для callback_data (более компактно и безопасно)
        for i in range(0, len(items), 2):
            row = []
            # Используем индекс товара в списке
            row.append(InlineKeyboardButton(text=items[i], callback_data=f"own_variant_item:{category}:{subcategory}:{i}"))
            if i + 1 < len(items):
                row.append(InlineKeyboardButton(text=items[i + 1], callback_data=f"own_variant_item:{category}:{subcategory}:{i+1}"))
            rows.append(row)
        
        # Добавляем кнопку "Другое" если её нет в списке (используем индекс -1)
        if subcategory != "other":
            rows.append([InlineKeyboardButton(text="Другое", callback_data=f"own_variant_item:{category}:{subcategory}:-1")])
    
    # Кнопка "Назад"
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="own_variant_subcat_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


