from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.utils.i18n import t
from bot.handlers.welcome.rules import HELP_CATEGORIES

router = Router(name="start_help")

CATEGORIES_LIST = ", ".join(HELP_CATEGORIES.keys())


@router.message(Command("start"))
async def cmd_start(message: Message, chat_settings: dict | None = None) -> None:
    lang = "ru"
    await message.answer(t(lang, "help_text"), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, command: CommandObject) -> None:
    category = (command.args or "").strip().lower()
    if category and category in HELP_CATEGORIES:
        await message.answer(HELP_CATEGORIES[category], parse_mode="HTML")
        return
    await message.answer(
        "<b>Основные разделы команд</b>\n"
        "/rules — правила чата\n"
        "/ban /mute /kick /warn — модерация (ответом на сообщение)\n"
        "/settings — информация о настройках чата\n"
        "/commands — полный список команд по категориям\n\n"
        f"Используйте /help &lt;категория&gt; для деталей.\n"
        f"Категории: {CATEGORIES_LIST}",
        parse_mode="HTML",
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, chat_settings: dict | None = None) -> None:
    cfg = chat_settings or {}
    if message.chat.type == "private":
        await message.answer(
            "\u2139\ufe0f Команда /settings работает в группах.\n"
            "Добавьте бота в группу и напишите /settings там."
        )
        return
    # Краткий обзор текущих настроек
    lines = ["<b>\u2699\ufe0f Текущие настройки чата</b>\n"]
    checks = [
        ("antispam", "Антиспам"),
        ("antiflood", "Антифлуд"),
        ("anti_nsfw", "Анти-NSFW"),
        ("approve_mode", "Режим одобрения"),
        ("night_mode", "Ночной режим"),
        ("max_message_length", "Макс. длина сообщений"),
    ]
    for key, label in checks:
        enabled = cfg.get(key, {}).get("enabled", False)
        status = "\u2705" if enabled else "\u274c"
        lines.append(f"{status} {label}")
    lines.append("\nДля изменений используйте конкретные команды (/help admin, /help moderation и т.д.)")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("commands"))
async def cmd_commands(message: Message) -> None:
    await message.answer(
        f"\U0001f4c2 <b>Категории команд:</b> {CATEGORIES_LIST}\n\n"
        "Используйте /help &lt;категория&gt; для просмотра команд в категории.",
        parse_mode="HTML",
    )
