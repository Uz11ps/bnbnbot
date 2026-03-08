from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.strings import get_string


def terms_keyboard(lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=True, inline=False)
    keyboard.add(Text(get_string("accept_terms", lang)), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text(get_string("agreement", lang)), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def main_menu_keyboard(lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text(get_string("create_normal_gen", lang)), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text(get_string("menu_market", lang)), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text(get_string("buy_plan", lang)), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text(get_string("menu_support", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("menu_profile", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text(get_string("menu_howto", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("menu_settings", lang)), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def settings_keyboard(lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text(get_string("select_lang", lang)), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text(get_string("agreement", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("back_main", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def marketplace_keyboard(enabled: dict[str, bool], lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=False, inline=False)

    if enabled.get("random", True):
        keyboard.add(Text(get_string("cat_random", lang)), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
    if enabled.get("random_other", True):
        keyboard.add(Text(get_string("cat_random_other", lang)), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()

    # В VK сразу даем обе инфографики отдельными кнопками
    if enabled.get("infographic_clothing", True):
        keyboard.add(Text(get_string("cat_infographic_clothing", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()
    if enabled.get("infographic_other", True):
        keyboard.add(Text(get_string("cat_infographic_other", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()

    if enabled.get("storefront", True):
        keyboard.add(Text(get_string("cat_storefront", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()
    if enabled.get("whitebg", True):
        keyboard.add(Text(get_string("cat_whitebg", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()
    if enabled.get("own", True):
        keyboard.add(Text(get_string("cat_own", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()
    if enabled.get("own_variant", True):
        keyboard.add(Text(get_string("cat_own_variant", lang)), color=KeyboardButtonColor.SECONDARY)
        keyboard.row()

    keyboard.add(Text(get_string("back_main", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def language_keyboard(lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=True, inline=False)
    keyboard.add(Text(get_string("lang_ru", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text(get_string("lang_en", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("lang_vi", lang)), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("back_main", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def back_to_main_keyboard(lang: str = "ru") -> str:
    keyboard = Keyboard(one_time=True, inline=False)
    keyboard.add(Text(get_string("back_main", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()


def aspect_ratio_keyboard(lang: str = "ru") -> str:
    """Клавиатура выбора формата фото для обычной генерации (VK)"""
    keyboard = Keyboard(one_time=True, inline=False)
    keyboard.add(Text("1:1"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("9:16"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("16:9"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("4:5"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("3:4"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("4:3"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(get_string("back_main", lang)), color=KeyboardButtonColor.NEGATIVE)
    return keyboard.get_json()
