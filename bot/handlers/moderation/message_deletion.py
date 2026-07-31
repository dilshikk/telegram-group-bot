import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database.engine import SessionFactory
from bot.filters.roles import HasRole
from bot.services.settings_service import update_settings

router = Router(name="message_deletion")


async def _delayed_delete(message: Message, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("cleanservice"), HasRole("admin"))
async def toggle_clean_service(message: Message, chat_settings: dict | None = None) -> None:
    cfg = chat_settings or {}
    new_state = not cfg.get("message_deletion", {}).get("delete_service_messages", True)
    async with SessionFactory() as session:
        await update_settings(session, message.chat.id, "message_deletion", {"delete_service_messages": new_state})
    await message.answer(f"Удаление служебных сообщений: {'включено' if new_state else 'выключено'}")


@router.message(F.text.startswith("/"))
async def maybe_autodelete_command(message: Message, chat_settings: dict | None = None) -> None:
    cfg = chat_settings or {}
    delay = cfg.get("message_deletion", {}).get("delete_commands_after_sec", 0)
    if delay:
        asyncio.create_task(_delayed_delete(message, delay))
