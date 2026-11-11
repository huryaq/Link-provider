import asyncio
from datetime import datetime
from pyrogram import Client
from pyrogram.enums import ParseMode
from config import API_HASH, APP_ID, LOGGER, TG_BOT_TOKEN, TG_BOT_WORKERS, PORT, OWNER_ID
from plugins import web_server
from plugins.helpers import setup_bot_commands, get_preview, sbtn
from pyrogram.types import InlineKeyboardMarkup
import pyrogram.utils
from aiohttp import web

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

name = """
Links Sharing Bot Started
"""

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
        )
        self.LOGGER = LOGGER

    async def start(self, *args, **kwargs):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        self.username = usr_bot_me.username
        self.set_parse_mode(ParseMode.HTML)

        # Auto-register all commands on VPS start
        await setup_bot_commands(self)

        # Notify owner of bot restart in new UI
        try:
            close_markup = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
            await self.send_message(
                chat_id=OWNER_ID,
                text=(
                    f"{get_preview()}"
                    f"<blockquote><b>➲ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗢𝗡𝗟𝗜𝗡𝗘 ⚡</b></blockquote>\n"
                    f"<blockquote>◍ ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!\n"
                    f"◍ ᴄᴏᴍᴍᴀɴᴅs sʏɴᴄᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.</blockquote>"
                ),
                reply_markup=close_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            self.LOGGER(__name__).warning(f"Failed to notify owner ({OWNER_ID}) of bot start: {e}")

        self.LOGGER(__name__).info(f"Bot Running..! @{self.username}")
        self.LOGGER(__name__).info(f"{name}")

        # Web-response
        try:
            app = web.AppRunner(await web_server())
            await app.setup()
            bind_address = "0.0.0.0"
            await web.TCPSite(app, bind_address, PORT).start()
            self.LOGGER(__name__).info(f"Web server started on {bind_address}:{PORT}")
        except Exception as e:
            self.LOGGER(__name__).error(f"Failed to start web server: {e}")

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

# Global cancel flag for broadcast
is_canceled = False
cancel_lock = asyncio.Lock()

if __name__ == "__main__":
    Bot().run()
