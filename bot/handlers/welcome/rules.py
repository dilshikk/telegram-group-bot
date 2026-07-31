from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database.engine import SessionFactory
from bot.filters.roles import HasRole
from bot.services.settings_service import update_settings

router = Router(name="rules")

HELP_CATEGORIES: dict[str, str] = {
    "moderation": (
        "<b>Модерация</b>\n"
        "/ban [причина] — забанить (ответом)\n"
        "/mute [время] [причина] — замутить (ответом)\n"
        "/kick [причина] — кикнуть (ответом)\n"
        "/warn [причина] — предупредить (ответом)\n"
        "/unwarn — снять предупреждение (ответом)\n"
        "/warnlist — список предупреждений (ответом)\n"
        "/unban — разбанить (ответом)\n"
        "/unmute — размутить (ответом)"
    ),
    "welcome": (
        "<b>Приветствие</b>\n"
        "/setwelcome &lt;текст&gt; — установить приветствие\n"
        "/setgoodbye &lt;текст&gt; — установить прощание\n"
        "/rules — показать правила\n"
        "/setrules &lt;текст&gt; — установить правила"
    ),
    "antiflood": (
        "<b>Антифлуд</b>\n"
        "/setflood <макс> <секунд> [mute|kick|ban] — настроить флуд"
    ),
    "captcha": (
        "<b>Капча</b>\n"
        "/captcha on|off — включить/выключить капчу"
    ),
    "blocks": (
        "<b>Блокировки</b>\n"
        "/cleanservice on|off — удалять служебные сообщения\n"
        "/maxlength <число> — макс. длина сообщения\n"
        "/antinsfw on|off — блокировать NSFW\n"
        "/maskedlinks on|off — блокировать замаскированные ссылки"
    ),
    "filters": (
        "<b>Фильтры</b>\n"
        "/addbadword <слово> — добавить запрещённое слово\n"
        "/delbadword <слово> — удалить запрещённое слово\n"
        "/badwords — список запрещённых слов"
    ),
    "admin": (
        "<b>Администрирование</b>\n"
        "/checkperms — проверить права бота\n"
        "/setlang <ru|en> — язык бота\n"
        "/settz <±HH:MM> — часовой пояс для ночного режима"
    ),
    "stats": (
        "<b>Статистика</b>\n"
        "/stats — статистика группы"
    ),
    "privacy": (
        "<b>Приватность</b>\n"
        "/privacy — переключить режим приватности"
    ),
    "warns": (
        "<b>Предупреждения</b>\n"
        "/warn — предупредить (ответом)\n"
        "/warnlist — список варнов (ответом)\n"
        "/unwarn — снять варн (ответом)"
    ),
    "modules": (
        "<b>Модули</b>\n"
        "/antispam on|off — антиспам\n"
        "/antiflood on|off — антифлуд\n"
        "/nightmode <start> <end> — ночной режим"
    ),
    "notes": (
        "<b>Заметки</b>\n"
        "(скоро)"
    ),
}


@router.message(Command("setrules"), HasRole("admin"))
async def set_rules(message: Message, command: CommandObject, chat_settings: dict | None = None) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer("Использование: /setrules <текст правил>")
        return
    async with SessionFactory() as session:
        await update_settings(session, message.chat.id, "rules", {"text": text})
    await message.answer("\u2705 Правила обновлены.")


@router.message(Command("rules"))
async def show_rules(message: Message, chat_settings: dict | None = None) -> None:
    cfg = chat_settings or {}
    text = cfg.get("rules", {}).get("text")
    await message.answer(text if text else "Правила для этого чата ещё не заданы.")
