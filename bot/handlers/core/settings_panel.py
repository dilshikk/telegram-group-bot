"""
Панель настроек /settings — inline-клавиатура для управления модулями чата.
Основана на интерфейсе эталонного бота (скриншоты).
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
from bot.services.settings_service import update_settings

router = Router(name="settings_panel")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _close() -> InlineKeyboardButton:
    return _btn("✅ Закрыть", "sp:close")


def _back() -> InlineKeyboardButton:
    return _btn("◀ Назад", "sp:main:0")


def _on(val: bool) -> str:
    return "✅ Включено" if val else "❌ Выключено"


def _action_label(action: str) -> str:
    labels = {
        "warn":    "⚠ Предупреждение",
        "mute":    "🔇 Заглушить",
        "kick":    "👢 Кикнуть",
        "ban":     "🚫 Заблокировать",
        "restrict":"🚷 Ограничить",
        "delete":  "🗑 Удалить",
        "off":     "❌ Выкл",
    }
    return labels.get(action, action)


# ---------------------------------------------------------------------------
# Main menu definition
# ---------------------------------------------------------------------------

MAIN_ROWS: list[tuple[str, str]] = [
    ("📋 Правила",                   "sp:m:rules"),
    ("🚫 Антиспам",                  "sp:m:antispam"),
    ("👋 Приветствие",               "sp:m:welcome"),
    ("💨 Антифлуд",                  "sp:m:antiflood"),
    ("👋 Прощание",                  "sp:m:goodbye"),
    ("🔤 Алфавиты",                  "sp:m:alphabets"),
    ("🧠 Капча",                     "sp:m:captcha"),
    ("🔍 Проверки",                  "sp:m:checkperms"),
    ("🚨 @Admin",                    "sp:m:admin_tag"),
    ("🔒 Блокировки",                "sp:m:blocks"),
    ("📸 Медиа",                     "sp:m:media_blocks"),
    ("🔞 Фильтр порно",              "sp:m:anti_nsfw"),
    ("⚠️ Предупреждения",            "sp:m:warns"),
    ("🌙 Ночной режим",              "sp:m:night_mode"),
    ("📝 Упоминание",                "sp:m:tag_all"),
    ("🔗 Ссылки",                    "sp:m:link_settings"),
    ("🕵 Бот-страж",                 "sp:m:bot_guard"),
    ("🚪 Режим одобрения",           "sp:m:approve_mode"),
    ("🗑 Удаление сообщений",        "sp:m:message_deletion"),
    ("📁 Темы",                      "sp:m:topics"),
    ("abc Запрещённые слова",        "sp:m:banned_words"),
    ("⏱ Повт. сообщения",           "sp:m:recurring"),
    ("👥 Управление польз.",         "sp:m:members"),
    ("👻 Скрытые польз.",            "sp:m:masked_users"),
    ("💬 Группа обсуждения",         "sp:m:discussion"),
    ("✨ Личн. команды",             "sp:m:personal_commands"),
    ("🎭 Стикеры и GIF",             "sp:m:magic_stickers"),
    ("📏 Длина сообщения",           "sp:m:max_message_length"),
    ("📺 Управл. каналами",          "sp:m:channel_mod"),
    ("✏️ Разрешения",                "sp:m:permissions"),
    ("🔭 Канал событий",             "sp:m:log_channel"),
]

PAGE_SIZE = 7  # rows per page (2 cols each → 14 buttons + nav)


def _main_keyboard(page: int) -> InlineKeyboardMarkup:
    total = len(MAIN_ROWS)
    pages = (total + PAGE_SIZE * 2 - 1) // (PAGE_SIZE * 2)
    start = page * PAGE_SIZE * 2
    chunk = MAIN_ROWS[start: start + PAGE_SIZE * 2]

    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(chunk), 2):
        pair = chunk[i: i + 2]
        rows.append([_btn(t, d) for t, d in pair])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("◀ Назад", f"sp:main:{page - 1}"))
    nav.append(_close())
    if page < pages - 1:
        nav.append(_btn("▶ Другие", f"sp:main:{page + 1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _main_text(chat_title: str) -> str:
    return (
        f"⚙️ <b>ПАРАМЕТРЫ</b>\n"
        f"Группа: <code>{chat_title}</code>\n\n"
        "<i>Выберите один из параметров, который вы хотите изменить.</i>"
    )


_NO_GROUPS_TEXT = (
    "😟 <b>Группы не найдены.</b>\n\n"
    "Если группа, в которой <b>вы являетесь администратором</b>, не отображается здесь:\n"
    "  • Отправьте <code>/reload</code> в группу, и повторите попытку\n"
    "  • Отправьте <code>/settings</code> в группе, а затем нажмите «Открыть в личке бота»"
)


# ---------------------------------------------------------------------------
# Per-module sub-menus
# ---------------------------------------------------------------------------

def _make_kb_module(module: str, cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Return (text, keyboard) for a given module sub-menu."""

    def _toggle_btn(field: str, cur: bool, label_on: str = "✔ Включить", label_off: str = "✖ Отключить") -> list[InlineKeyboardButton]:
        if cur:
            return [_btn(label_on, f"sp:noop"), _btn(label_off, f"sp:set:{module}:{field}:0")]
        return [_btn(label_on, f"sp:set:{module}:{field}:1"), _btn(label_off, f"sp:noop")]

    def _action_row(cur_action: str, choices: list[str]) -> list[InlineKeyboardButton]:
        return [_btn(_action_label(a) + (" ✓" if a == cur_action else ""), f"sp:set:{module}:action:{a}") for a in choices]

    nav = [_back(), _close()]

    if module == "antispam":
        enabled = cfg.get("enabled", False)
        action = cfg.get("action", "warn")
        text = (
            "🚫 <b>Антиспам</b>\n"
            "Этот модуль позволяет вам контролировать спам-сообщения в вашей группе.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Наказание: {_action_label(action)}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            _action_row(action, ["warn", "mute", "kick", "ban"]),
            nav,
        )

    elif module == "antiflood":
        enabled = cfg.get("enabled", False)
        action = cfg.get("action", "mute")
        count = cfg.get("count", 5)
        period = cfg.get("period", 5)
        text = (
            "💨 <b>Антифлуд</b>\n"
            "Этот модуль позволяет вам контролировать флуд-сообщения.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Наказание: {_action_label(action)}\n"
            f"Кол-во сообщений: {count}\n"
            f"За секунд: {period}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            _action_row(action, ["warn", "mute", "kick", "ban"]),
            nav,
        )

    elif module == "anti_nsfw":
        enabled = cfg.get("enabled", False)
        delete = cfg.get("delete", True)
        action = cfg.get("action", "warn")
        text = (
            "🔞 <b>Фильтр порно</b>\n"
            "Этот модуль автоматически обнаруживает и удаляет сообщения с непристойным содержимым.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удаление: {'Да ✅' if delete else 'Нет ❌'}\n"
            f"Наказание: {_action_label(action)}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("🗑 Удалять сообщения " + ("✅" if delete else "❌"), f"sp:set:{module}:delete:{int(not delete)}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    elif module == "captcha":
        enabled = cfg.get("enabled", False)
        ctype = cfg.get("type", "button")
        text = (
            "🧠 <b>Капча</b>\n"
            "Защита группы от ботов. Новый участник должен пройти проверку.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Тип: {ctype}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [
                _btn("🔘 Кнопка" + (" ✓" if ctype == "button" else ""), f"sp:set:{module}:type:button"),
                _btn("🔢 Математика" + (" ✓" if ctype == "math" else ""), f"sp:set:{module}:type:math"),
            ],
            [_btn("🔠 Текст" + (" ✓" if ctype == "text" else ""), f"sp:set:{module}:type:text")],
            nav,
        )

    elif module == "welcome":
        enabled = cfg.get("enabled", False)
        delete_prev = cfg.get("delete_previous", False)
        text = (
            "👋 <b>Приветствие</b>\n"
            "Настройте сообщение, которое бот отправляет новым участникам.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять предыдущее: {'Да ✅' if delete_prev else 'Нет ❌'}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("🗑 Удалять предыдущее " + ("✅" if delete_prev else "❌"), f"sp:set:{module}:delete_previous:{int(not delete_prev)}")],
            [_btn("✏️ Изменить текст", "sp:info:welcome_text")],
            nav,
        )

    elif module == "goodbye":
        enabled = cfg.get("enabled", False)
        delete_prev = cfg.get("delete_previous", False)
        text = (
            "👋 <b>Прощание</b>\n"
            "Настройте сообщение, которое бот отправляет при выходе участника.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять предыдущее: {'Да ✅' if delete_prev else 'Нет ❌'}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("🗑 Удалять предыдущее " + ("✅" if delete_prev else "❌"), f"sp:set:{module}:delete_previous:{int(not delete_prev)}")],
            [_btn("✏️ Изменить текст", "sp:info:goodbye_text")],
            nav,
        )

    elif module == "rules":
        text = (
            "📋 <b>Правила</b>\n"
            "Установите правила группы. Участники смогут прочитать их командой /rules.\n\n"
            "Для изменения правил используйте:\n"
            "<code>/setrules &lt;текст правил&gt;</code>"
        )
        kb = _kb(nav)

    elif module == "warns":
        max_warns = cfg.get("max_warns", 3)
        action = cfg.get("action", "ban")
        text = (
            "⚠️ <b>Предупреждения</b>\n"
            "Настройте систему предупреждений для нарушителей.\n\n"
            f"Макс. предупреждений: {max_warns}\n"
            f"Действие при достижении: {_action_label(action)}"
        )
        kb = _kb(
            [
                _btn("➖ Уменьшить", f"sp:set:{module}:max_warns:{max(1, max_warns - 1)}"),
                _btn(f"{max_warns} варнов", "sp:noop"),
                _btn("➕ Увеличить", f"sp:set:{module}:max_warns:{max_warns + 1}"),
            ],
            _action_row(action, ["mute", "kick", "ban"]),
            nav,
        )

    elif module == "night_mode":
        enabled = cfg.get("enabled", False)
        start = cfg.get("start", "23:00")
        end = cfg.get("end", "07:00")
        text = (
            "🌙 <b>Ночной режим</b>\n"
            "В ночное время группа будет ограничена (только чтение).\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Начало: {start}\n"
            f"Конец: {end}\n\n"
            "Для изменения времени: /nightmode &lt;HH:MM&gt; &lt;HH:MM&gt;"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            nav,
        )

    elif module == "max_message_length":
        enabled = cfg.get("enabled", False)
        delete = cfg.get("delete", False)
        max_len = cfg.get("limit", 2000)
        action = cfg.get("action", "off")
        text = (
            "📏 <b>Длина сообщения</b>\n"
            "В этом меню вы можете установить минимальную/максимальную длину символов для сообщений, "
            "отправляемых пользователями.\n\n"
            f"Наказание: {_action_label(action)}\n"
            f"Удаление: {'Да ✅' if delete else 'Нет ❌'}\n"
            f"Максимальная длина: {max_len} символов"
        )
        kb = _kb(
            [
                _btn("❌ Выкл" + (" ✓" if action == "off" else ""),      f"sp:set:{module}:action:off"),
                _btn("⚠ Предупреждение" + (" ✓" if action == "warn" else ""), f"sp:set:{module}:action:warn"),
                _btn("⚠ Исключить" + (" ✓" if action == "kick" else ""),  f"sp:set:{module}:action:kick"),
            ],
            [
                _btn("🚷 Ограничить" + (" ✓" if action == "restrict" else ""), f"sp:set:{module}:action:restrict"),
                _btn("🚫 Заблокировать" + (" ✓" if action == "ban" else ""),   f"sp:set:{module}:action:ban"),
            ],
            [_btn("🗑 Удалять сообщения " + ("✅" if delete else "❌"),   f"sp:set:{module}:delete:{int(not delete)}")],
            [_btn("📏 Минимальная длина", "sp:info:min_length")],
            [_btn("📏 Максимальная длина", "sp:info:max_length")],
            nav,
        )

    elif module == "link_settings":
        enabled = cfg.get("enabled", False)
        delete = cfg.get("delete", True)
        action = cfg.get("action", "warn")
        text = (
            "🔗 <b>Ссылки</b>\n"
            "Блокировка ссылок от обычных пользователей.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удаление: {'Да ✅' if delete else 'Нет ❌'}\n"
            f"Наказание: {_action_label(action)}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("🗑 Удалять сообщения " + ("✅" if delete else "❌"), f"sp:set:{module}:delete:{int(not delete)}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    elif module == "banned_words":
        enabled = cfg.get("enabled", False)
        delete = cfg.get("delete", True)
        action = cfg.get("action", "warn")
        text = (
            "abc <b>Запрещённые слова</b>\n"
            "Автоматическая фильтрация запрещённых слов и фраз.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удаление: {'Да ✅' if delete else 'Нет ❌'}\n"
            f"Наказание: {_action_label(action)}\n\n"
            "Для управления словами: /addbadword, /delbadword, /badwords"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("🗑 Удалять сообщения " + ("✅" if delete else "❌"), f"sp:set:{module}:delete:{int(not delete)}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    elif module == "message_deletion":
        del_service = cfg.get("delete_service_messages", True)
        del_commands = cfg.get("delete_commands", False)
        text = (
            "🗑 <b>Удаление сообщений</b>\n"
            "Настройте автоматическое удаление служебных сообщений и команд.\n\n"
            f"Удалять служебные: {'✅' if del_service else '❌'}\n"
            f"Удалять команды: {'✅' if del_commands else '❌'}"
        )
        kb = _kb(
            [_btn("🗑 Служебные " + ("✅" if del_service else "❌"), f"sp:set:{module}:delete_service_messages:{int(not del_service)}")],
            [_btn("🗑 Команды " + ("✅" if del_commands else "❌"), f"sp:set:{module}:delete_commands:{int(not del_commands)}")],
            nav,
        )

    elif module == "approve_mode":
        enabled = cfg.get("enabled", False)
        text = (
            "🚪 <b>Режим одобрения</b>\n"
            "Новые участники не смогут писать до одобрения администратором.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "admin_tag":
        enabled = cfg.get("enabled", False)
        text = (
            "🚨 <b>@Admin</b>\n"
            "Когда участник тегает @admin, все администраторы получат уведомление.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "blocks":
        block_arabic = cfg.get("block_arabic", False)
        block_rtl = cfg.get("block_rtl", False)
        text = (
            "🔒 <b>Блокировки</b>\n"
            "Настройте блокировку определённых типов сообщений.\n\n"
            f"Арабский текст: {'✅' if block_arabic else '❌'}\n"
            f"RTL символы: {'✅' if block_rtl else '❌'}"
        )
        kb = _kb(
            [_btn("🔤 Арабский " + ("✅" if block_arabic else "❌"), f"sp:set:{module}:block_arabic:{int(not block_arabic)}")],
            [_btn("↩ RTL " + ("✅" if block_rtl else "❌"), f"sp:set:{module}:block_rtl:{int(not block_rtl)}")],
            nav,
        )

    elif module == "media_blocks":
        block_stickers = cfg.get("block_stickers", False)
        block_gifs = cfg.get("block_gifs", False)
        block_voice = cfg.get("block_voice", False)
        block_video = cfg.get("block_video_notes", False)
        text = (
            "📸 <b>Медиа</b>\n"
            "Ограничьте отправку медиафайлов в группе.\n\n"
            f"Стикеры: {'✅' if block_stickers else '❌'}\n"
            f"GIF: {'✅' if block_gifs else '❌'}\n"
            f"Голосовые: {'✅' if block_voice else '❌'}\n"
            f"Видеосообщения: {'✅' if block_video else '❌'}"
        )
        kb = _kb(
            [
                _btn("🎭 Стикеры " + ("✅" if block_stickers else "❌"), f"sp:set:{module}:block_stickers:{int(not block_stickers)}"),
                _btn("🎬 GIF " + ("✅" if block_gifs else "❌"), f"sp:set:{module}:block_gifs:{int(not block_gifs)}"),
            ],
            [
                _btn("🎙 Голос " + ("✅" if block_voice else "❌"), f"sp:set:{module}:block_voice:{int(not block_voice)}"),
                _btn("📹 Видео " + ("✅" if block_video else "❌"), f"sp:set:{module}:block_video_notes:{int(not block_video)}"),
            ],
            nav,
        )

    elif module == "alphabets":
        allow_en = cfg.get("allow_english", True)
        allow_ru = cfg.get("allow_russian", True)
        text = (
            "🔤 <b>Алфавиты</b>\n"
            "Разрешите или запретите сообщения на определённых языках.\n\n"
            f"Английский: {'✅' if allow_en else '❌'}\n"
            f"Русский: {'✅' if allow_ru else '❌'}"
        )
        kb = _kb(
            [
                _btn("🇬🇧 Английский " + ("✅" if allow_en else "❌"), f"sp:set:{module}:allow_english:{int(not allow_en)}"),
                _btn("🇷🇺 Русский " + ("✅" if allow_ru else "❌"), f"sp:set:{module}:allow_russian:{int(not allow_ru)}"),
            ],
            nav,
        )

    elif module == "tag_all":
        enabled = cfg.get("enabled", False)
        text = (
            "📝 <b>Упоминание всех</b>\n"
            "Администраторы могут тегнуть всех участников группы командой.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "bot_guard":
        enabled = cfg.get("enabled", False)
        text = (
            "🕵 <b>Бот-страж</b>\n"
            "Автоматически удаляет ботов, добавленных без разрешения.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "magic_stickers":
        enabled = cfg.get("enabled", False)
        text = (
            "🎭 <b>Волшебные Стикеры И GIF</b>\n"
            "Волшебный стикер (или GIF) позволяет запустить команду бота "
            "(или личную команду), отправив стикер или GIF.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(
            _toggle_btn("enabled", enabled),
            [_btn("❓ Как их настроить?", "sp:info:magic_stickers")],
            nav,
        )

    elif module == "permissions":
        text = (
            "✏️ <b>Разрешения</b>\n"
            "В этом меню вы можете выбрать права доступа, которые будут "
            "иметь пользователи и администраторы к некоторым функциям бота."
        )
        kb = _kb(
            [_btn("🎖 Права на команды",           "sp:info:perm_commands")],
            [_btn("🤖 Анонимный администратор",    "sp:info:perm_anon")],
            [_btn("⚙️ Изменение настроек",          "sp:info:perm_settings")],
            [_btn("🎫 Свои роли",                  "sp:info:perm_roles")],
            nav,
        )

    elif module == "log_channel":
        text = (
            "🔭 <b>Канал Событий</b>\n"
            "Здесь вы можете настроить канал, в котором будут сохраняться "
            "все события этой группы. Чтобы добавить канал, вы должны быть "
            "владельцем самого канала и бот должен быть администратором этого канала.\n\n"
            "<i>Канал может быть как публичным, так и приватным.</i>"
        )
        kb = _kb(
            [_btn("➕ Добавить Канал Событий", "sp:info:add_log_channel")],
            nav,
        )

    elif module == "topics":
        enabled = cfg.get("enabled", False)
        text = (
            "📁 <b>Темы</b>\n"
            "Управление темами (форумами) в супергруппе.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "recurring":
        text = (
            "⏱ <b>Повторяющиеся сообщения</b>\n"
            "Настройте автоматическую отправку сообщений через заданный интервал.\n\n"
            "Управление: /recurring"
        )
        kb = _kb(nav)

    elif module == "members":
        text = (
            "👥 <b>Управление пользователями</b>\n"
            "Просмотр и управление участниками группы.\n\n"
            "Команды: /ban /unban /mute /unmute /kick /warn /warnlist"
        )
        kb = _kb(nav)

    elif module == "masked_users":
        enabled = cfg.get("enabled", False)
        text = (
            "👻 <b>Скрытые пользователи</b>\n"
            "Позволяет участникам скрыть своё присутствие в группе.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "discussion":
        text = (
            "💬 <b>Группа обсуждения</b>\n"
            "Свяжите канал с группой обсуждения.\n\n"
            "Настраивается через меню Telegram."
        )
        kb = _kb(nav)

    elif module == "personal_commands":
        text = (
            "✨ <b>Личные команды</b>\n"
            "Создайте свои команды для быстрого доступа к заметкам и текстам.\n\n"
            "Управление: /addcommand, /delcommand, /mycommands"
        )
        kb = _kb(nav)

    elif module == "channel_mod":
        enabled = cfg.get("enabled", False)
        text = (
            "📺 <b>Управление каналами</b>\n"
            "Модерация сообщений от связанных каналов.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle_btn("enabled", enabled), nav)

    elif module == "checkperms":
        text = (
            "🔍 <b>Проверка прав бота</b>\n"
            "Убедитесь, что бот имеет все необходимые права.\n\n"
            "Для проверки используйте: /checkperms"
        )
        kb = _kb(nav)

    else:
        text = f"⚙️ <b>{module}</b>\n\nНастройки скоро появятся."
        kb = _kb(nav)

    return text, kb


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(Command("settings"))
async def cmd_settings(message: Message, chat_settings: dict | None = None) -> None:
    # В личке — показываем инструкцию "Группы не найдены"
    if message.chat.type == "private":
        await message.answer(_NO_GROUPS_TEXT, parse_mode="HTML")
        return

    # Только для админов в группе
    # (HasRole не применяем глобально, чтобы в личке всё равно отвечать)
    from bot.utils.permissions import role_at_least
    role = getattr(message, "_chat_user_role", None)
    # role прокидывается через data в middleware, но в handler'е доступен через инъекцию
    # поэтому добавляем chat_user_role как параметр
    await _settings_in_group(message)


async def _settings_in_group(message: Message, chat_user_role: str = "member") -> None:
    from bot.utils.permissions import role_at_least
    if not role_at_least(chat_user_role, "admin"):
        return  # не реагируем на не-админов в группе
    title = message.chat.title or str(message.chat.id)
    await message.answer(
        _main_text(title),
        reply_markup=_main_keyboard(0),
        parse_mode="HTML",
    )


# Переписываем handler правильно с инъекцией chat_user_role
@router.message(Command("settings"))
async def cmd_settings_v2(message: Message, chat_user_role: str = "member") -> None:
    if message.chat.type == "private":
        await message.answer(_NO_GROUPS_TEXT, parse_mode="HTML")
        return
    from bot.utils.permissions import role_at_least
    if not role_at_least(chat_user_role, "admin"):
        return
    title = message.chat.title or str(message.chat.id)
    await message.answer(
        _main_text(title),
        reply_markup=_main_keyboard(0),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("sp:main:"))
async def cb_main(call: CallbackQuery) -> None:
    page = int(call.data.split(":")[2])
    title = call.message.chat.title or str(call.message.chat.id)
    await call.message.edit_text(
        _main_text(title),
        reply_markup=_main_keyboard(page),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data == "sp:close")
async def cb_close(call: CallbackQuery) -> None:
    await call.message.delete()
    await call.answer()


@router.callback_query(F.data == "sp:noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("sp:m:"))
async def cb_module(call: CallbackQuery, chat_settings: dict | None = None) -> None:
    module = call.data.split(":")[2]
    cfg = (chat_settings or {}).get(module, {})
    text, kb = _make_kb_module(module, cfg)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("sp:info:"))
async def cb_info(call: CallbackQuery) -> None:
    info_key = call.data.split(":")[2]
    messages = {
        "welcome_text":    "Используйте /setwelcome &lt;текст&gt; для установки текста приветствия.",
        "goodbye_text":    "Используйте /setgoodbye &lt;текст&gt; для установки текста прощания.",
        "min_length":      "Используйте /setminlength &lt;число&gt; для установки минимальной длины.",
        "max_length":      "Используйте /setmaxlength &lt;число&gt; для установки максимальной длины.",
        "magic_stickers":  "Отправьте любой стикер боту в ЛС и следуйте инструкциям.",
        "add_log_channel": "Добавьте бота в канал как администратора, затем перешлите любое сообщение из канала сюда.",
        "perm_commands":   "Права на выполнение команд настраиваются через /roles.",
        "perm_anon":       "Анонимные администраторы могут использовать команды без раскрытия личности.",
        "perm_settings":   "Выберите кто может изменять настройки: только владелец или все администраторы.",
        "perm_roles":      "Создайте свои роли с кастомными правами командой /addrole.",
    }
    msg = messages.get(info_key, "ℹ️ Информация скоро появится.")
    await call.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("sp:set:"))
async def cb_set(call: CallbackQuery, chat_settings: dict | None = None) -> None:
    parts = call.data.split(":")
    module = parts[2]
    field = parts[3]
    raw = parts[4]

    value: str | int | bool
    if raw in ("0", "1"):
        value = bool(int(raw))
    elif raw.lstrip("-").isdigit():
        value = int(raw)
    else:
        value = raw

    async with SessionFactory() as session:
        await update_settings(session, call.message.chat.id, module, {field: value})

    cfg = dict((chat_settings or {}).get(module, {}))
    cfg[field] = value

    text, kb = _make_kb_module(module, cfg)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("✅ Сохранено")
