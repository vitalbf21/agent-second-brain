"""Entry point for running d-brain as a module."""

import asyncio
import logging

from dotenv import load_dotenv

# Load .env into os.environ so subprocess (mimo CLI) gets API keys
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    from d_brain.bot.main import run_bot, run_bot_webhook
    from d_brain.config import get_settings

    settings = get_settings()
    logger.info("d-brain starting...")
    logger.info("Vault path: %s", settings.vault_path)
    logger.info("Allowed users: %s", settings.allowed_user_ids or "all")

    if settings.webhook_enabled:
        logger.info("Running in webhook mode")
        await run_bot_webhook(settings)
    else:
        logger.info("Running in polling mode")
        await run_bot(settings)


if __name__ == "__main__":
    asyncio.run(main())
