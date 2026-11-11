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
from config import ADMINS, OWNER_ID
from database.database import (
    add_user, total_users_count, full_userbase, del_user,
    is_admin, add_admin, remove_admin, list_admins,
    add_fsub_channel, remove_fsub_channel, get_fsub_channels,
    get_channel_by_encoded_link, get_channel_by_encoded_link2,
    get_original_link, get_fsub_mode, set_fsub_mode,
    save_encoded_link, save_encoded_link2
)
from helper_func import get_readable_time
from plugins.helpers import (
    STICKERS, sbtn, reply_ui, edit_ui, send_ui,
    get_start_text, get_about_text, get_help_text,
    get_directory_text, get_fsub_text, get_leave_text
)
from plugins.newpost import perform_channel_search

# Broadcast & Interactive Search states
cancel_lock = asyncio.Lock()
is_canceled = False
waiting_for_search = set()

# ─── MAIN START MENU KEYBOARD ───────────────────────────────────────────
def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            sbtn("◈ ᴀʙᴏᴜᴛ", callback_data="about", style="primary"),
            sbtn("🔎 ᴅɪʀᴇᴄᴛᴏʀʏ", callback_data="directory", style="primary")
        ],
        [
            sbtn("? ʜᴇʟᴘ", callback_data="help", style="primary"),
            sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
        ]
    ])

# ─── FSUB VERIFICATION HELPERS ──────────────────────────────────────────
async def check_user_fsub(client: Bot, user_id: int):
    fsub_channels = await get_fsub_channels()
    if not fsub_channels:
        return True, []

    unjoined = []
    for ch_id in fsub_channels:
        try:
            member = await client.get_chat_member(ch_id, user_id)
            if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]:
                unjoined.append(ch_id)
        except UserNotParticipant:
            unjoined.append(ch_id)
        except Exception:
            pass
    return (len(unjoined) == 0), unjoined

async def build_fsub_keyboard(client: Bot, unjoined_channels: list, payload: str = "") -> InlineKeyboardMarkup:
    keyboard = []
    mode = await get_fsub_mode()
    btn_label = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if mode == "request" else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"

    row = []
    for ch_id in unjoined_channels:
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

            row.append(sbtn(btn_label, url=inv_url, style="primary"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        except Exception as e:
            print(f"FSub link error for {ch_id}: {e}")

    if row:
        keyboard.append(row)

    retry_cb = f"check_sub_{payload}" if payload else "check_sub"
    keyboard.append([sbtn("↻ ᴛʀʏ ᴀɢᴀɪɴ ↻", callback_data=retry_cb, style="success")])
    return InlineKeyboardMarkup(keyboard)

# ─── /start COMMAND HANDLER ─────────────────────────────────────────────
@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Bot, message: Message):
    user_id = message.from_user.id
    waiting_for_search.discard(user_id)
    await add_user(user_id)

    # 1. React on user's /start message
    try:
        await message.react("⚡")
    except Exception:
        pass

    # 2. Send random sticker for ~1.1s and auto-delete
    try:
        stk = await message.reply_sticker(random.choice(STICKERS))
        await asyncio.sleep(1.1)
        await stk.delete()
    except Exception:
        pass

    text = message.text or ""
    payload = text.split(" ", 1)[1].strip() if len(text.split()) > 1 else ""

    # 3. Checking required channels message (Quote + Small Caps)
    check_msg = await message.reply_text(
        "<blockquote>◍ ᴄʜᴇᴄᴋɪɴɢ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs...</blockquote>",
        parse_mode=ParseMode.HTML
    )
    await asyncio.sleep(0.4)

    # 4. Verify Force Sub
    is_joined, unjoined = await check_user_fsub(client, user_id)
    try:
        await check_msg.delete()
    except Exception:
        pass

    if not is_joined:
        fsub_markup = await build_fsub_keyboard(client, unjoined, payload)
        fsub_msg = await reply_ui(message, get_fsub_text(), reply_markup=fsub_markup)
        asyncio.create_task(auto_delete(fsub_msg, 300))
        return

    # 5. If user opened a channel/file link
    if payload:
        return await deliver_channel_link(client, message, payload)

    # 6. Normal Start Message
    start_msg = await reply_ui(message, get_start_text(), reply_markup=get_main_keyboard())
    asyncio.create_task(auto_delete(start_msg, 600))

# ─── INTERACTIVE DIRECTORY SEARCH LISTENER ──────────────────────────────
@Bot.on_message(filters.private & filters.text & ~filters.command([
    'start', 'get', 'add_fsub', 'del_fsub', 'fsub_chnl', 'req',
    'addch', 'setchannel', 'delch', 'delchannel', 'ch_links', 'reqlink',
    'links', 'bulklink', 'genlink', 'channels', 'add_admin', 'remove_admin',
    'list_admin', 'status', 'broadcast', 'cancel', 'stats', 'reqtime',
    'reqmode', 'approveoff', 'approveon'
]))
async def interactive_search_listener(client: Bot, message: Message):
    user_id = message.from_user.id
    if user_id not in waiting_for_search:
        return
    waiting_for_search.discard(user_id)
    query_str = message.text.strip()
    await perform_channel_search(client, message, query_str)

# ─── LINK GENERATOR & DELIVERY (100% TIMEZONE & OLD-LINK SAFE) ──────────
async def deliver_channel_link(client: Bot, message: Message, payload: str):
    is_request = payload.startswith("req_")
    clean_code = payload[4:].strip() if is_request else payload.strip()

    if is_request:
        channel_id = await get_channel_by_encoded_link2(clean_code)
        if not channel_id:
            channel_id = await get_channel_by_encoded_link(clean_code)
    else:
        channel_id = await get_channel_by_encoded_link(clean_code)
        if not channel_id:
            channel_id = await get_channel_by_encoded_link2(clean_code)

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if not channel_id:
        return await reply_ui(
            message,
            f"<blockquote><b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗢𝗥 𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗟𝗜𝗡𝗞</b></blockquote>\n"
            f"<blockquote>◍ ᴛʜɪs ʟɪɴᴋ ɪs ɪɴᴠᴀʟɪᴅ ᴏʀ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴄᴛɪᴠᴇ.</blockquote>",
            reply_markup=close_btn
        )

    # Check if it's a /genlink stored URL
    original_link = await get_original_link(channel_id)
    if original_link:
        markup = InlineKeyboardMarkup([
            [sbtn("➪ ᴏᴘᴇɴ ʟɪɴᴋ", url=original_link, style="success")],
            [sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]
        ])
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗟𝗜𝗡𝗞 𝗨𝗡𝗟𝗢𝗖𝗞𝗘𝗗 ⚡</b></blockquote>\n"
            f"<blockquote>◍ ʏᴏᴜʀ ᴘʀᴏᴛᴇᴄᴛᴇᴅ ʟɪɴᴋ ɪs ʀᴇᴀᴅʏ.\n"
            f"◍ ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴘʀᴏᴄᴇᴇᴅ.</blockquote>",
            reply_markup=markup
        )

    try:
        chat = await client.get_chat(channel_id)
        expire_time = datetime.now(timezone.utc) + timedelta(minutes=5)

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
            is_request = False

        join_label = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if is_request else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"
        markup = InlineKeyboardMarkup([
            [sbtn(join_label, url=invite.invite_link, style="success")],
            [
                sbtn("↻ ʀᴇʟᴏᴀᴅ", callback_data=f"reload_{payload}", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])

        sent = await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗧𝗘𝗠𝗣𝗢𝗥𝗔𝗥𝗬 𝗜𝗡𝗩𝗜𝗧𝗘 𝗥𝗘𝗔𝗗𝗬 ⚡</b></blockquote>\n"
            f"<blockquote>▸ <b>{chat.title}</b>\n"
            f"◍ ᴇxᴘɪʀᴇs ɪɴ: <code>5 ᴍɪɴᴜᴛᴇs</code>\n"
            f"◍ ᴍᴏᴅᴇ: <code>{'ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ' if is_request else 'ᴅɪʀᴇᴄᴛ ᴊᴏɪɴ'}</code>\n\n"
            f"≡ <i>ɪғ ᴛʜᴇ ʟɪɴᴋ ᴇxᴘɪʀᴇs, ᴄʟɪᴄᴋ ʀᴇʟᴏᴀᴅ ʙᴇʟᴏᴡ.</i></blockquote>",
            reply_markup=markup
        )
        asyncio.create_task(auto_delete(sent, 300))

    except Exception as e:
        print(f"Invite creation error for {channel_id}: {e}")
        await reply_ui(
            message,
            f"<blockquote><b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗢𝗥 𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗟𝗜𝗡𝗞</b></blockquote>\n"
            f"<blockquote>◍ ᴜɴᴀʙʟᴇ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ɪɴᴠɪᴛᴇ ʟɪɴᴋ. ᴘʟᴇᴀsᴇ ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜᴇ ʙᴏᴛ ʜᴀs <b>'Invite Users via Link'</b> ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴ ɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ.</blockquote>",
            reply_markup=close_btn
        )

# ─── CHANNEL LEAVE WARNING DETECTOR ─────────────────────────────────────
@Bot.on_chat_member_updated()
async def fsub_leave_alert(client: Bot, update: ChatMemberUpdated):
    if not update.old_chat_member or not update.new_chat_member:
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    if old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and new_status == ChatMemberStatus.LEFT:
        fsub_channels = await get_fsub_channels()
        if update.chat.id in fsub_channels:
            user = update.from_user
            if not user or user.is_bot:
                return
            try:
                mode = await get_fsub_mode()
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
                btn = InlineKeyboardMarkup([
                    [sbtn("• ʀᴇᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=inv.invite_link, style="success")],
                    [sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]
                ])
                await send_ui(
                    chat_id=user.id,
                    text=get_leave_text(update.chat.title),
                    reply_markup=btn
                )
            except Exception:
                pass

# ─── FSUB COMMANDS (/add_fsub, /del_fsub, /fsub_chnl, /req) ─────────────
@Bot.on_message(filters.command("add_fsub") & filters.private)
async def add_fsub_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2:
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗔𝗗𝗗 𝗙𝗦𝗨𝗕</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/add_fsub -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    try:
        channel_id = int(message.command[1])
        chat = await client.get_chat(channel_id)
        channel_name = chat.title
    except Exception:
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗘𝗥𝗥𝗢𝗥 ❌</b></blockquote>\n"
            f"<blockquote>◍ ɪɴᴠᴀʟɪᴅ ɪᴅ ᴏʀ ʙᴏᴛ ɪs ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ/ɢʀᴏᴜᴘ!</blockquote>",
            reply_markup=close_btn
        )

    await add_fsub_channel(channel_id)
    await reply_ui(
        message,
        f"<blockquote><b>➲ 𝗙𝗦𝗨𝗕 𝗔𝗗𝗗𝗘𝗗</b></blockquote>\n"
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
            f"<blockquote><b>➲ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗙𝗦𝗨𝗕</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/del_fsub -100xxxxxxxxxx</code></blockquote>",
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
    if not removed:
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗 ❌</b></blockquote>\n"
            f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code> ɪs ɴᴏᴛ ɪɴ ғsᴜʙ ʟɪsᴛ.</blockquote>",
            reply_markup=close_btn
        )

    await reply_ui(
        message,
        f"<blockquote><b>➲ 𝗙𝗦𝗨𝗕 𝗥𝗘𝗠𝗢𝗩𝗘𝗗</b></blockquote>\n"
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
            f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
            f"<blockquote>◍ ɴᴏ ғsᴜʙ ᴄʜᴀɴɴᴇʟs ᴏʀ ɢʀᴏᴜᴘs ᴀᴅᴅᴇᴅ ʏᴇᴛ.</blockquote>",
            reply_markup=close_btn
        )

    text = f"<blockquote><b>➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b></blockquote>\n"
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

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    await reply_ui(
        message,
        f"<blockquote><b>➲ 𝗙𝗦𝗨𝗕 𝗠𝗢𝗗𝗘 𝗨𝗣𝗗𝗔𝗧𝗘𝗗 ⚡</b></blockquote>\n"
        f"<blockquote>◍ ᴍᴏᴅᴇ: <code>{new_mode.upper()}</code>\n"
        f"◍ ʙᴜᴛᴛᴏɴ: <code>{'• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •' if new_mode == 'request' else '• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •'}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── ADMIN MANAGEMENT (/add_admin, /remove_admin, /list_admin) ──────────
@Bot.on_message(filters.command("add_admin") & filters.private)
async def add_admin_handler(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗔𝗗𝗗 𝗔𝗗𝗠𝗜𝗡</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/add_admin &lt;user_id&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    adm_id = int(message.command[1])
    await add_admin(adm_id)
    await reply_ui(
        message,
        f"<blockquote><b>➲ 𝗔𝗗𝗠𝗜𝗡 𝗔𝗗𝗗𝗘𝗗 ⚡</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{adm_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("remove_admin") & filters.private)
async def remove_admin_handler(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await reply_ui(
            message,
            f"<blockquote><b>➲ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗔𝗗𝗠𝗜𝗡</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/remove_admin &lt;user_id&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    adm_id = int(message.command[1])
    await remove_admin(adm_id)
    await reply_ui(
        message,
        f"<blockquote><b>➲ 𝗔𝗗𝗠𝗜𝗡 𝗥𝗘𝗠𝗢𝗩𝗘𝗗</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{adm_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Bot.on_message(filters.command("list_admin") & filters.private)
async def list_admin_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    admins = await list_admins()
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    text = f"<blockquote><b>➲ 𝗔𝗗𝗠𝗜𝗡𝗦 𝗟𝗜𝗦𝗧</b></blockquote>\n"
    for adm_id in admins:
        text += f"<blockquote>▸ ᴀᴅᴍɪɴ\nɪᴅ: <code>{adm_id}</code></blockquote>\n"

    await reply_ui(message, text.strip(), reply_markup=close_btn)

# ─── STATUS & BROADCAST COMMANDS ────────────────────────────────────────
@Bot.on_message(filters.command('status') & filters.private)
async def status_handler(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    start_t = time.time()
    temp = await message.reply_text("<blockquote>◍ ᴄʜᴇᴄᴋɪɴɢ sʏsᴛᴇᴍ sᴛᴀᴛᴜs...</blockquote>", parse_mode=ParseMode.HTML)
    ping_ms = (time.time() - start_t) * 1000

    total_users = await total_users_count()
    delta = datetime.now() - client.uptime
    uptime_str = get_readable_time(delta.seconds)

    await edit_ui(
        temp,
        f"<blockquote><b>➲ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 ⚡</b></blockquote>\n"
        f"<blockquote>◍ <b>ᴜsᴇʀs:</b> <code>{total_users}</code>\n"
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
            f"<blockquote><b>➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗚𝗨𝗜𝗗𝗘</b></blockquote>\n"
            f"<blockquote>◍ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ:\n"
            f"▸ <code>/broadcast</code>\n"
            f"▸ <code>/broadcast pin</code>\n"
            f"▸ <code>/broadcast delete 30</code>\n"
            f"▸ <code>/broadcast silent</code></blockquote>",
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
        f"<blockquote><b>➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧𝗜𝗡𝗚... ⚡</b></blockquote>\n"
        f"<blockquote>◍ sᴇɴᴅɪɴɢ ᴛᴏ <code>{total}</code> ᴜsᴇʀs...</blockquote>"
    )

    for i, chat_id in enumerate(query, start=1):
        async with cancel_lock:
            if is_canceled:
                return await edit_ui(
                    pls_wait,
                    f"<blockquote><b>➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗔𝗡𝗖𝗘𝗟𝗟𝗘𝗗 ❌</b></blockquote>",
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
        f"<blockquote><b>➲ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 ✅</b></blockquote>\n"
        f"<blockquote>◍ <b>ᴛᴏᴛᴀʟ:</b> <code>{total}</code>\n"
        f"◍ <b>sᴜᴄᴄᴇss:</b> <code>{successful}</code>\n"
        f"◍ <b>ʙʟᴏᴄᴋᴇᴅ:</b> <code>{blocked}</code>\n"
        f"◍ <b>ᴅᴇʟᴇᴛᴇᴅ:</b> <code>{deleted}</code>\n"
        f"◍ <b>ғᴀɪʟᴇᴅ:</b> <code>{unsuccessful}</code></blockquote>",
        reply_markup=close_btn
    )

# ─── ALL UI CALLBACK QUERIES ────────────────────────────────────────────
@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if data == "close":
        waiting_for_search.discard(user_id)
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        try:
            if query.message.reply_to_message:
                await query.message.reply_to_message.delete()
        except Exception:
            pass

    elif data == "about":
        waiting_for_search.discard(user_id)
        await query.answer()
        markup = InlineKeyboardMarkup([
            [
                sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])
        await edit_ui(query.message, get_about_text(), reply_markup=markup)

    elif data == "directory":
        waiting_for_search.discard(user_id)
        await query.answer()
        markup = InlineKeyboardMarkup([
            [sbtn("🔎 sᴇᴀʀᴄʜ ᴄʜᴀɴɴᴇʟ", callback_data="search_ch", style="success")],
            [
                sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])
        await edit_ui(query.message, get_directory_text(), reply_markup=markup)

    elif data == "search_ch":
        waiting_for_search.add(user_id)
        await query.answer("Type channel name in chat!", show_alert=False)
        markup = InlineKeyboardMarkup([
            [
                sbtn("‹ ʙᴀᴄᴋ", callback_data="directory", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])
        await edit_ui(
            query.message,
            f"<blockquote><b>➲ 𝗦𝗘𝗔𝗥𝗖𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 🔎</b></blockquote>\n"
            f"<blockquote>◍ ᴘʟᴇᴀsᴇ <b>ᴛʏᴘᴇ ᴀɴᴅ sᴇɴᴅ</b> ᴛʜᴇ ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ ɪɴ ᴄʜᴀᴛ ɴᴏᴡ!\n"
            f"◍ ᴇxᴀᴍᴘʟᴇ: <code>naruto</code> ᴏʀ <code>hellfire</code></blockquote>",
            reply_markup=markup
        )

    elif data.startswith("getch_"):
        waiting_for_search.discard(user_id)
        await query.answer("⚡ Generating invite link...", show_alert=False)
        ch_id = int(data.split("_", 1)[1])

        is_joined, unjoined = await check_user_fsub(client, user_id)
        code = await save_encoded_link(ch_id)
        await save_encoded_link2(ch_id, code)
        mode = await get_fsub_mode()
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
        waiting_for_search.discard(user_id)
        await query.answer()
        markup = InlineKeyboardMarkup([
            [
                sbtn("‹ ʙᴀᴄᴋ", callback_data="start", style="primary"),
                sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
            ]
        ])
        await edit_ui(query.message, get_help_text(), reply_markup=markup)

    elif data in ["start", "home"]:
        waiting_for_search.discard(user_id)
        await query.answer()
        await edit_ui(query.message, get_start_text(), reply_markup=get_main_keyboard())

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

        await reply_ui(query.message, get_start_text(), reply_markup=get_main_keyboard())

    elif data.startswith("reload_"):
        await query.answer("↻ Generating fresh link...", show_alert=False)
        payload = data[7:]
        try:
            await query.message.delete()
        except Exception:
            pass
        await deliver_channel_link(client, query.message, payload)

async def auto_delete(msg, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass
