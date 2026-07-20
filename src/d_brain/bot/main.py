"""Telegram bot initialization and polling/webhook."""

import asyncio
import logging
import ssl
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from d_brain.config import Settings
from d_brain.services.cron_runner import run_cron
from d_brain.services.systemd_notify import notify, watchdog_interval

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    """Create and configure the Telegram bot."""
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Create and configure the dispatcher with routers."""
    from d_brain.bot.handlers import (
        buttons,
        chat,
        commands,
        process,
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Register routers - ORDER MATTERS
    dp.include_router(commands.router)
    dp.include_router(process.router)
    dp.include_router(buttons.router)  # Reply keyboard buttons
    dp.include_router(chat.router)  # Catch-all for private chat (LAST)
    return dp


MiddlewareHandler = Callable[[Update, dict[str, Any]], Awaitable[Any]]
MiddlewareType = Callable[[MiddlewareHandler, Update, dict[str, Any]], Awaitable[Any]]


def create_auth_middleware(settings: Settings) -> MiddlewareType:
    """Create middleware to check user authorization."""

    async def auth_middleware(
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        # If explicitly allowed all users, just bypass check
        if settings.allow_all_users:
            return await handler(event, data)

        user = None
        if event.message:
            user = event.message.from_user
        elif event.callback_query:
            user = event.callback_query.from_user

        # If no users allowed and not allow_all_users -> deny everyone
        if not settings.allowed_user_ids:
            logger.warning(
                "Access denied: no allowed_user_ids configured and "
                "allow_all_users is False"
            )
            return None

        # Check if user is in allowed list
        if user and user.id not in settings.allowed_user_ids:
            logger.warning("Unauthorized access attempt from user %s", user.id)
            return None

        return await handler(event, data)

    return auth_middleware


async def _watchdog_pinger() -> None:
    """Ping systemd's watchdog while the event loop is healthy."""
    interval = watchdog_interval()
    while True:
        await asyncio.sleep(interval)
        notify("WATCHDOG=1")


async def run_bot(settings: Settings) -> None:
    """Run the bot with polling."""
    bot = create_bot(settings)
    dp = create_dispatcher()

    # Always add auth middleware for security (it handles allow_all_users internally)
    dp.update.middleware(create_auth_middleware(settings))

    notify("READY=1")
    pinger = asyncio.create_task(_watchdog_pinger())
    cron_task = (
        asyncio.create_task(run_cron(settings, bot)) if settings.cron_enabled else None
    )

    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        pinger.cancel()
        if cron_task is not None:
            cron_task.cancel()
        await bot.session.close()


async def run_bot_webhook(settings: Settings) -> None:
    """Run the bot with webhook."""
    bot = create_bot(settings)
    dp = create_dispatcher()

    # Always add auth middleware for security (it handles allow_all_users internally)
    dp.update.middleware(create_auth_middleware(settings))

    notify("READY=1")
    pinger = asyncio.create_task(_watchdog_pinger())
    cron_task = (
        asyncio.create_task(run_cron(settings, bot)) if settings.cron_enabled else None
    )

    # Register webhook with Telegram
    webhook_url = f"{settings.webhook_host}/webhook/{settings.telegram_bot_token}"
    webhook_path = f"/webhook/{settings.telegram_bot_token}"

    for attempt in range(5):
        try:
            await bot.set_webhook(
                url=webhook_url,
                allowed_updates=dp.resolve_used_update_types(),
            )
            logger.info("Webhook set to: %s", webhook_url)
            break
        except Exception as e:
            logger.warning("set_webhook attempt %d failed: %s", attempt + 1, e)
            if attempt < 4:
                await asyncio.sleep(5 * (attempt + 1))
            else:
                logger.error("Failed to set webhook after 5 attempts")
                raise

    # Create aiohttp application
    app = web.Application()

    async def handle_webhook(request: web.Request) -> web.Response:
        """Handle incoming webhook updates from Telegram."""
        try:
            update = Update.model_validate(await request.json())
            await dp.feed_update(bot, update)
        except Exception as e:
            logger.error("Error processing webhook update: %s", e)
        return web.Response()

    async def handle_health(request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.Response(text="OK")

    app.router.add_post(webhook_path, handle_webhook)
    app.router.add_get("/health", handle_health)

    # Start webhook server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.webhook_port)
    await site.start()
    logger.info("Webhook server started on port %d", settings.webhook_port)

    try:
        # Keep running until cancelled
        await asyncio.Event().wait()
    finally:
        pinger.cancel()
        if cron_task is not None:
            cron_task.cancel()
        await runner.cleanup()
        await bot.session.close()
