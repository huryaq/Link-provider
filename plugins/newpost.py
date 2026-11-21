import asyncio
import time
from bot import Bot
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, Message
from pyrogram.errors import UserNotParticipant, FloodWait
from config import DATABASE_CHANNEL
from database.database import (
    save_channel, delete_channel, get_channels,
    save_encoded_link, save_encoded_link2, channels_collection,
    set_channel_hidden, get_hidden_channels, is_admin
)
from plugins.helpers import sbtn, reply_ui, edit_ui, normalize_text

PAGE_SIZE = 6

# ─── IN-MEMORY RAM INDEX FOR 0.1s INSTANT /get SEARCH ──────────────────
# Structure: {channel_id: {"title": str, "norm": str, "nospace": str, "words": list}}
_CHANNEL_INDEX = {}
_WARMUP_RUNNING = False

def update_ram_index(channel_id: int, title: str):
    if not title:
        return
    norm = normalize_text(title)
    _CHANNEL_INDEX[int(channel_id)] = {
        "title": title,
        "norm": norm,
        "nospace": norm.replace(" ", ""),
        "words": norm.split()
    }

def remove_from_ram_index(channel_id: int):
    _CHANNEL_INDEX.pop(int(channel_id), None)

async def warmup_channel_index(client: Bot):
    """
    Runs in background on bot startup.
    Skips channels marked hidden_from_get=True so they never appear in /get.
    """
    global _WARMUP_RUNNING
    if _WARMUP_RUNNING:
        return
    _WARMUP_RUNNING = True
    try:
        docs = await channels_collection.find({}).to_list(None)
        missing_ids = []

        for doc in docs:
            ch_id = doc.get("channel_id")
            if not ch_id or doc.get("original_link"):
                continue
            if doc.get("hidden_from_get", False):
                remove_from_ram_index(ch_id)
                continue
            title = doc.get("title")
            if title:
                update_ram_index(ch_id, title)
            else:
                missing_ids.append(int(ch_id))

        for ch_id in missing_ids:
            if ch_id in _CHANNEL_INDEX:
                continue
            try:
                chat = await client.get_chat(ch_id)
                if chat and chat.title:
                    update_ram_index(ch_id, chat.title)
                    await channels_collection.update_one(
                        {"channel_id": ch_id},
                        {"$set": {"title": chat.title, "status": "active"}},
                        upsert=True
                    )
                await asyncio.sleep(0.25)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    chat = await client.get_chat(ch_id)
                    if chat and chat.title:
                        update_ram_index(ch_id, chat.title)
                        await channels_collection.update_one(
                            {"channel_id": ch_id},
                            {"$set": {"title": chat.title, "status": "active"}},
                            upsert=True
                        )
                except Exception:
                    pass
            except Exception:
                pass
    except Exception as e:
        print(f"Warmup index error: {e}")
    finally:
        _WARMUP_RUNNING = False

# Kept for backward compatibility
async def revoke_invite_after_5_minutes(client: Bot, channel_id: int, link: str, is_request: bool = False):
    await asyncio.sleep(300)
    try:
        await client.revoke_chat_invite_link(channel_id, link)
    except Exception:
        pass

# ─── HIDE / UNHIDE CHANNELS FROM /get (LINKS STAY 100% WORKING!) ───────
@Bot.on_message(filters.command('hidech') & filters.private)
async def hide_channel_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗛𝗜𝗗𝗘 𝗙𝗥𝗢𝗠 /𝗚𝗘𝗧 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/hidech -100xxxxxxxxxx</code>\n"
            "╰┈➤ <i>ɪɴᴠɪᴛᴇ ʟɪɴᴋs ᴡɪʟʟ sᴛɪʟʟ ᴡᴏʀᴋ ɴᴏʀᴍᴀʟʟʏ.</i></blockquote>",
            reply_markup=close_btn
        )

    title = _CHANNEL_INDEX.get(channel_id, {}).get("title")
    if not title:
        try:
            chat = await client.get_chat(channel_id)
            title = chat.title
        except Exception:
            title = "Channel"

    await set_channel_hidden(channel_id, True)
    remove_from_ram_index(channel_id)

    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗛𝗜𝗗𝗗𝗘𝗡 🙈 」</b></blockquote>\n"
        f"<blockquote>▸ <b>{title}</b>\n"
        f"◍ ɪᴅ: <code>{channel_id}</code>\n\n"
        f"╰┈➤ <i>ʜɪᴅᴅᴇɴ ғʀᴏᴍ /get &amp; ᴛʀᴇɴᴅɪɴɢ. ᴀʟʟ ɪɴᴠɪᴛᴇ ʟɪɴᴋs ʀᴇᴍᴀɪɴ ᴀᴄᴛɪᴠᴇ!</i></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command('unhidech') & filters.private)
async def unhide_channel_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗨𝗡𝗛𝗜𝗗𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/unhidech -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    await set_channel_hidden(channel_id, False)
    try:
        chat = await client.get_chat(channel_id)
        title = chat.title
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"title": title, "status": "active"}},
            upsert=True
        )
        update_ram_index(channel_id, title)
    except Exception:
        title = "Channel"

    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗩𝗜𝗦𝗜𝗕𝗟𝗘 ⚡ 」</b></blockquote>\n"
        f"<blockquote>▸ <b>{title}</b>\n"
        f"◍ ɪᴅ: <code>{channel_id}</code>\n\n"
        f"╰┈➤ <i>ɴᴏᴡ ᴠɪsɪʙʟᴇ ɪɴ /get sᴇᴀʀᴄʜ!</i></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command('hiddench') & filters.private)
async def list_hidden_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    docs = await get_hidden_channels()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if not docs:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗛𝗜𝗗𝗗𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀʀᴇ ʜɪᴅᴅᴇɴ ғʀᴏᴍ /get.</blockquote>",
            reply_markup=close_btn
        )

    text = "<blockquote><b>「 ➲ 𝗛𝗜𝗗𝗗𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 🙈 」</b></blockquote>\n"
    for d in docs[:25]:
        ch_id = d.get("channel_id")
        title = d.get("title") or "Unknown Channel"
        text += f"<blockquote>▸ <b>{title}</b>\nɪᴅ: <code>{ch_id}</code></blockquote>\n"
    await reply_ui(message, text.strip(), reply_markup=close_btn)

# ─── INSTANT 0.1s /get SEARCH (PURE RAM + SPEED BADGE) ─────────────────
@Bot.on_message(filters.command('get') & filters.private)
async def search_channel_cmd(client: Bot, message: Message):
    t0 = time.perf_counter()
    if not _CHANNEL_INDEX and not _WARMUP_RUNNING:
        asyncio.create_task(warmup_channel_index(client))
        docs = await channels_collection.find({"title": {"$exists": True}, "hidden_from_get": {"$ne": True}}).to_list(None)
        for d in docs:
            if d.get("channel_id") and d.get("title") and not d.get("original_link"):
                update_ram_index(d["channel_id"], d["title"])

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if len(message.command) < 2:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗙𝗜𝗡𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 🔎 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code>\n"
            "╰┈➤ <i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/get naruto</code></blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

    raw_query = " ".join(message.command[1:]).strip()
    query_norm = normalize_text(raw_query)
    query_nospace = query_norm.replace(" ", "")

    if not query_norm:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗤𝗨𝗘𝗥𝗬 ⚠️ 」</b></blockquote>\n"
            "<blockquote>◍ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ.</blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

    query_words = query_norm.split()
    matched_buttons = []

    for ch_id, info in list(_CHANNEL_INDEX.items()):
        t_norm = info["norm"]
        t_nospace = info["nospace"]
        t_words = info["words"]

        if (
            query_norm in t_norm
            or query_nospace in t_nospace
            or all(any(qw in tw for tw in t_words) for qw in query_words)
        ):
            matched_buttons.append([sbtn(f"▸ {info['title']}", callback_data=f"getch_{ch_id}", style="success")])
            if len(matched_buttons) >= 12:
                break

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not matched_buttons:
        return await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗡𝗢 𝗥𝗘𝗦𝗨𝗟𝗧𝗦 𝗙𝗢𝗨𝗡𝗗 ❌ 」</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟ ᴍᴀᴛᴄʜᴇᴅ: <code>{raw_query}</code>\n"
            f"╰┈➤ <i>sᴇᴀʀᴄʜᴇᴅ ɪɴ</i> <code>{elapsed_ms:.1f}ᴍs</code></blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

    total_m = len(matched_buttons)
    matched_buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗦𝗘𝗔𝗥𝗖𝗛 𝗥𝗘𝗦𝗨𝗟𝗧𝗦 🔎 」</b></blockquote>\n"
        f"<blockquote>⟡ ғᴏᴜɴᴅ <code>{total_m}</code> ᴍᴀᴛᴄʜ(ᴇs) • ⚡ <code>{elapsed_ms:.1f}ᴍs</code>\n"
        f"╰┈➤ <i>ᴛᴀᴘ ᴀɴʏ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ғᴏʀ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ:</i></blockquote>",
        reply_markup=InlineKeyboardMarkup(matched_buttons),
        auto_delete_sec=120
    )

# ─── ADD CHANNEL (/addch) ──────────────────────────────────────────────
@Bot.on_message(filters.command(['addch', 'setchannel']) & filters.private)
async def set_channel(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗜𝗡𝗣𝗨𝗧 ⚠️ 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/addch -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    try:
        chat = await client.get_chat(channel_id)
        await save_channel(channel_id)
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"title": chat.title, "status": "active", "hidden_from_get": False}},
            upsert=True
        )
        update_ram_index(channel_id, chat.title)

        base64_invite = await save_encoded_link(channel_id)
        await save_encoded_link2(channel_id, base64_invite)

        normal_link = f"https://t.me/{client.username}?start={base64_invite}"
        request_link = f"https://t.me/{client.username}?start=req_{base64_invite}"

        reply_text = (
            f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗔𝗗𝗗𝗘𝗗 ⚡ 」</b></blockquote>\n"
            f"<blockquote>▸ <b>{chat.title}</b>\n"
            f"◍ ɪᴅ: <code>{channel_id}</code>\n\n"
            f"◍ <b>ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"◍ <b>ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        return await reply_ui(message, reply_text, reply_markup=close_btn)

    except UserNotParticipant:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n"
            "<blockquote>◍ ɪ ᴀᴍ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ ᴛʜɪs ᴄʜᴀɴɴᴇʟ. ᴘʟᴇᴀsᴇ ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ғɪʀsᴛ.</blockquote>",
            reply_markup=close_btn
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await set_channel(client, message)
    except Exception as e:
        return await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n<blockquote><code>{str(e)}</code></blockquote>",
            reply_markup=close_btn
        )

# ─── DELETE CHANNEL (/delch) ───────────────────────────────────────────
@Bot.on_message(filters.command(['delch', 'delchannel']) & filters.private)
async def del_channel(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗜𝗡𝗣𝗨𝗧 ⚠️ 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/delch -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    await delete_channel(channel_id)
    remove_from_ram_index(channel_id)
    return await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗥𝗘𝗠𝗢𝗩𝗘𝗗 」</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── ADMIN CHANNEL BUTTON PAGES (/ch_links & /reqlink) ─────────────────
@Bot.on_message(filters.command('ch_links') & filters.private)
async def channel_post(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
        )
    await send_channel_page(client, message, channels, page=0)

async def send_channel_page(client, message, channels, page, edit=False):
    total_pages = (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    buttons = []
    row = []

    for channel_id in channels[start_idx:end_idx]:
        try:
            base64_invite = await save_encoded_link(channel_id)
            button_link = f"https://t.me/{client.username}?start={base64_invite}"
            title = _CHANNEL_INDEX.get(channel_id, {}).get("title")
            if not title:
                chat = await client.get_chat(channel_id)
                title = chat.title
            row.append(sbtn(f"▸ {title}", url=button_link, style="primary"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        except Exception:
            pass

    if row:
        buttons.append(row)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(sbtn("‹ ᴘʀᴇᴠ", callback_data=f"channelpage_{page-1}", style="primary"))
    if page < total_pages - 1:
        nav_buttons.append(sbtn("ɴᴇxᴛ ›", callback_data=f"channelpage_{page+1}", style="primary"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    text = (
        "<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞𝗦 」</b></blockquote>\n"
        "<blockquote>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ᴀɴ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</blockquote>"
    )
    if edit:
        await edit_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await reply_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))

@Bot.on_callback_query(filters.regex(r"^channelpage_(\d+)$"))
async def paginate_channels(client, callback_query):
    page = int(callback_query.data.split("_")[1])
    channels = await get_channels()
    await send_channel_page(client, callback_query.message, channels, page, edit=True)

@Bot.on_message(filters.command('reqlink') & filters.private)
async def req_post(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
        )
    await send_request_page(client, message, channels, page=0)

async def send_request_page(client, message, channels, page, edit=False):
    total_pages = (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    buttons = []
    row = []

    for channel_id in channels[start_idx:end_idx]:
        try:
            code = await save_encoded_link(channel_id)
            await save_encoded_link2(channel_id, code)
            button_link = f"https://t.me/{client.username}?start=req_{code}"
            title = _CHANNEL_INDEX.get(channel_id, {}).get("title")
            if not title:
                chat = await client.get_chat(channel_id)
                title = chat.title
            row.append(sbtn(f"▸ {title}", url=button_link, style="primary"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        except Exception:
            pass

    if row:
        buttons.append(row)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(sbtn("‹ ᴘʀᴇᴠ", callback_data=f"reqpage_{page-1}", style="primary"))
    if page < total_pages - 1:
        nav_buttons.append(sbtn("ɴᴇxᴛ ›", callback_data=f"reqpage_{page+1}", style="primary"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    text = (
        "<blockquote><b>「 ➲ 𝗥𝗘𝗤𝗨𝗘𝗦𝗧 𝗟𝗜𝗡𝗞𝗦 」</b></blockquote>\n"
        "<blockquote>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇǫᴜᴇsᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</blockquote>"
    )
    if edit:
        await edit_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await reply_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))

@Bot.on_callback_query(filters.regex(r"^reqpage_(\d+)$"))
async def paginate_requests(client, callback_query):
    page = int(callback_query.data.split("_")[1])
    channels = await get_channels()
    await send_request_page(client, callback_query.message, channels, page, edit=True)

# ─── ALL LINKS LIST (/links) ───────────────────────────────────────────
@Bot.on_message(filters.command('links') & filters.private)
async def show_links(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
        )
    await send_links_page(client, message, channels, page=0)

async def send_links_page(client, message, channels, page, edit=False):
    total_pages = (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE

    links_text = "<blockquote><b>「 ➲ 𝗔𝗟𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞𝗦 」</b></blockquote>\n"
    for i, channel_id in enumerate(channels[start_idx:end_idx], start=start_idx + 1):
        try:
            title = _CHANNEL_INDEX.get(channel_id, {}).get("title")
            if not title:
                chat = await client.get_chat(channel_id)
                title = chat.title
                await channels_collection.update_one(
                    {"channel_id": channel_id},
                    {"$set": {"title": title}},
                    upsert=True
                )
            code = await save_encoded_link(channel_id)
            await save_encoded_link2(channel_id, code)
            normal_link = f"https://t.me/{client.username}?start={code}"
            request_link = f"https://t.me/{client.username}?start=req_{code}"
            links_text += (
                f"<blockquote>▸ <b>{i}. {title}</b>\n"
                f"◍ ɪᴅ: <code>{channel_id}</code>\n"
                f"◍ ɴᴏʀᴍᴀʟ: <code>{normal_link}</code>\n"
                f"◍ ʀᴇǫᴜᴇsᴛ: <code>{request_link}</code></blockquote>\n"
            )
        except Exception:
            links_text += f"<blockquote>▸ <b>{i}. ᴄʜᴀɴɴᴇʟ</b> <code>{channel_id}</code> (ᴇʀʀᴏʀ)</blockquote>\n"

    links_text += f"<blockquote>◍ ᴘᴀɢᴇ <code>{page + 1}</code> ᴏғ <code>{total_pages}</code></blockquote>"

    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(sbtn("‹ ᴘʀᴇᴠ", callback_data=f"linkspage_{page-1}", style="primary"))
    if page < total_pages - 1:
        nav_buttons.append(sbtn("ɴᴇxᴛ ›", callback_data=f"linkspage_{page+1}", style="primary"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    if edit:
        await edit_ui(message, links_text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await reply_ui(message, links_text, reply_markup=InlineKeyboardMarkup(buttons))

@Bot.on_callback_query(filters.regex(r"^linkspage_(\d+)$"))
async def paginate_links(client, callback_query):
    page = int(callback_query.data.split("_")[1])
    channels = await get_channels()
    await send_links_page(client, callback_query.message, channels, page, edit=True)

# ─── BULK LINK GENERATION (/bulklink) ──────────────────────────────────
@Bot.on_message(filters.command('bulklink') & filters.private)
async def bulk_link(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗕𝗨𝗟𝗞 𝗟𝗜𝗡𝗞𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/bulklink &lt;id1&gt; &lt;id2&gt; ...</code></blockquote>",
            reply_markup=close_btn
        )

    ids = message.command[1:]
    reply_text = "<blockquote><b>「 ➲ 𝗕𝗨𝗟𝗞 𝗟𝗜𝗡𝗞𝗦 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗 ⚡ 」</b></blockquote>\n"
    for idx, id_str in enumerate(ids, start=1):
        try:
            channel_id = int(id_str)
            chat = await client.get_chat(channel_id)
            await save_channel(channel_id)
            await channels_collection.update_one(
                {"channel_id": channel_id},
                {"$set": {"title": chat.title, "status": "active"}},
                upsert=True
            )
            update_ram_index(channel_id, chat.title)
            code = await save_encoded_link(channel_id)
            await save_encoded_link2(channel_id, code)
            normal_link = f"https://t.me/{client.username}?start={code}"
            request_link = f"https://t.me/{client.username}?start=req_{code}"
            reply_text += (
                f"<blockquote>▸ <b>{idx}. {chat.title}</b>\n"
                f"◍ ɪᴅ: <code>{channel_id}</code>\n"
                f"◍ ɴᴏʀᴍᴀʟ: <code>{normal_link}</code>\n"
                f"◍ ʀᴇǫᴜᴇsᴛ: <code>{request_link}</code></blockquote>\n"
            )
        except Exception as e:
            reply_text += f"<blockquote>▸ <b>{idx}. {id_str}</b> (ᴇʀʀᴏʀ: <code>{e}</code>)</blockquote>\n"

    await reply_ui(message, reply_text, reply_markup=close_btn)

# ─── GENERATE PROTECTED LINK (/genlink) ────────────────────────────────
@Bot.on_message(filters.command('genlink') & filters.private)
async def generate_link_command(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘 𝗟𝗜𝗡𝗞 」</b></blockquote>\n"
            "<blockquote>◍ ᴜsᴀɢᴇ: <code>/genlink &lt;url&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    link = message.command[1]
    try:
        sent_msg = await client.send_message(DATABASE_CHANNEL, f"#LINK\n{link}")
        channel_id = sent_msg.id
        code = await save_encoded_link(channel_id)
        await save_encoded_link2(channel_id, code)
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"original_link": link, "status": "active"}},
            upsert=True
        )
        normal_link = f"https://t.me/{client.username}?start={code}"
        request_link = f"https://t.me/{client.username}?start=req_{code}"
        reply_text = (
            "<blockquote><b>「 ➲ 𝗟𝗜𝗡𝗞 𝗦𝗧𝗢𝗥𝗘𝗗 ⚡ 」</b></blockquote>\n"
            f"<blockquote>◍ <b>ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"◍ <b>ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        await reply_ui(message, reply_text, reply_markup=close_btn)
    except Exception as e:
        await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n<blockquote><code>{e}</code></blockquote>",
            reply_markup=close_btn
        )

# ─── CONNECTED CHANNELS LIST (/channels) ───────────────────────────────
@Bot.on_message(filters.command('channels') & filters.private)
async def show_channel_ids(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴄᴏɴɴᴇᴄᴛᴇᴅ ʏᴇᴛ.</blockquote>"
        )
    await send_channel_ids_page(client, message, channels, page=0)

async def send_channel_ids_page(client, message, channels, page, edit=False):
    PER_PAGE = 10
    total_pages = (len(channels) + PER_PAGE - 1) // PER_PAGE
    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE

    text = "<blockquote><b>「 ➲ 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
    for idx, channel_id in enumerate(channels[start_idx:end_idx], start=start_idx + 1):
        try:
            title = _CHANNEL_INDEX.get(channel_id, {}).get("title")
            if not title:
                chat = await client.get_chat(channel_id)
                title = chat.title
            text += f"<blockquote>▸ <b>{idx}. {title}</b>\n◍ ɪᴅ: <code>{channel_id}</code></blockquote>\n"
        except Exception:
            text += f"<blockquote>▸ <b>{idx}. ᴜɴᴋɴᴏᴡɴ</b>\n◍ ɪᴅ: <code>{channel_id}</code></blockquote>\n"

    text += f"<blockquote>◍ ᴘᴀɢᴇ <code>{page + 1}</code> ᴏғ <code>{total_pages}</code></blockquote>"

    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(sbtn("‹ ᴘʀᴇᴠ", callback_data=f"channelids_{page-1}", style="primary"))
    if page < total_pages - 1:
        nav_buttons.append(sbtn("ɴᴇxᴛ ›", callback_data=f"channelids_{page+1}", style="primary"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    if edit:
        await edit_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await reply_ui(message, text, reply_markup=InlineKeyboardMarkup(buttons))

@Bot.on_callback_query(filters.regex(r"^channelids_(\d+)$"))
async def paginate_channel_ids(client, callback_query):
    page = int(callback_query.data.split("_")[1])
    channels = await get_channels()
    await send_channel_ids_page(client, callback_query.message, channels, page, edit=True)
