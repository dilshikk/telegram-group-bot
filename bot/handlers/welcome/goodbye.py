"""
Goodbye — сообщение при выходе участника.

Два экрана:
  Экран 1 (главное меню модуля):  sp:m:goodbye / sp:gb:back_main:<chat_id>
    – статус включено/выключено
    – «Настроить сообщение» → экран 2
    – «Отправить в приватный чат» ↔ переключатель
    – «Удалять последнее сообщение» ↔ переключатель
    – «Назад» → главное меню настроек

  Экран 2 (конструктор):  sp:gb:configure:<chat_id>
    – текст / медиа / URL-кнопки + просмотр каждого
    – «Полный предпросмотр»
    – «Выбрать Тему NEW»
    – «Назад» → возврат на экран 1

Логика отправки:
  send_to_pm=False (по умолчанию) → прощание публикуется в группу
  send_to_pm=True                 → прощание отправляется в ЛС ушедшему участнику
                                    (только если он ранее запустил бота)
  delete_last=True                → предыдущее прощальное сообщение в группе удаляется
                                    перед отправкой нового (только при send_to_pm=False)

ID последнего сообщения хранится в chat_settings.goodbye.last_msg_id.

Переменные: {ID} {NAME} {SURNAME} {NAMESURNAME} {MENTION} {USERNAME}
            {GROUPNAME} {RULES} {DATE} {TIME} {WEEKDAY} {LANG}
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
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
# Helpers — screen 1 (main)
# ---------------------------------------------------------------------------

def _main_text(cfg: dict) -> str:
    enabled  = cfg.get("enabled", False)
    status   = "✅ Включено" if enabled else "❌ Выключено"
    send_pm  = cfg.get("send_to_pm", False)
    del_last = cfg.get("delete_last", False)

    pm_note = (
        "\n⚠️ Сообщение будет отправлено только пользователям, "
        "которые запустили бота в приватном чате."
        if send_pm else
        "\nСообщение отправляется в группу."
    )
    return (
        "👋 <b>Прощание</b>\n"
        "В этом меню вы можете установить прощальное сообщение, "
        "которое будет отправлено, когда кто-то покинет группу."
        f"{pm_note}\n\n"
        f"Статус: {status}"
    )


def _main_keyboard(chat_id: int, cfg: dict) -> InlineKeyboardMarkup:
    enabled  = cfg.get("enabled", False)
    send_pm  = cfg.get("send_to_pm", False)
    del_last = cfg.get("delete_last", False)

    if enabled:
        toggle_row = [
            InlineKeyboardButton(text="✖ Отключить", callback_data=f"sp:set:goodbye:enabled:0:{chat_id}"),
            InlineKeyboardButton(text="✔ Включить",  callback_data="sp:noop"),
        ]
    else:
        toggle_row = [
            InlineKeyboardButton(text="✖ Отключить", callback_data="sp:noop"),
            InlineKeyboardButton(text="✔ Включить",  callback_data=f"sp:set:goodbye:enabled:1:{chat_id}"),
        ]

    pm_mark  = " ✓" if send_pm  else ""
    del_mark = " ✓" if del_last else ""

    return InlineKeyboardMarkup(inline_keyboard=[
        toggle_row,
        [InlineKeyboardButton(
            text="✏️ Настроить сообщение",
            callback_data=f"sp:gb:configure:{chat_id}",
        )],
        [InlineKeyboardButton(
            text=f"💌 Отправить в приватный чат{pm_mark}",
            callback_data=f"sp:set:goodbye:send_to_pm:{int(not send_pm)}:{chat_id}",
        )],
        [InlineKeyboardButton(
            text=f"🗑 Удалять последнее сообщение{del_mark}",
            callback_data=f"sp:set:goodbye:delete_last:{int(not del_last)}:{chat_id}",
        )],
        [InlineKeyboardButton(text="◀ Назад", callback_data="sp:main:0")],
    ])


# ---------------------------------------------------------------------------
# Helpers — screen 2 (constructor)
# ---------------------------------------------------------------------------

def _configure_text(cfg: dict) -> str:
    def _s(flag: bool) -> str:
        return "✅" if flag else "❌"

    has_text    = bool(cfg.get("text"))
    has_media   = bool(cfg.get("media_file_id"))
    has_buttons = bool(cfg.get("buttons"))
    return (
        "👋 <b>Прощание</b>\n\n"
        f"📄 Текст: {_s(has_text) if has_text else '❌ Сообщение не установлено.'}\n"
        f"🖼 Медиа: {_s(has_media) if has_media else '❌ Сообщение не установлено.'}\n"
        f"🔤 URL-кнопки: {_s(has_buttons) if has_buttons else '❌ Сообщение не установлено.'}\n\n"
        "👉 Используйте кнопки ниже, чтобы выбрать то, что вы хотите установить"
    )


def _configure_keyboard(chat_id: int, cfg: dict) -> InlineKeyboardMarkup:
    def _s(flag: bool) -> str:
        return "✅" if flag else "❌"

    has_text    = bool(cfg.get("text"))
    has_media   = bool(cfg.get("media_file_id"))
    has_buttons = bool(cfg.get("buttons"))

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"📄 Текст {_s(has_text)}",         callback_data=f"sp:gb:set_text:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                       callback_data=f"sp:gb:preview_text:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text=f"🖼 Медиа {_s(has_media)}",        callback_data=f"sp:gb:set_media:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                       callback_data=f"sp:gb:preview_media:{chat_id}"),
        ],
        [
            InlineKeyboardButton(text=f"🔤 URL-кнопки {_s(has_buttons)}", callback_data=f"sp:gb:set_buttons:{chat_id}"),
            InlineKeyboardButton(text="👀 Просмотр",                       callback_data=f"sp:gb:preview_buttons:{chat_id}"),
        ],
        [InlineKeyboardButton(text="👀 Полный предпросмотр",  callback_data=f"sp:gb:full_preview:{chat_id}")],
        [InlineKeyboardButton(text="🎨 Выбрать Тему  NEW",    callback_data=f"sp:gb:theme:{chat_id}")],
        [InlineKeyboardButton(text="◀ Назад",                 callback_data=f"sp:gb:back_main:{chat_id}")],
    ])


# ---------------------------------------------------------------------------
# FSM prompts / keyboards
# ---------------------------------------------------------------------------

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
    "• <code>{USERNAME}</code> = имя пользователя (@username или пусто)\n"
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
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sp:gb:cancel")],
    ])


def _buttons_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Простое создание кнопок", callback_data="sp:gb:simple_buttons")],
        [InlineKeyboardButton(text="🚫 Удалить URL-кнопки",      callback_data="sp:gb:del_buttons_now")],
        [InlineKeyboardButton(text="❌ Отмена",                   callback_data="sp:gb:cancel")],
    ])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_buttons(raw: str) -> list[list[tuple[str, str]]]:
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


def _format_text(
    template: str,
    member: object | None = None,
    chat_title: str = "",
    rules: str = "",
) -> str:
    """
    Подставляет переменные в шаблон прощального сообщения.

    Исправления:
      - Баг 1: имя/фамилия/username/название группы экранируются через html.escape(),
               чтобы спецсимволы HTML (<, >, &, ") не ломали разметку.
      - Баг 2: {RULES} теперь принимает реальный текст правил через аргумент rules.
      - Баг 3: {USERNAME} при отсутствии username возвращает пустую строку,
               а не имя пользователя (было неочевидное поведение).
    """
    now      = datetime.now(timezone.utc)
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

    # Баг 1: экранируем все строковые данные от пользователя/группы
    raw_name       = getattr(member, "first_name", "") or ""
    raw_surname    = getattr(member, "last_name",  "") or ""
    raw_username   = getattr(member, "username",   "") or ""
    raw_chat_title = chat_title or ""

    name       = html.escape(raw_name)
    surname    = html.escape(raw_surname)
    username   = html.escape(raw_username)
    group_name = html.escape(raw_chat_title)

    uid     = getattr(member, "id", 0)
    # {MENTION} использует сырое имя внутри href-тега — экранируем тоже
    mention = f'<a href="tg://user?id={uid}">{name}</a>' if member else name

    # Баг 3: {USERNAME} → @username если есть, иначе пустая строка
    username_val = f"@{username}" if username else ""

    return (
        template
        .replace("{ID}",          str(uid))
        .replace("{NAME}",        name)
        .replace("{SURNAME}",     surname)
        .replace("{NAMESURNAME}", f"{name} {surname}".strip())
        .replace("{MENTION}",     mention)
        .replace("{USERNAME}",    username_val)
        .replace("{GROUPNAME}",   group_name)
        # Баг 2: подставляем реальные правила (или пустую строку если не переданы)
        .replace("{RULES}",       html.escape(rules) if rules else "")
        .replace("{DATE}",        now.strftime("%d.%m.%Y"))
        .replace("{TIME}",        now.strftime("%H:%M"))
        .replace("{WEEKDAY}",     weekdays[now.weekday()])
        .replace("{LANG}",        getattr(member, "language_code", "ru") or "ru")
    )


# ---------------------------------------------------------------------------
# Event handler: отправка прощания при выходе участника
# ---------------------------------------------------------------------------

@router.message(F.left_chat_member)
async def farewell(message: Message, bot: Bot, chat_settings: dict | None = None) -> None:
    cfg = (chat_settings or {}).get("goodbye", {})
    if not cfg.get("enabled"):
        return

    member        = message.left_chat_member
    text_tmpl     = cfg.get("text", "")
    media_file_id: str | None  = cfg.get("media_file_id")
    media_type:   str | None   = cfg.get("media_type")   # photo/video/sticker/animation/document
    buttons_raw:  list | None  = cfg.get("buttons")
    send_pm:      bool         = bool(cfg.get("send_to_pm", False))
    delete_last:  bool         = bool(cfg.get("delete_last", False))
    last_msg_id:  int | None   = cfg.get("last_msg_id")

    # Баг 2: получаем правила из настроек чата для передачи в _format_text
    rules: str = (chat_settings or {}).get("rules", {}).get("text", "") or ""

    reply_markup = _buttons_to_inline_kb(buttons_raw) if buttons_raw else None
    text         = _format_text(text_tmpl, member, message.chat.title or "", rules) if text_tmpl else None
    caption      = text if media_file_id else None
    send_text    = text if not media_file_id else None

    # ------------------------------------------------------------------
    # Если включена опция «Отправить в приватный чат» — пишем в ЛС
    # ------------------------------------------------------------------
    if send_pm:
        user_id = getattr(member, "id", None)
        if not user_id:
            return
        try:
            if media_file_id and media_type:
                send_fn = {
                    "photo":     bot.send_photo,
                    "video":     bot.send_video,
                    "sticker":   bot.send_sticker,
                    "animation": bot.send_animation,
                    "document":  bot.send_document,
                }.get(media_type)
                if send_fn:
                    if media_type == "sticker":
                        await send_fn(user_id, media_file_id, reply_markup=reply_markup)
                    else:
                        await send_fn(user_id, media_file_id, caption=caption,
                                      parse_mode="HTML", reply_markup=reply_markup)
                    return
            if send_text:
                await bot.send_message(user_id, send_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            # Пользователь не запускал бота — молча пропускаем
            pass
        return

    # ------------------------------------------------------------------
    # Отправка в группу
    # ------------------------------------------------------------------

    # Удаляем предыдущее прощальное сообщение, если включена опция
    if delete_last and last_msg_id:
        try:
            await bot.delete_message(message.chat.id, last_msg_id)
        except Exception:
            pass

    sent_msg_id: int | None = None
    try:
        if media_file_id and media_type:
            send_fn = {
                "photo":     message.answer_photo,
                "video":     message.answer_video,
                "sticker":   message.answer_sticker,
                "animation": message.answer_animation,
                "document":  message.answer_document,
            }.get(media_type)
            if send_fn:
                if media_type == "sticker":
                    sent = await send_fn(media_file_id, reply_markup=reply_markup)
                else:
                    sent = await send_fn(media_file_id, caption=caption,
                                         parse_mode="HTML", reply_markup=reply_markup)
                sent_msg_id = sent.message_id
        elif send_text:
            sent = await message.answer(send_text, parse_mode="HTML", reply_markup=reply_markup)
            sent_msg_id = sent.message_id
    except Exception:
        pass

    # Сохраняем ID отправленного сообщения для последующего удаления
    if delete_last and sent_msg_id:
        try:
            async with SessionFactory() as session:
                await update_settings(session, message.chat.id, "goodbye", {"last_msg_id": sent_msg_id})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Legacy command /setgoodbye
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
# Screen 2: open configure menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:configure:"))
async def cb_configure_open(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    gb = cfg.get("goodbye", {})

    await call.message.edit_text(
        _configure_text(gb),
        parse_mode="HTML",
        reply_markup=_configure_keyboard(chat_id, gb),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# Screen 2 → Screen 1: back button
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:back_main:"))
async def cb_back_main(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    gb = cfg.get("goodbye", {})

    await call.message.edit_text(
        _main_text(gb),
        parse_mode="HTML",
        reply_markup=_main_keyboard(chat_id, gb),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# FSM: set text
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:set_text:"))
async def cb_set_text(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.split(":")[3])
    await state.set_state(GoodbyeFSM.waiting_text)
    await state.update_data(chat_id=chat_id)
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
    gb = cfg.get("goodbye", {})

    await message.answer(
        "✅ Текст прощания обновлён!\n\n" + _configure_text(gb),
        parse_mode="HTML",
        reply_markup=_configure_keyboard(chat_id, gb),
    )


# ---------------------------------------------------------------------------
# FSM: set media
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

    file_id:    str | None = None
    media_type: str | None = None

    if message.photo:
        file_id, media_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, media_type = message.video.file_id, "video"
    elif message.sticker:
        file_id, media_type = message.sticker.file_id, "sticker"
    elif message.animation:
        file_id, media_type = message.animation.file_id, "animation"
    elif message.document:
        file_id, media_type = message.document.file_id, "document"

    if not file_id:
        await message.answer("❌ Не удалось получить медиафайл. Попробуйте ещё раз.")
        return

    caption = message.caption or ""
    async with SessionFactory() as session:
        await update_settings(session, chat_id, "goodbye", {
            "media_file_id": file_id,
            "media_type":    media_type,
            "text":          caption,
            "enabled":       True,
        })

    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    gb = cfg.get("goodbye", {})

    await message.answer(
        "✅ Медиа прощания обновлено!\n\n" + _configure_text(gb),
        parse_mode="HTML",
        reply_markup=_configure_keyboard(chat_id, gb),
    )


# ---------------------------------------------------------------------------
# FSM: set URL-buttons
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
    gb = cfg.get("goodbye", {})

    await message.answer(
        "✅ URL-кнопки обновлены!\n\n" + _configure_text(gb),
        parse_mode="HTML",
        reply_markup=_configure_keyboard(chat_id, gb),
    )


# ---------------------------------------------------------------------------
# Cancel FSM
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "sp:gb:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Действие отменено.", reply_markup=None)
    await call.answer()


# ---------------------------------------------------------------------------
# Delete URL-buttons
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "sp:gb:del_buttons_now")
async def cb_del_buttons(call: CallbackQuery, state: FSMContext) -> None:
    data    = await state.get_data()
    chat_id: int = data.get("chat_id", 0)
    await state.clear()

    if chat_id:
        async with SessionFactory() as session:
            await update_settings(session, chat_id, "goodbye", {"buttons": None})
        async with SessionFactory() as session:
            cfg = await get_settings(session, chat_id)
        gb = cfg.get("goodbye", {})
        await call.message.edit_text(
            _configure_text(gb),
            parse_mode="HTML",
            reply_markup=_configure_keyboard(chat_id, gb),
        )
        await call.answer("✅ URL-кнопки удалены.")
    else:
        await call.answer("✅ URL-кнопки удалены.", show_alert=True)
        await call.message.edit_text("🗑 URL-кнопки удалены.", reply_markup=None)


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:gb:preview_text:"))
async def cb_preview_text(call: CallbackQuery) -> None:
    chat_id = int(call.data.split(":")[3])
    async with SessionFactory() as session:
        cfg = await get_settings(session, chat_id)
    full_cfg = cfg
    text = full_cfg.get("goodbye", {}).get("text", "")
    if not text:
        await call.answer("❌ Текст не установлен.", show_alert=True)
        return
    rules: str = full_cfg.get("rules", {}).get("text", "") or ""
    preview = _format_text(text, call.from_user, "Ваша группа", rules)
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

    text_tmpl     = gb.get("text", "")
    media_file_id = gb.get("media_file_id")
    media_type    = gb.get("media_type")
    buttons       = gb.get("buttons")

    rules: str = cfg.get("rules", {}).get("text", "") or ""
    text         = _format_text(text_tmpl, call.from_user, "Ваша группа", rules) if text_tmpl else None
    reply_markup = _buttons_to_inline_kb(buttons) if buttons else None

    try:
        if media_file_id and media_type:
            send_fn = {
                "photo":     call.message.answer_photo,
                "video":     call.message.answer_video,
                "sticker":   call.message.answer_sticker,
                "animation": call.message.answer_animation,
                "document":  call.message.answer_document,
            }.get(media_type)
            if send_fn:
                if media_type == "sticker":
                    await send_fn(media_file_id, reply_markup=reply_markup)
                else:
                    await send_fn(media_file_id, caption=text, parse_mode="HTML",
                                  reply_markup=reply_markup)
                await call.answer("👀 Предпросмотр отправлен")
                return

        if text:
            await call.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
            await call.answer("👀 Предпросмотр отправлен")
        else:
            await call.answer("❌ Прощание не настроено.", show_alert=True)
    except Exception as exc:
        await call.answer(f"Ошибка предпросмотра: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("sp:gb:theme:"))
async def cb_theme(call: CallbackQuery) -> None:
    await call.answer("🎨 Выбор темы будет доступен в следующем обновлении.", show_alert=True)


@router.callback_query(F.data == "sp:gb:simple_buttons")
async def cb_simple_buttons(call: CallbackQuery) -> None:
    await call.answer(
        "Простой формат:\nНазвание - https://t.me/example",
        show_alert=True,
    )
