import asyncio
from bot import Bot
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, Message
from pyrogram.errors import UserNotParticipant, FloodWait, RPCError
from config import DATABASE_CHANNEL
from database.database import (
    save_channel, delete_channel, get_channels,
    save_encoded_link, save_encoded_link2, channels_collection
)
from helper_func import is_owner_or_admin
from plugins.helpers import get_preview, sbtn, reply_ui, edit_ui

PAGE_SIZE = 6

# Kept for backward compatibility if imported anywhere
async def revoke_invite_after_5_minutes(client: Bot, channel_id: int, link: str, is_request: bool = False):
    await asyncio.sleep(300)
    try:
        await client.revoke_chat_invite_link(channel_id, link)
    except Exception:
        pass

# ─── ADD CHANNEL (/addch) ──────────────────────────────────────────────
@Bot.on_message(filters.command(['addch', 'setchannel']) & is_owner_or_admin)
async def set_channel(client: Bot, message: Message):
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗜𝗡𝗣𝗨𝗧 ⚠️</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/addch -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    try:
        chat = await client.get_chat(channel_id)
        await save_channel(channel_id)
        base64_invite = await save_encoded_link(channel_id)
        await save_encoded_link2(channel_id, base64_invite)

        normal_link = f"https://t.me/{client.username}?start={base64_invite}"
        request_link = f"https://t.me/{client.username}?start=req_{base64_invite}"

        reply_text = (
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗔𝗗𝗗𝗘𝗗 ⚡</b></blockquote>\n"
            f"<blockquote>▸ <b>{chat.title}</b>\n"
            f"◍ ɪᴅ: <code>{channel_id}</code>\n\n"
            f"◍ <b>ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"◍ <b>ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        return await reply_ui(message, reply_text, reply_markup=close_btn)

    except UserNotParticipant:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗘𝗥𝗥𝗢𝗥 ❌</b></blockquote>\n"
            f"<blockquote>◍ ɪ ᴀᴍ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ ᴛʜɪs ᴄʜᴀɴɴᴇʟ. ᴘʟᴇᴀsᴇ ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ғɪʀsᴛ.</blockquote>",
            reply_markup=close_btn
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await set_channel(client, message)
    except Exception as e:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗘𝗥𝗥𝗢𝗥 ❌</b></blockquote>\n<blockquote><code>{str(e)}</code></blockquote>",
            reply_markup=close_btn
        )

# ─── DELETE CHANNEL (/delch) ───────────────────────────────────────────
@Bot.on_message(filters.command(['delch', 'delchannel']) & is_owner_or_admin)
async def del_channel(client: Bot, message: Message):
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    try:
        channel_id = int(message.command[1])
    except (IndexError, ValueError):
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗜𝗡𝗣𝗨𝗧 ⚠️</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/delch -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    await delete_channel(channel_id)
    return await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗥𝗘𝗠𝗢𝗩𝗘𝗗</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── PUBLIC DIRECTORY (/index & /get) (AS SEEN IN VIDEO) ───────────────
@Bot.on_message(filters.command('index') & filters.private)
async def index_directory(client: Bot, message: Message):
    channels = await get_channels()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if not channels:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬 🔎</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀʀᴇ ᴄᴜʀʀᴇɴᴛʟʏ ʟɪsᴛᴇᴅ ɪɴ ᴛʜᴇ ᴅɪʀᴇᴄᴛᴏʀʏ.</blockquote>",
            reply_markup=close_btn
        )
    await send_request_page(client, message, channels, page=0)

@Bot.on_message(filters.command('get') & filters.private)
async def search_channel_cmd(client: Bot, message: Message):
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗦𝗘𝗔𝗥𝗖𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 🔎</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/get &lt;ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    query_str = " ".join(message.command[1:]).lower()
    channels = await get_channels()
    buttons = []

    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            if query_str in chat.title.lower():
                code = await save_encoded_link(ch_id)
                await save_encoded_link2(ch_id, code)
                link = f"https://t.me/{client.username}?start=req_{code}"
                buttons.append([sbtn(f"▸ {chat.title}", url=link, style="primary")])
        except Exception:
            pass

    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])
    if len(buttons) == 1:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗡𝗢 𝗥𝗘𝗦𝗨𝗟𝗧𝗦 𝗙𝗢𝗨𝗡𝗗 ❌</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟ ᴍᴀᴛᴄʜᴇᴅ: <code>{query_str}</code></blockquote>",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    await reply_ui(
        message,
        f"{get_preview()}<blockquote><b>➲ 𝗦𝗘𝗔𝗥𝗖𝗛 𝗥𝗘𝗦𝗨𝗟𝗧𝗦 🔎</b></blockquote>\n"
        f"<blockquote>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</blockquote>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ─── CHANNEL BUTTON PAGES (/ch_links & /reqlink) ───────────────────────
@Bot.on_message(filters.command('ch_links') & is_owner_or_admin)
async def channel_post(client: Bot, message: Message):
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
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
            chat = await client.get_chat(channel_id)
            row.append(sbtn(f"▸ {chat.title}", url=button_link, style="primary"))
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
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬</b></blockquote>\n"
        f"<blockquote>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ᴀɴ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</blockquote>"
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

@Bot.on_message(filters.command('reqlink') & is_owner_or_admin)
async def req_post(client: Bot, message: Message):
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
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
            chat = await client.get_chat(channel_id)
            row.append(sbtn(f"▸ {chat.title}", url=button_link, style="primary"))
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
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬 🔎</b></blockquote>\n"
        f"<blockquote>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇǫᴜᴇsᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</blockquote>"
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
@Bot.on_message(filters.command('links') & is_owner_or_admin)
async def show_links(client: Bot, message: Message):
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</blockquote>"
        )
    await send_links_page(client, message, channels, page=0)

async def send_links_page(client, message, channels, page, edit=False):
    total_pages = (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE

    links_text = f"{get_preview()}<blockquote><b>➲ 𝗔𝗟𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞𝗦</b></blockquote>\n"
    for i, channel_id in enumerate(channels[start_idx:end_idx], start=start_idx + 1):
        try:
            chat = await client.get_chat(channel_id)
            code = await save_encoded_link(channel_id)
            await save_encoded_link2(channel_id, code)
            normal_link = f"https://t.me/{client.username}?start={code}"
            request_link = f"https://t.me/{client.username}?start=req_{code}"
            links_text += (
                f"<blockquote>▸ <b>{i}. {chat.title}</b>\n"
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
@Bot.on_message(filters.command('bulklink') & is_owner_or_admin)
async def bulk_link(client: Bot, message: Message):
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗕𝗨𝗟𝗞 𝗟𝗜𝗡𝗞𝗦</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/bulklink &lt;id1&gt; &lt;id2&gt; ...</code></blockquote>",
            reply_markup=close_btn
        )

    ids = message.command[1:]
    reply_text = f"{get_preview()}<blockquote><b>➲ 𝗕𝗨𝗟𝗞 𝗟𝗜𝗡𝗞𝗦 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗 ⚡</b></blockquote>\n"
    for idx, id_str in enumerate(ids, start=1):
        try:
            channel_id = int(id_str)
            chat = await client.get_chat(channel_id)
            await save_channel(channel_id)
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
@Bot.on_message(filters.command('genlink') & filters.private & is_owner_or_admin)
async def generate_link_command(client: Bot, message: Message):
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘 𝗟𝗜𝗡𝗞</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/genlink &lt;url&gt;</code></blockquote>",
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
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗟𝗜𝗡𝗞 𝗦𝗧𝗢𝗥𝗘𝗗 ⚡</b></blockquote>\n"
            f"<blockquote>◍ <b>ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"◍ <b>ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        await reply_ui(message, reply_text, reply_markup=close_btn)
    except Exception as e:
        await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗘𝗥𝗥𝗢𝗥 ❌</b></blockquote>\n<blockquote><code>{e}</code></blockquote>",
            reply_markup=close_btn
        )

# ─── CONNECTED CHANNELS LIST (/channels) ───────────────────────────────
@Bot.on_message(filters.command('channels') & is_owner_or_admin)
async def show_channel_ids(client: Bot, message: Message):
    channels = await get_channels()
    if not channels:
        return await reply_ui(
            message,
            f"{get_preview()}<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴄᴏɴɴᴇᴄᴛᴇᴅ ʏᴇᴛ.</blockquote>"
        )
    await send_channel_ids_page(client, message, channels, page=0)

async def send_channel_ids_page(client, message, channels, page, edit=False):
    PER_PAGE = 10
    total_pages = (len(channels) + PER_PAGE - 1) // PER_PAGE
    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE

    text = f"{get_preview()}<blockquote><b>➲ 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
    for idx, channel_id in enumerate(channels[start_idx:end_idx], start=start_idx + 1):
        try:
            chat = await client.get_chat(channel_id)
            text += f"<blockquote>▸ <b>{idx}. {chat.title}</b>\n◍ ɪᴅ: <code>{channel_id}</code></blockquote>\n"
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
