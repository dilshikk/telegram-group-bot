from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.handlers.welcome.rules import HELP_CATEGORIES

router = Router(name="start_help")

CATEGORIES_LIST = ", ".join(HELP_CATEGORIES.keys())

# Юзернейм бота подставляется динамически (см. main.py → bot.get_me())
# Для кнопки "Добавить меня в группу" используем deep-link
BOT_USERNAME_PLACEHOLDER = "GroupHelpBot"  # будет перезаписан в main.py через bot_username


def _start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура для /start — идентична скриншоту."""
    add_url = f"https://t.me/{bot_username}?startgroup=start&admin=restrict_members+delete_messages+ban_users+pin_messages+invite_users"
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


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="start:back")]
    ])


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    # Получаем username бота
    bot_me = await message.bot.get_me()
    username = bot_me.username or BOT_USERNAME_PLACEHOLDER
    await message.answer(
        _START_TEXT,
        parse_mode="HTML",
        reply_markup=_start_keyboard(username),
        disable_web_page_preview=True,
    )


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
    await call.message.edit_text(_SETTINGS_INFO_TEXT, parse_mode="HTML", reply_markup=_back_kb())
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
    await call.message.edit_text(_INFO_TEXT, parse_mode="HTML", reply_markup=_back_kb())
    await call.answer()


@router.callback_query(F.data == "start:lang")
async def cb_lang(call: CallbackQuery) -> None:
    await call.message.edit_text(_LANG_TEXT, parse_mode="HTML", reply_markup=_back_kb())
    await call.answer()


# ---------------------------------------------------------------------------
# /help и /commands
# ---------------------------------------------------------------------------

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
