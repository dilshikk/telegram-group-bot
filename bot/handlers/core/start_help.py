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
        "/settings — панель настроек чата (только в группах)\n"
        "/commands — полный список команд по категориям\n\n"
        f"Используйте /help &lt;категория&gt; для деталей.\n"
        f"Категории: {CATEGORIES_LIST}",
        parse_mode="HTML",
    )


@router.message(Command("commands"))
async def cmd_commands(message: Message) -> None:
    await message.answer(
        f"\U0001f4c2 <b>Категории команд:</b> {CATEGORIES_LIST}\n\n"
        "Используйте /help &lt;категория&gt; для просмотра команд в категории.",
        parse_mode="HTML",
    )
