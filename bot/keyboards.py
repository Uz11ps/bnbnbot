from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.strings import get_string

def terms_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("agreement", lang), callback_data="menu_agreement")],
            [InlineKeyboardButton(text=get_string("accept_terms", lang), callback_data="accept_terms")]
        ]
    )

def subscription_check_keyboard(channel_url: str, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("subscribe_channel", lang), url=channel_url)],
            [InlineKeyboardButton(text=get_string("subscribed", lang), callback_data="check_subscription")]
        ]
    )

def main_menu_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("create_normal_gen", lang), callback_data="menu_create")],
            [InlineKeyboardButton(text=get_string("menu_market", lang), callback_data="menu_market")],
            [InlineKeyboardButton(text=get_string("menu_profile", lang), callback_data="menu_profile")],
            [InlineKeyboardButton(text=get_string("menu_howto", lang), callback_data="menu_howto")],
            [InlineKeyboardButton(text=get_string("menu_settings", lang), callback_data="menu_settings")]
        ]
    )

def profile_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("menu_subscription", lang), callback_data="menu_subscription")],
            [InlineKeyboardButton(text=get_string("menu_history", lang), callback_data="menu_history")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")]
        ]
    )

def settings_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("select_lang", lang), callback_data="settings_lang")],
            [InlineKeyboardButton(text=get_string("agreement", lang), callback_data="menu_agreement")],
            [InlineKeyboardButton(text=get_string("buy_plan", lang), callback_data="menu_subscription")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")]
        ]
    )

def language_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("lang_ru", lang), callback_data="lang:ru")],
            [InlineKeyboardButton(text=get_string("lang_en", lang), callback_data="lang:en")],
            [InlineKeyboardButton(text=get_string("lang_vi", lang), callback_data="lang:vi")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_settings")]
        ]
    )

def marketplace_menu_keyboard(enabled: dict[str, bool], lang="ru") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    
    # Готовые пресеты — теперь ВСЕГДА показываем этот раздел первым
    rows.append([InlineKeyboardButton(text=get_string("cat_presets", lang), callback_data="create_cat:presets")])

    # Разделы Рандом
    if enabled.get("random", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_random", lang), callback_data="create_cat:random")])
    if enabled.get("random_other", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_random_other", lang), callback_data="create_cat:random_other")])
    
    # Кнопка Инфографика (внутри которой теперь 3 кнопки)
    rows.append([InlineKeyboardButton(text=get_string("cat_infographics", lang), callback_data="create_cat:infographics")])

    # Витринное фото
    if enabled.get("storefront", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_storefront", lang), callback_data="create_cat:storefront")])
        
    # На белом фоне
    if enabled.get("whitebg", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_whitebg", lang), callback_data="create_cat:whitebg")])
    
    # Свой вариант
    if enabled.get("own", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_own", lang), callback_data="create_cat:own")])
    if enabled.get("own_variant", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_own_variant", lang), callback_data="create_cat:own_variant")])
    
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def gender_selection_keyboard(category: str, lang="ru", back_data="menu_market") -> InlineKeyboardMarkup:
    """Универсальная клавиатура выбора пола для разных категорий"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_string("cat_female", lang), callback_data=f"gender_select:{category}:female"),
                InlineKeyboardButton(text=get_string("cat_male", lang), callback_data=f"gender_select:{category}:male")
            ],
            [
                InlineKeyboardButton(text=get_string("gender_boy", lang), callback_data=f"gender_select:{category}:boy"),
                InlineKeyboardButton(text=get_string("gender_girl", lang), callback_data=f"gender_select:{category}:girl")
            ],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data=back_data)]
        ]
    )

def plans_keyboard(plans: list[tuple], lang="ru") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for plan in plans:
        # plan: (id, name_ru, name_en, name_vi, desc_ru, desc_en, desc_vi, price, duration, limit, active)
        pid = plan[0]
        name_ru, name_en, name_vi = plan[1], plan[2], plan[3]
        price = plan[7]
        name = name_ru if lang == "ru" else (name_en if lang == "en" else name_vi)
        # Если это пробный период (trial), не показываем его в списке планов для покупки
        if "TRIAL" in str(name_ru).upper() or "ПРОБНЫЙ" in str(name_ru).upper():
            continue
        rows.append([InlineKeyboardButton(text=f"{name} — {price} ₽", callback_data=f"buy_plan:{pid}")])
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def history_pagination_keyboard(page: int, total_pages: int, lang="ru") -> InlineKeyboardMarkup:
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"history_page:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"history_page:{page+1}"))
    rows: list[list[InlineKeyboardButton]] = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def aspect_ratio_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1:1", callback_data="form_aspect:1x1"), InlineKeyboardButton(text="9:16", callback_data="form_aspect:9x16")],
            [InlineKeyboardButton(text="16:9", callback_data="form_aspect:16x9"), InlineKeyboardButton(text="3:4", callback_data="form_aspect:3x4")],
            [InlineKeyboardButton(text="4:3", callback_data="form_aspect:4x3"), InlineKeyboardButton(text="3:2", callback_data="form_aspect:3x2")],
            [InlineKeyboardButton(text="2:3", callback_data="form_aspect:2x3"), InlineKeyboardButton(text="5:4", callback_data="form_aspect:5x4")],
            [InlineKeyboardButton(text="4:5", callback_data="form_aspect:4x5"), InlineKeyboardButton(text="21:9", callback_data="form_aspect:21x9")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
        ]
    )

def form_generate_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("create_photo", lang), callback_data="form_generate")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
        ]
    )

def admin_main_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_stats", lang), callback_data="admin_stats")],
            [InlineKeyboardButton(text=get_string("admin_users", lang), callback_data="admin_users_page:0"), InlineKeyboardButton(text=get_string("admin_search", lang), callback_data="admin_user_search")],
            [InlineKeyboardButton(text=get_string("admin_categories", lang), callback_data="admin_categories")],
            [InlineKeyboardButton(text=get_string("admin_own_prompts", lang), callback_data="admin_own_prompts")],
            [InlineKeyboardButton(text=get_string("admin_own_variant_prompts", lang), callback_data="admin_own_variant_prompts")],
            [InlineKeyboardButton(text=get_string("admin_howto_edit", lang), callback_data="admin_howto_edit")],
            [InlineKeyboardButton(text=get_string("admin_api_keys", lang), callback_data="admin_api_keys")],
            [InlineKeyboardButton(text=get_string("admin_own_variant_api_keys", lang), callback_data="admin_own_variant_api_keys")],
            [InlineKeyboardButton(text=get_string("admin_logs", lang), callback_data="admin_logs"), InlineKeyboardButton(text=get_string("admin_proxy", lang), callback_data="admin_proxy_status")],
            [InlineKeyboardButton(text=get_string("admin_maint_on", lang), callback_data="admin_maint_on"), InlineKeyboardButton(text=get_string("admin_maint_off", lang), callback_data="admin_maint_off")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")],
        ]
    )

def admin_users_keyboard(users: list[tuple], page: int, has_next: bool, lang="ru") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in users:
        uid, username, blocked = row
        uname = f"@{username}" if username else "—"
        status = "⛔" if blocked else "✅"
        rows.append([
            InlineKeyboardButton(text=f"{status} ID {uid} {uname}", callback_data=f"admin_user:{uid}")
        ])
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text=get_string("back", lang), callback_data=f"admin_users_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_categories_keyboard(status: dict[str, bool], lang="ru") -> InlineKeyboardMarkup:
    def label(name: str, key: str) -> str:
        return ("✅ " if status.get(name, True) else "⛔ ") + get_string(key, lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label("female", "cat_female"), callback_data="admin_toggle_cat:female"), InlineKeyboardButton(text=label("male", "cat_male"), callback_data="admin_toggle_cat:male")],
            [InlineKeyboardButton(text=label("child", "cat_child"), callback_data="admin_toggle_cat:child")],
            [InlineKeyboardButton(text=label("storefront", "cat_storefront"), callback_data="admin_toggle_cat:storefront"), InlineKeyboardButton(text=label("whitebg", "cat_whitebg"), callback_data="admin_toggle_cat:whitebg")],
            [InlineKeyboardButton(text=label("random", "cat_random"), callback_data="admin_toggle_cat:random"), InlineKeyboardButton(text=label("random_other", "cat_random_other"), callback_data="admin_toggle_cat:random_other")],
            [InlineKeyboardButton(text=label("infographic_clothing", "cat_infographic_clothing"), callback_data="admin_toggle_cat:infographic_clothing")],
            [InlineKeyboardButton(text=label("infographic_other", "cat_infographic_other"), callback_data="admin_toggle_cat:infographic_other")],
            [InlineKeyboardButton(text=label("own", "cat_own"), callback_data="admin_toggle_cat:own")],
            [InlineKeyboardButton(text=label("own_variant", "cat_own_variant"), callback_data="admin_toggle_cat:own_variant")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")],
        ]
    )

def create_product_keyboard_dynamic(enabled: dict[str, bool], lang="ru") -> InlineKeyboardMarkup:
    """Обычная генерация теперь просто возвращает кнопку Назад, 
    так как основная логика теперь сразу просит фото."""
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def ready_presets_keyboard(enabled: dict[str, bool], lang="ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора пола внутри готовых пресетов"""
    rows: list[list[InlineKeyboardButton]] = []

    rows.append([
        InlineKeyboardButton(text=get_string("cat_female", lang), callback_data="preset_gender:female"),
        InlineKeyboardButton(text=get_string("cat_male", lang), callback_data="preset_gender:male")
    ])

    rows.append([
        InlineKeyboardButton(text=get_string("gender_boy", lang), callback_data="preset_gender:boy"),
        InlineKeyboardButton(text=get_string("gender_girl", lang), callback_data="preset_gender:girl")
    ])

    rows.append([InlineKeyboardButton(text="⬅️ Назад в маркет", callback_data="menu_market")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def yes_no_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("yes", lang), callback_data="choice:yes"), InlineKeyboardButton(text=get_string("no", lang), callback_data="choice:no")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
        ]
    )

def style_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Современный", callback_data="style:modern"), InlineKeyboardButton(text="Брутальный", callback_data="style:brutal")],
            [InlineKeyboardButton(text="Техно", callback_data="style:techno"), InlineKeyboardButton(text="Арт", callback_data="style:art")],
            [InlineKeyboardButton(text="Дизайнерский", callback_data="style:design"), InlineKeyboardButton(text="Праздничный", callback_data="style:festive")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="style:custom")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="style:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
        ]
    )

def camera_dist_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_string("dist_far", lang), callback_data="angle:far"),
                InlineKeyboardButton(text=get_string("dist_medium", lang), callback_data="angle:medium"),
                InlineKeyboardButton(text=get_string("dist_close", lang), callback_data="angle:close")
            ],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def skip_step_keyboard(step_name: str, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data=f"{step_name}:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]
        ]
    )

def back_step_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")]]
    )

def random_vibe_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("season_summer", lang), callback_data="rand_vibe:summer"), InlineKeyboardButton(text=get_string("season_winter", lang), callback_data="rand_vibe:winter")],
            [InlineKeyboardButton(text=get_string("season_autumn", lang), callback_data="rand_vibe:autumn"), InlineKeyboardButton(text=get_string("season_spring", lang), callback_data="rand_vibe:spring")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_decor_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1", callback_data="rand_decor:1"), InlineKeyboardButton(text="2", callback_data="rand_decor:2")],
            [InlineKeyboardButton(text="3", callback_data="rand_decor:3"), InlineKeyboardButton(text="4", callback_data="rand_decor:4")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_shot_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="В полный рост", callback_data="rand_shot:full"), InlineKeyboardButton(text="Крупный план", callback_data="rand_shot:close")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def plus_location_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Улица", callback_data="plus_loc:outdoor"), InlineKeyboardButton(text="Помещение", callback_data="plus_loc:indoor")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def plus_season_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лето", callback_data="plus_season:summer"), InlineKeyboardButton(text="Зима", callback_data="plus_season:winter")],
            [InlineKeyboardButton(text="Осень", callback_data="plus_season:autumn"), InlineKeyboardButton(text="Весна", callback_data="plus_season:spring")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def plus_vibe_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Городской", callback_data="plus_vibe:city"), InlineKeyboardButton(text="Природа", callback_data="plus_vibe:nature")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def plus_gender_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Женский", callback_data="plus_gender:female"), InlineKeyboardButton(text="Мужской", callback_data="plus_gender:male")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def child_gender_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("gender_boy", lang), callback_data="child_gender:boy"), InlineKeyboardButton(text=get_string("gender_girl", lang), callback_data="child_gender:girl")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="create_cat:presets")]
        ]
    )

def back_main_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")]]
    )

def result_actions_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("btn_repeat", lang), callback_data="result_repeat")],
            [InlineKeyboardButton(text=get_string("btn_edit", lang), callback_data="result_edit")],
            [InlineKeyboardButton(text="🔍 Показать промпт", callback_data="result_show_prompt")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")],
        ]
    )

def result_actions_own_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("btn_repeat", lang), callback_data="result_repeat")],
            [InlineKeyboardButton(text="🔍 Показать промпт", callback_data="result_show_prompt")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")],
        ]
    )

def model_select_keyboard(category: str, cloth: str, index: int, total: int, lang: str = "ru", logic_category: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора пресета с быстрой навигацией 1-10"""
    rows: list[list[InlineKeyboardButton]] = []
    
    # Кнопки навигации по одной
    # model_nav:display_cat:cloth:index:logic_cat
    logic_suffix = f":{logic_category}" if logic_category else ""
    pick_cat = logic_category or category

    nav_row = [
        InlineKeyboardButton(text="⬅️", callback_data=f"model_nav:{category}:{cloth}:{index-1}{logic_suffix}"),
        InlineKeyboardButton(text=get_string("confirm_btn", lang), callback_data=f"model_pick:{pick_cat}:{category}:{cloth}:{index}"),
        InlineKeyboardButton(text="➡️", callback_data=f"model_nav:{category}:{cloth}:{index+1}{logic_suffix}"),
    ]
    rows.append(nav_row)
    
    # Оставляем только поиск по номеру
    rows.append([InlineKeyboardButton(text="Поиск 🔍", callback_data=f"model_search:{category}:{cloth}{logic_suffix}")])
        
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="presets_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def pose_keyboard(lang="ru", show_vulgar=True) -> InlineKeyboardMarkup:
    buttons = []
    if show_vulgar:
        buttons.append([InlineKeyboardButton(text=get_string("pose_vulgar", lang), callback_data="pose:vulgar")])
    
    buttons.extend([
        [InlineKeyboardButton(text=get_string("pose_unusual", lang), callback_data="pose:unusual")],
        [InlineKeyboardButton(text=get_string("pose_normal", lang), callback_data="pose:normal")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def angle_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_string("dist_far", lang), callback_data="form_dist:far"),
                InlineKeyboardButton(text=get_string("dist_medium", lang), callback_data="form_dist:medium"),
                InlineKeyboardButton(text=get_string("dist_close", lang), callback_data="form_dist:close"),
            ],
            [
                InlineKeyboardButton(text=get_string("skip", lang), callback_data="form_dist:skip"),
                InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")
            ],
        ]
    )

def info_load_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("load_min", lang), callback_data="info_load:min")],
            [InlineKeyboardButton(text=get_string("load_med", lang), callback_data="info_load:med")],
            [InlineKeyboardButton(text=get_string("load_max", lang), callback_data="info_load:max")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="info_load:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_location_outdoor_keyboard(lang="ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора уличной локации"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("loc_car", lang), callback_data="rand_loc:outdoor_car")],
            [InlineKeyboardButton(text=get_string("loc_cafe", lang), callback_data="rand_loc:outdoor_cafe")],
            [InlineKeyboardButton(text=get_string("loc_wall", lang), callback_data="rand_loc:outdoor_wall")],
            [InlineKeyboardButton(text=get_string("loc_building", lang), callback_data="rand_loc:outdoor_building")],
            [InlineKeyboardButton(text=get_string("loc_moscow_city", lang), callback_data="rand_loc:outdoor_moscow")],
            [InlineKeyboardButton(text=get_string("loc_forest", lang), callback_data="rand_loc:outdoor_forest")],
            [InlineKeyboardButton(text=get_string("loc_mountains", lang), callback_data="rand_loc:outdoor_mountains")],
            [InlineKeyboardButton(text=get_string("loc_alley", lang), callback_data="rand_loc:outdoor_alley")],
            [InlineKeyboardButton(text=get_string("loc_park", lang), callback_data="rand_loc:outdoor_park")],
            [InlineKeyboardButton(text=get_string("loc_city", lang), callback_data="rand_loc:outdoor_city")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="rand_loc:custom")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_location_indoor_keyboard(lang="ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора локации в помещении"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("loc_studio", lang), callback_data="rand_loc:indoor_studio")],
            [InlineKeyboardButton(text=get_string("loc_room", lang), callback_data="rand_loc:indoor_room")],
            [InlineKeyboardButton(text=get_string("loc_restaurant", lang), callback_data="rand_loc:indoor_restaurant")],
            [InlineKeyboardButton(text=get_string("loc_hotel", lang), callback_data="rand_loc:indoor_hotel")],
            [InlineKeyboardButton(text=get_string("loc_mall", lang), callback_data="rand_loc:indoor_mall")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="rand_loc:custom")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_season_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("season_winter", lang), callback_data="rand_season:winter"), InlineKeyboardButton(text=get_string("season_summer", lang), callback_data="rand_season:summer")],
            [InlineKeyboardButton(text=get_string("season_autumn", lang), callback_data="rand_season:autumn"), InlineKeyboardButton(text=get_string("season_spring", lang), callback_data="rand_season:spring")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="rand_season:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_holiday_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("holiday_wedding", lang), callback_data="rand_holiday:wedding")],
            [InlineKeyboardButton(text=get_string("holiday_bday", lang), callback_data="rand_holiday:bday"), InlineKeyboardButton(text=get_string("holiday_may9", lang), callback_data="rand_holiday:may9")],
            [InlineKeyboardButton(text=get_string("holiday_march8", lang), callback_data="rand_holiday:march8"), InlineKeyboardButton(text=get_string("holiday_momday", lang), callback_data="rand_holiday:momday")],
            [InlineKeyboardButton(text=get_string("holiday_teacherday", lang), callback_data="rand_holiday:teacherday"), InlineKeyboardButton(text=get_string("holiday_russiaday", lang), callback_data="rand_holiday:russiaday")],
            [InlineKeyboardButton(text=get_string("holiday_feb23", lang), callback_data="rand_holiday:feb23")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="rand_holiday:custom")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="rand_holiday:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def camera_distance_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_string("dist_close", lang), callback_data="form_view:close"),
                InlineKeyboardButton(text=get_string("dist_far", lang), callback_data="form_view:far"),
                InlineKeyboardButton(text=get_string("dist_medium", lang), callback_data="form_view:medium")
            ],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def infographic_gender_keyboard(lang="ru", back_data="back_step") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("gender_male", lang), callback_data="info_gender:male"), InlineKeyboardButton(text=get_string("gender_female", lang), callback_data="info_gender:female")],
            [InlineKeyboardButton(text=get_string("gender_boy", lang), callback_data="info_gender:boy"), InlineKeyboardButton(text=get_string("gender_girl", lang), callback_data="info_gender:girl")],
            [InlineKeyboardButton(text=get_string("gender_unisex", lang), callback_data="info_gender:unisex")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data=back_data)],
        ]
    )

def infographic_style_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. " + get_string("style_modern", lang), callback_data="info_style:modern"), InlineKeyboardButton(text="2. " + get_string("style_simple", lang), callback_data="info_style:simple")],
            [InlineKeyboardButton(text="3. " + get_string("style_bright", lang), callback_data="info_style:bright"), InlineKeyboardButton(text="4. " + get_string("style_premium", lang), callback_data="info_style:premium")],
            [InlineKeyboardButton(text="5. " + get_string("style_child", lang), callback_data="info_style:child"), InlineKeyboardButton(text="6. " + get_string("style_tech", lang), callback_data="info_style:tech")],
            [InlineKeyboardButton(text="7. " + get_string("style_natural", lang), callback_data="info_style:natural"), InlineKeyboardButton(text="8. " + get_string("style_retro", lang), callback_data="info_style:retro")],
            [InlineKeyboardButton(text="9. " + get_string("style_classic", lang), callback_data="info_style:classic"), InlineKeyboardButton(text="10. " + get_string("style_atmos", lang), callback_data="info_style:atmos")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="info_style:custom")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="info_style:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def font_type_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. " + get_string("font_modern", lang), callback_data="font_type:modern"), InlineKeyboardButton(text="2. " + get_string("font_serif", lang), callback_data="font_type:serif")],
            [InlineKeyboardButton(text="3. " + get_string("font_sans", lang), callback_data="font_type:sans"), InlineKeyboardButton(text="4. " + get_string("font_bold", lang), callback_data="font_type:bold")],
            [InlineKeyboardButton(text="5. " + get_string("font_italic", lang), callback_data="font_type:italic"), InlineKeyboardButton(text="6. " + get_string("font_semibold", lang), callback_data="font_type:semibold")],
            [InlineKeyboardButton(text="7. " + get_string("font_hand", lang), callback_data="font_type:hand"), InlineKeyboardButton(text="8. " + get_string("font_decor", lang), callback_data="font_type:decor")],
            [InlineKeyboardButton(text="9. " + get_string("font_mono", lang), callback_data="font_type:mono"), InlineKeyboardButton(text="10. " + get_string("font_narrow", lang), callback_data="font_type:narrow")],
            [InlineKeyboardButton(text="11. " + get_string("font_tech", lang), callback_data="font_type:tech")],
            [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="font_type:custom")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="font_type:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def info_lang_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. 🇷🇺 Русский", callback_data="info_lang:Russian"), InlineKeyboardButton(text="2. 🇺🇸 English", callback_data="info_lang:English")],
            [InlineKeyboardButton(text="3. 🇻🇳 Вьетнамский", callback_data="info_lang:Vietnamese"), InlineKeyboardButton(text="4. 🇨🇳 Китайский", callback_data="info_lang:Chinese")],
            [InlineKeyboardButton(text="5. ✏️ Свой вариант", callback_data="info_lang:custom")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="info_lang:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def holiday_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Новый год", callback_data="holiday:newyear"), InlineKeyboardButton(text="🎄 Рождество", callback_data="holiday:christmas")],
            [InlineKeyboardButton(text="💐 8 марта", callback_data="holiday:8march"), InlineKeyboardButton(text="🎂 День рождения", callback_data="holiday:birthday")],
            [InlineKeyboardButton(text="🔥 Распродажа", callback_data="holiday:sale"), InlineKeyboardButton(text="🛍 Черная пятница", callback_data="holiday:blackfriday")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="holiday:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def infographic_selection_keyboard(enabled: dict[str, bool], lang="ru") -> InlineKeyboardMarkup:
    rows = []
    # Убираем дублирование Рандома здесь, так как он уже есть в корневом меню
    
    if enabled.get("infographic_clothing", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_infographic_clothing", lang), callback_data="create_cat:infographic_clothing")])
    
    if enabled.get("infographic_other", True):
        rows.append([InlineKeyboardButton(text=get_string("cat_infographic_other", lang), callback_data="create_cat:infographic_other")])
    
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="menu_market")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def info_holiday_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("holiday_march8", lang), callback_data="info_holiday:8march")],
            [InlineKeyboardButton(text=get_string("holiday_feb23", lang), callback_data="info_holiday:23feb")],
            [InlineKeyboardButton(text=get_string("holiday_bday", lang), callback_data="info_holiday:bday")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="info_holiday:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def skip_step_keyboard(callback_prefix: str, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data=f"{callback_prefix}:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def pants_style_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("pants_relaxed", lang), callback_data="pants_style:relaxed"), InlineKeyboardButton(text=get_string("pants_slim", lang), callback_data="pants_style:slim")],
            [InlineKeyboardButton(text=get_string("pants_banana", lang), callback_data="pants_style:banana"), InlineKeyboardButton(text=get_string("pants_flare_knee", lang), callback_data="pants_flare_knee")],
            [InlineKeyboardButton(text=get_string("pants_baggy", lang), callback_data="pants_style:baggy"), InlineKeyboardButton(text=get_string("pants_mom", lang), callback_data="pants_mom")],
            [InlineKeyboardButton(text=get_string("pants_straight", lang), callback_data="pants_straight"), InlineKeyboardButton(text=get_string("skip", lang), callback_data="pants_style:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def sleeve_length_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("sleeve_normal", lang), callback_data="form_sleeve:normal"), InlineKeyboardButton(text=get_string("sleeve_long", lang), callback_data="form_sleeve:long")],
            [InlineKeyboardButton(text=get_string("sleeve_three_quarter", lang), callback_data="form_sleeve:three_quarter"), InlineKeyboardButton(text=get_string("sleeve_elbow", lang), callback_data="form_sleeve:elbow")],
            [InlineKeyboardButton(text=get_string("sleeve_short", lang), callback_data="form_sleeve:short"), InlineKeyboardButton(text=get_string("sleeve_none", lang), callback_data="form_sleeve:none")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="form_sleeve:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def garment_length_keyboard(lang="ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=get_string("len_short_top", lang), callback_data="garment_len:short_top"), InlineKeyboardButton(text=get_string("len_regular_top", lang), callback_data="garment_len:regular_top")],
        [InlineKeyboardButton(text=get_string("len_to_waist", lang), callback_data="garment_len:to_waist"), InlineKeyboardButton(text=get_string("len_below_waist", lang), callback_data="garment_len:below_waist")],
        [InlineKeyboardButton(text=get_string("len_mid_thigh", lang), callback_data="garment_len:mid_thigh"), InlineKeyboardButton(text=get_string("len_to_knees", lang), callback_data="garment_len:to_knees")],
        [InlineKeyboardButton(text=get_string("len_below_knees", lang), callback_data="garment_len:below_knees"), InlineKeyboardButton(text=get_string("len_midi", lang), callback_data="garment_len:midi")],
        [InlineKeyboardButton(text=get_string("len_to_ankles", lang), callback_data="garment_len:to_ankles"), InlineKeyboardButton(text=get_string("len_to_floor", lang), callback_data="garment_len:to_floor")],
        [InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="garment_len:custom")],
        [InlineKeyboardButton(text=get_string("skip", lang), callback_data="garment_len:skip")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def form_view_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_string("view_front", lang), callback_data="form_view:front"),
                InlineKeyboardButton(text=get_string("view_back", lang), callback_data="form_view:back"),
            ],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def confirm_generation_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("create_photo", lang), callback_data="form_generate")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_gender_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("gender_male", lang), callback_data="rand_gender:male"), InlineKeyboardButton(text=get_string("gender_female", lang), callback_data="rand_gender:female")],
            [InlineKeyboardButton(text=get_string("gender_boy", lang), callback_data="rand_gender:boy"), InlineKeyboardButton(text=get_string("gender_girl", lang), callback_data="rand_gender:girl")],
            [InlineKeyboardButton(text=get_string("gender_unisex", lang), callback_data="rand_gender:unisex")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_loc_group_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("loc_outdoor", lang), callback_data="rand_locgroup:outdoor"), InlineKeyboardButton(text=get_string("loc_indoor", lang), callback_data="rand_locgroup:indoor")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def random_location_keyboard(group: str, lang="ru") -> InlineKeyboardMarkup:
    if group == "indoor":
        items = [
            ("inside_restaurant", "view_restaurant"),
            ("photo_studio", "view_studio"),
            ("coffee_shop", "view_room"),
        ]
    else:
        items = [
            ("city", "view_city"),
            ("building", "view_building"),
            ("wall", "view_wall"),
            ("park", "view_park"),
            ("coffee_shop_out", "loc_cafe"),
            ("forest", "view_forest"),
            ("car", "loc_car"),
        ]
    rows: list[list[InlineKeyboardButton]] = []
    for k, skey in items:
        rows.append([InlineKeyboardButton(text=get_string(skey, lang), callback_data=f"rand_location:{k}")])
    # Кнопка для собственного варианта
    rows.append([InlineKeyboardButton(text=get_string("custom_variant", lang), callback_data="rand_location_custom")])
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def female_clothes_keyboard(lang="ru", back_data="create_cat:presets") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 " + get_string("cloth_coat", lang), callback_data="female_cloth:coat"), InlineKeyboardButton(text="👗 " + get_string("cloth_dress", lang), callback_data="female_cloth:dress")],
            [InlineKeyboardButton(text="👖 " + get_string("pants_straight", lang), callback_data="female_cloth:pants"), InlineKeyboardButton(text="🩳 " + get_string("cloth_shorts", lang), callback_data="female_cloth:shorts")],
            [InlineKeyboardButton(text="👚 " + get_string("subcat_top", lang), callback_data="female_cloth:top"), InlineKeyboardButton(text="🏠 " + get_string("cloth_loungewear", lang), callback_data="female_cloth:loungewear")],
            [InlineKeyboardButton(text="🥼 " + get_string("cloth_suit", lang), callback_data="female_cloth:suit"), InlineKeyboardButton(text="🦺 " + get_string("cloth_overall", lang), callback_data="female_cloth:overall")],
            [InlineKeyboardButton(text="👗 " + get_string("cloth_skirt", lang), callback_data="female_cloth:skirt"), InlineKeyboardButton(text="👠 " + get_string("cloth_shoes", lang), callback_data="female_cloth:shoes")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data=back_data)],
        ]
    )

def male_clothes_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 " + get_string("cloth_coat", lang), callback_data="male_cloth:coat"), InlineKeyboardButton(text="👖 " + get_string("pants_straight", lang), callback_data="male_cloth:pants")],
            [InlineKeyboardButton(text="🩳 " + get_string("cloth_shorts", lang), callback_data="male_cloth:shorts"), InlineKeyboardButton(text="🥼 " + get_string("cloth_suit", lang), callback_data="male_cloth:suit")],
            [InlineKeyboardButton(text="👕 " + get_string("subcat_top", lang), callback_data="male_cloth:top"), InlineKeyboardButton(text="🏠 " + get_string("cloth_loungewear", lang), callback_data="male_cloth:loungewear")],
            [InlineKeyboardButton(text="🦺 " + get_string("cloth_overall", lang), callback_data="male_cloth:overall"), InlineKeyboardButton(text="👟 " + get_string("cloth_shoes", lang), callback_data="male_cloth:shoes")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="create_cat:presets")],
        ]
    )

def boy_clothes_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 " + get_string("cloth_coat", lang), callback_data="child_cloth:coat"), InlineKeyboardButton(text="👖 " + get_string("pants_straight", lang), callback_data="child_cloth:pants")],
            [InlineKeyboardButton(text="🩳 " + get_string("cloth_shorts", lang), callback_data="child_cloth:shorts"), InlineKeyboardButton(text="🥼 " + get_string("cloth_suit", lang), callback_data="child_cloth:suit")],
            [InlineKeyboardButton(text="👕 " + get_string("subcat_top", lang), callback_data="child_cloth:top"), InlineKeyboardButton(text="🏠 " + get_string("cloth_loungewear", lang), callback_data="child_cloth:loungewear")],
            [InlineKeyboardButton(text="🦺 " + get_string("cloth_overall", lang), callback_data="child_cloth:overall"), InlineKeyboardButton(text="👟 " + get_string("cloth_shoes", lang), callback_data="child_cloth:shoes")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="create_cat:presets")],
        ]
    )

def girl_clothes_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧥 " + get_string("cloth_coat", lang), callback_data="child_cloth:coat"), InlineKeyboardButton(text="👗 " + get_string("cloth_dress", lang), callback_data="child_cloth:dress")],
            [InlineKeyboardButton(text="👖 " + get_string("pants_straight", lang), callback_data="child_cloth:pants"), InlineKeyboardButton(text="🩳 " + get_string("cloth_shorts", lang), callback_data="child_cloth:shorts")],
            [InlineKeyboardButton(text="🥼 " + get_string("cloth_suit", lang), callback_data="child_cloth:suit"), InlineKeyboardButton(text="👚 " + get_string("subcat_top", lang), callback_data="child_cloth:top")],
            [InlineKeyboardButton(text="🏠 " + get_string("cloth_loungewear", lang), callback_data="child_cloth:loungewear"), InlineKeyboardButton(text="🦺 " + get_string("cloth_overall", lang), callback_data="child_cloth:overall")],
            [InlineKeyboardButton(text="👗 " + get_string("cloth_skirt", lang), callback_data="child_cloth:skirt"), InlineKeyboardButton(text="👠 " + get_string("cloth_shoes", lang), callback_data="child_cloth:shoes")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="create_cat:presets")],
        ]
    )

def admin_user_actions_keyboard(user_id: int, lang="ru", blocked: bool = False) -> InlineKeyboardMarkup:
    block_text = get_string("admin_unblock", lang) if blocked else get_string("admin_block", lang)
    block_val = "0" if blocked else "1"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=block_text, callback_data=f"admin_block:{user_id}:{block_val}")],
            [InlineKeyboardButton(text=get_string("menu_history", lang), callback_data=f"admin_user_history:{user_id}")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_users_page:0")]
        ]
    )

def admin_user_history_keyboard(user_id: int, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("back", lang), callback_data=f"admin_user:{user_id}")]
        ]
    )

def admin_models_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_list_all", lang), callback_data="admin_models_browse")],
            [InlineKeyboardButton(text=get_string("admin_add", lang), callback_data="admin_model_add")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")],
        ]
    )

def admin_models_category_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("cat_female", lang), callback_data="admin_cat:female"), InlineKeyboardButton(text=get_string("cat_male", lang), callback_data="admin_cat:male")],
            [InlineKeyboardButton(text=get_string("cat_child", lang), callback_data="admin_cat:child")],
            [InlineKeyboardButton(text=get_string("cat_storefront", lang), callback_data="admin_cat:storefront"), InlineKeyboardButton(text=get_string("cat_whitebg", lang), callback_data="admin_cat:whitebg")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_models")],
        ]
    )

def admin_models_cloth_keyboard(category: str, lang="ru") -> InlineKeyboardMarkup:
    # Simplified version
    rows = [
        [InlineKeyboardButton(text="👗 " + get_string("cloth_dress", lang), callback_data=f"admin_cloth:{category}:dress")],
        [InlineKeyboardButton(text="🧥 " + get_string("subcat_outerwear", lang), callback_data=f"admin_cloth:{category}:coat")],
        [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_models_browse")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_models_actions_keyboard(category: str, cloth: str, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_list", lang), callback_data=f"admin_model_list:{category}:{cloth}:0")],
            [InlineKeyboardButton(text=get_string("admin_add", lang), callback_data=f"admin_model_add:{category}:{cloth}")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data=f"admin_cat:{category}")],
        ]
    )

def admin_model_list_keyboard(category: str, cloth: str, items: list, page: int, has_next: bool, lang="ru") -> InlineKeyboardMarkup:
    rows = []
    for mid, name, ptitle in items:
        rows.append([InlineKeyboardButton(text=f"#{mid} {name} ({ptitle})", callback_data=f"admin_model_edit:{mid}")])
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_model_list:{category}:{cloth}:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_model_list:{category}:{cloth}:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data=f"admin_cloth:{category}:{cloth}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_model_edit_keyboard(model_id: int, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_rename", lang), callback_data=f"admin_model_rename:{model_id}")],
            [InlineKeyboardButton(text=get_string("admin_change_photo", lang), callback_data=f"admin_model_setphoto:{model_id}")],
            [InlineKeyboardButton(text=get_string("admin_change_prompt", lang), callback_data=f"admin_model_prompt:{model_id}:0")],
            [InlineKeyboardButton(text=get_string("admin_delete", lang), callback_data=f"admin_model_delete:{model_id}")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_models")],
        ]
    )

def admin_prompt_pick_keyboard(model_id: int, prompts: list, page: int, has_next: bool, lang="ru") -> InlineKeyboardMarkup:
    rows = []
    for pid, title in prompts:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"admin_model_setprompt:{model_id}:{pid}")])
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_model_prompt:{model_id}:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_model_prompt:{model_id}:{page+1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data=f"admin_model_edit:{model_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_model_created_keyboard(category: str, cloth: str, lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_to_list", lang), callback_data=f"admin_model_list:{category}:{cloth}:0")],
            [InlineKeyboardButton(text=get_string("back_main", lang), callback_data="back_main")],
        ]
    )

def admin_api_keys_keyboard(keys: list, lang="ru") -> InlineKeyboardMarkup:
    rows = []
    for key_tuple in keys:
        kid, token, is_active = key_tuple[0], key_tuple[1], key_tuple[2]
        status = "✅" if is_active else "⛔"
        rows.append([
            InlineKeyboardButton(text=f"{status} #{kid} {token[:10]}...", callback_data=f"api_key_show:{kid}"),
            InlineKeyboardButton(text="⚙️", callback_data=f"api_key_edit:{kid}"),
            InlineKeyboardButton(text="🔄", callback_data=f"api_key_toggle:{kid}"),
            InlineKeyboardButton(text="❌", callback_data=f"api_key_delete:{kid}"),
        ])
    rows.append([InlineKeyboardButton(text=get_string("admin_add_key", lang), callback_data="api_key_add")])
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def broadcast_skip_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="broadcast_skip")],
            [InlineKeyboardButton(text=get_string("admin_cancel", lang), callback_data="broadcast_cancel")],
        ]
    )

def broadcast_confirm_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_send", lang), callback_data="broadcast_send")],
            [InlineKeyboardButton(text=get_string("admin_cancel", lang), callback_data="broadcast_cancel")],
        ]
    )

def admin_own_prompts_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_step_model", lang), callback_data="admin_own_prompt_edit:1")],
            [InlineKeyboardButton(text=get_string("admin_step_gen", lang), callback_data="admin_own_prompt_edit:3")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")],
        ]
    )

def admin_own_variant_prompts_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_view", lang), callback_data="admin_own_variant_prompt_view")],
            [InlineKeyboardButton(text=get_string("admin_edit", lang), callback_data="admin_own_variant_prompt_edit")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")],
        ]
    )

def admin_own_variant_api_keys_keyboard(keys: list, lang="ru") -> InlineKeyboardMarkup:
    rows = []
    for key_tuple in keys:
        kid, token, is_active = key_tuple[0], key_tuple[1], key_tuple[2]
        status = "✅" if is_active else "⛔"
        rows.append([
            InlineKeyboardButton(text=f"{status} #{kid} {token[:10]}...", callback_data=f"own_variant_api_key_show:{kid}"),
            InlineKeyboardButton(text="🔄", callback_data=f"own_variant_api_key_toggle:{kid}"),
            InlineKeyboardButton(text="❌", callback_data=f"own_variant_api_key_delete:{kid}"),
        ])
    rows.append([InlineKeyboardButton(text=get_string("admin_add_key", lang), callback_data="own_variant_api_key_add")])
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def own_sleeve_length_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("sleeve_normal", lang), callback_data="own_sleeve:normal"), InlineKeyboardButton(text=get_string("sleeve_long", lang), callback_data="own_sleeve:long")],
            [InlineKeyboardButton(text=get_string("sleeve_three_quarter", lang), callback_data="own_sleeve:three_quarter"), InlineKeyboardButton(text=get_string("sleeve_elbow", lang), callback_data="own_sleeve:elbow")],
            [InlineKeyboardButton(text=get_string("sleeve_short", lang), callback_data="own_sleeve:short"), InlineKeyboardButton(text=get_string("sleeve_none", lang), callback_data="own_sleeve:none")],
            [InlineKeyboardButton(text=get_string("skip", lang), callback_data="own_sleeve:skip")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="back_step")],
        ]
    )

def admin_category_prices_keyboard(prices: list, lang="ru") -> InlineKeyboardMarkup:
    rows = []
    rows.append([InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_howto_edit_keyboard(lang="ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_string("admin_edit_btn", lang), callback_data="admin_howto_edit_start")],
            [InlineKeyboardButton(text=get_string("back", lang), callback_data="admin_main")],
        ]
    )

def dynamic_keyboard(options: list[tuple], is_optional: bool = False, lang="ru") -> InlineKeyboardMarkup:
    """Универсальная клавиатура для динамических шагов"""
    import logging
    logger = logging.getLogger(__name__)
    
    rows = []
    # options: list of (id, text, value, order, custom_prompt)
    # Группируем по 2 кнопки в ряд
    for i in range(0, len(options), 2):
        row = []
        for opt in options[i:i+2]:
            # Используем ID опции для однозначной идентификации в колбэке
            row.append(InlineKeyboardButton(text=opt[1], callback_data=f"dyn_opt:{opt[0]}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
