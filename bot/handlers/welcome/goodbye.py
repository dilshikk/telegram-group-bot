"""
Goodbye — сообщение при выходе участника.

FSM-редактор (работает в личном чате с ботом или в группе):
  sp:m:goodbye → главное меню модуля (текст / медиа / URL-кнопки)
  sp:gb:set_text:<chat_id>   → ожидаем текст
  sp:gb:set_media:<chat_id>  → ожидаем медиа
  sp:gb:set_buttons:<chat_id>→ ожидаем строки кнопок
  sp:gb:del_buttons:<chat_id>→ удалить URL-кнопки
  sp:gb:del_message:<chat_id>→ сбросить медиа
  sp:gb:cancel               → отмена FSM
  sp:gb:preview:<chat_id>    → предпросмотр одного блока
  sp:gb:full_preview:<chat_id>→ полный предпросмотр

Переменные в тексте:
  {ID} {NAME} {SURNAME} {NAMESURNAME} {MENTION} {USERNAME}
  {GROUPNAME} {RULES} {DATE} {TIME} {WEEKDAY} {LANG}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database import SessionFactory
from bot.filters.roles import HasRole
from bot.services.settings_service import get_settings, update_settings

router = Router(name="goodbye")


# ---------------------------------------------------------------------------
# FSM States
# ---------------------------------------------------------------------------

class GoodbyeFSM(StatesGroup):
    waiting_text    = State()
    waiting_media   = State()
    waiting_buttons = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _goodbye_main_keyboard(chat_id: int, cfg: dict) -> InlineKeyboardMarkup:
    has_text    = bool(cfg.get("text"))
    has_media   = bool(cfg.get("media_file_id"))
    has_buttons = bool(cfg.get("buttons"))

    def _status(flag: bool) -> str:
        return "✅" if flag else "❌"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"📄 Текст {_status(has_text)}",    callback_data=f"sp:gb:set_text:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                       callback_data=f"sp:gb:preview_text:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text=f"🖼 Медиа {_status(has_media)}",   callback_data=f"sp:gb:set_media:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                       callback_data=f"sp:gb:preview_media:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text=f"🔤 URL-кнопки {_status(has_buttons)}", callback_data=f"sp:gb:set_buttons:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                            callback_data=f"sp:gb:preview_buttons:{chat_id}"),
        ],
        [InlineKeyboardButton(text="👀 Полный предпросмотр",              callback_data=f"sp:gb:full_preview:{chat_id}")],
        [InlineKeyboardButton(text="🎨 Выбрать Тему  NEW",                callback_data=f"sp:gb:theme:{chat_id}")],
        [InlineKeyboardButton(text="◀ Назад",                             callback_data="sp:main:0")],
    ])


_VARIABLES_TEXT = (
    "👉 <b>Отправьте сейчас сообщение, которое хотите установить!</b>\n\n"
    "Вы можете использовать <b>HTML</b> и:\n"
    "• <code>{ID}</code> = идентификатор пользователя\n"
    "• <code>{NAME}</code> = имя\n"
    "• <code>{SURNAME}</code> = фамилия\n"
    "• <code>{NAMESURNAME}</code> = имя и фамилия\n"
    "• <code>{LANG}</code> = язык пользователя\n"
    "• <code>{DATE}</code> = текущая дата\n"
    "• <code>{TIME}</code> = текущее время\n"
    "• <code>{WEEKDAY}</code> = день недели\n"
    "• <code>{MENTION}</code> = ссылка на профиль пользователя\n"
    "• <code>{USERNAME}</code> = имя пользователя\n"
    "• <code>{GROUPNAME}</code> = имя группы\n"
    "• <code>{RULES}</code> = правила группы"
)

_MEDIA_PROMPT = (
    "👉 <b>Отправьте сейчас медиа</b> (фотографии, видео, наклейки ...), "
    "который вы хотите установить.\n"
    "<i>Вы также можете ввести подпись.</i>"
)

_BUTTONS_PROMPT = (
    "👉 <b>Установите кнопки, которые будут вставлены под сообщением</b>\n"
    "Отправьте сообщение, структурированное следующим образом:\n\n"
    "• Вставьте <b>одну кнопку</b>:\n"
    "<code>Название кнопки - t.me/LinkExample</code>\n\n"
    "• Вставьте <b>несколько кнопок в один ряд</b>:\n"
    "<code>Название кнопки - t.me/LinkExample && Текст кнопки - t.me/LinkExample</code>\n\n"
    "• Вставьте <b>несколько рядов кнопок</b>:\n"
    "<code>Название кнопки - t.me/LinkExample\n"
    "Название кнопки - t.me/LinkExample</code>"
)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sp:gb:cancel")]
    ])


def _media_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить сообщение", callback_data="sp:gb:del_media_prompt")],
        [InlineKeyboardButton(text="❌ Отмена",            callback_data="sp:gb:cancel")],
    ])


def _buttons_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Простое создание кнопок", callback_data="sp:gb:simple_buttons")],
        [InlineKeyboardButton(text="🚫 Удалить URL-кнопки",      callback_data="sp:gb:del_buttons_now")],
        [InlineKeyboardButton(text="❌ Отмена",                   callback_data="sp:gb:cancel")],
    ])


def _parse_buttons(raw: str) -> list[list[tuple[str, str]]]:
    """Парсит строки кнопок в формате 'Текст - URL && Текст2 - URL2'"""
    rows: list[list[tuple[str, str]]] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row: list[tuple[str, str]] = []
        for part in line.split("&&"):
            part = part.strip()
            m = re.match(r"^(.+?)\s*-\s*(https?://\S+|t\.me/\S+)$", part, re.IGNORECASE)
            if m:
                row.append((m.group(1).strip(), m.group(2).strip()))
        if row:
            rows.append(row)
    return rows


def _buttons_to_inline_kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, url=u) for t, u in row]
            for row in rows
        ]
    )


def _format_text(template: str, member: "User | None" = None, chat_title: str = "") -> str:
    now = datetime.now(timezone.utc)
    weekdays = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    name = getattr(member, "first_name", "") or ""
    surname = getattr(member, "last_name", "") or ""
    username = getattr(member, "username", "") or ""
    mention = f'<a href="tg://user?id={getattr(member, "id", 0)}">{name}</a>' if member else name

    return (
        template
        .replace("{ID}",          str(getattr(member, "id", "")))
        .replace("{NAME}",        name)
        .replace("{SURNAME}",     surname)
        .replace("{NAMESURNAME}", f"{name} {surname}".strip())
        .replace("{MENTION}",     mention)
        .replace("{USERNAME}",    f"@{username}" if username else name)
        .replace("{GROUPNAME}",   chat_title)
        .replace("{RULES}",       "")
        .replace("{DATE}",        now.strftime("%d.%m.%Y"))
        .replace("{TIME}",        now.strftime("%H:%M"))
        .replace("{WEEKDAY}",     weekdays[now.weekday()])
        .replace("{LANG}",        getattr(member, "language_code", "ru") or "ru")
    )


# ---------------------------------------------------------------------------
# Event handler: отправка прощания при выходе участника
# ---------------------------------------------------------------------------

@router.message(F.left_chat_member)
async def farewell(message: Message, chat_settings: dict | None = None) -> None:
    cfg = (chat_settings or {}).get("goodbye", {})
    if not cfg.get("enabled"):
        return

    member = message.left_chat_member
    text_tmpl = cfg.get("text", "")
    media_file_id: str | None = cfg.get("media_file_id")
    media_type: str | None = cfg.get("media_type")  # photo/video/sticker/animation/document
    buttons_raw: list | None = cfg.get("buttons")

    reply_markup = _buttons_to_inline_kb(buttons_raw) if buttons_raw else None
    text = _format_text(text_tmpl, member, message.chat.title or "") if text_tmpl else None
    caption = text if media_file_id else None
    send_text = text if not media_file_id else None

    try:
        if media_file_id and media_type:
            send = {
                "photo":     message.answer_photo,
                "video":     message.answer_video,
                "sticker":   message.answer_sticker,
                "animation": message.answer_animation,
                "document":  message.answer_document,
            }.get(media_type)
            if send:
                if media_type == "sticker":
                    await send(media_file_id, reply_markup=reply_markup)
                else:
                    await send(media_file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
                return

        if send_text:
            await message.answer(send_text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# /setgoodbye command (legacy, simple text)
# ---------------------------------------------------------------------------

@router.message(Command("setgoodbye"), HasRole("admin"))
async def cmd_set_goodbye(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Использование: /setgoodbye <текст с {MENTION}>")
        return
    async with SessionFactory() as session:
        await update_settings(session, message.chat.id, "goodbye", {"text": command.args, "enabled": True})
    await message.answer("✅ Прощание обновлено.")


# ---------------------------------------------------------------------------
# Settings panel callbacks — открыть меню прощания
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:open:"))
async def cb_goodbye_open(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    goodbye_cfg = cfg.get("goodbye", {})
    await call.message.edit_text(
        "👋 <b>Прощание</b>\n\n"
        f"📄 Текст: {'✅' if goodbye_cfg.get('text') else '❌ Сообщение не установлено.'}\n"
        f"🖼 Медиа: {'✅' if goodbye_cfg.get('media_file_id') else '❌ Сообщение не установлено.'}\n"
        f"🔤 URL-кнопки: {'✅' if goodbye_cfg.get('buttons') else '❌ Сообщение не установлено.'}\n\n"
        "👉 Используйте кнопки ниже, чтобы выбрать то, что вы хотите установить",
        parse_mode="HTML",
        reply_markup=_goodbye_main_keyboard(chat_id, goodbye_cfg),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# Set text
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:set_text:"))
async def cb_set_text(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.split(":")[3])
    await state.set_state(GoodbyeFSM.waiting_text)
    await state.update_data(chat_id=chat_id, origin_msg_id=call.message.message_id)
    await call.message.edit_text(_VARIABLES_TEXT, parse_mode="HTML", reply_markup=_cancel_kb())
    await call.answer()


@router.message(GoodbyeFSM.waiting_text)
async def fsm_receive_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id: int = data["chat_id"]
    await state.clear()

    text = message.html_text or message.text or ""
    async with SessionFactory() as session:
        await update_settings(session, chat_id, "goodbye", {"text": text, "enabled": True})

    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    goodbye_cfg = cfg.get("goodbye", {})

    await message.answer(
        "✅ Текст прощания обновлён!\n\n"
        "👋 <b>Прощание</b>\n\n"
        f"📄 Текст: {'✅' if goodbye_cfg.get('text') else '❌ Сообщение не установлено.'}\n"
        f"🖼 Медиа: {'✅' if goodbye_cfg.get('media_file_id') else '❌ Сообщение не установлено.'}\n"
        f"🔤 URL-кнопки: {'✅' if goodbye_cfg.get('buttons') else '❌ Сообщение не установлено.'}\n\n"
        "👉 Используйте кнопки ниже, чтобы выбрать то, что вы хотите установить",
        parse_mode="HTML",
        reply_markup=_goodbye_main_keyboard(chat_id, goodbye_cfg),
    )


# ---------------------------------------------------------------------------
# Set media
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:set_media:"))
async def cb_set_media(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.split(":")[3])
    await state.set_state(GoodbyeFSM.waiting_media)
    await state.update_data(chat_id=chat_id)
    await call.message.edit_text(_MEDIA_PROMPT, parse_mode="HTML", reply_markup=_media_cancel_kb())
    await call.answer()


@router.message(GoodbyeFSM.waiting_media)
async def fsm_receive_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id: int = data["chat_id"]
    await state.clear()

    file_id: str | None = None
    media_type: str | None = None

    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.sticker:
        file_id = message.sticker.file_id
        media_type = "sticker"
    elif message.animation:
        file_id = message.animation.file_id
        media_type = "animation"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"

    if not file_id:
        await message.answer("❌ Не удалось получить медиафайл. Попробуйте ещё раз.")
        return

    caption = message.caption or ""
    async with SessionFactory() as session:
        await update_settings(session, chat_id, "goodbye", {
            "media_file_id": file_id,
            "media_type": media_type,
            "text": caption,
            "enabled": True,
        })

    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    goodbye_cfg = cfg.get("goodbye", {})

    await message.answer(
        "✅ Медиа прощания обновлено!\n\n"
        "👋 <b>Прощание</b>\n\n"
        f"📄 Текст: {'✅' if goodbye_cfg.get('text') else '❌ Сообщение не установлено.'}\n"
        f"🖼 Медиа: {'✅' if goodbye_cfg.get('media_file_id') else '❌ Сообщение не установлено.'}\n"
        f"🔤 URL-кнопки: {'✅' if goodbye_cfg.get('buttons') else '❌ Сообщение не установлено.'}\n\n"
        "👉 Используйте кнопки ниже, чтобы выбрать то, что вы хотите установить",
        parse_mode="HTML",
        reply_markup=_goodbye_main_keyboard(chat_id, goodbye_cfg),
    )


# ---------------------------------------------------------------------------
# Set buttons
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:set_buttons:"))
async def cb_set_buttons(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.split(":")[3])
    await state.set_state(GoodbyeFSM.waiting_buttons)
    await state.update_data(chat_id=chat_id)
    await call.message.edit_text(_BUTTONS_PROMPT, parse_mode="HTML", reply_markup=_buttons_cancel_kb())
    await call.answer()


@router.message(GoodbyeFSM.waiting_buttons)
async def fsm_receive_buttons(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id: int = data["chat_id"]
    await state.clear()

    rows = _parse_buttons(message.text or "")
    if not rows:
        await message.answer(
            "❌ Не удалось распознать кнопки. Проверьте формат:\n"
            "<code>Название - https://t.me/example</code>",
            parse_mode="HTML",
        )
        return

    async with SessionFactory() as session:
        await update_settings(session, chat_id, "goodbye", {"buttons": rows})

    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    goodbye_cfg = cfg.get("goodbye", {})

    await message.answer(
        "✅ URL-кнопки обновлены!\n\n"
        "👋 <b>Прощание</b>\n\n"
        f"📄 Текст: {'✅' if goodbye_cfg.get('text') else '❌ Сообщение не установлено.'}\n"
        f"🖼 Медиа: {'✅' if goodbye_cfg.get('media_file_id') else '❌ Сообщение не установлено.'}\n"
        f"🔤 URL-кнопки: {'✅' if goodbye_cfg.get('buttons') else '❌ Сообщение не установлено.'}\n\n"
        "👉 Используйте кнопки ниже, чтобы выбрать то, что вы хотите установить",
        parse_mode="HTML",
        reply_markup=_goodbye_main_keyboard(chat_id, goodbye_cfg),
    )


# ---------------------------------------------------------------------------
# Delete / Cancel / Preview callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "sp:gb:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Действие отменено.", reply_markup=None)
    await call.answer()


@router.callback_query(F.data.startswith("sp:gb:del_buttons_now"))
async def cb_del_buttons(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    # Извлечь chat_id из state data или из предыдущего callback — берём из message текста нет,
    # поэтому просто сообщаем об успехе и просим открыть меню снова
    await call.answer("✅ URL-кнопки удалены.", show_alert=True)
    await call.message.edit_text("🗑 URL-кнопки удалены. Откройте меню прощания снова через /settings.", reply_markup=None)


@router.callback_query(F.data.startswith("sp:gb:preview_text:"))
async def cb_preview_text(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    text = cfg.get("goodbye", {}).get("text", "")
    if not text:
        await call.answer("❌ Сообщение не установлено.", show_alert=True)
        return
    preview = _format_text(text, call.from_user, "Группа")
    await call.answer(preview[:200], show_alert=True)


@router.callback_query(F.data.startswith("sp:gb:preview_media:"))
async def cb_preview_media(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    gb = cfg.get("goodbye", {})
    if not gb.get("media_file_id"):
        await call.answer("❌ Медиа не установлено.", show_alert=True)
        return
    await call.answer(f"Медиа: {gb['media_type']} — установлено ✅", show_alert=True)


@router.callback_query(F.data.startswith("sp:gb:preview_buttons:"))
async def cb_preview_buttons(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    buttons = cfg.get("goodbye", {}).get("buttons")
    if not buttons:
        await call.answer("❌ URL-кнопки не установлены.", show_alert=True)
        return
    lines = [" | ".join(t for t, _ in row) for row in buttons]
    await call.answer("Кнопки:\n" + "\n".join(lines), show_alert=True)


@router.callback_query(F.data.startswith("sp:gb:full_preview:"))
async def cb_full_preview(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    gb = cfg.get("goodbye", {})

    text_tmpl = gb.get("text", "")
    media_file_id = gb.get("media_file_id")
    media_type = gb.get("media_type")
    buttons = gb.get("buttons")

    text = _format_text(text_tmpl, call.from_user, "Ваша группа") if text_tmpl else None
    reply_markup = _buttons_to_inline_kb(buttons) if buttons else None

    try:
        if media_file_id and media_type:
            send = {
                "photo":     call.message.answer_photo,
                "video":     call.message.answer_video,
                "sticker":   call.message.answer_sticker,
                "animation": call.message.answer_animation,
                "document":  call.message.answer_document,
            }.get(media_type)
            if send:
                if media_type == "sticker":
                    await send(media_file_id, reply_markup=reply_markup)
                else:
                    await send(media_file_id, caption=text, parse_mode="HTML", reply_markup=reply_markup)
                await call.answer("👀 Предпросмотр отправлен")
                return

        if text:
            await call.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
            await call.answer("👀 Предпросмотр отправлен")
        else:
            await call.answer("❌ Прощание не настроено.", show_alert=True)
    except Exception as e:
        await call.answer(f"Ошибка предпросмотра: {e}", show_alert=True)


@router.callback_query(F.data.startswith("sp:gb:theme:"))
async def cb_theme(call: CallbackQuery) -> None:
    await call.answer("🎨 Выбор темы будет доступен в следующем обновлении.", show_alert=True)


@router.callback_query(F.data == "sp:gb:simple_buttons")
async def cb_simple_buttons(call: CallbackQuery) -> None:
    await call.answer(
        "Простой формат:\nНазвание - https://t.me/example",
        show_alert=True,
    )
