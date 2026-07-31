from aiogram import Router, F
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.handlers.welcome.rules import HELP_CATEGORIES

router = Router(name="start_help")

CATEGORIES_LIST = ", ".join(HELP_CATEGORIES.keys())

BOT_USERNAME_PLACEHOLDER = "GroupHelpBot"


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура для /start (личка)."""
    add_url = (
        f"https://t.me/{bot_username}?startgroup=start"
        "&admin=restrict_members+delete_messages+ban_users+pin_messages+invite_users"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить меня в группу ➕", url=add_url)],
        [InlineKeyboardButton(text="⚙️ Настройки Группы ✏️", callback_data="start:settings_info")],
        [
            InlineKeyboardButton(text="👥 Группа ↗", url="https://t.me/+0000000000000000"),
            InlineKeyboardButton(text="📢 Канал 🔊↗", url="https://t.me/+0000000000000000"),
        ],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="start:support"),
            InlineKeyboardButton(text="ℹ️ Информация 💬", callback_data="start:info"),
        ],
        [InlineKeyboardButton(text="🇷🇺 Languages 🇷🇺", callback_data="start:lang")],
    ])


def _go_to_pm_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Кнопка 'Перейти в чат' — в группе после отправки настроек в ЛС."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👉 Перейти в чат", url=f"https://t.me/{bot_username}")]
    ])


def _start_bot_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Кнопка для запуска бота в ЛС (если PM ещё не открыт)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶ Запустить бота", url=f"https://t.me/{bot_username}?start=start")]
    ])


def _help_keyboard() -> InlineKeyboardMarkup:
    """Кнопки категорий помощи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Основные",      callback_data="help:basic"),
            InlineKeyboardButton(text="🧑 Продвинутые",   callback_data="help:advanced"),
        ],
        [
            InlineKeyboardButton(text="🧐 Эксперт",        callback_data="help:expert"),
            InlineKeyboardButton(text="💂 Профессиональные", callback_data="help:pro"),
        ],
        [InlineKeyboardButton(text="🤖 Создать клон-бота", callback_data="help:clone")],
    ])


def _back_help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="help:back")]
    ])


def _back_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="start:back")]
    ])


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------

_START_TEXT = (
    "👋 <b>Привет!</b>\n\n"
    "<b>Group Help</b> наиболее полный бот, который поможет вам легко "
    "и безопасно управлять вашими группами!\n\n"
    "👉 <b>Добавьте меня в супергруппу</b> и сделайте меня "
    "<b>Администратором</b>, чтобы я сразу же начал действовать!\n\n"
    "❓ <b>КАКИЕ КОМАНДЫ?</b>\n"
    "Нажмите /help, чтобы увидеть <b>все команды</b> и то, как они работают!\n"
    "📋 <a href='https://t.me/+0000000000000000'>Privacy policy</a>"
)

_SETTINGS_INFO_TEXT = (
    "⚙️ <b>Настройки группы</b>\n\n"
    "Используйте команду /settings в своей группе, чтобы открыть панель управления.\n\n"
    "Бот должен быть <b>Администратором</b> в группе с правами:\n"
    "• Ограничивать участников\n"
    "• Удалять сообщения\n"
    "• Блокировать участников\n"
    "• Закреплять сообщения"
)

_INFO_TEXT = (
    "ℹ️ <b>Информация о боте</b>\n\n"
    "Group Help — многофункциональный бот для управления группами и каналами Telegram.\n\n"
    "<b>Возможности:</b>\n"
    "• Антиспам и антифлуд\n"
    "• Капча для новых участников\n"
    "• Система предупреждений\n"
    "• Приветствие и прощание\n"
    "• Ночной режим\n"
    "• Фильтры слов и медиа\n"
    "• Статистика чата\n"
    "• И многое другое!"
)

_LANG_TEXT = (
    "🌍 <b>Выбор языка / Language select</b>\n\n"
    "Текущий язык: 🇷🇺 Русский\n\n"
    "<i>Дополнительные языки будут добавлены в следующих обновлениях.</i>"
)

_HELP_CATEGORIES_TEXT: dict[str, str] = {
    "basic": (
        "👤 <b>Основные команды</b>\n\n"
        "/start — запустить бота\n"
        "/help — меню помощи\n"
        "/rules — правила чата\n"
        "/settings — настройки группы\n"
        "/stats — статистика чата"
    ),
    "advanced": (
        "🧑 <b>Продвинутые команды</b>\n\n"
        "/ban — заблокировать пользователя\n"
        "/unban — разблокировать пользователя\n"
        "/mute — заглушить пользователя\n"
        "/unmute — снять ограничение\n"
        "/kick — исключить пользователя\n"
        "/warn — выдать предупреждение\n"
        "/unwarn — снять предупреждение\n"
        "/warnlist — список предупреждений"
    ),
    "expert": (
        "🧐 <b>Команды эксперта</b>\n\n"
        "/setrules — установить правила\n"
        "/setwelcome — установить приветствие\n"
        "/setgoodbye — установить прощание\n"
        "/addbadword — добавить запрещённое слово\n"
        "/delbadword — удалить запрещённое слово\n"
        "/badwords — список запрещённых слов\n"
        "/nightmode — настройка ночного режима"
    ),
    "pro": (
        "💂 <b>Профессиональные команды</b>\n\n"
        "/addcommand — добавить личную команду\n"
        "/delcommand — удалить личную команду\n"
        "/mycommands — список личных команд\n"
        "/addrole — создать роль\n"
        "/roles — список ролей\n"
        "/tagall — упомянуть всех участников\n"
        "/checkperms — проверить права бота"
    ),
    "clone": (
        "🤖 <b>Создать клон-бота</b>\n\n"
        "Вы можете создать собственного бота на той же кодовой базе.\n\n"
        "Шаги:\n"
        "1. Создайте бота через @BotFather\n"
        "2. Скопируйте токен\n"
        "3. Отправьте /addclone &lt;токен&gt; боту в ЛС\n\n"
        "<i>Оркестратор запустит ваш бот в течение минуты.</i>"
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _send_start_pm(message: Message) -> None:
    """Отправляет стартовое сообщение в личку."""
    bot_me = await message.bot.get_me()
    username = bot_me.username or BOT_USERNAME_PLACEHOLDER
    await message.answer(
        _START_TEXT,
        parse_mode="HTML",
        reply_markup=_start_keyboard(username),
        disable_web_page_preview=True,
    )


async def _forward_settings_to_pm(message: Message) -> bool:
    """
    Пытается отправить панель настроек в ЛС администратора.
    Возвращает True при успехе, False если ЛС недоступен.
    """
    from bot.handlers.core.settings_panel import _main_keyboard, _main_text  # type: ignore[import]
    user_id = message.from_user.id
    title = message.chat.title or str(message.chat.id)
    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=_main_text(title),
            reply_markup=_main_keyboard(0),
            parse_mode="HTML",
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


# ---------------------------------------------------------------------------
# Handlers: /start, /reload
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.chat.type == "private":
        await _send_start_pm(message)
        return

    # В группе — отправляем настройки в ЛС администратора
    bot_me = await message.bot.get_me()
    username = bot_me.username or BOT_USERNAME_PLACEHOLDER
    sent = await _forward_settings_to_pm(message)
    if sent:
        await message.answer(
            "📨 <b>Меню настроек отправлено в личный чат</b>",
            parse_mode="HTML",
            reply_markup=_go_to_pm_keyboard(username),
        )
    else:
        await message.answer(
            "⚠️ Пожалуйста, сначала запустите бота в личном чате!",
            reply_markup=_start_bot_keyboard(username),
        )


@router.message(Command("reload"))
async def cmd_reload(message: Message) -> None:
    """Повторяет /start — используется для обновления."""
    if message.chat.type == "private":
        await _send_start_pm(message)
        return

    bot_me = await message.bot.get_me()
    username = bot_me.username or BOT_USERNAME_PLACEHOLDER
    sent = await _forward_settings_to_pm(message)
    if sent:
        await message.answer(
            "📨 <b>Меню настроек отправлено в личный чат</b>",
            parse_mode="HTML",
            reply_markup=_go_to_pm_keyboard(username),
        )
    else:
        await message.answer(
            "⚠️ Пожалуйста, сначала запустите бота в личном чате!",
            reply_markup=_start_bot_keyboard(username),
        )


# ---------------------------------------------------------------------------
# Callbacks: /start меню
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "start:back")
async def cb_start_back(call: CallbackQuery) -> None:
    bot_me = await call.bot.get_me()
    username = bot_me.username or BOT_USERNAME_PLACEHOLDER
    await call.message.edit_text(
        _START_TEXT,
        parse_mode="HTML",
        reply_markup=_start_keyboard(username),
        disable_web_page_preview=True,
    )
    await call.answer()


@router.callback_query(F.data == "start:settings_info")
async def cb_settings_info(call: CallbackQuery) -> None:
    await call.message.edit_text(
        _SETTINGS_INFO_TEXT, parse_mode="HTML", reply_markup=_back_start_kb()
    )
    await call.answer()


@router.callback_query(F.data == "start:support")
async def cb_support(call: CallbackQuery) -> None:
    support_id = settings.support_chat_id
    if support_id:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать в поддержку", url=f"https://t.me/{support_id}")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="start:back")],
        ])
        await call.message.edit_text(
            "🆘 <b>Поддержка</b>\n\nЕсли у вас есть вопросы или проблемы — напишите нам:",
            parse_mode="HTML", reply_markup=kb,
        )
    else:
        await call.answer("Поддержка временно недоступна.", show_alert=True)


@router.callback_query(F.data == "start:info")
async def cb_info(call: CallbackQuery) -> None:
    await call.message.edit_text(
        _INFO_TEXT, parse_mode="HTML", reply_markup=_back_start_kb()
    )
    await call.answer()


@router.callback_query(F.data == "start:lang")
async def cb_lang(call: CallbackQuery) -> None:
    await call.message.edit_text(
        _LANG_TEXT, parse_mode="HTML", reply_markup=_back_start_kb()
    )
    await call.answer()


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

@router.message(Command("help"))
async def cmd_help(message: Message, command: CommandObject) -> None:
    # /help <категория> — старый режим для совместимости
    category = (command.args or "").strip().lower()
    if category and category in HELP_CATEGORIES:
        await message.answer(HELP_CATEGORIES[category], parse_mode="HTML")
        return
    await message.answer(
        "👋 <b>Добро пожаловать в меню поддержки!</b>",
        parse_mode="HTML",
        reply_markup=_help_keyboard(),
    )


@router.callback_query(F.data == "help:back")
async def cb_help_back(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "👋 <b>Добро пожаловать в меню поддержки!</b>",
        parse_mode="HTML",
        reply_markup=_help_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("help:"))
async def cb_help_category(call: CallbackQuery) -> None:
    key = call.data.split(":")[1]
    text = _HELP_CATEGORIES_TEXT.get(key)
    if not text:
        await call.answer("Раздел не найден.", show_alert=True)
        return
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=_back_help_kb())
    await call.answer()


# ---------------------------------------------------------------------------
# /commands
# ---------------------------------------------------------------------------

@router.message(Command("commands"))
async def cmd_commands(message: Message) -> None:
    await message.answer(
        f"\U0001f4c2 <b>Категории команд:</b> {CATEGORIES_LIST}\n\n"
        "Используйте /help &lt;категория&gt; для просмотра команд в категории.",
        parse_mode="HTML",
    )
