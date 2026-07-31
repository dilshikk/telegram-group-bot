"""
Панель настроек /settings — inline-клавиатура для управления модулями чата.
Структура: главное меню → подменю модуля → переключение настроек.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database.engine import SessionFactory
from bot.filters.roles import HasRole
from bot.services.settings_service import get_settings, update_settings

router = Router(name="settings_panel")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _on_off(enabled: bool) -> str:
    return "\u2705 Вкл" if enabled else "\u274c Выкл"


def _close_btn() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="\u274c Закрыть", callback_data="settings:close")]


def _back_btn() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="\u25c4 Назад", callback_data="settings:main")]


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

MAIN_MENU_PAGES = [
    [
        ("\U0001f4cb Правила",           "settings:rules"),
        ("\U0001f6ab Антиспам",          "settings:antispam"),
    ],
    [
        ("\U0001f44b Приветствие",       "settings:welcome"),
        ("\U0001f4a8 Антифлуд",          "settings:antiflood"),
    ],
    [
        ("\U0001f44b Прощание",          "settings:goodbye"),
        ("\U0001f524 Алфавиты",          "settings:alphabets"),
    ],
    [
        ("\U0001f9e0 Капча",             "settings:captcha"),
        ("\U0001f50d Проверки",          "settings:checkperms"),
    ],
    [
        ("\U0001f6a8 @Admin",            "settings:admin_tag"),
        ("\U0001f512 Блокировки",        "settings:blocks"),
    ],
    [
        ("\U0001f4f8 Медиа",             "settings:media_blocks"),
        ("\U0001f51e Фильтр порно",      "settings:anti_nsfw"),
    ],
    [
        ("\u26a0\ufe0f Предупреждения",  "settings:warns"),
        ("\U0001f319 Ночной режим",      "settings:night_mode"),
    ],
    [
        ("\U0001f4dd Упоминание",        "settings:tag_all"),
        ("\U0001f517 Ссылки",            "settings:link_settings"),
    ],
    [
        ("\U0001f9b9 Режим одобрения",   "settings:approve_mode"),
    ],
    [
        ("\U0001f5d1 Удаление сообщений","settings:message_deletion"),
    ],
    [
        ("\U0001f4cf Длина сообщения",   "settings:max_message_length"),
    ],
    [
        ("\U0001f4e2 Повт. сообщения",   "settings:recurring"),
        ("\U0001f46a Упр. пользователями","settings:members"),
    ],
    [
        ("\U0001f47b Скрытые польз.",    "settings:masked_users"),
        ("\U0001f4ac Обс. группа",       "settings:discussion"),
    ],
    [
        ("\u2728 Личн. команды",         "settings:personal_commands"),
        ("\U0001f3ad Стикеры/GIF",       "settings:magic_stickers"),
    ],
    [
        ("\U0001f4fa Управл. каналами",  "settings:channel_mod"),
        ("\U0001f512 Разрешения",        "settings:permissions"),
    ],
]


def build_main_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    page_size = 7  # rows per page
    total_pages = (len(MAIN_MENU_PAGES) + page_size - 1) // page_size
    rows = MAIN_MENU_PAGES[page * page_size: (page + 1) * page_size]

    buttons = [[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u25c4 Назад", callback_data=f"settings:page:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="\u25ba Далее", callback_data=f"settings:page:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append(_close_btn())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _settings_text(chat_title: str) -> str:
    return (
        f"\u2699\ufe0f <b>ПАРАМЕТРЫ</b>\n"
        f"Группа: <code>{chat_title}</code>\n\n"
        "<i>Выберите один из параметров, который вы хотите изменить.</i>"
    )


# ---------------------------------------------------------------------------
# Module sub-menus
# ---------------------------------------------------------------------------

def build_toggle_keyboard(module: str, enabled: bool, extra: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([
        InlineKeyboardButton(
            text=_on_off(enabled),
            callback_data=f"stoggle:{module}:enabled:{int(not enabled)}"
        )
    ])
    if extra:
        rows.extend(extra)
    rows.append(_back_btn() + _close_btn())
    return InlineKeyboardMarkup(inline_keyboard=rows)


MODULE_LABELS: dict[str, str] = {
    "antispam":           "Антиспам",
    "antiflood":          "Антифлуд",
    "anti_nsfw":          "Фильтр порно",
    "captcha":            "Капча",
    "approve_mode":       "Режим одобрения",
    "night_mode":         "Ночной режим",
    "max_message_length": "Длина сообщения",
    "alphabets":          "Алфавиты",
    "tag_all":            "Упоминание всех",
    "welcome":            "Приветствие",
    "goodbye":            "Прощание",
    "rules":              "Правила",
    "admin_tag":          "Тег @Admin",
    "blocks":             "Блокировки",
    "media_blocks":       "Медиа-блокировки",
    "warns":              "Предупреждения",
    "link_settings":      "Ссылки",
    "message_deletion":   "Удаление сообщений",
    "masked_users":       "Скрытые пользователи",
    "recurring":          "Повторяющиеся сообщения",
    "members":            "Управление пользователями",
    "discussion":         "Группа обсуждения",
    "personal_commands":  "Личные команды",
    "magic_stickers":     "Стикеры/GIF",
    "channel_mod":        "Управление каналами",
    "permissions":        "Разрешения",
    "checkperms":         "Проверка прав бота",
}

# Modules that are not simple on/off toggles — just show info
INFO_ONLY = {"checkperms", "rules", "members", "permissions", "discussion",
             "personal_commands", "magic_stickers", "channel_mod", "recurring"}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(Command("settings"), HasRole("admin"))
async def cmd_settings(message: Message, chat_settings: dict | None = None) -> None:
    if message.chat.type == "private":
        await message.answer(
            "\u2139\ufe0f Команда /settings работает только в группах.\n"
            "Добавьте бота в группу как администратора и используйте /settings там."
        )
        return
    title = message.chat.title or str(message.chat.id)
    await message.answer(
        _settings_text(title),
        reply_markup=build_main_keyboard(0),
        parse_mode="HTML",
    )


# Page navigation
@router.callback_query(F.data.startswith("settings:page:"))
async def cb_page(call: CallbackQuery) -> None:
    page = int(call.data.split(":")[2])
    title = call.message.chat.title or str(call.message.chat.id)
    await call.message.edit_text(
        _settings_text(title),
        reply_markup=build_main_keyboard(page),
        parse_mode="HTML",
    )
    await call.answer()


# Close
@router.callback_query(F.data == "settings:close")
async def cb_close(call: CallbackQuery) -> None:
    await call.message.delete()
    await call.answer()


# Back to main
@router.callback_query(F.data == "settings:main")
async def cb_main(call: CallbackQuery) -> None:
    title = call.message.chat.title or str(call.message.chat.id)
    await call.message.edit_text(
        _settings_text(title),
        reply_markup=build_main_keyboard(0),
        parse_mode="HTML",
    )
    await call.answer()


# Open module sub-menu
@router.callback_query(F.data.startswith("settings:") & ~F.data.startswith("settings:page:") & ~F.data.startswith("settings:main") & ~F.data.startswith("settings:close"))
async def cb_module(call: CallbackQuery, chat_settings: dict | None = None) -> None:
    module = call.data.split(":")[1]
    label = MODULE_LABELS.get(module, module)
    cfg = (chat_settings or {}).get(module, {})

    if module in INFO_ONLY:
        await call.answer(f"\u2139\ufe0f {label}: настраивается командами.", show_alert=True)
        return

    enabled = cfg.get("enabled", False)
    text = (
        f"\u2699\ufe0f <b>{label}</b>\n\n"
        f"Статус: {_on_off(enabled)}"
    )
    await call.message.edit_text(
        text,
        reply_markup=build_toggle_keyboard(module, enabled),
        parse_mode="HTML",
    )
    await call.answer()


# Toggle a module on/off
@router.callback_query(F.data.startswith("stoggle:"))
async def cb_toggle(call: CallbackQuery, chat_settings: dict | None = None) -> None:
    _, module, field, value_str = call.data.split(":")
    new_value = bool(int(value_str))

    async with SessionFactory() as session:
        await update_settings(session, call.message.chat.id, module, {field: new_value})

    label = MODULE_LABELS.get(module, module)
    text = (
        f"\u2699\ufe0f <b>{label}</b>\n\n"
        f"Статус: {_on_off(new_value)}"
    )
    await call.message.edit_text(
        text,
        reply_markup=build_toggle_keyboard(module, new_value),
        parse_mode="HTML",
    )
    await call.answer(f"{'Включено' if new_value else 'Выключено'} \u2705")
