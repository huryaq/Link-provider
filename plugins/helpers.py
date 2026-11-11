import random
import inspect
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup

# ─── STICKERS & PREVIEW IMAGES POOL ────────────────────────────────────
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

def get_preview() -> str:
    """Zero-width HTML link for instant top preview without file upload lag"""
    return f'<a href="{random.choice(IMAGES)}">&#8203;</a>'

# ─── SMART COLORED BUTTON BUILDER (PRIMARY / DANGER / SUCCESS) ─────────
_BTN_PARAMS = inspect.signature(InlineKeyboardButton.__init__).parameters

def sbtn(text: str, callback_data: str = None, url: str = None, style: str = None) -> InlineKeyboardButton:
    """
    Creates an InlineKeyboardButton with Telegram's new button color styles
    ('primary' = Blue, 'danger' = Red, 'success' = Green) if supported by the installed library.
    """
    kwargs = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style:
        if "style" in _BTN_PARAMS:
            kwargs["style"] = style
        elif "button_style" in _BTN_PARAMS:
            kwargs["button_style"] = style
    return InlineKeyboardButton(**kwargs)

# ─── SMART SEND / EDIT WITH TOP IMAGE PREVIEW ──────────────────────────
async def reply_ui(message, text: str, reply_markup: InlineKeyboardMarkup = None):
    kwargs = {
        "text": text,
        "reply_markup": reply_markup,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": False,
    }
    if "invert_media" in inspect.signature(message.reply_text).parameters:
        kwargs["invert_media"] = True
    return await message.reply_text(**kwargs)

async def edit_ui(message, text: str, reply_markup: InlineKeyboardMarkup = None):
    kwargs = {
        "text": text,
        "reply_markup": reply_markup,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": False,
    }
    if "invert_media" in inspect.signature(message.edit_text).parameters:
        kwargs["invert_media"] = True
    return await message.edit_text(**kwargs)

# ─── UI MESSAGE TEMPLATES (VIDEO STYLE DOUBLE QUOTE BLOCKS) ────────────
def get_start_text() -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘</b></blockquote>\n"
        f"<blockquote>ʜᴇʏ, ᴅᴏɴ'ᴛ ᴏᴠᴇʀᴛʜɪɴᴋ ɪᴛ! ɪ'ᴠᴇ ɢᴏᴛ ᴛʜᴇ ʟɪɴᴋs ᴄᴏᴠᴇʀᴇᴅ. ʏᴏᴜ ᴊᴜsᴛ ᴇɴᴊᴏʏ ʏᴏᴜʀ ᴅᴀʏ!</blockquote>"
    )

def get_about_text() -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗔𝗕𝗢𝗨𝗧 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘</b></blockquote>\n"
        f"<blockquote>◍ ʙʀᴏᴡsᴇ ᴀ ᴍᴀɴᴀɢᴇᴅ ᴄʜᴀɴɴᴇʟ ᴅɪʀᴇᴄᴛᴏʀʏ ᴀɴᴅ ʀᴇᴄᴇɪᴠᴇ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋs. "
        f"ʟɪɴᴋs ᴄᴀɴ ᴇxᴘɪʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.\n\n"
        f"ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ <a href='https://t.me/Karasu_07'>ᴋᴀʀᴀsᴜ</a>.</blockquote>"
    )

def get_help_text() -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘 𝗤𝗨𝗜𝗖𝗞 𝗚𝗨𝗜𝗗𝗘</b></blockquote>\n"
        f"<blockquote>◍ /start — ᴏᴘᴇɴ ʟɪɴᴋsʜᴀʀᴇ\n"
        f"◍ /index — ʙʀᴏᴡsᴇ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ ᴅɪʀᴇᴄᴛᴏʀʏ\n"
        f"◍ /get &lt;ᴛɪᴛʟᴇ&gt; — ғɪɴᴅ ᴀ ᴄʜᴀɴɴᴇʟ\n"
        f"◍ ᴏᴘᴇɴ ᴀ sʜᴀʀᴇᴅ ʟɪɴᴋ ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ.</blockquote>"
    )

def get_directory_text() -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬 🔎</b></blockquote>\n"
        f"<blockquote>◍ ᴜsᴇ /index ᴛᴏ ʙʀᴏᴡsᴇ ᴄʜᴀɴɴᴇʟs ʙʏ ɴᴀᴍᴇ.\n"
        f"ᴏᴘᴇɴ ᴀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ɢᴇᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋ.</blockquote>"
    )

def get_fsub_text() -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗 🔒</b></blockquote>\n"
        f"<blockquote>◍ ᴇʜ? ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ! ᴊᴏɪɴ ᴛʜᴇᴍ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ʏᴏᴜʀ ғɪʟᴇs ɪɴsᴛᴀɴᴛʟʏ~\n\n"
        f"<b>≡ 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗠𝗘𝗡𝗧𝗦 :</b>\n"
        f"◍ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs\n"
        f"◍ ᴄʟɪᴄᴋ <b>ᴛʀʏ ᴀɢᴀɪɴ ↻</b> ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ʏᴏᴜʀ ғɪʟᴇs</blockquote>"
    )

def get_leave_text(channel_title: str) -> str:
    return (
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗘𝗙𝗧 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 ⚠️</b></blockquote>\n"
        f"<blockquote>◍ ʏᴏᴜ ᴊᴜsᴛ ʟᴇғᴛ <b>{channel_title}</b>!\n"
        f"◍ ᴘʟᴇᴀsᴇ ʀᴇᴊᴏɪɴ ᴛᴏ ᴋᴇᴇᴘ ʏᴏᴜʀ ᴀᴄᴄᴇss ᴛᴏ ᴏᴜʀ ʟɪɴᴋs ᴀɴᴅ ғɪʟᴇs ᴀᴄᴛɪᴠᴇ.</blockquote>"
    )

# ─── AUTO COMMANDS REGISTRATION ON VPS STARTUP ─────────────────────────
async def setup_bot_commands(client):
    commands = [
        BotCommand("start", "Open LinkShare"),
        BotCommand("index", "Browse channel directory"),
        BotCommand("get", "Search a channel by name"),
        BotCommand("add_fsub", "Add Force Subscribe channel (Admin)"),
        BotCommand("del_fsub", "Remove Force Subscribe channel (Admin)"),
        BotCommand("fsub_chnl", "View FSub channels list (Admin)"),
        BotCommand("req", "Toggle Request/Direct mode (Admin)"),
        BotCommand("addch", "Add a channel to database (Admin)"),
        BotCommand("delch", "Delete a channel from database (Admin)"),
        BotCommand("links", "View all channel links (Admin)"),
        BotCommand("genlink", "Generate protected link (Admin)"),
        BotCommand("add_admin", "Add a new admin (Owner)"),
        BotCommand("remove_admin", "Remove an admin (Owner)"),
        BotCommand("list_admin", "View all admins (Admin)"),
        BotCommand("status", "Check bot ping, uptime & users (Admin)"),
        BotCommand("broadcast", "Broadcast message to users (Admin)"),
    ]
    try:
        await client.set_bot_commands(commands)
    except Exception as e:
        print(f"Failed to set bot commands: {e}")
