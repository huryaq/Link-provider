import asyncio
import random
import time
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.types import (
    Message, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
)
from pyrogram.errors import (
    UserNotParticipant, FloodWait, UserIsBlocked, InputUserDeactivated
)

from bot import Bot
from config import OWNER_ID
from database.database import (
    add_user, total_users_count, full_userbase, del_user,
    is_admin, add_admin, remove_admin, list_admins,
    add_fsub_channel, remove_fsub_channel, get_fsub_channels,
    get_channel_by_encoded_link, get_channel_by_encoded_link2,
    get_original_link, get_fsub_mode, set_fsub_mode,
    save_encoded_link, save_encoded_link2,
    increment_channel_clicks, get_top_channels, get_hidden_channels
)
from helper_func import get_readable_time
from plugins.helpers import (
    STICKERS, sbtn, reply_ui, edit_ui, send_ui,
    delete_bot_and_user_msg, format_count,
    get_start_text, get_about_text, get_help_text,
    get_directory_text, get_fsub_text, get_leave_text
)
from plugins.newpost import _CHANNEL_INDEX, update_ram_index

cancel_lock = asyncio.Lock()
is_canceled = False

# ─── HIGH-CONCURRENCY RAM CACHES (KOYEB FREE TIER 5K-10K USERS) ─────────
_FSUB_LIST_CACHE = {"channels": None, "mode": "request", "ts": 0.0}
_FSUB_INVITE_CACHE = {}     # (ch_id, mode) -> (invite_url, ts)
_BURST_INVITE_CACHE = {}    # (ch_id, is_req) -> (invite_url, title, members_count, actual_is_req, ts)

def invalidate_fsub_cache():
    _FSUB_LIST_CACHE["channels"] = None
    _FSUB_LIST_CACHE["ts"] = 0.0
    _FSUB_INVITE_CACHE.clear()

async def get_cached_fsub_config():
    now = time.monotonic()
    if _FSUB_LIST_CACHE["channels"] is not None and (now - _FSUB_LIST_CACHE["ts"]) < 120:
        return _FSUB_LIST_CACHE["channels"], _FSUB_LIST_CACHE["mode"]
    ch_list = await get_fsub_channels()
    mode = await get_fsub_mode()
    _FSUB_LIST_CACHE["channels"] = ch_list
    _FSUB_LIST_CACHE["mode"] = mode
    _FSUB_LIST_CACHE["ts"] = now
    return ch_list, mode

# ─── MAIN START MENU KEYBOARD ───────────────────────────────────────────
def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            sbtn("◈ ᴀʙᴏᴜᴛ", callback_data="about", style="primary"),
            sbtn("🔎 ᴅɪʀᴇᴄᴛᴏʀʏ", callback_data="directory", style="primary")
        ],
        [
            sbtn("🔥 ᴛʀᴇɴᴅɪɴɢ", callback_data="trending", style="success"),
            sbtn("? ʜᴇʟᴘ", callback_data="help", style="primary")
        ],
        [
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]
    ])

def get_panel_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            sbtn("⚡ sʏsᴛᴇᴍ sᴛᴀᴛᴜs", callback_data="panel_status", style="primary"),
            sbtn(f"↻ ᴍᴏᴅᴇ: {mode.upper()}", callback_data="panel_toggle_req", style="success")
        ],
        [
            sbtn("🔒 ғsᴜʙ ʟɪsᴛ", callback_data="panel_fsub", style="primary"),
            sbtn("🙈 ʜɪᴅᴅᴇɴ ᴄʜ", callback_data="panel_hidden", style="primary")
        ],
        [
            sbtn("👑 ᴀᴅᴍɪɴs", callback_data="panel_admins", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]
    ])

# ─── PARALLEL FSUB VERIFICATION & CACHED KEYBOARD ───────────────────────
async def _check_single_channel(client: Bot, ch_id: int, user_id: int):
    try:
        member = await client.get_chat_member(ch_id, user_id)
        if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]:
            return ch_id
    except UserNotParticipant:
        return ch_id
    except Exception:
        pass
    return None

async def check_user_fsub(client: Bot, user_id: int):
    fsub_channels, _ = await get_cached_fsub_config()
    if not fsub_channels:
        return True, []
    results = await asyncio.gather(*[
        _check_single_channel(client, ch_id, user_id) for ch_id in fsub_channels
    ])
    unjoined = [ch for ch in results if ch is not None]
    return (len(unjoined) == 0), unjoined

async def build_fsub_keyboard(client: Bot, unjoined_channels: list, payload: str = "") -> InlineKeyboardMarkup:
    keyboard = []
    _, mode = await get_cached_fsub_config()
    btn_label = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if mode == "request" else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"
    now = time.monotonic()

    row = []
    for ch_id in unjoined_channels:
        cache_key = (ch_id, mode)
        cached = _FSUB_INVITE_CACHE.get(cache_key)
        if cached and (now - cached[1]) < 1800:
            inv_url = cached[0]
        else:
            try:
                try:
                    link_obj = await client.create_chat_invite_link(
                        chat_id=ch_id,
                        creates_join_request=(mode == "request")
                    )
                    inv_url = link_obj.invite_link
                except Exception:
                    link_obj = await client.create_chat_invite_link(
                        chat_id=ch_id,
                        creates_join_request=False
                    )
                    inv_url = link_obj.invite_link
                _FSUB_INVITE_CACHE[cache_key] = (inv_url, now)
            except Exception:
                continue

        row.append(sbtn(btn_label, url=inv_url, style="primary"))
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    retry_cb = f"check_sub_{payload}" if payload else "check_sub"
    keyboard.append([
        sbtn("↻ ᴛʀʏ ᴀɢᴀɪɴ ↻", callback_data=retry_cb, style="success"),
        sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
    ])
    return InlineKeyboardMarkup(keyboard)

# ─── /start COMMAND HANDLER ─────────────────────────────────────────────
@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Bot, message: Message):
    user_id = message.from_user.id
    asyncio.create_task(add_user(user_id))
    asyncio.create_task(_safe_react(message))

    try:
        stk = await message.reply_sticker(random.choice(STICKERS))
        await asyncio.sleep(0.9)
        asyncio.create_task(_safe_delete(stk))
    except Exception:
        pass

    text = message.text or ""
    payload = text.split(" ", 1)[1].strip() if len(text.split()) > 1 else ""

    check_msg_task = asyncio.create_task(
        message.reply_text("<blockquote>◍ ᴄʜᴇᴄᴋɪɴɢ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs...</blockquote>", parse_mode=ParseMode.HTML)
    )
    fsub_task = asyncio.create_task(check_user_fsub(client, user_id))

    is_joined, unjoined = await fsub_task
    try:
        check_msg = await check_msg_task
        asyncio.create_task(_safe_delete(check_msg))
    except Exception:
        pass

    if not is_joined:
        fsub_markup = await build_fsub_keyboard(client, unjoined, payload)
        return await reply_ui(message, get_fsub_text(), reply_markup=fsub_markup, auto_delete_sec=120)

    if payload:
        return await deliver_channel_link(client, message, payload)

    await reply_ui(
        message,
        get_start_text(message.from_user.mention),
        reply_markup=get_main_keyboard(),
        auto_delete_sec=120
    )

async def _safe_react(message: Message):
    try:
        await message.react("⚡")
    except Exception:
        pass

async def _safe_delete(msg):
    try:
        await msg.delete()
    except Exception:
        pass

# ─── LINK GENERATOR & DELIVERY (WITH LIVE SUBS COUNT + BURST CACHE) ────
async def deliver_channel_link(client: Bot, message: Message, payload: str, force_new: bool = False):
    is_request = payload.startswith("req_")
    clean_code = payload[4:].strip() if is_request else payload.strip()

    if is_request:
        channel_id = await get_channel_by_encoded_link2(clean_code) or await get_channel_by_encoded_link(clean_code)
    else:
        channel_id = await get_channel_by_encoded_link(clean_code) or await get_channel_by_encoded_link2(clean_code)

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if not channel_id:
        return await reply_ui(
            message,
            "<blockquote><b>「 ❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗢𝗥 𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗟𝗜𝗡𝗞 」</b></blockquote>\n"
            "<blockquote>◍ ᴛʜɪs ʟɪɴᴋ ɪs ɪɴᴠᴀʟɪᴅ ᴏʀ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴄᴛɪᴠᴇ.</blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

    original_link = await get_original_link(channel_id)
    if original_link:
        markup = InlineKeyboardMarkup([
            [sbtn("➪ ᴏᴘᴇɴ ʟɪɴᴋ", url=original_link, style="success")],
            [sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]
        ])
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗟𝗜𝗡𝗞 𝗨𝗡𝗟𝗢𝗖𝗞𝗘𝗗 ⚡ 」</b></blockquote>\n"
            "<blockquote>◍ ʏᴏᴜʀ ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʟɪɴᴋ ɪs ʀᴇᴀᴅʏ.\n"
            "╰┈➤ <i>ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴘʀᴏᴄᴇᴇᴅ.</i></blockquote>",
            reply_markup=markup,
            auto_delete_sec=300
        )

    try:
        asyncio.create_task(increment_channel_clicks(channel_id))
        now_mono = time.monotonic()
        burst_key = (channel_id, is_request)
        cached_burst = _BURST_INVITE_CACHE.get(burst_key)

        if not force_new and cached_burst and (now_mono - cached_burst[4]) < 15:
            inv_url, title, members_count, actual_is_req = cached_burst[0], cached_burst[1], cached_burst[2], cached_burst[3]
        else:
            chat = await client.get_chat(channel_id)
            title = chat.title
            members_count = getattr(chat, "members_count", 0) or 0

            expire_time = datetime.now(timezone.utc) + timedelta(minutes=5)
            actual_is_req = is_request
            try:
                invite = await client.create_chat_invite_link(
                    chat_id=channel_id,
                    expire_date=expire_time,
                    creates_join_request=is_request
                )
            except Exception:
                invite = await client.create_chat_invite_link(
                    chat_id=channel_id,
                    expire_date=expire_time,
                    creates_join_request=False
                )
                actual_is_req = False

            inv_url = invite.invite_link
            _BURST_INVITE_CACHE[burst_key] = (inv_url, title, members_count, actual_is_req, now_mono)

        join_label = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if actual_is_req else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"
        subs_line = f"◍ ᴍᴇᴍʙᴇʀs: <code>{format_count(members_count)}</code>\n" if members_count else ""

        markup = InlineKeyboardMarkup([
            [sbtn(join_label, url=inv_url, style="success")],
            [
                sbtn("↻ ʀᴇʟᴏᴀᴅ", callback_data=f"reload_{payload}", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])

        await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗧𝗘𝗠𝗣𝗢𝗥𝗔𝗥𝗬 𝗜𝗡𝗩𝗜𝗧𝗘 𝗥𝗘𝗔𝗗𝗬 ⚡ 」</b></blockquote>\n"
            f"<blockquote>▸ <b>{title}</b>\n"
            f"{subs_line}"
            f"◍ ᴇxᴘɪʀᴇs ɪɴ: <code>5 ᴍɪɴᴜᴛᴇs</code>\n"
            f"◍ ᴍᴏᴅᴇ: <code>{'ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ' if actual_is_req else 'ᴅɪʀᴇᴄᴛ ᴊᴏɪɴ'}</code>\n\n"
            f"╰┈➤ <i>ɪғ ᴇxᴘɪʀᴇᴅ, ᴛᴀᴘ ʀᴇʟᴏᴀᴅ ғᴏʀ ᴀ ғʀᴇsʜ ʟɪɴᴋ.</i></blockquote>",
            reply_markup=markup,
            auto_delete_sec=300
        )

    except Exception as e:
        print(f"Invite creation error for {channel_id}: {e}")
        await reply_ui(
            message,
            "<blockquote><b>「 ❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗢𝗥 𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗟𝗜𝗡𝗞 」</b></blockquote>\n"
            "<blockquote>◍ ᴜɴᴀʙʟᴇ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ɪɴᴠɪᴛᴇ ʟɪɴᴋ. ʙᴏᴛ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ.</blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

# ─── CHANNEL LEAVE WARNING DETECTOR ─────────────────────────────────────
@Bot.on_chat_member_updated()
async def fsub_leave_alert(client: Bot, update: ChatMemberUpdated):
    if not update.old_chat_member or not update.new_chat_member:
        return
    old_s = update.old_chat_member.status
    new_s = update.new_chat_member.status
    if old_s in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and new_s == ChatMemberStatus.LEFT:
        fsub_channels, mode = await get_cached_fsub_config()
        if update.chat.id in fsub_channels:
            user = update.from_user
            if not user or user.is_bot:
                return
            try:
                cache_key = (update.chat.id, mode)
                cached = _FSUB_INVITE_CACHE.get(cache_key)
                if cached and (time.monotonic() - cached[1]) < 1800:
                    inv_url = cached[0]
                else:
                    try:
                        inv = await client.create_chat_invite_link(
                            chat_id=update.chat.id,
                            creates_join_request=(mode == "request")
                        )
                    except Exception:
                        inv = await client.create_chat_invite_link(
                            chat_id=update.chat.id,
                            creates_join_request=False
                        )
                    inv_url = inv.invite_link
                    _FSUB_INVITE_CACHE[cache_key] = (inv_url, time.monotonic())

                btn = InlineKeyboardMarkup([
                    [sbtn("• ʀᴇᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=inv_url, style="success")],
                    [sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]
                ])
                await send_ui(
                    chat_id=user.id,
                    text=get_leave_text(update.chat.title),
                    reply_markup=btn,
                    auto_delete_sec=300
                )
            except Exception:
                pass

# ─── ADMIN CONTROL PANEL (/panel) ───────────────────────────────────────
@Bot.on_message(filters.command("panel") & filters.private)
async def admin_panel_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    _, mode = await get_cached_fsub_config()
    await reply_ui(
        message,
        "<blockquote><b>「 ⚙ 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗣𝗔𝗡𝗘𝗟 」</b></blockquote>\n"
        "<blockquote>◍ ᴍᴀɴᴀɢᴇ ғsᴜʙ, ʜɪᴅᴅᴇɴ ᴄʜᴀɴɴᴇʟs, ᴀᴅᴍɪɴs &amp; ʟɪᴠᴇ sᴛᴀᴛs ғʀᴏᴍ ᴏɴᴇ ᴘʟᴀᴄᴇ.\n"
        "╰┈➤ <i>sᴇʟᴇᴄᴛ ᴀ ᴄᴏɴᴛʀᴏʟ ʙᴇʟᴏᴡ:</i></blockquote>",
        reply_markup=get_panel_keyboard(mode),
        auto_delete_sec=180
    )

# ─── FSUB COMMANDS (/add_fsub, /del_fsub, /fsub_chnl, /req) ─────────────
@Bot.on_message(filters.command("add_fsub") & filters.private)
async def add_fsub_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗔𝗗𝗗 𝗙𝗦𝗨𝗕 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/add_fsub -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )
    try:
        channel_id = int(message.command[1])
        chat = await client.get_chat(channel_id)
        channel_name = chat.title
    except Exception:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n"
            "<blockquote>◍ ɪɴᴠᴀʟɪᴅ ɪᴅ ᴏʀ ʙᴏᴛ ɪs ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ/ɢʀᴏᴜᴘ!</blockquote>",
            reply_markup=close_btn
        )
    await add_fsub_channel(channel_id)
    invalidate_fsub_cache()
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗙𝗦𝗨𝗕 𝗔𝗗𝗗𝗘𝗗 」</b></blockquote>\n"
        f"<blockquote>▸ <b>{channel_name}</b>\n"
        f"◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("del_fsub") & filters.private)
async def del_fsub_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗙𝗦𝗨𝗕 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/del_fsub -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )
    try:
        channel_id = int(message.command[1])
        chat = await client.get_chat(channel_id)
        channel_name = chat.title
    except Exception:
        channel_id = int(message.command[1]) if message.command[1].lstrip("-").isdigit() else 0
        channel_name = "Removed Channel"

    removed = await remove_fsub_channel(channel_id)
    invalidate_fsub_cache()
    if not removed:
        return await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗 ❌ 」</b></blockquote>\n"
            f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code> ɪs ɴᴏᴛ ɪɴ ғsᴜʙ ʟɪsᴛ.</blockquote>",
            reply_markup=close_btn
        )
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗙𝗦𝗨𝗕 𝗥𝗘𝗠𝗢𝗩𝗘𝗗 」</b></blockquote>\n"
        f"<blockquote>▸ <b>{channel_name}</b>\n"
        f"◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("fsub_chnl") & filters.private)
async def list_fsub_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await get_fsub_channels()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if not channels:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ғsᴜʙ ᴄʜᴀɴɴᴇʟs ᴏʀ ɢʀᴏᴜᴘs ᴀᴅᴅᴇᴅ ʏᴇᴛ.</blockquote>",
            reply_markup=close_btn
        )
    text = "<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            title = chat.title
        except Exception:
            title = "Unknown Channel/Group"
        text += f"<blockquote>▸ <b>{title}</b>\nɪᴅ: <code>{ch_id}</code></blockquote>\n"
    await reply_ui(message, text.strip(), reply_markup=close_btn)

@Bot.on_message(filters.command("req") & filters.private)
async def toggle_fsub_mode_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    current = await get_fsub_mode()
    new_mode = "direct" if current == "request" else "request"
    await set_fsub_mode(new_mode)
    invalidate_fsub_cache()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗙𝗦𝗨𝗕 𝗠𝗢𝗗𝗘 𝗨𝗣𝗗𝗔𝗧𝗘𝗗 ⚡ 」</b></blockquote>\n"
        f"<blockquote>◍ ᴍᴏᴅᴇ: <code>{new_mode.upper()}</code>\n"
        f"◍ ʙᴜᴛᴛᴏɴ: <code>{'• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •' if new_mode == 'request' else '• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •'}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── FIXED ADMIN MANAGEMENT (/add_admin, /remove_admin, /list_admin) ───
@Bot.on_message(filters.command("add_admin") & filters.private)
async def add_admin_handler(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    adm_id = None
    if len(message.command) >= 2 and message.command[1].isdigit():
        adm_id = int(message.command[1])
    elif message.reply_to_message and message.reply_to_message.from_user:
        adm_id = message.reply_to_message.from_user.id

    if not adm_id:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗔𝗗𝗗 𝗔𝗗𝗠𝗜𝗡 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/add_admin &lt;user_id&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    await add_admin(adm_id)
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗔𝗗𝗠𝗜𝗡 𝗔𝗗𝗗𝗘𝗗 ⚡ 」</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{adm_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("remove_admin") & filters.private)
async def remove_admin_handler(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    adm_id = None
    if len(message.command) >= 2 and message.command[1].isdigit():
        adm_id = int(message.command[1])
    elif message.reply_to_message and message.reply_to_message.from_user:
        adm_id = message.reply_to_message.from_user.id

    if not adm_id:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗔𝗗𝗠𝗜𝗡 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/remove_admin &lt;user_id&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    if adm_id == OWNER_ID:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗔𝗖𝗧𝗜𝗢𝗡 𝗗𝗘𝗡𝗜𝗘𝗗 ❌ 」</b></blockquote>\n"
            "<blockquote>◍ ʏᴏᴜ ᴄᴀɴɴᴏᴛ ʀᴇᴍᴏᴠᴇ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ!</blockquote>",
            reply_markup=close_btn
        )

    removed = await remove_admin(adm_id)
    if not removed:
        return await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗡𝗢𝗧 𝗔𝗡 𝗔𝗗𝗠𝗜𝗡 ❌ 」</b></blockquote>\n"
            f"<blockquote>◍ ɪᴅ: <code>{adm_id}</code> ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ ᴀᴅᴍɪɴ ʟɪsᴛ.</blockquote>",
            reply_markup=close_btn
        )

    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗔𝗗𝗠𝗜𝗡 𝗥𝗘𝗠𝗢𝗩𝗘𝗗 ⚡ 」</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{adm_id}</code>\n"
        f"╰┈➤ <i>ᴘᴇʀᴍᴀɴᴇɴᴛʟʏ ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴀᴅᴍɪɴs.</i></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("list_admin") & filters.private)
async def list_admin_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    admins = await list_admins()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    text = "<blockquote><b>「 ➲ 𝗔𝗗𝗠𝗜𝗡𝗦 𝗟𝗜𝗦𝗧 」</b></blockquote>\n"
    for adm_id in admins:
        role = "ᴏᴡɴᴇʀ 👑" if adm_id == OWNER_ID else "ᴀᴅᴍɪɴ"
        text += f"<blockquote>▸ {role}\nɪᴅ: <code>{adm_id}</code></blockquote>\n"
    await reply_ui(message, text.strip(), reply_markup=close_btn)

# ─── STATUS & BROADCAST ─────────────────────────────────────────────────
@Bot.on_message(filters.command('status') & filters.private)
async def status_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    start_t = time.time()
    temp = await reply_ui(message, "<blockquote>◍ ᴄʜᴇᴄᴋɪɴɢ sʏsᴛᴇᴍ sᴛᴀᴛᴜs...</blockquote>")
    ping_ms = (time.time() - start_t) * 1000
    total_users = await total_users_count()
    delta = datetime.now() - client.uptime
    uptime_str = get_readable_time(delta.seconds)
    await edit_ui(
        temp,
        f"<blockquote><b>「 ➲ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 ⚡ 」</b></blockquote>\n"
        f"<blockquote>◍ <b>ᴜsᴇʀs:</b> <code>{total_users}</code>\n"
        f"◍ <b>ɪɴᴅᴇxᴇᴅ ᴄʜ:</b> <code>{len(_CHANNEL_INDEX)}</code>\n"
        f"◍ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{uptime_str}</code>\n"
        f"◍ <b>ᴘɪɴɢ:</b> <code>{ping_ms:.2f} ᴍs</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command('cancel') & filters.private)
async def cancel_broadcast(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    global is_canceled
    async with cancel_lock:
        is_canceled = True

@Bot.on_message(filters.private & filters.command('broadcast'))
async def broadcast_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    global is_canceled
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if not message.reply_to_message:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗚𝗨𝗜𝗗𝗘 」</b></blockquote>\n"
            "<blockquote>◍ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ:\n"
            "▸ <code>/broadcast</code>\n"
            "▸ <code>/broadcast pin</code>\n"
            "▸ <code>/broadcast delete 30</code>\n"
            "▸ <code>/broadcast silent</code></blockquote>",
            reply_markup=close_btn
        )

    args = [a.lower() for a in message.text.split()[1:]]
    do_pin = "pin" in args
    silent = "silent" in args
    do_delete = "delete" in args
    duration = 30
    if do_delete:
        try:
            idx = args.index("delete")
            duration = int(args[idx + 1])
        except Exception:
            pass

    async with cancel_lock:
        is_canceled = False

    query = await full_userbase()
    broadcast_msg = message.reply_to_message
    total = len(query)
    successful = blocked = deleted = unsuccessful = 0

    pls_wait = await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧𝗜𝗡𝗚... ⚡ 」</b></blockquote>\n"
        f"<blockquote>◍ sᴇɴᴅɪɴɢ ᴛᴏ <code>{total}</code> ᴜsᴇʀs...</blockquote>",
        auto_delete_sec=0
    )

    for chat_id in query:
        async with cancel_lock:
            if is_canceled:
                return await edit_ui(
                    pls_wait,
                    "<blockquote><b>「 ➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗔𝗡𝗖𝗘𝗟𝗟𝗘𝗗 ❌ 」</b></blockquote>",
                    reply_markup=close_btn
                )
        try:
            sent_msg = await broadcast_msg.copy(chat_id, disable_notification=silent)
            if do_pin:
                await client.pin_chat_message(chat_id, sent_msg.id, both_sides=True)
            if do_delete:
                asyncio.create_task(auto_delete(sent_msg, duration))
            successful += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                sent_msg = await broadcast_msg.copy(chat_id, disable_notification=silent)
                successful += 1
            except Exception:
                unsuccessful += 1
        except UserIsBlocked:
            await del_user(chat_id)
            blocked += 1
        except InputUserDeactivated:
            await del_user(chat_id)
            deleted += 1
        except Exception:
            unsuccessful += 1

    await edit_ui(
        pls_wait,
        f"<blockquote><b>「 ➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 ✅ 」</b></blockquote>\n"
        f"<blockquote>◍ <b>ᴛᴏᴛᴀʟ:</b> <code>{total}</code>\n"
        f"◍ <b>sᴜᴄᴄᴇss:</b> <code>{successful}</code>\n"
        f"◍ <b>ʙʟᴏᴄᴋᴇᴅ:</b> <code>{blocked}</code>\n"
        f"◍ <b>ᴅᴇʟᴇᴛᴇᴅ:</b> <code>{deleted}</code>\n"
        f"◍ <b>ғᴀɪʟᴇᴅ:</b> <code>{unsuccessful}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── ALL INTERACTIVE UI & PANEL CALLBACKS ──────────────────────────────
@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if data == "close":
        await query.answer()
        fb_id = query.message.reply_to_message.id if getattr(query.message, "reply_to_message", None) else None
        await delete_bot_and_user_msg(query.message.chat.id, query.message.id, fb_id)

    elif data == "about":
        await query.answer()
        markup = InlineKeyboardMarkup([[
            sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]])
        await edit_ui(query.message, get_about_text(), reply_markup=markup)

    elif data == "directory":
        await query.answer()
        markup = InlineKeyboardMarkup([
            [sbtn("🔥 ᴛʀᴇɴᴅɪɴɢ ᴄʜᴀɴɴᴇʟs", callback_data="trending", style="success")],
            [
                sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])
        await edit_ui(query.message, get_directory_text(), reply_markup=markup)

    elif data == "trending":
        await query.answer()
        top_docs = await get_top_channels(limit=5)
        buttons = []
        for doc in top_docs:
            ch_id = doc.get("channel_id")
            title = doc.get("title")
            clicks = doc.get("clicks", 0)
            if ch_id and title:
                badge = f" • ⚡ {format_count(clicks)}" if clicks else ""
                buttons.append([sbtn(f"🔥 {title}{badge}", callback_data=f"getch_{ch_id}", style="success")])

        buttons.append([
            sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ])

        if len(buttons) == 1:
            txt = (
                "<blockquote><b>「 🔥 𝗧𝗥𝗘𝗡𝗗𝗜𝗡𝗚 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
                "<blockquote>◍ ɴᴏ ᴛʀᴇɴᴅɪɴɢ ᴅᴀᴛᴀ ʏᴇᴛ. ᴜsᴇ <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code> ᴛᴏ ғɪɴᴅ ᴄʜᴀɴɴᴇʟs!</blockquote>"
            )
        else:
            txt = (
                "<blockquote><b>「 🔥 𝗧𝗥𝗘𝗡𝗗𝗜𝗡𝗚 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
                "<blockquote>◍ ᴍᴏsᴛ ᴘᴏᴘᴜʟᴀʀ ᴄʜᴀɴɴᴇʟs ʀɪɢʜᴛ ɴᴏᴡ.\n"
                "╰┈➤ <i>ᴛᴀᴘ ᴀɴʏ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇᴛ ᴀɴ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ:</i></blockquote>"
            )
        await edit_ui(query.message, txt, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("getch_"):
        await query.answer("⚡ Generating invite link...", show_alert=False)
        ch_id = int(data.split("_", 1)[1])
        is_joined, unjoined = await check_user_fsub(client, user_id)
        code = await save_encoded_link(ch_id)
        await save_encoded_link2(ch_id, code)
        _, mode = await get_cached_fsub_config()
        payload = f"req_{code}" if mode == "request" else code

        if not is_joined:
            fsub_markup = await build_fsub_keyboard(client, unjoined, payload)
            return await edit_ui(query.message, get_fsub_text(), reply_markup=fsub_markup)

        try:
            await query.message.delete()
        except Exception:
            pass
        await deliver_channel_link(client, query.message, payload)

    elif data == "help":
        await query.answer()
        markup = InlineKeyboardMarkup([[
            sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]])
        await edit_ui(query.message, get_help_text(), reply_markup=markup)

    elif data in ["start", "home"]:
        await query.answer()
        await edit_ui(query.message, get_start_text(query.from_user.mention), reply_markup=get_main_keyboard())

    # ─── ADMIN PANEL CALLBACKS ─────────────────────────────────────────
    elif data.startswith("panel_"):
        if not await is_admin(user_id):
            return await query.answer("⚠️ Admins only!", show_alert=True)
        back_panel = InlineKeyboardMarkup([[
            sbtn("‹ ᴘᴀɴᴇʟ", callback_data="panel_home", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]])

        if data == "panel_home":
            await query.answer()
            _, mode = await get_cached_fsub_config()
            await edit_ui(
                query.message,
                "<blockquote><b>「 ⚙ 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗣𝗔𝗡𝗘𝗟 」</b></blockquote>\n"
                "<blockquote>◍ ᴍᴀɴᴀɢᴇ ғsᴜʙ, ʜɪᴅᴅᴇɴ ᴄʜᴀɴɴᴇʟs, ᴀᴅᴍɪɴs &amp; ʟɪᴠᴇ sᴛᴀᴛs ғʀᴏᴍ ᴏɴᴇ ᴘʟᴀᴄᴇ.</blockquote>",
                reply_markup=get_panel_keyboard(mode)
            )
        elif data == "panel_toggle_req":
            current = await get_fsub_mode()
            new_mode = "direct" if current == "request" else "request"
            await set_fsub_mode(new_mode)
            invalidate_fsub_cache()
            await query.answer(f"FSub Mode -> {new_mode.upper()}", show_alert=False)
            await edit_ui(
                query.message,
                f"<blockquote><b>「 ⚙ 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗣𝗔𝗡𝗘𝗟 」</b></blockquote>\n"
                f"<blockquote>◍ ғsᴜʙ ᴍᴏᴅᴇ sᴡɪᴛᴄʜᴇᴅ ᴛᴏ: <code>{new_mode.upper()}</code> ⚡</blockquote>",
                reply_markup=get_panel_keyboard(new_mode)
            )
        elif data == "panel_status":
            await query.answer()
            total_u = await total_users_count()
            delta = datetime.now() - client.uptime
            up = get_readable_time(delta.seconds)
            await edit_ui(
                query.message,
                f"<blockquote><b>「 ⚡ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 」</b></blockquote>\n"
                f"<blockquote>◍ <b>ᴜsᴇʀs:</b> <code>{total_u}</code>\n"
                f"◍ <b>/ɢᴇᴛ ɪɴᴅᴇxᴇᴅ:</b> <code>{len(_CHANNEL_INDEX)}</code>\n"
                f"◍ <b>ᴜᴘᴛɪᴍᴇ:</b> <code>{up}</code></blockquote>",
                reply_markup=back_panel
            )
        elif data == "panel_fsub":
            await query.answer()
            chs = await get_fsub_channels()
            txt = "<blockquote><b>「 🔒 𝗙𝗦𝗨𝗕 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            if not chs:
                txt += "<blockquote>◍ ɴᴏ ғsᴜʙ ᴄʜᴀɴɴᴇʟs ᴀᴅᴅᴇᴅ.</blockquote>"
            else:
                for cid in chs:
                    txt += f"<blockquote>▸ ɪᴅ: <code>{cid}</code></blockquote>\n"
            await edit_ui(query.message, txt.strip(), reply_markup=back_panel)
        elif data == "panel_hidden":
            await query.answer()
            docs = await get_hidden_channels()
            txt = "<blockquote><b>「 🙈 𝗛𝗜𝗗𝗗𝗘𝗡 𝗙𝗥𝗢𝗠 /𝗚𝗘𝗧 」</b></blockquote>\n"
            if not docs:
                txt += "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ʜɪᴅᴅᴇɴ.</blockquote>"
            else:
                for d in docs[:15]:
                    txt += f"<blockquote>▸ <b>{d.get('title', 'Channel')}</b>\nɪᴅ: <code>{d.get('channel_id')}</code></blockquote>\n"
            await edit_ui(query.message, txt.strip(), reply_markup=back_panel)
        elif data == "panel_admins":
            await query.answer()
            adms = await list_admins()
            txt = "<blockquote><b>「 👑 𝗔𝗗𝗠𝗜𝗡𝗦 𝗟𝗜𝗦𝗧 」</b></blockquote>\n"
            for aid in adms:
                r = "ᴏᴡɴᴇʀ 👑" if aid == OWNER_ID else "ᴀᴅᴍɪɴ"
                txt += f"<blockquote>▸ {r}: <code>{aid}</code></blockquote>\n"
            await edit_ui(query.message, txt.strip(), reply_markup=back_panel)

    elif data.startswith("check_sub"):
        payload = data[10:] if data.startswith("check_sub_") else ""
        is_joined, unjoined = await check_user_fsub(client, user_id)

        if not is_joined:
            await query.answer("⚠️ You haven't joined all required channels yet!", show_alert=True)
            fsub_markup = await build_fsub_keyboard(client, unjoined, payload)
            try:
                await edit_ui(query.message, get_fsub_text(), reply_markup=fsub_markup)
            except Exception:
                pass
            return

        await query.answer("⚡ Verified!", show_alert=False)
        try:
            await query.message.delete()
        except Exception:
            pass

        if payload:
            return await deliver_channel_link(client, query.message, payload)

        await reply_ui(query.message, get_start_text(query.from_user.mention), reply_markup=get_main_keyboard())

    elif data.startswith("reload_"):
        await query.answer("↻ Generating fresh link...", show_alert=False)
        payload = data[7:]
        try:
            await query.message.delete()
        except Exception:
            pass
        await deliver_channel_link(client, query.message, payload, force_new=True)

async def auto_delete(msg, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass
