import asyncio
import functools
import logging
import os
import traceback

from PIL import Image, ImageDraw, ImageFont, ImageColor
from telethon import TelegramClient, events
from telethon.tl.types import User
from telethon.events.newmessage import NewMessage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def log_on_error():
    def wrapper(function):
        @functools.wraps(function)
        async def wrapped(self: 'AvatarBot', event: NewMessage.Event):
            try:
                result = await function(self, event)
                return result
            except Exception as error:
                logger.exception(f"Error: {error} on event: {event}")
                await self.bot.send_message(
                    "@zotho",
                    (
                        f"Avatar bot error:\n"
                        f"<code>{error}</code>\n\n"
                        f"Traceback:\n"
                        f"<code>{traceback.format_exc()}</code>\n"
                        f"Event:\n"
                        f"<code>{event}</code>"
                    ),
                    parse_mode="html",
                )
                await event.message.respond("Произошла непредвиденная ошибка.. Попробуем разобраться")
                raise

        return wrapped
    return wrapper


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

    @log_on_error()
    async def start_handler(self, event: NewMessage.Event):
        user: User = event.chat
        logger.info(f"Process start: {user.id} {user.username} {user.first_name}")
        avatar_filename = await self.bot.download_profile_photo(user)

        if avatar_filename is not None:
            await self.reply_photo(avatar_filename, event)
        else:
            logger.info(f"No avatar for @{user.username} ({user.id})")

        await event.message.respond("Вы можете отправить мне любое изображение и я его обработаю..")

    @log_on_error()
    async def image_handler(self, event: NewMessage.Event):
        user: User = event.chat
        logger.info(f"Process image: {user.id} {user.username} {user.first_name}")
        avatar_filename = await self.bot.download_media(event.message)

        if avatar_filename is not None:
            await self.reply_photo(avatar_filename, event)
        else:
            await event.message.respond("Не могу найти фото для загрузки")

    async def reply_photo(self, avatar_filename: str, event: NewMessage.Event):
        image: Image.Image = Image.open(avatar_filename).copy().convert("RGBA")
        width, height = size = image.size
        if max(size) > 4000:
            await event.message.respond(f"Слишком большое изображение: {width}:{height}")
            return
        elif min(size) < 10:
            await event.message.respond(f"Слишком маленькое изображение: {width}:{height}")
            return

        rect_side = min(size)
        resized_arcs = self.arcs.resize((rect_side, rect_side))
        offset = round((width - height) / 2)
        offset_box = (offset, 0) if offset > 0 else (0, -offset)
        image.paste(resized_arcs, mask=resized_arcs, box=offset_box)

        image = image.convert("RGB")
        image.save(avatar_filename)

        await self.bot.send_file(event.chat, avatar_filename)

        os.remove(avatar_filename)


async def main():
    api_id: int = int(os.environ["API_ID"])
    api_hash: str = os.environ["API_HASH"]
    token: str = os.environ["TG_TOKEN"]
    bot = await AvatarBot.create(api_id, api_hash, token)
    await bot.start_bot()


if __name__ == "__main__":
    asyncio.run(main())
