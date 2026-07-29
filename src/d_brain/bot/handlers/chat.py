"""Unified private chat handler with persistent Claude sessions.

Voice + text only (v3.0): replaces the legacy split handlers for private chats.
Every message is saved to daily (safety net) and routed IMMEDIATELY through
ChatSessionManager for Claude to process and respond — no debounce buffer.

v3.1: Added undo integration and progress bar.
"""

import asyncio
import html
import logging
import re
from datetime import datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from d_brain.bot.formatters import send_response
from d_brain.bot.undo import register_undo, build_undo_keyboard, schedule_button_removal
from d_brain.config import get_settings
from d_brain.services.chat_session import ChatSessionManager
from d_brain.services.git import VaultGit
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import DeepgramTranscriber

router = Router(name="chat")
logger = logging.getLogger(__name__)

router.message.filter(F.chat.type == ChatType.PRIVATE)

MAX_RESPONSE_LENGTH = 4096

_CONTROL = {"/clear", "/model"}
_TUI_ONLY = {"/agents", "/config", "/login"}

_manager: ChatSessionManager | None = None


def classify_command(text: str) -> str:
    if not text.startswith("/"):
        return "turn"
    head = text.split(maxsplit=1)[0]
    if head in _CONTROL:
        return "control"
    if head in _TUI_ONLY:
        return "tui"
    return "turn"


_STOP_WORDS = {"/stop", "stop", "стоп"}


def classify_concurrent_input(text: str, turn_active: bool) -> str:
    if not turn_active:
        return "ask"
    if text.strip().lower() in _STOP_WORDS:
        return "interrupt"
    return "steer"


def _get_manager() -> ChatSessionManager:
    global _manager  # noqa: PLW0603
    if _manager is None:
        settings = get_settings()
        _manager = ChatSessionManager(settings.vault_path)
    return _manager


async def _dispatch_text(bot: Bot, chat_id: int, user_id: int, text: str) -> None:
    kind = classify_command(text)
    if kind == "control":
        await _get_manager().send_control(text)
        await bot.send_message(
            chat_id, f"⌨️ <code>{html.escape(text)}</code> отправлена в сессию."
        )
        return
    if kind == "tui":
        await bot.send_message(
            chat_id,
            "Эта команда открывает интерактивный интерфейс — доступно только "
            "через <code>dbrain attach</code> на сервере.",
        )
        return

    manager = _get_manager()
    mode = classify_concurrent_input(text, manager.is_turn_active())
    if mode == "interrupt":
        await manager.interrupt()
        await bot.send_message(chat_id, "⏹ Останавливаю текущий ответ.")
        return
    if mode == "steer":
        if not manager.is_steerable_turn():
            await bot.send_message(
                chat_id,
                "🔧 Идёт фоновое обслуживание — повтори сообщение через "
                "пару минут, отвечу как освобожусь.",
            )
            return
        await manager.steer(text)
        await bot.send_message(chat_id, "↪️ Передал в текущую задачу.")
        return
    await _process_and_reply(bot, chat_id, user_id, text)


async def _process_and_reply(bot: Bot, chat_id: int, user_id: int, prompt: str) -> None:
    """Send the prompt to the shared session, deliver the reply, and attach undo button if vault changed."""
    typing_task = asyncio.create_task(_typing_loop(bot, chat_id))
    try:
        manager = _get_manager()

        # Capture HEAD SHA before AI processes (for undo)
        settings = get_settings()
        git = VaultGit(settings.vault_path)
        sha_before = await asyncio.to_thread(git.get_head_sha)

        response = await manager.send_message(user_id, prompt)

        if response:
            # Check if vault changed (new commit was created)
            sha_after = await asyncio.to_thread(git.get_head_sha)
            if sha_after and sha_after != sha_before:
                # Vault changed — add undo button
                undo_key = register_undo(sha_after, "AI ответ")
                undo_kb = build_undo_keyboard(undo_key)
                await send_response_with_undo(bot, chat_id, response, undo_kb)
            else:
                await send_response(bot, chat_id, response)
        else:
            logger.warning("Empty response from Claude for user %d, retrying...", user_id)
            response = await manager.send_message(user_id, prompt)
            if response:
                await send_response(bot, chat_id, response)
            else:
                logger.warning("Empty response after retry for user %d", user_id)
                await bot.send_message(
                    chat_id,
                    "Claude не ответил дважды. Повтори сообщение.",
                )

    except Exception as e:
        logger.exception("Chat session error for user %d", user_id)
        error_text = f"Error: {html.escape(str(e)[:200])}"
        try:
            await bot.send_message(chat_id, error_text)
        except Exception:
            logger.exception("Failed to send error message")
    finally:
        typing_task.cancel()


async def send_response_with_undo(bot: Any, chat_id: int, text: str, undo_kb) -> None:
    """Send Claude reply with undo keyboard attached."""
    from d_brain.bot.formatters import sanitize_telegram_html, validate_telegram_html, split_text
    import html as html_mod

    sanitized = sanitize_telegram_html(text)
    if not validate_telegram_html(sanitized):
        sanitized = html_mod.escape(text)

    chunks = split_text(sanitized, MAX_RESPONSE_LENGTH)
    for i, chunk in enumerate(chunks):
        try:
            if i == len(chunks) - 1:
                # Last chunk gets the undo keyboard
                msg = await bot.send_message(chat_id, chunk, reply_markup=undo_kb)
                # Schedule keyboard removal after 5 minutes
                asyncio.create_task(schedule_button_removal(msg, delay_seconds=300))
            else:
                await bot.send_message(chat_id, chunk)
        except Exception:
            await bot.send_message(chat_id, chunk, parse_mode=None)
        if i < len(chunks) - 1:
            await asyncio.sleep(0.3)


async def _typing_loop(bot: Bot, chat_id: int) -> None:
    try:
        while True:
            await bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


UNSUPPORTED_REPLY = (
    "Я принимаю голос, текст, фото и файлы. "
    "Этот тип сообщения обработать не могу."
)

_MEDIA_EXTRACTORS = (
    ("document", "document", None),
    ("video", "video", "mp4"),
    ("audio", "audio", "mp3"),
    ("animation", "animation", "mp4"),
    ("video_note", "video_note", "mp4"),
)


def extract_media(message: Any) -> tuple[str, str, str, str | None]:
    if getattr(message, "photo", None):
        return ("photo", message.photo[-1].file_id, "jpg", None)
    for kind, attr, default_ext in _MEDIA_EXTRACTORS:
        obj = getattr(message, attr, None)
        if obj is None:
            continue
        name = getattr(obj, "file_name", None)
        ext = default_ext or "bin"
        if name and "." in name:
            candidate = name.rsplit(".", 1)[-1].lower()
            if re.fullmatch(r"[a-z0-9]{1,10}", candidate):
                ext = candidate
        return (kind, obj.file_id, ext, name)
    raise ValueError("message carries no known media")


def forward_note(origin: Any) -> str:
    if origin is None:
        return ""
    user = getattr(origin, "sender_user", None)
    if user is not None:
        return f"[переслано от: {user.full_name}]\n"
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    if chat is not None:
        return f"[переслано из: {chat.title}]\n"
    name = getattr(origin, "sender_user_name", None)
    if name:
        return f"[переслано от: {name}]\n"
    return "[переслано]\n"


def build_media_prompt(
    *, kind: str, rel_path: str, original_name: str | None, caption: str, fwd: str
) -> str:
    name_part = f" (имя файла: {original_name})" if original_name else ""
    caption_part = f"\nПодпись: {caption}" if caption else ""
    return (
        f"{fwd}Пользователь прислал {kind}: {rel_path}{name_part}{caption_part}\n"
        "Прочитай файл (Read поддерживает изображения и PDF; для "
        "видео/аудио опиши по подписи и контексту), сохрани суть в память "
        "по правилам vault и кратко ответь, что сохранил."
    )


ALBUM_SETTLE = 1.5
_album_buf: dict[str, list[dict[str, str]]] = {}
_album_tasks: dict[str, asyncio.Task] = {}


def build_album_prompt(items: list[dict[str, str]]) -> str:
    fwd = next((i["fwd"] for i in items if i["fwd"]), "")
    captions = [i["caption"] for i in items if i["caption"]]
    files = "\n".join(f"- {i['rel_path']} ({i['kind']})" for i in items)
    caption_part = f"\nПодпись: {' / '.join(captions)}" if captions else ""
    return (
        f"{fwd}Пользователь прислал альбом из {len(items)} файлов:\n"
        f"{files}{caption_part}\n"
        "Прочитай файлы (Read поддерживает изображения и PDF), сохрани суть "
        "в память по правилам vault одной записью и кратко ответь."
    )


async def queue_album_item(
    bot: Bot, *, chat_id: int, user_id: int, group_id: str, item: dict[str, str]
) -> None:
    _album_buf.setdefault(group_id, []).append(item)
    if group_id not in _album_tasks:
        _album_tasks[group_id] = asyncio.create_task(
            _flush_album(bot, chat_id, user_id, group_id)
        )


async def _flush_album(bot: Bot, chat_id: int, user_id: int, group_id: str) -> None:
    await asyncio.sleep(ALBUM_SETTLE)
    items = _album_buf.pop(group_id, [])
    _album_tasks.pop(group_id, None)
    if items:
        await _process_and_reply(bot, chat_id, user_id, build_album_prompt(items))


# --- Handlers ---


@router.message(F.voice)
async def handle_chat_voice(message: Message, bot: Bot) -> None:
    if not message.voice or not message.from_user:
        return

    settings = get_settings()
    storage = VaultStorage(settings.vault_path)
    transcriber = DeepgramTranscriber(settings.deepgram_api_key)

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file.file_path:
            await message.answer("Failed to download voice")
            return

        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await message.answer("Failed to download voice")
            return

        transcript = await transcriber.transcribe(file_bytes.read())
        if not transcript:
            await message.answer("Could not transcribe audio")
            return

        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(transcript, timestamp, "[voice]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "voice",
            text=transcript,
            duration=message.voice.duration,
            msg_id=message.message_id,
        )

        await _process_and_reply(
            bot, message.chat.id, message.from_user.id, f"[voice] {transcript}"
        )

    except Exception as e:
        logger.exception("Error processing voice in chat")
        try:
            await message.answer(f"Error: {html.escape(str(e)[:200])}")
        except Exception:
            logger.exception("Failed to send voice error message")


@router.message(F.text)
async def handle_chat_text(message: Message, bot: Bot) -> None:
    if not message.text or not message.from_user:
        return

    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    fwd = forward_note(getattr(message, "forward_origin", None))
    text = f"{fwd}{message.text}" if fwd else message.text

    timestamp = datetime.fromtimestamp(message.date.timestamp())
    storage.append_to_daily(text, timestamp, "[forward]" if fwd else "[text]")

    session = SessionStore(settings.vault_path)
    session.append(
        message.from_user.id,
        "text",
        text=text,
        msg_id=message.message_id,
    )

    await _dispatch_text(bot, message.chat.id, message.from_user.id, text)


@router.message(
    F.photo | F.document | F.video | F.audio | F.animation | F.video_note
)
async def handle_chat_media(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return

    settings = get_settings()
    storage = VaultStorage(settings.vault_path)
    timestamp = datetime.fromtimestamp(message.date.timestamp())
    caption = message.caption or ""
    fwd = forward_note(getattr(message, "forward_origin", None))

    try:
        kind, file_id, ext, original_name = extract_media(message)
    except ValueError:
        await message.answer(UNSUPPORTED_REPLY)
        return

    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            await message.answer("Не удалось скачать файл.")
            return
        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await message.answer("Не удалось скачать файл.")
            return

        rel_path = storage.save_attachment(
            file_bytes.read(), timestamp.date(), timestamp, ext
        )

        daily_entry = f"{fwd}![[{rel_path}]]"
        if caption:
            daily_entry += f"\n\n{caption}"
        storage.append_to_daily(daily_entry, timestamp, f"[{kind}]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            kind,
            text=caption or rel_path,
            msg_id=message.message_id,
        )

        group_id = getattr(message, "media_group_id", None)
        if group_id:
            await queue_album_item(
                bot,
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                group_id=str(group_id),
                item={
                    "kind": kind,
                    "rel_path": rel_path,
                    "caption": caption,
                    "fwd": fwd,
                },
            )
            return

        prompt = build_media_prompt(
            kind=kind,
            rel_path=rel_path,
            original_name=original_name,
            caption=caption,
            fwd=fwd,
        )
        await _process_and_reply(bot, message.chat.id, message.from_user.id, prompt)

    except Exception as e:
        logger.exception("Error processing media in chat")
        if "too big" in str(e).lower():
            note = f"{fwd}(файл >20MB — Telegram не отдаёт его ботам)"
            if caption:
                note += f"\n\n{caption}"
            storage.append_to_daily(note, timestamp, f"[{kind}]")
            await message.answer(
                "Файл больше 20 МБ — Telegram не отдаёт такие ботам. "
                "Подпись сохранил; перешли файл иначе (ссылкой/частями)."
            )
            return
        try:
            await message.answer(f"Error: {html.escape(str(e)[:200])}")
        except Exception:
            logger.exception("Failed to send media error message")


@router.message()
async def handle_chat_other(message: Message) -> None:
    await message.answer(UNSUPPORTED_REPLY)
