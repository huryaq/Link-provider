import asyncio
import html
import random
import re
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

# Aap yahan direct graph.org / i.ibb.co ya normal ibb.co links daal sakte hain;
# bot ibb.co links ko automatically direct .jpg URL mein convert kar dega!
IMAGES = [
    "https://ibb.co/gMn60D40",
    "https://ibb.co/q36gxXTP",
    "https://ibb.co/MkXjSwkm",
    "https://ibb.co/CS5zPq2",
    "https://graph.org/file/fdb6274d6fcf654b95863-90c4e60858529ba752.jpg",
    "https://graph.org/file/b9b92be3fc206c88b780b-d80a12ea996e96de20.jpg",
    "https://graph.org/file/2eba72bc5cc4470c99b9d-c9e9ceb117d1a498e0.jpg",
    "https://graph.org/file/075e8d47f63f9f45dfb54-1121766c13625f4bc4.jpg",
    "https://graph.org/file/e4d9bee7a78e3f248f3bd-5249020a8b06628278.jpg"
]

_RESOLVED_IMGBB = {}
_LAST_MSG_IMG = {}

WELCOME_VIBES = [
    "ʜᴇʏ, ᴅᴏɴ'ᴛ ᴏᴠᴇʀᴛʜɪɴᴋ ɪᴛ! ɪ'ᴠᴇ ɢᴏᴛ ᴛʜᴇ ʟɪɴᴋs ᴄᴏᴠᴇʀᴇᴅ. ʏᴏᴜ ᴊᴜsᴛ ᴇɴᴊᴏʏ ʏᴏᴜʀ ᴅᴀʏ!",
    "ᴄᴏᴍᴇ ᴏɴ! ʟᴇᴛ's ᴋᴇᴇᴘ ᴛʜɪɴɢs sɪᴍᴘʟᴇ. ᴏɴᴇ ʟɪɴᴋ, ᴏɴᴇ sᴛᴇᴘ ᴀᴛ ᴀ ᴛɪᴍᴇ~",
    "ʏᴏᴜʀ ʟɪɴᴋ sʜᴀʀᴇ ᴀssɪsᴛᴀɴᴛ ɪs ᴏɴʟɪɴᴇ. ғᴀsᴛ, sᴀғᴇ, ᴀɴᴅ ᴀʟᴡᴀʏs ʀᴇᴀᴅʏ!",
    "sᴇᴄᴜʀᴇ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇs, ɪɴsᴛᴀɴᴛ ᴀᴄᴄᴇss. ᴘɪᴄᴋ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ~"
]

def get_preview() -> str:
    return ""

def safe_mention(user) -> str:
    """Bulletproof HTML mention that never breaks Telegram entity parsing"""
    if not user:
        return "<b>ғʀɪᴇɴᴅ</b>"
    name = html.escape(user.first_name or "ᴜsᴇʀ")
    return f'<a href="tg://user?id={user.id}"><b>{name}</b></a>'

def format_count(n: int) -> str:
    if not n:
        return "0"
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)

# ─── AUTO IMGBB DIRECT IMAGE RESOLVER (REMOVES 'hosted at ImgBB' TEXT) ─
async def resolve_direct_image(url: str) -> str:
    if "ibb.co/" not in url or "i.ibb.co/" in url:
        return url
    if url in _RESOLVED_IMGBB:
        return _RESOLVED_IMGBB[url]
    try:
        session = await get_http_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            page_html = await resp.text()
            m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html)
            if m:
                direct = m.group(1)
                _RESOLVED_IMGBB[url] = direct
                return direct
    except Exception:
        pass
    return url

async def pick_clean_image(key=None) -> str:
    prev = _LAST_MSG_IMG.get(key) if key else None
    choices = [u for u in IMAGES if u != prev] or IMAGES
    chosen = random.choice(choices)
    if key:
        _LAST_MSG_IMG[key] = chosen
    return await resolve_direct_image(chosen)

# ─── ULTRA-FAST UNICODE, SMALL-CAPS & FANCY FONT NORMALIZER ────────────
_FANCY_FONT_MAP = str.maketrans({
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ғ": "f",
    "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m",
    "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ǫ": "q", "ꞯ": "q", "ʀ": "r", "s": "s",
    "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "x": "x", "ʏ": "y", "ᴢ": "z",
    "Ꭺ": "a", "Ᏼ": "b", "Ꮯ": "c", "Ꭰ": "d", "Ꭼ": "e", "Ꮐ": "g", "Ꮋ": "h",
    "Ꮖ": "i", "Ꮰ": "j", "Ꮶ": "k", "Ꮮ": "l", "Ꮇ": "m", "Ν": "n", "Ꭴ": "o",
    "Ꮲ": "p", "ℚ": "q", "Ꮢ": "r", "Ꮪ": "s", "Ꭲ": "t", "Ꮜ": "u", "Ꮩ": "v",
    "Ꮃ": "w", "Χ": "x", "Ꭹ": "y", "Ꮓ": "z", "α": "a", "в": "b", "є": "e",
    "ι": "i", "к": "k", "м": "m", "η": "n", "σ": "o", "ρ": "p", "т": "t",
    "υ": "u", "ω": "w", "у": "y", "а": "a", "е": "e", "о": "o", "р": "p",
    "с": "c", "х": "x"
})

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.translate(_FANCY_FONT_MAP)
    text = unicodedata.normalize("NFKD", text)
    chars = [ch.lower() if ch.isalnum() else " " for ch in text]
    return " ".join("".join(chars).split())

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
_LAST_ACTIVE = {}
_LINKED_USER_MSG = {}

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
    _LAST_MSG_IMG.pop(key, None)
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
    auto_delete_sec: int = 120
):
    session = await get_http_session()
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    img_url = await pick_clean_image()

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
                _LAST_MSG_IMG[key] = img_url
                if reply_to_message_id:
                    _LINKED_USER_MSG[key] = reply_to_message_id
                if auto_delete_sec and auto_delete_sec > 0:
                    asyncio.create_task(_inactivity_watcher(chat_id, bot_msg_id, auto_delete_sec))
                return BotApiMessage(chat_id, bot_msg_id, reply_to_message_id)
            else:
                print(f"BotAPI sendMessage error: {data}")
    except Exception as e:
        print(f"BotAPI sendMessage exception: {e}")
    return None

async def reply_ui(message, text: str, reply_markup: InlineKeyboardMarkup = None, auto_delete_sec: int = 120):
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

    chat_id = message.chat.id
    msg_id = message.id
    key = (chat_id, msg_id)
    img_url = await pick_clean_image(key)

    if key in _LAST_ACTIVE:
        _LAST_ACTIVE[key] = time.monotonic()
    else:
        _LAST_ACTIVE[key] = time.monotonic()
        if getattr(message, "reply_to_message", None):
            _LINKED_USER_MSG[key] = message.reply_to_message.id
        asyncio.create_task(_inactivity_watcher(chat_id, msg_id, 120))

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
            else:
                print(f"BotAPI editMessageText error: {data}")
    except Exception as e:
        print(f"BotAPI editMessageText exception: {e}")
    return None

# ─── NEXT-LEVEL AESTHETIC UI TEMPLATES (BOLD SMALL CAPS + GOJO CREDIT) ─
def get_start_text(user_mention: str = "") -> str:
    vibe = random.choice(WELCOME_VIBES)
    greet = f"<b>⟡ ᴡᴇʟᴄᴏᴍᴇ {user_mention} ~</b>\n\n" if user_mention else ""
    return (
        f"<blockquote><b>「 ➲ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘 」</b></blockquote>\n"
        f"<blockquote>{greet}"
        f"<b>◍ {vibe}</b>\n\n"
        f"<b>◈ ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ <a href='https://t.me/urr_sanjiii'>𝗚ᴏᴊᴏ</a></b></blockquote>"
    )

def get_about_text() -> str:
    return (
        f"<blockquote><b>「 ➲ 𝗔𝗕𝗢𝗨𝗧 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘 」</b></blockquote>\n"
        f"<blockquote><b>◍ ʙʀᴏᴡsᴇ ᴀ ᴍᴀɴᴀɢᴇᴅ ᴄʜᴀɴɴᴇʟ ᴅɪʀᴇᴄᴛᴏʀʏ ᴀɴᴅ ʀᴇᴄᴇɪᴠᴇ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋs. "
        f"ʟɪɴᴋs ᴄᴀɴ ᴇxᴘɪʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.</b>\n\n"
        f"<b>⟡ sᴛᴀᴛᴜs:</b> <code>ᴏɴʟɪɴᴇ ⚡</code>\n"
        f"<b>◈ ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ: <a href='https://t.me/urr_sanjiii'>𝗚ᴏᴊᴏ</a></b></blockquote>"
    )

def get_help_text() -> str:
    return (
        f"<blockquote><b>「 ➲ 𝗟𝗜𝗡𝗞𝗦𝗛𝗔𝗥𝗘 𝗤𝗨𝗜𝗖𝗞 𝗚𝗨𝗜𝗗𝗘 」</b></blockquote>\n"
        f"<blockquote><b>▸ <code>/start</code> — ᴏᴘᴇɴ ʟɪɴᴋsʜᴀʀᴇ\n"
        f"▸ <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code> — ғɪɴᴅ ᴀ ᴄʜᴀɴɴᴇʟ\n"
        f"▸ ᴏᴘᴇɴ ᴀɴʏ sʜᴀʀᴇᴅ ʟɪɴᴋ ᴛᴏ ɢᴇᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ.</b>\n\n"
        f"<b>╰┈➤ <i>ᴀʟʟ ʟɪɴᴋs ᴀᴜᴛᴏ-ᴇxᴘɪʀᴇ ғᴏʀ sᴇᴄᴜʀɪᴛʏ.</i></b></blockquote>"
    )

def get_directory_text() -> str:
    return (
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬 🔎 」</b></blockquote>\n"
        f"<blockquote><b>◍ ᴜsᴇ <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code> ᴛᴏ ғɪɴᴅ ᴀɴʏ ᴄʜᴀɴɴᴇʟ ɪɴsᴛᴀɴᴛʟʏ.\n"
        f"◍ ᴏʀ ᴛᴀᴘ 🔥 ᴛʀᴇɴᴅɪɴɢ ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ғᴇᴀᴛᴜʀᴇᴅ ᴄʜᴀɴɴᴇʟs!</b>\n\n"
        f"<b>╰┈➤ <i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/get naruto</code></b></blockquote>"
    )

def get_fsub_text() -> str:
    return (
        f"<blockquote><b>「 ➲ 𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗 🔒 」</b></blockquote>\n"
        f"<blockquote><b>◍ ᴇʜ? ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ! ᴊᴏɪɴ ᴛʜᴇᴍ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ʏᴏᴜʀ ғɪʟᴇs ɪɴsᴛᴀɴᴛʟʏ~</b>\n\n"
        f"<b>≡ 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗠𝗘𝗡𝗧𝗦 :</b>\n"
        f"<b>▸ ᴊᴏɪɴ ᴀʟʟ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs\n"
        f"▸ ᴄʟɪᴄᴋ ᴛʀʏ ᴀɢᴀɪɴ ↻ ᴛᴏ ʀᴇᴄᴇɪᴠᴇ ʏᴏᴜʀ ғɪʟᴇs</b></blockquote>"
    )

def get_leave_text(channel_title: str) -> str:
    return (
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗘𝗙𝗧 ⚠️ 」</b></blockquote>\n"
        f"<blockquote><b>◍ ʏᴏᴜ ᴊᴜsᴛ ʟᴇғᴛ {html.escape(channel_title)}!\n"
        f"◍ ᴘʟᴇᴀsᴇ ʀᴇᴊᴏɪɴ ᴛᴏ ᴋᴇᴇᴘ ʏᴏᴜʀ ᴀᴄᴄᴇss ᴛᴏ ᴏᴜʀ ʟɪɴᴋs ᴀɴᴅ ғɪʟᴇs ᴀᴄᴛɪᴠᴇ.</b></blockquote>"
    )

# ─── AUTO COMMANDS (SHORT SMALL CAPS & /get AT THE VERY BOTTOM) ────────
async def setup_bot_commands(client):
    commands = [
        BotCommand("start", "ᴏᴘᴇɴ ʟɪɴᴋsʜᴀʀᴇ"),
        BotCommand("panel", "ᴀᴅᴍɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ"),
        BotCommand("add_trend", "ᴀᴅᴅ ᴛᴏ ᴛʀᴇɴᴅɪɴɢ"),
        BotCommand("del_trend", "ʀᴇᴍᴏᴠᴇ ғʀᴏᴍ ᴛʀᴇɴᴅɪɴɢ"),
        BotCommand("list_trend", "ᴠɪᴇᴡ ᴛʀᴇɴᴅɪɴɢ ʟɪsᴛ"),
        BotCommand("add_fsub", "ᴀᴅᴅ ғsᴜʙ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("del_fsub", "ʀᴇᴍᴏᴠᴇ ғsᴜʙ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("fsub_chnl", "ᴠɪᴇᴡ ғsᴜʙ ʟɪsᴛ"),
        BotCommand("req", "ᴛᴏɢɢʟᴇ ғsᴜʙ ᴍᴏᴅᴇ"),
        BotCommand("addch", "ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("delch", "ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("hidech", "ʜɪᴅᴇ ғʀᴏᴍ /ɢᴇᴛ"),
        BotCommand("unhidech", "sʜᴏᴡ ɪɴ /ɢᴇᴛ"),
        BotCommand("hiddench", "ᴠɪᴇᴡ ʜɪᴅᴅᴇɴ ʟɪsᴛ"),
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
