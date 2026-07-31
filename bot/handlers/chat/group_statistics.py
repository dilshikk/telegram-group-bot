"""
Group statistics: счётчики сообщений/вступлений/выходов через Redis,
сброс в PostgreSQL при вызове /stats или раз в сутки.
Такой подход избегает попадания в БД на каждое сообщение.
"""
from datetime import date

from aiogram import Router, F
from aiogram.filters import Command
from sqlalchemy import select

from bot.database import SessionFactory
from bot.database.models import GroupStat
from bot.filters.roles import HasRole
from bot.services.cache import redis

router = Router(name="group_statistics")

# Redis key helpers
def _key(chat_id: int, field: str) -> str:
    return f"stats:{chat_id}:{date.today().isoformat()}:{field}"


async def _incr(chat_id: int, field: str) -> None:
    """Инкремент Redis-счётчика. Дешевле, чем открывать сессию БД."""
    key = _key(chat_id, field)
    await redis.incr(key)
    await redis.expire(key, 86400 * 2)  # хранить 2 дня


async def _flush_to_db(chat_id: int) -> GroupStat | None:
    """Читает Redis-счётчики и сохраняет/обновляет запись в PostgreSQL."""
    today = date.today()
    fields = ["messages_count", "joins_count", "leaves_count", "sanctions_count"]

    values: dict[str, int] = {}
    for field in fields:
        raw = await redis.get(_key(chat_id, field))
        values[field] = int(raw) if raw else 0

    async with SessionFactory() as session:
        row = (await session.execute(
            select(GroupStat).where(GroupStat.chat_id == chat_id, GroupStat.date == today)
        )).scalar_one_or_none()
        if row is None:
            row = GroupStat(chat_id=chat_id, date=today)
            session.add(row)
        for field, val in values.items():
            setattr(row, field, val)
        await session.commit()
        return row


# ---------------------------------------------------------------------------
# Обработчики событий — только инкремент Redis, без открытия БД-сессии
# ---------------------------------------------------------------------------

@router.message(F.text, ~F.text.startswith("/"))
async def count_message(message) -> None:
    if message.chat and message.chat.type != "private":
        await _incr(message.chat.id, "messages_count")


@router.message(F.new_chat_members)
async def count_join(message) -> None:
    await _incr(message.chat.id, "joins_count")


@router.message(F.left_chat_member)
async def count_leave(message) -> None:
    await _incr(message.chat.id, "leaves_count")


# ---------------------------------------------------------------------------
# Команда /stats — сбрасывает Redis → DB и показывает итог
# ---------------------------------------------------------------------------

@router.message(Command("stats"), HasRole("admin"))
async def show_stats(message) -> None:
    row = await _flush_to_db(message.chat.id)
    if not row:
        await message.answer("Статистики за сегодня пока нет.")
        return
    await message.answer(
        f"\U0001f4ca <b>Статистика за сегодня</b>\n"
        f"Сообщений: {row.messages_count}\n"
        f"Вступлений: {row.joins_count}\n"
        f"Выходов: {row.leaves_count}\n"
        f"Санкций: {row.sanctions_count}",
        parse_mode="HTML",
    )
