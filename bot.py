import asyncio
import functools
import json
import logging
import os
import traceback
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageColor
from telethon import TelegramClient, events
from telethon.errors import UserIsBlockedError, InputUserDeactivatedError
from telethon.tl.types import User, Message
from telethon.events.newmessage import NewMessage

MAX_MESSAGE_LENGTH = 4096  # https://core.telegram.org/bots/api#message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def safe_respond(message: Message, text: str):
    try:
        await message.respond(text)
    except (UserIsBlockedError, InputUserDeactivatedError):
        logger.error("Can't send message to user")


def log_on_error(function):
    @functools.wraps(function)
    async def wrapped(self: 'AvatarBot', event: NewMessage.Event):
        try:
            result = await function(self, event)
            return result
        except Exception as error:
            logger.exception(f"Error: {error} on event: {event}")
            admin_message = (
                f"Avatar bot error:\n"
                f"<code>{error}</code>\n\n"
                f"Traceback:\n"
                f"<code>{traceback.format_exc()}</code>\n"
                f"Event:\n"
                f"<code>{event}</code>"
            )[:MAX_MESSAGE_LENGTH]
            await self.bot.send_message(
                "@zotho",
                admin_message,
                parse_mode="html",
            )
            await safe_respond(event.message, "Произошла непредвиденная ошибка.. Попробуем разобраться")
            raise
    return wrapped


class AvatarBot:
    def __init__(self, bot: TelegramClient):
        self.bot = bot

        bot.add_event_handler(
            self.start_handler,
            events.NewMessage(
                pattern="/start",
                incoming=True,
                func=lambda e: e.is_private
            )
        )
        bot.add_event_handler(
            self.image_handler,
            events.NewMessage(
                incoming=True,
                func=lambda e: e.is_private and e.message.photo
            )
        )

        self.arcs: Image.Image
        arcs: Image.Image
        self.arcs = arcs = Image.open("arcs.png")

        width, height = arcs.size
        draw = ImageDraw.Draw(arcs)
        font = ImageFont.truetype("Lobster-Regular.ttf", 700)
        text = "Free LPR"
        text_width, text_height = draw.textsize(text, font)
        draw.text(
            (width / 2 - text_width / 2, height - text_height - 300),
            text,
            font=font,
            fill=ImageColor.getrgb("#2b2b2a"),
            align="left",
            stroke_width=20,
            stroke_fill=ImageColor.getrgb("#ec6a20"),
        )

    async def start_bot(self):
        await self.bot.catch_up()
        await self.bot.run_until_disconnected()

    @classmethod
    async def create(cls, api_id: int, api_hash: str, token: str) -> "AvatarBot":
        bot = await TelegramClient("Avatar bot", api_id, api_hash).start(bot_token=token)
        self = cls(bot)
        return self

    @log_on_error
    async def start_handler(self, event: NewMessage.Event):
        user: User = event.chat
        logger.info(f"Process start: {user.id} {user.username} {user.first_name}")
        avatar_filename = await self.bot.download_profile_photo(user)

        if avatar_filename is not None:
            await self.reply_photo(avatar_filename, event)
        else:
            logger.info(f"No avatar for @{user.username} ({user.id})")

        await safe_respond(event.message, "Вы можете отправить мне любое изображение и я его обработаю..")

    @log_on_error
    async def image_handler(self, event: NewMessage.Event):
        user: User = event.chat
        logger.info(f"Process image: {user.id} {user.username} {user.first_name}")
        message: Message = event.message
        avatar_filename = await self.bot.download_media(message)

        if avatar_filename is not None:
            await self.reply_photo(avatar_filename, event)
        else:
            await safe_respond(message, "Не могу найти фото для загрузки")

    async def reply_photo(self, avatar_filename: str, event: NewMessage.Event):
        message: Message = event.message
        image: Image.Image = Image.open(avatar_filename).copy().convert("RGBA")
        width, height = size = image.size
        if max(size) > 4000:
            await safe_respond(message, f"Слишком большое изображение: {width}:{height}")
            return
        elif min(size) < 10:
            await safe_respond(message, f"Слишком маленькое изображение: {width}:{height}")
            return

        rect_side = min(size)
        resized_arcs = self.arcs.resize((rect_side, rect_side))
        offset = round((width - height) / 2)
        offset_box = (offset, 0) if offset > 0 else (0, -offset)
        image.paste(resized_arcs, mask=resized_arcs, box=offset_box)

        image = image.convert("RGB")
        image.save(avatar_filename)

        try:
            await self.bot.send_file(event.chat, avatar_filename)
        except (UserIsBlockedError, InputUserDeactivatedError):
            logger.error("Can't send file to user")
        finally:
            os.remove(avatar_filename)


async def main():
    config = json.loads(Path("config.json").read_text())
    api_id: int = int(os.getenv("API_ID") or config["API_ID"])
    api_hash: str = os.getenv("API_HASH") or config["API_HASH"]
    token: str = os.getenv("TG_TOKEN") or config["TG_TOKEN"]
    bot = await AvatarBot.create(api_id, api_hash, token)
    await bot.start_bot()


if __name__ == "__main__":
    asyncio.run(main())
