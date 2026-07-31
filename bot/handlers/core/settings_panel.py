"""
Панель настроек — inline-клавиатура.

Ключевой принцип: chat_id ВСТРОЕН в каждую callback_data кнопку.
Формат: sp:set:{module}:{field}:{value}:{chat_id}
        sp:m:{module}:{chat_id}
        sp:main:{page}:{chat_id}
        sp:sel:{chat_id}

Никакого FSM, никакого Redis для передачи контекста — всё самодостаточно.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.engine import SessionFactory
from bot.services.settings_service import get_admin_chats, get_settings, update_settings

router = Router(name="settings_panel")


# ---------------------------------------------------------------------------
# Button / keyboard helpers
# ---------------------------------------------------------------------------

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _on(val: bool) -> str:
    return "✅ Включено" if val else "❌ Выключено"


def _action_label(action: str) -> str:
    labels = {
        "warn":     "⚠ Предупреждение",
        "mute":     "🔇 Заглушить",
        "kick":     "👢 Кикнуть",
        "ban":      "🚫 Заблокировать",
        "restrict": "🚷 Ограничить",
        "delete":   "🗑 Удалить",
        "off":      "❌ Выкл",
    }
    return labels.get(action, action)


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

_PAGE0_PAIRS: list[tuple[str, str]] = [
    ("📋 Правила",        "rules"),
    ("🚫 Антиспам",       "antispam"),
    ("💬 Приветствие",    "welcome"),
    ("💨 Антифлуд",       "antiflood"),
    ("👋 Прощание",       "goodbye"),
    ("🔱 Алфавиты",       "alphabets"),
    ("🧠 Капча",          "captcha"),
    ("✅ Проверки",       "checkperms"),
    ("🆘 @Admin",         "admin_tag"),
    ("🔒 Блокировки",     "blocks"),
    ("📸 Медиа",          "media_blocks"),
    ("🔞 Фильтр порно",   "anti_nsfw"),
    ("❗ Предупреждения",  "warns"),
    ("🌙 Ночной режим",   "night_mode"),
    ("🔔 Упоминание",     "tag_all"),
    ("🔗 Ссылки",         "link_settings"),
]

_PAGE0_FULL: list[tuple[str, str]] = [
    ("👑 Бот-страж  NEW",    "bot_guard"),
    ("🎭 Режим одобрения",    "approve_mode"),
    ("🗑 Удаление сообщений", "message_deletion"),
]

_PAGE1_ROWS: list[tuple[str, str]] = [
    ("📁 Темы",              "topics"),
    ("abc Запрещённые слова", "banned_words"),
    ("⏱ Повт. сообщения",   "recurring"),
    ("👥 Управление польз.", "members"),
    ("👻 Скрытые польз.",    "masked_users"),
    ("💬 Группа обсуждения", "discussion"),
    ("✨ Личн. команды",     "personal_commands"),
    ("🎭 Стикеры и GIF",     "magic_stickers"),
    ("📏 Длина сообщения",   "msg_length"),
    ("📺 Управл. каналами",  "channel_mod"),
    ("✏️ Разрешения",        "permissions"),
    ("🔭 Канал событий",     "log_channel"),
]

_PAGE1_SIZE = 6


def _main_keyboard(page: int, chat_id: int) -> InlineKeyboardMarkup:
    c = chat_id
    rows: list[list[InlineKeyboardButton]] = []

    if page == 0:
        for i in range(0, len(_PAGE0_PAIRS), 2):
            pair = _PAGE0_PAIRS[i: i + 2]
            rows.append([_btn(t, f"sp:m:{m}:{c}") for t, m in pair])
        for t, m in _PAGE0_FULL:
            rows.append([_btn(t, f"sp:m:{m}:{c}")])
        rows.append([
            _btn("🇷🇺 Lang",    f"sp:lang:{c}"),
            _btn("✅ Закрыть",   "sp:close"),
            _btn("▶ Другие",    f"sp:main:1:{c}"),
        ])
    else:
        idx   = page - 1
        start = idx * _PAGE1_SIZE * 2
        chunk = _PAGE1_ROWS[start: start + _PAGE1_SIZE * 2]
        for i in range(0, len(chunk), 2):
            pair = chunk[i: i + 2]
            rows.append([_btn(t, f"sp:m:{m}:{c}") for t, m in pair])

        total_pages = 1 + (len(_PAGE1_ROWS) + _PAGE1_SIZE * 2 - 1) // (_PAGE1_SIZE * 2)
        nav: list[InlineKeyboardButton] = [_btn("◀ Назад", f"sp:main:{page - 1}:{c}")]
        nav.append(_btn("✅ Закрыть", "sp:close"))
        if page < total_pages - 1:
            nav.append(_btn("▶ Другие", f"sp:main:{page + 1}:{c}"))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _main_text(chat_title: str) -> str:
    return (
        "⚙️ <b>ПАРАМЕТРЫ</b>\n"
        f"Группа: <b>{chat_title}</b>\n\n"
        "<i>Выберите параметр для изменения.</i>"
    )


_NO_GROUPS_TEXT = (
    "😟 <b>Групп не найдено.</b>\n\n"
    "Убедитесь, что:\n"
    "• Вы являетесь <b>администратором</b> или <b>владельцем</b> группы\n"
    "• Бот добавлен в группу и является администратором\n\n"
    "Напишите <code>/reload</code> в группе, затем нажмите «Перейти в чат»"
)


def _groups_list_keyboard(chats: list) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"👥 {chat.title or str(chat.id)}", f"sp:sel:{chat.id}")]
        for chat in chats
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Module sub-menus  (chat_id встроен в каждую кнопку)
# ---------------------------------------------------------------------------

def _make_kb_module(module: str, cfg: dict, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """
    Возвращает (text, keyboard) для подменю модуля.
    chat_id прописан в каждом callback_data.
    Лимит Telegram: 64 байта на callback_data.
    """
    c = chat_id

    def _toggle(field: str, cur: bool) -> list[InlineKeyboardButton]:
        on_d  = f"sp:set:{module}:{field}:1:{c}"
        off_d = f"sp:set:{module}:{field}:0:{c}"
        if cur:
            return [_btn("✔ Включить ✓", "sp:noop"), _btn("✖ Отключить",  off_d)]
        return  [_btn("✔ Включить",       on_d),     _btn("✖ Отключить ✓", "sp:noop")]

    def _action_row(cur: str, choices: list[str]) -> list[InlineKeyboardButton]:
        return [
            _btn(_action_label(a) + (" ✓" if a == cur else ""),
                 f"sp:set:{module}:action:{a}:{c}")
            for a in choices
        ]

    back = _btn("◀ Назад", f"sp:main:0:{c}")
    nav  = [back, _btn("✅ Закрыть", "sp:close")]

    # ---- antispam ----
    if module == "antispam":
        enabled = cfg.get("enabled", False)
        action  = cfg.get("action", "warn")
        text = (
            "🚫 <b>Антиспам</b>\n"
            "Контроль спам-сообщений в группе.\n\n"
            f"Статус: {_on(enabled)}\nНаказание: {_action_label(action)}"
        )
        kb = _kb(_toggle("enabled", enabled),
                 _action_row(action, ["warn", "mute", "kick", "ban"]),
                 nav)

    # ---- antiflood ----
    elif module == "antiflood":
        enabled = cfg.get("enabled", False)
        action  = cfg.get("action", "mute")
        count   = cfg.get("count", 5)
        period  = cfg.get("period", 5)
        text = (
            "💨 <b>Антифлуд</b>\n"
            "Контроль флуда.\n\n"
            f"Статус: {_on(enabled)}\nНаказание: {_action_label(action)}\n"
            f"Лимит: {count} сообщ. за {period} сек."
        )
        kb = _kb(_toggle("enabled", enabled),
                 _action_row(action, ["warn", "mute", "kick", "ban"]),
                 nav)

    # ---- anti_nsfw ----
    elif module == "anti_nsfw":
        enabled = cfg.get("enabled", False)
        delete  = cfg.get("delete", True)
        action  = cfg.get("action", "warn")
        text = (
            "🔞 <b>Фильтр порно</b>\n"
            "Автообнаружение NSFW-контента.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять: {'✅' if delete else '❌'}\n"
            f"Наказание: {_action_label(action)}"
        )
        kb = _kb(
            _toggle("enabled", enabled),
            [_btn(f"🗑 Удалять {'✅' if delete else '❌'}",
                  f"sp:set:{module}:delete:{int(not delete)}:{c}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    # ---- captcha ----
    elif module == "captcha":
        enabled = cfg.get("enabled", False)
        ctype   = cfg.get("type", "button")
        text = (
            "🧠 <b>Капча</b>\n"
            "Защита от ботов для новых участников.\n\n"
            f"Статус: {_on(enabled)}\nТип: {ctype}"
        )
        kb = _kb(
            _toggle("enabled", enabled),
            [
                _btn("🔘 Кнопка"      + (" ✓" if ctype == "button" else ""), f"sp:set:{module}:type:button:{c}"),
                _btn("🔢 Математика"  + (" ✓" if ctype == "math"   else ""), f"sp:set:{module}:type:math:{c}"),
            ],
            [_btn("🔠 Текст" + (" ✓" if ctype == "text" else ""), f"sp:set:{module}:type:text:{c}")],
            nav,
        )

    # ---- welcome ----
    elif module == "welcome":
        enabled = cfg.get("enabled", False)
        del_p   = cfg.get("delete_previous", False)
        text = (
            "💬 <b>Приветствие</b>\n"
            "Сообщение при входе новых участников.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять предыдущее: {'✅' if del_p else '❌'}"
        )
        kb = _kb(
            _toggle("enabled", enabled),
            [_btn(f"🗑 Удалять предыдущее {'✅' if del_p else '❌'}",
                  f"sp:set:{module}:delete_previous:{int(not del_p)}:{c}")],
            nav,
        )

    # ---- goodbye ----
    elif module == "goodbye":
        enabled  = cfg.get("enabled", False)
        send_pm  = cfg.get("send_to_pm", False)
        del_last = cfg.get("delete_last", False)
        delivery = (
            "\n⚠️ Только для пользователей, запустивших бота в ЛС."
            if send_pm else "\nСообщение отправляется в группу."
        )
        text = (
            "👋 <b>Прощание</b>\n"
            "Сообщение при выходе участника из группы."
            f"{delivery}\n\nСтатус: {_on(enabled)}"
        )
        if enabled:
            toggle_row = [_btn("✔ Включить ✓", "sp:noop"),
                          _btn("✖ Отключить",   f"sp:set:goodbye:enabled:0:{c}")]
        else:
            toggle_row = [_btn("✔ Включить",    f"sp:set:goodbye:enabled:1:{c}"),
                          _btn("✖ Отключить ✓", "sp:noop")]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            toggle_row,
            [_btn(f"💌 Отправить в ЛС{' ✓' if send_pm else ''}",
                  f"sp:set:goodbye:send_to_pm:{int(not send_pm)}:{c}")],
            [_btn(f"🗑 Удалять посл. сообщение{' ✓' if del_last else ''}",
                  f"sp:set:goodbye:delete_last:{int(not del_last)}:{c}")],
            [back, _btn("✅ Закрыть", "sp:close")],
        ])

    # ---- rules ----
    elif module == "rules":
        text = (
            "📋 <b>Правила</b>\n"
            "Установите правила командой:\n"
            "<code>/setrules &lt;текст правил&gt;</code>"
        )
        kb = _kb(nav)

    # ---- warns ----
    elif module == "warns":
        max_w  = cfg.get("max_warns", 3)
        action = cfg.get("action", "ban")
        text = (
            "❗ <b>Предупреждения</b>\n\n"
            f"Макс. варнов: {max_w}\nДействие: {_action_label(action)}"
        )
        kb = _kb(
            [
                _btn("➖", f"sp:set:{module}:max_warns:{max(1, max_w - 1)}:{c}"),
                _btn(f"{max_w} варнов", "sp:noop"),
                _btn("➕", f"sp:set:{module}:max_warns:{max_w + 1}:{c}"),
            ],
            _action_row(action, ["mute", "kick", "ban"]),
            nav,
        )

    # ---- night_mode ----
    elif module == "night_mode":
        enabled = cfg.get("enabled", False)
        start   = cfg.get("start", "23:00")
        end     = cfg.get("end",   "07:00")
        text = (
            "🌙 <b>Ночной режим</b>\n"
            "Группа переходит в режим «только чтение» ночью.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Начало: {start}  →  Конец: {end}\n\n"
            "Время: <code>/nightmode HH:MM HH:MM</code>"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- msg_length (сокращение в _PAGE1_ROWS, хранится как max_message_length) ----
    elif module == "msg_length":
        delete  = cfg.get("delete", False)
        max_len = cfg.get("limit", 2000)
        action  = cfg.get("action", "off")
        text = (
            "📏 <b>Длина сообщения</b>\n\n"
            f"Наказание: {_action_label(action)}\n"
            f"Удалять нарушения: {'✅' if delete else '❌'}\n"
            f"Макс. длина: {max_len} символов"
        )
        choices = ["off", "warn", "kick", "restrict", "ban"]
        kb = _kb(
            [_btn(_action_label(a) + (" ✓" if a == action else ""),
                  f"sp:set:{module}:action:{a}:{c}") for a in choices[:3]],
            [_btn(_action_label(a) + (" ✓" if a == action else ""),
                  f"sp:set:{module}:action:{a}:{c}") for a in choices[3:]],
            [_btn(f"🗑 Удалять {'✅' if delete else '❌'}",
                  f"sp:set:{module}:delete:{int(not delete)}:{c}")],
            [back, _btn("✅ Закрыть", "sp:close")],
        )

    # ---- link_settings ----
    elif module == "link_settings":
        enabled = cfg.get("enabled", False)
        delete  = cfg.get("delete", True)
        action  = cfg.get("action", "warn")
        text = (
            "🔗 <b>Ссылки</b>\n"
            "Блокировка ссылок от обычных пользователей.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять: {'✅' if delete else '❌'}\nНаказание: {_action_label(action)}"
        )
        kb = _kb(
            _toggle("enabled", enabled),
            [_btn(f"🗑 Удалять {'✅' if delete else '❌'}",
                  f"sp:set:{module}:delete:{int(not delete)}:{c}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    # ---- banned_words ----
    elif module == "banned_words":
        enabled = cfg.get("enabled", False)
        delete  = cfg.get("delete", True)
        action  = cfg.get("action", "warn")
        text = (
            "abc <b>Запрещённые слова</b>\n"
            "Фильтрация запрещённых слов.\n\n"
            f"Статус: {_on(enabled)}\n"
            f"Удалять: {'✅' if delete else '❌'}\nНаказание: {_action_label(action)}\n\n"
            "Управление: /addbadword · /delbadword · /badwords"
        )
        kb = _kb(
            _toggle("enabled", enabled),
            [_btn(f"🗑 Удалять {'✅' if delete else '❌'}",
                  f"sp:set:{module}:delete:{int(not delete)}:{c}")],
            _action_row(action, ["off", "warn", "mute", "kick", "ban"]),
            nav,
        )

    # ---- message_deletion ----
    elif module == "message_deletion":
        del_svc = cfg.get("delete_service_messages", True)
        del_cmd = cfg.get("delete_commands", False)
        text = (
            "🗑 <b>Удаление сообщений</b>\n\n"
            f"Служебные: {'✅' if del_svc else '❌'}\n"
            f"Команды:   {'✅' if del_cmd else '❌'}"
        )
        # NOTE: используем короткие псевдонимы полей чтобы вписаться в 64 байта.
        # del_svc → delete_service_messages, del_cmd → delete_commands
        # Маппинг применяется в cb_set.
        kb = _kb(
            [_btn(f"🗑 Служебные {'✅' if del_svc else '❌'}",
                  f"sp:set:msg_del:del_svc:{int(not del_svc)}:{c}")],
            [_btn(f"🗑 Команды {'✅' if del_cmd else '❌'}",
                  f"sp:set:msg_del:del_cmd:{int(not del_cmd)}:{c}")],
            nav,
        )

    # ---- approve_mode ----
    elif module == "approve_mode":
        enabled = cfg.get("enabled", False)
        text = (
            "🎭 <b>Режим одобрения</b>\n"
            "Новые участники не пишут до одобрения адм.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- admin_tag ----
    elif module == "admin_tag":
        enabled = cfg.get("enabled", False)
        text = (
            "🆘 <b>@Admin</b>\n"
            "Тег @admin уведомляет всех администраторов.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- blocks ----
    elif module == "blocks":
        ba = cfg.get("block_arabic", False)
        br = cfg.get("block_rtl",    False)
        text = (
            "🔒 <b>Блокировки текста</b>\n\n"
            f"Арабский текст: {'✅' if ba else '❌'}\n"
            f"RTL символы:    {'✅' if br else '❌'}"
        )
        kb = _kb(
            [_btn(f"🔤 Арабский {'✅' if ba else '❌'}",
                  f"sp:set:{module}:block_arabic:{int(not ba)}:{c}")],
            [_btn(f"↩ RTL {'✅' if br else '❌'}",
                  f"sp:set:{module}:block_rtl:{int(not br)}:{c}")],
            nav,
        )

    # ---- media_blocks ----
    elif module == "media_blocks":
        bs = cfg.get("block_stickers",    False)
        bg = cfg.get("block_gifs",        False)
        bv = cfg.get("block_voice",       False)
        bn = cfg.get("block_video_notes", False)
        text = (
            "📸 <b>Медиа</b>\n\n"
            f"Стикеры:        {'✅' if bs else '❌'}\n"
            f"GIF:            {'✅' if bg else '❌'}\n"
            f"Голосовые:      {'✅' if bv else '❌'}\n"
            f"Видеосообщения: {'✅' if bn else '❌'}"
        )
        kb = _kb(
            [
                _btn(f"🎭 Стикеры {'✅' if bs else '❌'}",
                     f"sp:set:{module}:block_stickers:{int(not bs)}:{c}"),
                _btn(f"🎬 GIF {'✅' if bg else '❌'}",
                     f"sp:set:{module}:block_gifs:{int(not bg)}:{c}"),
            ],
            [
                _btn(f"🎙 Голос {'✅' if bv else '❌'}",
                     f"sp:set:{module}:block_voice:{int(not bv)}:{c}"),
                _btn(f"📹 Видео {'✅' if bn else '❌'}",
                     f"sp:set:{module}:block_video_notes:{int(not bn)}:{c}"),
            ],
            nav,
        )

    # ---- alphabets ----
    elif module == "alphabets":
        en = cfg.get("allow_english", True)
        ru = cfg.get("allow_russian", True)
        text = (
            "🔱 <b>Алфавиты</b>\n\n"
            f"Английский: {'✅' if en else '❌'}\n"
            f"Русский:    {'✅' if ru else '❌'}"
        )
        kb = _kb(
            [
                _btn(f"🇬🇧 Английский {'✅' if en else '❌'}",
                     f"sp:set:{module}:allow_english:{int(not en)}:{c}"),
                _btn(f"🇷🇺 Русский {'✅' if ru else '❌'}",
                     f"sp:set:{module}:allow_russian:{int(not ru)}:{c}"),
            ],
            nav,
        )

    # ---- tag_all ----
    elif module == "tag_all":
        enabled = cfg.get("enabled", False)
        text = (
            "🔔 <b>Упоминание всех</b>\n"
            "Администраторы тегают всех участников.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- bot_guard ----
    elif module == "bot_guard":
        enabled = cfg.get("enabled", False)
        text = (
            "👑 <b>Бот-страж</b>\n"
            "Автоудаление ботов без разрешения.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- magic_stickers ----
    elif module == "magic_stickers":
        enabled = cfg.get("enabled", False)
        text = (
            "🎭 <b>Стикеры и GIF</b>\n"
            "Запуск команды по стикеру или GIF.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- permissions ----
    elif module == "permissions":
        text = "✏️ <b>Разрешения</b>\n\nПрава доступа к функциям бота.\n\nНастройка через /roles."
        kb = _kb(nav)

    # ---- log_channel ----
    elif module == "log_channel":
        text = (
            "🔭 <b>Канал событий</b>\n"
            "Все события группы сохраняются в канал.\n\n"
            "Добавьте бота в канал как администратора,\n"
            "затем перешлите любое сообщение из канала боту."
        )
        kb = _kb(nav)

    # ---- topics ----
    elif module == "topics":
        enabled = cfg.get("enabled", False)
        text = (
            "📁 <b>Темы</b>\n"
            "Управление темами (форумами) в супергруппе.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- recurring ----
    elif module == "recurring":
        text = "⏱ <b>Повторяющиеся сообщения</b>\n\nАвторассылка по расписанию.\n\nУправление: /recurring"
        kb = _kb(nav)

    # ---- members ----
    elif module == "members":
        text = "👥 <b>Управление пользователями</b>\n\n/ban /unban /mute /unmute /kick /warn /warnlist"
        kb = _kb(nav)

    # ---- masked_users ----
    elif module == "masked_users":
        enabled = cfg.get("enabled", False)
        text = f"👻 <b>Скрытые пользователи</b>\n\nСтатус: {_on(enabled)}"
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- discussion ----
    elif module == "discussion":
        text = "💬 <b>Группа обсуждения</b>\n\nНастраивается через меню Telegram."
        kb = _kb(nav)

    # ---- personal_commands ----
    elif module == "personal_commands":
        text = "✨ <b>Личные команды</b>\n\n/addcommand · /delcommand · /mycommands"
        kb = _kb(nav)

    # ---- channel_mod ----
    elif module == "channel_mod":
        enabled = cfg.get("enabled", False)
        text = (
            "📺 <b>Управление каналами</b>\n"
            "Модерация сообщений от связанных каналов.\n\n"
            f"Статус: {_on(enabled)}"
        )
        kb = _kb(_toggle("enabled", enabled), nav)

    # ---- checkperms ----
    elif module == "checkperms":
        text = "✅ <b>Проверка прав бота</b>\n\nИспользуйте: /checkperms"
        kb = _kb(nav)

    # ---- fallback ----
    else:
        text = f"⚙️ <b>{module}</b>\n\nНастройки скоро появятся."
        kb   = _kb(nav)

    return text, kb


# ---------------------------------------------------------------------------
# Маппинг коротких псевдонимов для msg_del (чтобы не выйти за 64 байта)
# ---------------------------------------------------------------------------

# Маппинг: (псевдоним_модуля, псевдоним_поля) → (реальный_модуль, реальное_поле)
_FIELD_ALIAS: dict[tuple[str, str], tuple[str, str]] = {
    ("msg_del", "del_svc"): ("message_deletion", "delete_service_messages"),
    ("msg_del", "del_cmd"): ("message_deletion", "delete_commands"),
}

# Маппинг: псевдоним_модуля → реальный_модуль (для отображения)
_MODULE_ALIAS: dict[str, str] = {
    "msg_del": "message_deletion",
    "msg_length": "msg_length",  # хранится под тем же именем
}


# ---------------------------------------------------------------------------
# Command: /settings
# ---------------------------------------------------------------------------

@router.message(Command("settings"))
async def cmd_settings(message: Message, chat_user_role: str = "member") -> None:
    if message.chat.type == "private":
        user_id = message.from_user.id
        async with SessionFactory() as session:
            chats = await get_admin_chats(session, user_id)

        if not chats:
            await message.answer(_NO_GROUPS_TEXT, parse_mode="HTML")
            return

        if len(chats) == 1:
            chat = chats[0]
            await message.answer(
                _main_text(chat.title or str(chat.id)),
                reply_markup=_main_keyboard(0, chat.id),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "⚙️ <b>Выберите группу для настройки:</b>",
                parse_mode="HTML",
                reply_markup=_groups_list_keyboard(chats),
            )
        return

    # В группе — только для администраторов
    from bot.utils.permissions import role_at_least  # type: ignore[import]
    if not role_at_least(chat_user_role, "admin"):
        return

    title = message.chat.title or str(message.chat.id)
    await message.answer(
        _main_text(title),
        reply_markup=_main_keyboard(0, message.chat.id),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("sp:sel:"))
async def cb_select_chat(call: CallbackQuery) -> None:
    """Выбор группы из списка в ЛС — переходим в главное меню с нужным chat_id."""
    chat_id = int(call.data.split(":")[2])

    async with SessionFactory() as session:
        from bot.database.models import Chat
        from sqlalchemy import select as sa_select
        result = await session.execute(sa_select(Chat).where(Chat.id == chat_id))
        chat   = result.scalar_one_or_none()

    if chat is None:
        await call.answer("Группа не найдена.", show_alert=True)
        return

    await call.message.edit_text(
        _main_text(chat.title or str(chat.id)),
        reply_markup=_main_keyboard(0, chat_id),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("sp:main:"))
async def cb_main(call: CallbackQuery) -> None:
    """Главное меню — переключение страниц."""
    parts   = call.data.split(":")
    page    = int(parts[2])
    chat_id = int(parts[3])

    async with SessionFactory() as session:
        from bot.database.models import Chat
        from sqlalchemy import select as sa_select
        result = await session.execute(sa_select(Chat).where(Chat.id == chat_id))
        chat   = result.scalar_one_or_none()

    title = (chat.title if chat else None) or str(chat_id)
    await call.message.edit_text(
        _main_text(title),
        reply_markup=_main_keyboard(page, chat_id),
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


@router.callback_query(F.data.startswith("sp:lang:"))
async def cb_lang(call: CallbackQuery) -> None:
    await call.answer("🌍 Смена языка пока недоступна.", show_alert=True)


@router.callback_query(F.data.startswith("sp:m:"))
async def cb_module(call: CallbackQuery) -> None:
    """Открыть подменю модуля. Формат: sp:m:{module}:{chat_id}"""
    parts   = call.data.split(":")
    module  = parts[2]
    chat_id = int(parts[3])

    async with SessionFactory() as session:
        all_cfg = await get_settings(session, chat_id)

    # Нормализация псевдонимов
    real_module = _MODULE_ALIAS.get(module, module)
    cfg = all_cfg.get(real_module, {})

    text, kb = _make_kb_module(module, cfg, chat_id)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("sp:set:"))
async def cb_set(call: CallbackQuery) -> None:
    """
    Универсальный setter.
    Формат: sp:set:{module}:{field}:{value}:{chat_id}

    Псевдонимы:
      msg_del / del_svc  → message_deletion / delete_service_messages
      msg_del / del_cmd  → message_deletion / delete_commands
    """
    parts   = call.data.split(":")
    module  = parts[2]
    field   = parts[3]
    raw     = parts[4]
    chat_id = int(parts[5])

    # Разворачиваем псевдонимы если есть
    real_module, real_field = _FIELD_ALIAS.get((module, field), (module, field))

    value: str | int | bool
    if raw in ("0", "1"):
        value = bool(int(raw))
    elif raw.lstrip("-").isdigit():
        value = int(raw)
    else:
        value = raw

    async with SessionFactory() as session:
        await update_settings(session, chat_id, real_module, {real_field: value})

    # Перечитать и показать обновлённый экран
    async with SessionFactory() as session:
        all_cfg = await get_settings(session, chat_id)

    display_module = _MODULE_ALIAS.get(module, real_module)
    cfg = all_cfg.get(display_module, {})

    text, kb = _make_kb_module(module, cfg, chat_id)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("✅ Сохранено")
