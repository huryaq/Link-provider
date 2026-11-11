# +++ LinkShare Ultra UI & FSub Engine +++
import asyncio
import base64
import random
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, OWNER_ID
from database.database import (
    add_user, total_users_count, full_userbase, del_user,
    is_admin, add_admin, remove_admin, list_admins,
    add_fsub_channel, remove_fsub_channel, get_fsub_channels,
    get_channel_by_encoded_link, get_channel_by_encoded_link2,
    get_original_link, get_fsub_mode, set_fsub_mode
)
from plugins.helpers import STICKERS, get_preview, get_start_text, get_about_text, get_fsub_text, setup_bot_commands

# Broadcast variables
cancel_lock = asyncio.Lock()
is_canceled = False

# ─── FSUB VERIFICATION HELPER ───────────────────────────────────────────
async def check_user_fsub(client: Bot, user_id: int):
    """Returns (is_all_joined, list_of_unjoined_channels)"""
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
            # If bot lacks permission or channel inaccessible, bypass to prevent blocking user
            pass
    return (len(unjoined) == 0), unjoined

async def build_fsub_keyboard(client: Bot, unjoined_channels: list, payload: str = ""):
    keyboard = []
    mode = await get_fsub_mode()
    btn_label = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if mode == "request" else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"
    
    for ch_id in unjoined_channels:
        try:
            chat = await client.get_chat(ch_id)
            invite_link = chat.invite_link
            if not invite_link:
                link_obj = await client.create_chat_invite_link(
                    chat_id=ch_id,
                    creates_join_request=(mode == "request")
                )
                invite_link = link_obj.invite_link
            keyboard.append([InlineKeyboardButton(f"{btn_label}", url=invite_link)])
        except Exception as e:
            print(f"Error fetching invite link for {ch_id}: {e}")
            
    retry_cb = f"check_sub_{payload}" if payload else "check_sub"
    keyboard.append([InlineKeyboardButton("↻ ᴛʀʏ ᴀɢᴀɪɴ ↻", callback_data=retry_cb)])
    return InlineKeyboardMarkup(keyboard)

# ─── START COMMAND HANDLER ──────────────────────────────────────────────
@Bot.on_message(filters.command('start') & filters.private)
async def start_handler(client: Bot, message: Message):
    user_id = message.from_user.id
    await add_user(user_id)

    # 1. Reaction on message
    try:
        await message.react("⚡")
    except Exception:
        pass

    # 2. Fast animated sticker
    try:
        sticker_msg = await message.reply_sticker(random.choice(STICKERS))
        await asyncio.sleep(1.2)
        await sticker_msg.delete()
    except Exception:
        pass

    text = message.text or ""
    payload = text.split(" ", 1)[1].strip() if len(text.split()) > 1 else ""

    # 3. Fast Checking Required Channels animation
    check_msg = await message.reply_text(
        "> ◍ ᴄʜᴇᴄᴋɪɴɢ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs...",
        parse_mode=ParseMode.MARKDOWN
    )
    await asyncio.sleep(0.4)

    # 4. FSub verification
    is_joined, unjoined = await check_user_fsub(client, user_id)
    await check_msg.delete()

    if not is_joined:
        reply_markup = await build_fsub_keyboard(client, unjoined, payload)
        return await message.reply_text(
            get_fsub_text(),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

    # 5. Deliver Link if payload exists
    if payload:
        return await send_access_link(client, message, payload)

    # 6. Default Welcome UI
    inline_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◈ ᴀʙᴏᴜᴛ ◈", callback_data="about"),
            InlineKeyboardButton("◈ ᴄʜᴀɴɴᴇʟs ◈", callback_data="channels")
        ],
        [InlineKeyboardButton("✖ ᴄʟᴏsᴇ ✖", callback_data="close")]
    ])
    
    await message.reply_text(
        get_start_text(),
        reply_markup=inline_buttons,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=False
    )

# ─── LINK CREATION ENGINE (BUG FIXED) ───────────────────────────────────
async def send_access_link(client: Bot, message: Message, payload: str):
    is_request = payload.startswith("req_")
    clean_payload = payload[4:] if is_request else payload

    if is_request:
        channel_id = await get_channel_by_encoded_link2(clean_payload)
    else:
        channel_id = await get_channel_by_encoded_link(clean_payload)

    if not channel_id:
        return await message.reply_text(
            f"{get_preview()}➲ **𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗢𝗥 𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗟𝗜𝗡𝗞** ❌\n\n"
            f"> ◍ ᴛʜɪs ʟɪɴᴋ ɪs ɴᴏ ʟᴏɴɢᴇʀ ᴠᴀʟɪᴅ ᴏʀ ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ.",
            parse_mode=ParseMode.MARKDOWN
        )

    # Check for direct original link
    original_link = await get_original_link(channel_id)
    if original_link:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("➪ ᴘʀᴏᴄᴇᴇᴅ ᴛᴏ ʟɪɴᴋ", url=original_link)]])
        return await message.reply_text(
            f"{get_preview()}➲ **ʏᴏᴜʀ ʟɪɴᴋ ɪs ʀᴇᴀᴅʏ** ⚡\n\n"
            f"> ◍ ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴄᴄᴇss ʏᴏᴜʀ ᴄᴏɴᴛᴇɴᴛ.",
            reply_markup=btn,
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        # Generate independent 5-minute temporary link (UTC based)
        invite = await client.create_chat_invite_link(
            chat_id=channel_id,
            expire_date=datetime.utcnow() + timedelta(minutes=5),
            creates_join_request=is_request
        )

        btn_text = "• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •" if is_request else "• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •"
        link_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_text, url=invite.invite_link)],
            [
                InlineKeyboardButton("↻ ʀᴇʟᴏᴀᴅ", callback_data=f"reload_{payload}"),
                InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")
            ]
        ])

        msg = await message.reply_text(
            f"{get_preview()}"
            f"➲ **𝗟𝗜𝗡𝗞 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬** ⚡\n\n"
            f"> ◍ ʏᴏᴜʀ ᴛᴇᴍᴘᴏʀᴀʀʏ ᴀᴄᴄᴇss ʟɪɴᴋ ɪs ʀᴇᴀᴅʏ.\n"
            f"> ◍ ᴠᴀʟɪᴅɪᴛʏ: `5 ᴍɪɴᴜᴛᴇs`\n\n"
            f"≡ **ɴᴏᴛᴇ:** ʟɪɴᴋ ᴡɪʟʟ ᴇxᴘɪʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.",
            reply_markup=link_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        # Auto delete warning after 5 minutes
        asyncio.create_task(auto_delete_message(msg, 300))

    except Exception as e:
        print(f"Error generating link for channel {channel_id}: {e}")
        await message.reply_text(
            f"{get_preview()}➲ **𝗘𝗥𝗥𝗢𝗥 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗜𝗡𝗚 𝗟𝗜𝗡𝗞** ❌\n\n"
            f"> ◍ ᴘʟᴇᴀsᴇ ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜᴇ ʙᴏᴛ ɪs ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴇ ᴛᴀʀɢᴇᴛ ᴄʜᴀɴɴᴇʟ.",
            parse_mode=ParseMode.MARKDOWN
        )

# ─── FSUB MANAGEMENT COMMANDS ───────────────────────────────────────────
@Bot.on_message(filters.command("add_fsub") & filters.private)
async def add_fsub_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text("<b>Usage:</b> `/add_fsub -100xxxxxxxxxx`")
    
    try:
        channel_id = int(args[1])
        chat = await client.get_chat(channel_id)
        channel_name = chat.title
    except Exception:
        return await message.reply_text("❌ **Invalid channel ID or bot is not an admin in that channel!**")

    added = await add_fsub_channel(channel_id)
    if not added:
        return await message.reply_text("❌ **Channel is already in FSub list!**")

    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])
    await message.reply_text(
        f"➲ **𝗙𝗦𝗨𝗕 𝗔𝗗𝗗𝗘𝗗**\n\n"
        f"> ◍ ᴄʜᴀɴɴᴇʟ: **{channel_name}**\n"
        f"> ◍ ɪᴅ: `{channel_id}`",
        reply_markup=close_btn,
        parse_mode=ParseMode.MARKDOWN
    )

@Bot.on_message(filters.command("del_fsub") & filters.private)
async def del_fsub_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text("<b>Usage:</b> `/del_fsub -100xxxxxxxxxx`")
    
    try:
        channel_id = int(args[1])
    except ValueError:
        return await message.reply_text("❌ **Channel ID must be an integer.**")

    removed = await remove_fsub_channel(channel_id)
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])
    if removed:
        await message.reply_text(
            f"➲ **𝗙𝗦𝗨𝗕 𝗥𝗘𝗠𝗢𝗩𝗘𝗗**\n\n"
            f"> ◍ ɪᴅ: `{channel_id}`",
            reply_markup=close_btn,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply_text("❌ **Channel not found in FSub list!**")

@Bot.on_message(filters.command("fsub_chnl") & filters.private)
async def list_fsub_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    channels = await get_fsub_channels()
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])

    if not channels:
        return await message.reply_text("➲ **𝗙𝗦𝗨𝗕 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦**\n\n> ◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴅᴅᴇᴅ ʏᴇᴛ.", reply_markup=close_btn, parse_mode=ParseMode.MARKDOWN)

    text = "➲ **𝗙𝗦𝗨𝗕 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦**\n\n"
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            title = chat.title
        except Exception:
            title = "Unknown Channel"
        text += f"> ▸ **{title}**\n> ◍ ɪᴅ: `{ch_id}`\n\n"

    await message.reply_text(text.strip(), reply_markup=close_btn, parse_mode=ParseMode.MARKDOWN)

@Bot.on_message(filters.command("req") & filters.private)
async def toggle_req_mode(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    current = await get_fsub_mode()
    new_mode = "direct" if current == "request" else "request"
    await set_fsub_mode(new_mode)

    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])
    await message.reply_text(
        f"➲ **𝗙𝗦𝗨𝗕 𝗠𝗢𝗗𝗘 𝗨𝗣𝗗𝗔𝗧𝗘𝗗**\n\n"
        f"> ◍ ɴᴇᴡ ᴍᴏᴅᴇ: `{new_mode.upper()}`\n"
        f"> ◍ ʙᴜᴛᴛᴏɴ: `{'• ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ •' if new_mode == 'request' else '• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •'}`",
        reply_markup=close_btn,
        parse_mode=ParseMode.MARKDOWN
    )

# ─── ADMIN MANAGEMENT COMMANDS ──────────────────────────────────────────
@Bot.on_message(filters.command("add_admin") & filters.private)
async def add_admin_cmd(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text("<b>Usage:</b> `/add_admin user_id`")
    
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.reply_text("❌ **Invalid User ID.**")

    await add_admin(user_id)
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])
    await message.reply_text(
        f"➲ **𝗔𝗗𝗠𝗜𝗡 𝗔𝗗𝗗𝗘𝗗**\n\n"
        f"> ◍ ɪᴅ: `{user_id}`",
        reply_markup=close_btn,
        parse_mode=ParseMode.MARKDOWN
    )

@Bot.on_message(filters.command("remove_admin") & filters.private)
async def remove_admin_cmd(client: Bot, message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text("<b>Usage:</b> `/remove_admin user_id`")

    try:
        user_id = int(args[1])
    except ValueError:
        return await message.reply_text("❌ **Invalid User ID.**")

    await remove_admin(user_id)
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])
    await message.reply_text(
        f"➲ **𝗔𝗗𝗠𝗜𝗡 𝗥𝗘𝗠𝗢𝗩𝗘𝗗**\n\n"
        f"> ◍ ɪᴅ: `{user_id}`",
        reply_markup=close_btn,
        parse_mode=ParseMode.MARKDOWN
    )

@Bot.on_message(filters.command("list_admin") & filters.private)
async def list_admin_cmd(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    admins = await list_admins()
    close_btn = InlineKeyboardMarkup([[InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]])

    text = "➲ **𝗔𝗗𝗠𝗜𝗡 𝗟𝗜𝗦𝗧**\n\n"
    for adm in admins:
        text += f"> ▸ ᴀᴅᴍɪɴ: `{adm}`\n"

    await message.reply_text(text, reply_markup=close_btn, parse_mode=ParseMode.MARKDOWN)

# ─── CALLBACK QUERY HANDLER ─────────────────────────────────────────────
@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if data == "close":
        await query.answer()
        return await query.message.delete()

    elif data == "about":
        await query.answer()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="start"), InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]
        ])
        return await query.message.edit_text(
            get_about_text(),
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

    elif data == "channels":
        await query.answer()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="start"), InlineKeyboardButton("✖ ᴄʟᴏsᴇ", callback_data="close")]
        ])
        chnl_text = (
            f"{get_preview()}"
            f"➲ **𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗗𝗜𝗥𝗘𝗖𝗧𝗢𝗥𝗬**\n\n"
            f"> ▸ **ᴀɴɪᴍᴇ**: [ʜᴇʟʟғɪʀᴇ ᴀᴄᴀᴅᴇᴍʏ](https://t.me/HellFire_Academy)\n"
            f"> ▸ **ᴏɴɢᴏɪɴɢ**: [ᴏɴɢᴏɪɴɢ ʜᴇʟʟғɪʀᴇ](https://t.me/Ongoing_HellFire_Academy)\n"
            f"> ▸ **ᴍᴏᴠɪᴇs**: [ᴍᴏᴠɪᴇ sᴘᴏᴛ](https://t.me/HellFire_Movies)\n"
            f"> ▸ **ɴᴇᴛᴡᴏʀᴋ**: [ᴏᴛᴀᴋᴜғʟɪx](https://t.me/HellFire_Network)"
        )
        return await query.message.edit_text(
            chnl_text,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

    elif data == "start":
        await query.answer()
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("◈ ᴀʙᴏᴜᴛ ◈", callback_data="about"),
                InlineKeyboardButton("◈ ᴄʜᴀɴɴᴇʟs ◈", callback_data="channels")
            ],
            [InlineKeyboardButton("✖ ᴄʟᴏsᴇ ✖", callback_data="close")]
        ])
        return await query.message.edit_text(
            get_start_text(),
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

    elif data.startswith("check_sub"):
        await query.answer("Checking channels...", show_alert=False)
        payload = data[10:] if len(data) > 9 and data.startswith("check_sub_") else ""
        
        is_joined, unjoined = await check_user_fsub(client, user_id)
        if not is_joined:
            reply_markup = await build_fsub_keyboard(client, unjoined, payload)
            try:
                return await query.message.edit_text(
                    get_fsub_text(),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False
                )
            except Exception:
                return

        # User is subscribed!
        await query.message.delete()
        if payload:
            return await send_access_link(client, query.message, payload)
        
        # Else send normal welcome message
        inline_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("◈ ᴀʙᴏᴜᴛ ◈", callback_data="about"),
                InlineKeyboardButton("◈ ᴄʜᴀɴɴᴇʟs ◈", callback_data="channels")
            ],
            [InlineKeyboardButton("✖ ᴄʟᴏsᴇ ✖", callback_data="close")]
        ])
        return await client.send_message(
            chat_id=query.message.chat.id,
            text=get_start_text(),
            reply_markup=inline_buttons,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

    elif data.startswith("reload_"):
        await query.answer("Reloading link...", show_alert=False)
        payload = data[7:]
        await query.message.delete()
        return await send_access_link(client, query.message, payload)

# ─── AUTO-DELETE HELPER ─────────────────────────────────────────────────
async def auto_delete_message(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass
