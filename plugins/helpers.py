import asyncio
import random
import time
import unicodedata
import aiohttp
from config import TG_BOT_TOKEN
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
    return ""

# ─── ULTRA-FAST UNICODE & SMALL-CAPS NORMALIZER ────────────────────────
_SMALL_CAPS_MAP = str.maketrans({
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ғ": "f",
    "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m",
    "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ǫ": "q", "ꞯ": "q", "ʀ": "r", "s": "s",
    "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "x": "x", "ʏ": "y", "ᴢ": "z"
})

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.translate(_SMALL_CAPS_MAP)
    text = unicodedata.normalize("NFKD", text)
    clean = "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace())
    return " ".join(clean.split())

# ─── COLORED BUTTON BUILDER (PRIMARY / DANGER / SUCCESS) ───────────────
def sbtn(text: str, callback_data: str = None, url: str = None, style: str = None) -> InlineKeyboardButton:
    btn = InlineKeyboardButton(text=text, callback_data=callback_data, url=url)
    btn._style = style
    return btn

def serialize_markup(markup: InlineKeyboardMarkup) -> dict:
    if not markup or not getattr(markup, "inline_keyboard", None):
        return None
    keyboard = []
    for row in markup.inline_keyboard:
        row_list = []
        for btn in row:
            b_dict = {"text": btn.text}
            if getattr(btn, "callback_data", None):
                b_dict["callback_data"] = btn.callback_data
            if getattr(btn, "url", None):
                b_dict["url"] = btn.url
            if getattr(btn, "_style", None):
                b_dict["style"] = btn._style
            row_list.append(b_dict)
        if row_list:
            keyboard.append(row_list)
    return {"inline_keyboard": keyboard}

# ─── HIGH-CONCURRENCY HTTP POOL & INACTIVITY AUTO-DELETE TRACKER ───────
_http_session = None
_LAST_ACTIVE = {}       # (chat_id, bot_msg_id) -> monotonic timestamp
_LINKED_USER_MSG = {}   # (chat_id, bot_msg_id) -> user_cmd_msg_id

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        connector = aiohttp.TCPConnector(limit=150, ttl_dns_cache=600, keepalive_timeout=60)
        timeout = aiohttp.ClientTimeout(total=10)
        _http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _http_session

async def api_delete_msg(chat_id: int, message_id: int):
    if not chat_id or not message_id:
        return
    session = await get_http_session()
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/deleteMessage"
    try:
        async with session.post(url, json={"chat_id": chat_id, "message_id": message_id}) as resp:
            await resp.read()
    except Exception:
        pass

async def delete_bot_and_user_msg(chat_id: int, bot_msg_id: int, fallback_user_msg_id: int = None):
    key = (chat_id, bot_msg_id)
    _LAST_ACTIVE.pop(key, None)
    user_msg_id = _LINKED_USER_MSG.pop(key, None) or fallback_user_msg_id
    await api_delete_msg(chat_id, bot_msg_id)
    if user_msg_id:
        await api_delete_msg(chat_id, user_msg_id)

async def _inactivity_watcher(chat_id: int, bot_msg_id: int, timeout_sec: int):
    key = (chat_id, bot_msg_id)
    while True:
        last_t = _LAST_ACTIVE.get(key)
        if last_t is None:
            return
        elapsed = time.monotonic() - last_t
        if elapsed >= timeout_sec:
            await delete_bot_and_user_msg(chat_id, bot_msg_id)
            return
        await asyncio.sleep(max(1.0, timeout_sec - elapsed))

class _ChatRef:
    def __init__(self, chat_id: int):
        self.id = chat_id

class BotApiMessage:
    def __init__(self, chat_id: int, message_id: int, user_msg_id: int = None):
        self.chat = _ChatRef(chat_id)
        self.id = message_id
        self.user_msg_id = user_msg_id

    async def delete(self):
        await delete_bot_and_user_msg(self.chat.id, self.id, self.user_msg_id)

async def send_ui(
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    reply_to_message_id: int = None,
    auto_delete_sec: int = 180
):
    session = await get_http_session()
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    img_url = random.choice(IMAGES)

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {
            "url": img_url,
            "prefer_large_media": True,
            "show_above_text": True
        }
    }
    if reply_to_message_id:
        payload["reply_parameters"] = {
            "message_id": reply_to_message_id,
            "allow_sending_without_reply": True
        }
    serialized_kb = serialize_markup(reply_markup)
    if serialized_kb:
        payload["reply_markup"] = serialized_kb

    try:
        async with session.post(api_url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                bot_msg_id = data["result"]["message_id"]
                key = (chat_id, bot_msg_id)
                _LAST_ACTIVE[key] = time.monotonic()
                if reply_to_message_id:
                    _LINKED_USER_MSG[key] = reply_to_message_id
                if auto_delete_sec and auto_delete_sec > 0:
                    asyncio.create_task(_inactivity_watcher(chat_id, bot_msg_id, auto_delete_sec))
                return BotApiMessage(chat_id, bot_msg_id, reply_to_message_id)
    except Exception as e:
        print(f"BotAPI sendMessage exception: {e}")
    return None

async def reply_ui(message, text: str, reply_markup: InlineKeyboardMarkup = None, auto_delete_sec: int = 180):
    chat_id = message.chat.id
    reply_id = None
    if getattr(message, "from_user", None) and not getattr(message.from_user, "is_self", False):
        reply_id = message.id
    elif getattr(message, "reply_to_message", None):
        reply_id = message.reply_to_message.id

    res = await send_ui(
        chat_id,
        text,
        reply_markup=reply_markup,
        reply_to_message_id=reply_id,
        auto_delete_sec=auto_delete_sec
    )
    if res:
        return res
    return await message.reply_text(text, reply_markup=reply_markup)

async def edit_ui(message, text: str, reply_markup: InlineKeyboardMarkup = None):
    session = await get_http_session()
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
    img_url = random.choice(IMAGES)

    chat_id = message.chat.id
    msg_id = message.id
    key = (chat_id, msg_id)

    # Refresh inactivity timer on button click!
    if key in _LAST_ACTIVE:
        _LAST_ACTIVE[key] = time.monotonic()
    else:
        _LAST_ACTIVE[key] = time.monotonic()
        if getattr(message, "reply_to_message", None):
            _LINKED_USER_MSG[key] = message.reply_to_message.id
        asyncio.create_task(_inactivity_watcher(chat_id, msg_id, 180))

    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {
            "url": img_url,
            "prefer_large_media": True,
            "show_above_text": True
        }
    }
    serialized_kb = serialize_markup(reply_markup)
    if serialized_kb:
        payload["reply_markup"] = serialized_kb

    try:
        async with session.post(api_url, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                return BotApiMessage(chat_id, msg_id, _LINKED_USER_MSG.get(key))
    except Exception as e:
        print(f"BotAPI editMessageText exception: {e}")
    return None

# ─── UI MESSAGE TEMPLATES ──────────────────────────────────────────────
def get_start_text() -> str:
    return (
        f"<blockquote><b>➲ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘</b></blockquote>\n"
        f"<blockquote>ʜᴇʏ, ᴅᴏɴ'ᴛ ᴏᴠᴇʀᴛʜɪɴᴋ ɪᴛ! ɪ'ᴠᴇ ɢᴏᴛ ᴛʜᴇ ʟɪɴᴋs ᴄᴏᴠᴇʀᴇᴅ. ʏᴏᴜ ᴊᴜsᴛ ᴇɴᴊᴏʏ ʏᴏᴜʀ ᴅᴀʏ!</blockquote>"
    )

def get_about_text() -> str:
    return (
        f"<blockquote><b>➲ 𝗔𝗕𝗢𝗨𝗧 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘</b></blockquote>\n"
        f"<blockquote>◍ ʙʀᴏᴡsᴇ ᴀ ᴍᴀɴᴀɢᴇᴅ ᴄʜᴀɴɴᴇʟ ᴅɪʀᴇᴄᴛᴏʀʏ ᴀɴᴅ ʀᴇᴄᴇɪᴠᴇ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋs. "
        f"ʟɪɴᴋs ᴄᴀɴ ᴇxᴘɪʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.\n\n"
        f"ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ <a href='https://t.me/Karasu_07'>ᴋᴀʀᴀsᴜ</a>.</blockquote>"
    )

def get_help_text() -> str:
    return (
        f"<blockquote><b>➲ 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘 𝗤𝗨𝗜𝗖𝗞 𝗚𝗨𝗜𝗗𝗘</b></blockquote>\n"
        f"<blockquote>◍ /start — ᴏᴘᴇɴ ʟɪɴᴋsʜᴀʀᴇ\n"
        f"◍ /get &lt;ᴛɪᴛʟᴇ&gt; — ғɪɴᴅ ᴀ ᴄʜᴀɴɴᴇʟ\n"
        f"◍ ᴏᴘᴇɴ ᴀ sʜᴀʀᴇᴅ ʟɪɴᴋ ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ.</blockquote>"
    )

def get_directory_text() -> str:
    return (
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬 🔎</b></blockquote>\n"
        f"<blockquote>◍ ᴜsᴇ <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code> ᴛᴏ ғɪɴᴅ ᴀɴʏ ᴄʜᴀɴɴᴇʟ ʙʏ ɴᴀᴍᴇ.\n"
        f"◍ ᴇxᴀᴍᴘʟᴇ: <code>/get naruto</code></blockquote>"
    )

def get_fsub_text() -> str:
    return (
        f"<blockquote><b>➲ 𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗 🔒</b></blockquote>\n"
        f"<blockquote>◍ ᴇʜ? ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ! ᴊᴏɪɴ ᴛʜᴇᴍ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ʏᴏᴜʀ ғɪʟᴇs ɪɴsᴛᴀɴᴛʟʏ~\n\n"
        f"<b>≡ 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗠𝗘𝗡𝗧𝗦 :</b>\n"
        f"◍ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs\n"
        f"◍ ᴄʟɪᴄᴋ <b>ᴛʀʏ ᴀɢᴀɪɴ ↻</b> ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ʏᴏᴜʀ ғɪʟᴇs</blockquote>"
    )

def get_leave_text(channel_title: str) -> str:
    return (
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗘𝗙𝗧 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 ⚠️</b></blockquote>\n"
        f"<blockquote>◍ ʏᴏᴜ ᴊᴜsᴛ ʟᴇғᴛ <b>{channel_title}</b>!\n"
        f"◍ ᴘʟᴇᴀsᴇ ʀᴇᴊᴏɪɴ ᴛᴏ ᴋᴇᴇᴘ ʏᴏᴜʀ ᴀᴄᴄᴇss ᴛᴏ ᴏᴜʀ ʟɪɴᴋs ᴀɴᴅ ғɪʟᴇs ᴀᴄᴛɪᴠᴇ.</blockquote>"
    )

# ─── AUTO COMMANDS (SMALL CAPS & /get AT THE VERY BOTTOM) ──────────────
async def setup_bot_commands(client):
    commands = [
        BotCommand("start", "ᴏᴘᴇɴ ʟɪɴᴋsʜᴀʀᴇ"),
        BotCommand("add_fsub", "ᴀᴅᴅ ғsᴜʙ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("del_fsub", "ʀᴇᴍᴏᴠᴇ ғsᴜʙ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("fsub_chnl", "ᴠɪᴇᴡ ғsᴜʙ ʟɪsᴛ"),
        BotCommand("req", "ᴛᴏɢɢʟᴇ ғsᴜʙ ᴍᴏᴅᴇ"),
        BotCommand("addch", "ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("delch", "ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("links", "ᴀʟʟ ᴄʜᴀɴɴᴇʟ ʟɪɴᴋs"),
        BotCommand("genlink", "ᴘʀᴏᴛᴇᴄᴛ ᴀ ʟɪɴᴋ"),
        BotCommand("add_admin", "ᴀᴅᴅ ᴀᴅᴍɪɴ"),
        BotCommand("remove_admin", "ʀᴇᴍᴏᴠᴇ ᴀᴅᴍɪɴ"),
        BotCommand("list_admin", "ᴀᴅᴍɪɴ ʟɪsᴛ"),
        BotCommand("status", "ʙᴏᴛ sᴛᴀᴛᴜs"),
        BotCommand("broadcast", "ʙʀᴏᴀᴅᴄᴀsᴛ ᴍsɢ"),
        BotCommand("get", "ғɪɴᴅ ᴄʜᴀɴɴᴇʟ"),
    ]
    try:
        await client.set_bot_commands(commands)
    except Exception as e:
        print(f"Failed to set bot commands: {e}")
