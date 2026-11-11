from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup
from bot import Bot
from database.database import is_admin, total_users_count
from helper_func import get_readable_time
from plugins.helpers import get_preview, sbtn, reply_ui

@Bot.on_message(filters.command('stats') & filters.private)
async def stats(bot: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    now = datetime.now()
    delta = now - bot.uptime
    uptime_str = get_readable_time(delta.seconds)
    users = await total_users_count()

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦 ⚡</b></blockquote>\n"
        f"<blockquote>◍ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{uptime_str}</code>\n"
        f"◍ <b>ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> <code>{users}</code></blockquote>",
        reply_markup=close_btn
    )
