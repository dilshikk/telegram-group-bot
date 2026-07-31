"""
Chat Context Middleware.
Загружает/создаёт Chat + ChatSettings, определяет роль отправителя в чате
(через Telegram get_chat_member, с кэшем в Redis) и прокидывает всё в handler data.
Поддерживает анонимных админов (sender_chat) — Support for anonymous admins.

Fix: при первом обнаружении роли owner/admin — сохраняем её в таблицу ChatUser,
чтобы get_admin_chats() мог найти группы пользователя при /settings из личного чата.

Fix 2: перед вставкой ChatUser обязательно upsert-им строку User,
иначе FK-ограничение `chat_users.user_id → users.id` роняет INSERT
и запись в chat_users никогда не появляется (ошибка глотается в except).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, Message, TelegramObject, Update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.database import SessionFactory
from bot.database.models import ChatUser, User
from bot.services.cache import get_json, set_json
from bot.services.settings_service import get_or_create_chat, get_settings

ROLE_CACHE_TTL = 60

class ChatContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message: Message | None = data.get("event_message") or getattr(event, "message", None)
        chat = getattr(message, "chat", None) if message else None

        if chat is None or chat.type == "private":
            return await handler(event, data)

        async with SessionFactory() as session:
            await get_or_create_chat(session, chat.id, chat.title or "", chat.type)
            data["chat_settings"] = await get_settings(session, chat.id)

        # Анонимный админ пишет от имени sender_chat == chat.id
        if message and message.sender_chat and message.sender_chat.id == chat.id:
            data["chat_user_role"] = "admin"
            data["is_anonymous_admin"] = True
            return await handler(event, data)

        user = getattr(message, "from_user", None) if message else None
        if user:
            role = await self._resolve_role(event, chat.id, user.id, data)
            data["chat_user_role"] = role

            # Синхронизируем роль owner/admin в БД, чтобы get_admin_chats() работал.
            # member-роль не пишем — таблица chat_users хранит только значимые роли.
            if role in ("owner", "admin"):
                await self._sync_chat_user(
                    chat_id=chat.id,
                    user_id=user.id,
                    role=role,
                    username=user.username,
                    full_name=user.full_name or "",
                )

        return await handler(event, data)

    @staticmethod
    async def _resolve_role(event: TelegramObject, chat_id: int, user_id: int, data: dict[str, Any]) -> str:
        cache_key = f"role:{chat_id}:{user_id}"
        cached = await get_json(cache_key)
        if cached is not None:
            return cached

        bot = data["bot"]
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except Exception:
            await set_json(cache_key, "member", ex=ROLE_CACHE_TTL)
            return "member"

        if isinstance(member, ChatMemberOwner):
            role = "owner"
        elif isinstance(member, ChatMemberAdministrator):
            role = "admin"
        else:
            role = "member"

        await set_json(cache_key, role, ex=ROLE_CACHE_TTL)
        return role

    @staticmethod
    async def _sync_chat_user(
        chat_id: int,
        user_id: int,
        role: str,
        username: str | None = None,
        full_name: str = "",
    ) -> None:
        """
        Upsert записи в users + chat_users атомарно.

        Порядок важен: сначала upsert User (иначе FK chat_users.user_id -> users.id
        нарушается и весь INSERT молча падает в except, оставляя chat_users пустой).
        """
        try:
            async with SessionFactory() as session:
                # 1. Upsert строки User — обязательно перед ChatUser из-за FK
                user_stmt = (
                    pg_insert(User)
                    .values(id=user_id, username=username, full_name=full_name)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "username":  username,
                            "full_name": full_name,
                        },
                    )
                )
                await session.execute(user_stmt)
                # flush чтобы строка User была видна следующему INSERT в этой же транзакции
                await session.flush()

                # 2. Upsert ChatUser — теперь FK гарантированно удовлетворён
                chat_user_stmt = (
                    pg_insert(ChatUser)
                    .values(chat_id=chat_id, user_id=user_id, role=role)
                    .on_conflict_do_update(
                        constraint="uq_chat_user",
                        set_={"role": role},
                        # Обновляем только если роль реально изменилась
                        where=(ChatUser.role != role),
                    )
                )
                await session.execute(chat_user_stmt)
                await session.commit()
        except Exception:
            # Не блокируем обработку сообщений при ошибке синхронизации
            pass
