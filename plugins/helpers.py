import random
import time
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

# ─── ASSETS CONFIGURATION ──────────────────────────────────────────────
STICKERS = [
    "CAACAgIAAxkBAAIspWr0Fup8dtz_geWOmfrraR0gLAEQAAJ3HAACabmQSOF_GcXWvtrNPQQ",
    "CAACAgUAAxkBAAIm72p5uhDyd5y4kTBgAAFXOJk32R8rAwAC2RQAAmcFaVZ86P4g9HBS6D0E",
    "CAACAgUAAxkBAAIm5Wp4nLY-xArcRez6HkUN0g80IAmIAAIeGgACx9AwVgmOMWuZKMGNPQQ"
]

IMAGES = [
    "https://graph.org/file/d3c445d06682054410fee-35d35426f977f171ef.jpg",
    "https://graph.org/file/b7bde228c107640ff11e3-a53a5c3d3f47763ea0.jpg",
    "https://graph.org/file/e1ea638f7de70509c565b-3414778e2ef4685b4f.jpg",
    "https://graph.org/file/59dc9808dc2d803d73d9f-ab72d2c527b8929986.jpg",
    "https://graph.org/file/fdb6274d6fcf654b95863-90c4e60858529ba752.jpg",
    "https://graph.org/file/b9b92be3fc206c88b780b-d80a12ea996e96de20.jpg",
    "https://graph.org/file/2eba72bc5cc4470c99b9d-c9e9ceb117d1a498e0.jpg",
    "https://graph.org/file/075e8d47f63f9f45dfb54-1121766c13625f4bc4.jpg",
    "https://graph.org/file/e4d9bee7a78e3f248f3bd-5249020a8b06628278.jpg"
]

def get_preview():
    """Ultra-fast zero-width image preview link injection"""
    return f"[\u200b]({random.choice(IMAGES)})"

# ─── MESSAGE TEMPLATES ─────────────────────────────────────────────────
def get_start_text():
    return (
        f"{get_preview()}"
        f"➲ **𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘**\n\n"
        f"> ʜᴇʏ, ᴅᴏɴ'ᴛ ᴏᴠᴇʀᴛʜɪɴᴋ ɪᴛ! ɪ'ᴠᴇ ɢᴏᴛ ᴛʜᴇ ʟɪɴᴋs ᴄᴏᴠᴇʀᴇᴅ. ʏᴏᴜ ᴊᴜsᴛ ᴇɴᴊᴏʏ ʏᴏᴜʀ ᴅᴀʏ!"
    )

def get_about_text():
    return (
        f"{get_preview()}"
        f"➲ **𝗔𝗕𝗢𝗨𝗧 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘**\n\n"
        f"> ◍ ʙʀᴏᴡsᴇ ᴀ ᴍᴀɴᴀɢᴇᴅ ᴄʜᴀɴɴᴇʟ ᴅɪʀᴇᴄᴛᴏʀʏ ᴀɴᴅ ʀᴇᴄᴇɪᴠᴇ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋs. "
        f"ʟɪɴᴋs ᴄᴀɴ ᴇxᴘɪʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.\n\n"
        f"> ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ [ᴋᴀʀᴀsᴜ](https://t.me/Karasu_07)"
    )

def get_fsub_text():
    return (
        f"{get_preview()}"
        f"➲ **𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗 🔒**\n\n"
        f"> ◍ ᴇʜ? ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ! ᴊᴏɪɴ ᴛʜᴇᴍ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ʏᴏᴜʀ ғɪʟᴇs ɪɴsᴛᴀɴᴛʟʏ~\n\n"
        f"≡ **𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗠𝗘𝗡𝗧𝗦 :**\n"
        f"> ◍ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs\n"
        f"> ◍ ᴄʟɪᴄᴋ **ᴛʀʏ ᴀɢᴀɪɴ ↻** ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ʏᴏᴜʀ ғɪʟᴇs"
    )

# ─── AUTO COMMANDS SETUP ON STARTUP ────────────────────────────────────
async def setup_bot_commands(client):
    commands = [
        BotCommand("start", "Start LinkShare bot"),
        BotCommand("add_fsub", "Add Force Subscribe channel/group"),
        BotCommand("del_fsub", "Remove Force Subscribe channel/group"),
        BotCommand("fsub_chnl", "View list of FSub channels"),
        BotCommand("req", "Toggle request mode vs direct join"),
    ]
    try:
        await client.set_bot_commands(commands)
    except Exception as e:
        print(f"Error setting commands: {e}")
