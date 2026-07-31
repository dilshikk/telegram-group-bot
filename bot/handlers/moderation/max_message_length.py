from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database.engine import SessionFactory
from bot.filters.roles import HasRole
from bot.services.settings_service import update_settings

router = Router(name="max_message_length")


@router.message(Command("maxlength"), HasRole("admin"))
async def set_max_length(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "Использование: /maxlength <число> — установить макс. длину сообщения.\n"
            "/maxlength 0 — отключить."
        )
        return

    limit = int(args[1])
    async with SessionFactory() as session:
        await update_settings(session, message.chat.id, "max_message_length", {
            "enabled": limit > 0, "limit": limit,
        })
    limit_display = str(limit) if limit else "\u2014 (выкл.)"
    await message.answer(f"\u2705 Максимальная длина сообщения: {limit_display}")


@router.message(F.text, ~F.text.startswith("/"))
async def check_max_length(message: Message) -> None:
    from bot.services.settings_service import get_settings
    async with SessionFactory() as session:
        settings = await get_settings(session, message.chat.id)

    cfg = settings.get("max_message_length", {})
    if not cfg.get("enabled"):
        return

    limit = cfg.get("limit", 4000)
    if message.text and len(message.text) > limit:
        await message.delete()
        warn_text = f"\u26a0\ufe0f Сообщение удалено: превышена максимальная длина ({limit} символов)."
        await message.answer(warn_text)
