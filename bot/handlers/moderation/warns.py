"""Warns settings: /warn /unwarn /warnlist + настройка порога и действия при достижении max_warns."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from bot.database import SessionFactory
from bot.database.models import ChatUser, User
from bot.filters.roles import HasRole
from bot.services.moderation_actions import apply_sanction
from bot.services.settings_service import update_settings
from bot.utils.i18n import t

router = Router(name="warns")


@router.message(Command("warn"), HasRole("admin"))
async def cmd_warn(message: Message, command: CommandObject, chat_settings: dict | None = None) -> None:
    if not message.reply_to_message:
        await message.answer("Ответьте на сообщение пользователя: /warn [причина]")
        return
    cfg = chat_settings or {}
    target = message.reply_to_message.from_user
    await apply_sanction(message.bot, message.chat.id, target.id, "warn", command.args or "", message.from_user.id)

    async with SessionFactory() as session:
        cu = (await session.execute(
            select(ChatUser).where(ChatUser.chat_id == message.chat.id, ChatUser.user_id == target.id)
        )).scalar_one_or_none()
        warns_count = cu.warns if cu else 1

    max_warns = cfg.get("warns", {}).get("max_warns", 3)
    await message.answer(t("ru", "user_warned", mention=target.mention_html(), count=warns_count, max=max_warns),
                          parse_mode="HTML")

    if warns_count >= max_warns:
        action = cfg.get("warns", {}).get("action", "ban")
        await apply_sanction(message.bot, message.chat.id, target.id, action,
                              "Достигнут лимит предупреждений", 0)
        await message.answer(f"\U0001f6ab Лимит предупреждений исчерпан \u2014 применено действие «{action}».")


@router.message(Command("unwarn"), HasRole("admin"))
async def cmd_unwarn(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Ответьте на сообщение пользователя: /unwarn")
        return
    target_id = message.reply_to_message.from_user.id
    async with SessionFactory() as session:
        cu = (await session.execute(
            select(ChatUser).where(ChatUser.chat_id == message.chat.id, ChatUser.user_id == target_id)
        )).scalar_one_or_none()
        if cu and cu.warns > 0:
            cu.warns -= 1
            await session.commit()
    await message.answer("\u2705 Одно предупреждение снято.")


@router.message(Command("warnlist"), HasRole("admin"))
async def cmd_warnlist(message: Message) -> None:
    """Показывает список пользователей с предупреждениями в чате."""
    async with SessionFactory() as session:
        rows = (await session.execute(
            select(ChatUser).where(
                ChatUser.chat_id == message.chat.id,
                ChatUser.warns > 0,
            ).order_by(ChatUser.warns.desc())
        )).scalars().all()

        if not rows:
            await message.answer("В этом чате нет пользователей с предупреждениями.")
            return

        lines = ["⚠️ <b>Предупреждения в чате</b>\n"]
        for cu in rows:
            user = await session.get(User, cu.user_id)
            if user:
                name = f"@{user.username}" if user.username else user.full_name or str(cu.user_id)
            else:
                name = f"<code>{cu.user_id}</code>"
            lines.append(f"• {name} — <b>{cu.warns}</b> предупр.")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("setwarnlimit"), HasRole("admin"))
async def set_warn_limit(message: Message, command: CommandObject) -> None:
    if not command.args or not command.args.isdigit():
        await message.answer("Использование: /setwarnlimit <число>")
        return
    async with SessionFactory() as session:
        await update_settings(session, message.chat.id, "warns", {"max_warns": int(command.args)})
    await message.answer(f"\u2705 Лимит предупреждений установлен: {command.args}")
