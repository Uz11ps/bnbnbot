from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from vk_bot.context import get_db, get_settings

router = BotLabeler()


class IsAdmin(ABCRule):
    async def check(self, message: Message) -> bool:
        settings = get_settings()
        return message.from_id in (settings.admin_ids or [])


@router.message(IsAdmin())
async def handle_admin(message: Message):
    text = (message.text or "").strip().lower()
    if text not in {"/admin", "admin"}:
        return

    db = get_db()
    users_count = 0
    try:
        users_count = len(await db.list_all_user_ids())
    except Exception:
        pass
    await message.answer(
        "VK Admin\n"
        f"Пользователей в базе: {users_count}\n"
        "Базовые админ-команды будут расширены далее."
    )
