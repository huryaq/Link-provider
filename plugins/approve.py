import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.types import Message, ChatJoinRequest, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant
from config import CHAT_ID, APPROVED
from database.database import set_approval_off, is_approval_off, is_admin
from plugins.helpers import get_preview, sbtn, reply_ui

# Default settings
APPROVAL_WAIT_TIME = 5  # seconds
AUTO_APPROVE_ENABLED = True

@Client.on_chat_join_request((filters.group | filters.channel) & filters.chat(CHAT_ID) if CHAT_ID else (filters.group | filters.channel))
async def autoapprove(client: Client, message: ChatJoinRequest):
    global AUTO_APPROVE_ENABLED
    if not AUTO_APPROVE_ENABLED:
        return

    chat = message.chat
    user = message.from_user

    if await is_approval_off(chat.id):
        return

    await asyncio.sleep(APPROVAL_WAIT_TIME)

    try:
        member = await client.get_chat_member(chat.id, user.id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return
    except UserNotParticipant:
        pass
    except Exception:
        pass

    try:
        await client.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
    except Exception as e:
        print(f"Auto-approve error in {chat.id}: {e}")
        return

    if APPROVED == "on":
        try:
            invite_link = chat.invite_link or await client.export_chat_invite_link(chat.id)
            buttons = [
                [sbtn(f"• ᴏᴘᴇɴ {chat.title} •", url=invite_link, style="success")],
                [
                    sbtn("◈ ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ ᴋᴀʀᴀsᴜ", url="https://t.me/Karasu_07", style="primary"),
                    sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")
                ]
            ]
            text = (
                f"{get_preview()}"
                f"<blockquote><b>➲ 𝗥𝗘𝗤𝗨𝗘𝗦𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 ⚡</b></blockquote>\n"
                f"<blockquote>◍ ʜᴇʏ {user.mention}!\n"
                f"◍ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ᴛᴏ ᴊᴏɪɴ <b>{chat.title}</b> ʜᴀs ʙᴇᴇɴ ᴀᴘᴘʀᴏᴠᴇᴅ ɪɴsᴛᴀɴᴛʟʏ!</blockquote>"
            )
            await client.send_message(
                chat_id=user.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Could not send approval DM to {user.id}: {e}")

# ─── AUTO-APPROVE ADMIN COMMANDS ───────────────────────────────────────
@Client.on_message(filters.command("reqtime") & filters.private)
async def set_reqtime(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    global APPROVAL_WAIT_TIME
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if len(message.command) != 2 or not message.command[1].isdigit():
        return await reply_ui(
            message,
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗥𝗘𝗤𝗨𝗘𝗦𝗧 𝗧𝗜𝗠𝗘𝗥</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/reqtime &lt;sᴇᴄᴏɴᴅs&gt;</code></blockquote>",
            reply_markup=close_btn
        )

    APPROVAL_WAIT_TIME = int(message.command[1])
    await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗧𝗜𝗠𝗘𝗥 𝗨𝗣𝗗𝗔𝗧𝗘𝗗 ⚡</b></blockquote>\n"
        f"<blockquote>◍ ᴀᴘᴘʀᴏᴠᴀʟ ᴅᴇʟᴀʏ: <code>{APPROVAL_WAIT_TIME} sᴇᴄᴏɴᴅs</code></blockquote>",
        reply_markup=close_btn
    )

@Client.on_message(filters.command("reqmode") & filters.private)
async def toggle_reqmode(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    global AUTO_APPROVE_ENABLED
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if len(message.command) != 2 or message.command[1].lower() not in ["on", "off"]:
        return await reply_ui(
            message,
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗔𝗨𝗧𝗢-𝗔𝗣𝗣𝗥𝗢𝗩𝗘 𝗠𝗢𝗗𝗘</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/reqmode on</code> ᴏʀ <code>/reqmode off</code></blockquote>",
            reply_markup=close_btn
        )

    mode = message.command[1].lower()
    AUTO_APPROVE_ENABLED = (mode == "on")
    status_str = "𝗘𝗡𝗔𝗕𝗟𝗘𝗗 ✅" if AUTO_APPROVE_ENABLED else "𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗 ❌"
    await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗔𝗨𝗧𝗢-𝗔𝗣𝗣𝗥𝗢𝗩𝗘 {status_str}</b></blockquote>\n"
        f"<blockquote>◍ sᴛᴀᴛᴜs: <code>{mode.upper()}</code></blockquote>",
        reply_markup=close_btn
    )

@Client.on_message(filters.command("approveoff") & filters.private)
async def approve_off_command(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if len(message.command) != 2 or not message.command[1].lstrip("-").isdigit():
        return await reply_ui(
            message,
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘 𝗢𝗙𝗙</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/approveoff -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    channel_id = int(message.command[1])
    await set_approval_off(channel_id, True)
    await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗔𝗨𝗧𝗢-𝗔𝗣𝗣𝗥𝗢𝗩𝗘 𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗 ❌</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )

@Client.on_message(filters.command("approveon") & filters.private)
async def approve_on_command(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])

    if len(message.command) != 2 or not message.command[1].lstrip("-").isdigit():
        return await reply_ui(
            message,
            f"{get_preview()}"
            f"<blockquote><b>➲ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘 𝗢𝗡</b></blockquote>\n"
            f"<blockquote>◍ ᴜsᴀɢᴇ: <code>/approveon -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    channel_id = int(message.command[1])
    await set_approval_off(channel_id, False)
    await reply_ui(
        message,
        f"{get_preview()}"
        f"<blockquote><b>➲ 𝗔𝗨𝗧𝗢-𝗔𝗣𝗣𝗥𝗢𝗩𝗘 𝗘𝗡𝗔𝗕𝗟𝗘𝗗 ⚡</b></blockquote>\n"
        f"<blockquote>◍ ɪᴅ: <code>{channel_id}</code></blockquote>",
        reply_markup=close_btn
    )
