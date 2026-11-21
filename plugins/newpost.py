import asyncio
import base64
import html
import io
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
from plugins.helpers import sbtn, reply_ui, edit_ui, normalize_text, to_small_caps

PAGE_SIZE = 6
LINKS_PER_PAGE = 10

# ─── IN-MEMORY RAM INDEX FOR 0.1s INSTANT /get SEARCH ──────────────────
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

async def revoke_invite_after_5_minutes(client: Bot, channel_id: int, link: str, is_request: bool = False):
    await asyncio.sleep(300)
    try:
        await client.revoke_chat_invite_link(channel_id, link)
    except Exception:
        pass

# ─── HELPER: FETCH ALL CHANNELS SORTED A-Z (INCLUDING HIDDEN) ──────────
async def get_all_channels_sorted_az(client: Bot):
    docs = await channels_collection.find({"status": "active"}).to_list(None)
    items = []
    for d in docs:
        ch_id = d.get("channel_id")
        if not ch_id or d.get("original_link"):
            continue
        title = d.get("title") or _CHANNEL_INDEX.get(int(ch_id), {}).get("title")
        if not title:
            title = f"Channel {ch_id}"
        norm = normalize_text(title)
        first_char = norm[0].upper() if norm and norm[0].isalpha() else "#"
        code = d.get("encoded_link") or base64.urlsafe_b64encode(str(ch_id).encode()).decode()
        req_code = d.get("req_encoded_link") or code
        items.append({
            "channel_id": int(ch_id),
            "title": title,
            "norm": norm,
            "nospace": norm.replace(" ", ""),
            "letter": first_char,
            "code": code,
            "req_code": req_code,
            "hidden": bool(d.get("hidden_from_get", False))
        })
    items.sort(key=lambda x: (x["letter"] == "#", x["norm"]))
    return items

# ─── HIDE / UNHIDE CHANNELS FROM /get ──────────────────────────────────
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/hidech -100xxxxxxxxxx</code>\n"
            "<b>╰┈➤ <i>ɪɴᴠɪᴛᴇ ʟɪɴᴋs ᴡɪʟʟ sᴛɪʟʟ ᴡᴏʀᴋ ɴᴏʀᴍᴀʟʟʏ.</i></b></blockquote>",
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
        f"<blockquote><b>▸ {html.escape(title)}</b>\n"
        f"<b>◍ ɪᴅ:</b> <code>{channel_id}</code>\n\n"
        f"<b>╰┈➤ <i>ʜɪᴅᴅᴇɴ ғʀᴏᴍ /get &amp; ɪɴᴅᴇx. ᴀʟʟ ɪɴᴠɪᴛᴇ ʟɪɴᴋs ʀᴇᴍᴀɪɴ ᴀᴄᴛɪᴠᴇ!</i></b></blockquote>",
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/unhidech -100xxxxxxxxxx</code></blockquote>",
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
        f"<blockquote><b>▸ {html.escape(title)}</b>\n"
        f"<b>◍ ɪᴅ:</b> <code>{channel_id}</code>\n\n"
        f"<b>╰┈➤ <i>ɴᴏᴡ ᴠɪsɪʙʟᴇ ɪɴ /get &amp; ɪɴᴅᴇx!</i></b></blockquote>",
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
            "<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀʀᴇ ʜɪᴅᴅᴇɴ ғʀᴏᴍ /get.</b></blockquote>",
            reply_markup=close_btn
        )

    text = "<blockquote><b>「 ➲ 𝗛𝗜𝗗𝗗𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 🙈 」</b></blockquote>\n"
    for d in docs[:25]:
        ch_id = d.get("channel_id")
        title = html.escape(d.get("title") or "Unknown Channel")
        text += f"<blockquote><b>▸ {title}</b>\n<b>ɪᴅ:</b> <code>{ch_id}</code></blockquote>\n"
    await reply_ui(message, text.strip(), reply_markup=close_btn)

# ─── INSTANT 0.1s /get SEARCH ──────────────────────────────────────────
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/get &lt;ᴛɪᴛʟᴇ&gt;</code>\n"
            "<b>╰┈➤ <i>ᴇxᴀᴍᴘʟᴇ:</i></b> <code>/get naruto</code></blockquote>",
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
            "<blockquote><b>◍ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ɴᴀᴍᴇ.</b></blockquote>",
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
            f"<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟ ᴍᴀᴛᴄʜᴇᴅ:</b> <code>{html.escape(raw_query)}</code>\n"
            f"<b>╰┈➤ <i>sᴇᴀʀᴄʜᴇᴅ ɪɴ</i></b> <code>{elapsed_ms:.1f}ᴍs</code></blockquote>",
            reply_markup=close_btn,
            auto_delete_sec=120
        )

    total_m = len(matched_buttons)
    matched_buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])
    await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗦𝗘𝗔𝗥𝗖𝗛 𝗥𝗘𝗦𝗨𝗟𝗧𝗦 🔎 」</b></blockquote>\n"
        f"<blockquote><b>⟡ ғᴏᴜɴᴅ</b> <code>{total_m}</code> <b>ᴍᴀᴛᴄʜ(ᴇs) • ⚡</b> <code>{elapsed_ms:.1f}ᴍs</code>\n"
        f"<b>╰┈➤ <i>ᴛᴀᴘ ᴀɴʏ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ғᴏʀ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ:</i></b></blockquote>",
        reply_markup=InlineKeyboardMarkup(matched_buttons),
        auto_delete_sec=120
    )

# ─── SMART A-Z /links DIRECTORY (CLEAN SMALL-CAPS A B C BUTTONS) ───────
async def render_links_az_menu(client: Bot, message, edit: bool = False):
    items = await get_all_channels_sorted_az(client)
    close_btn = InlineKeyboardMarkup([[sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
    if not items:
        txt = (
            "<blockquote><b>「 ➲ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</b></blockquote>"
        )
        return await (edit_ui(message, txt, close_btn) if edit else reply_ui(message, txt, close_btn))

    present_letters = {it["letter"] for it in items}
    sorted_letters = sorted([k for k in present_letters if k != "#"])
    if "#" in present_letters:
        sorted_letters.append("#")

    buttons = []
    row = []
    for ltr in sorted_letters:
        row.append(sbtn(f"{to_small_caps(ltr)}", callback_data=f"linksaz_{ltr}_0", style="primary"))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        sbtn("◈ ᴀʟʟ", callback_data="linksaz_ALL_0", style="primary"),
        sbtn("📄 ᴇxᴘᴏʀᴛ .ᴛxᴛ", callback_data="linksexport", style="success")
    ])
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    text = (
        f"<blockquote><b>「 ➲ 𝗔-𝗭 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞𝗦 ({len(items)}) 」</b></blockquote>\n"
        f"<blockquote><b>◍ ᴛᴀᴘ ᴀɴʏ ʟᴇᴛᴛᴇʀ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴜᴍᴘ ɪɴsᴛᴀɴᴛʟʏ!\n"
        f"◍ ᴏʀ ᴜsᴇ <code>/links &lt;ɴᴀᴍᴇ&gt;</code> ᴛᴏ ғɪʟᴛᴇʀ ᴅɪʀᴇᴄᴛʟʏ.\n"
        f"╰┈➤ <i>ᴇxᴀᴍᴘʟᴇ:</i> <code>/links n</code> ᴏʀ <code>/links naruto</code></b></blockquote>"
    )
    markup = InlineKeyboardMarkup(buttons)
    if edit:
        await edit_ui(message, text, reply_markup=markup)
    else:
        await reply_ui(message, text, reply_markup=markup, auto_delete_sec=180)

async def render_links_filtered_page(client: Bot, message, items: list, label: str, cb_key: str, page: int, edit: bool = False):
    total_pages = max(1, (len(items) + LINKS_PER_PAGE - 1) // LINKS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start_idx = page * LINKS_PER_PAGE
    end_idx = start_idx + LINKS_PER_PAGE

    header = f"<blockquote><b>「 ➲ 𝗟𝗜𝗡𝗞𝗦 • {to_small_caps(label)} ({len(items)}) 」</b></blockquote>\n"
    body = "<blockquote expandable>"
    for i, it in enumerate(items[start_idx:end_idx], start=start_idx + 1):
        hid = " 🙈" if it["hidden"] else ""
        n_link = f"https://t.me/{client.username}?start={it['code']}"
        r_link = f"https://t.me/{client.username}?start=req_{it['req_code']}"
        body += (
            f"<b>{i}. {html.escape(it['title'])}{hid}</b>\n"
            f"▸ <b>ɴ:</b> <code>{n_link}</code>\n"
            f"▸ <b>ʀ:</b> <code>{r_link}</code>\n\n"
        )
    body = body.rstrip() + "</blockquote>\n"
    footer = f"<blockquote><b>◍ ᴘᴀɢᴇ <code>{page + 1}/{total_pages}</code> • ᴛᴀᴘ ʟɪɴᴋ ᴛᴏ ᴄᴏᴘʏ</b></blockquote>"

    buttons = []
    nav = []
    if page > 0:
        nav.append(sbtn("‹ ᴘʀᴇᴠ", callback_data=f"linksaz_{cb_key}_{page-1}", style="primary"))
    nav.append(sbtn("📚 ᴀ-ᴢ ᴍᴇɴᴜ", callback_data="linksaz_MENU", style="primary"))
    if page < total_pages - 1:
        nav.append(sbtn("ɴᴇxᴛ ›", callback_data=f"linksaz_{cb_key}_{page+1}", style="primary"))
    buttons.append(nav)
    buttons.append([sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")])

    full_text = header + body + footer
    markup = InlineKeyboardMarkup(buttons)
    if edit:
        await edit_ui(message, full_text, reply_markup=markup)
    else:
        await reply_ui(message, full_text, reply_markup=markup, auto_delete_sec=180)

@Bot.on_message(filters.command('links') & filters.private)
async def show_links(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return

    if len(message.command) >= 2:
        raw_q = " ".join(message.command[1:]).strip()
        q_norm = normalize_text(raw_q)
        items = await get_all_channels_sorted_az(client)

        if len(q_norm) == 1 and q_norm.isalpha():
            ltr = q_norm.upper()
            filtered = [it for it in items if it["letter"] == ltr]
            if not filtered:
                close_btn = InlineKeyboardMarkup([[sbtn("📚 ᴀ-ᴢ ᴍᴇɴᴜ", callback_data="linksaz_MENU", style="primary"), sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
                return await reply_ui(message, f"<blockquote><b>「 ❌ 𝗡𝗢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 𝗨𝗡𝗗𝗘𝗥 {ltr} 」</b></blockquote>", reply_markup=close_btn)
            return await render_links_filtered_page(client, message, filtered, ltr, ltr, page=0, edit=False)

        q_nospace = q_norm.replace(" ", "")
        filtered = [it for it in items if q_norm in it["norm"] or q_nospace in it["nospace"]]
        if not filtered:
            close_btn = InlineKeyboardMarkup([[sbtn("📚 ᴀ-ᴢ ᴍᴇɴᴜ", callback_data="linksaz_MENU", style="primary"), sbtn("✖ ᴄʟᴏsᴇ", callback_data="close", style="danger")]])
            return await reply_ui(
                message,
                f"<blockquote><b>「 ❌ 𝗡𝗢 𝗠𝗔𝗧𝗖𝗛 」</b></blockquote>\n"
                f"<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟ ᴍᴀᴛᴄʜᴇᴅ:</b> <code>{html.escape(raw_q)}</code></blockquote>",
                reply_markup=close_btn
            )
        return await render_links_filtered_page(client, message, filtered, raw_q.upper(), "ALL", page=0, edit=False)

    await render_links_az_menu(client, message, edit=False)

@Bot.on_callback_query(filters.regex(r"^linksaz_"))
async def links_az_callback(client: Bot, callback_query):
    if not await is_admin(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Admins only!", show_alert=True)
    await callback_query.answer()

    parts = callback_query.data.split("_")
    if parts[1] == "MENU":
        return await render_links_az_menu(client, callback_query.message, edit=True)

    key = parts[1]
    page = int(parts[2])
    items = await get_all_channels_sorted_az(client)

    if key == "ALL":
        return await render_links_filtered_page(client, callback_query.message, items, "ALL A-Z", "ALL", page, edit=True)

    filtered = [it for it in items if it["letter"] == key]
    await render_links_filtered_page(client, callback_query.message, filtered, key, key, page, edit=True)

@Bot.on_callback_query(filters.regex(r"^linksexport$"))
async def export_links_txt_cb(client: Bot, callback_query):
    if not await is_admin(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Admins only!", show_alert=True)
    await callback_query.answer("📄 Generating A-Z links file...", show_alert=False)

    items = await get_all_channels_sorted_az(client)
    lines = [f"=== ALL CHANNEL LINKS (A-Z) | TOTAL: {len(items)} ===\n"]
    current_ltr = None
    for idx, it in enumerate(items, start=1):
        if it["letter"] != current_ltr:
            current_ltr = it["letter"]
            lines.append(f"\n--- [ {current_ltr} ] ---")
        n_link = f"https://t.me/{client.username}?start={it['code']}"
        r_link = f"https://t.me/{client.username}?start=req_{it['req_code']}"
        hid_tag = " [HIDDEN FROM /get]" if it["hidden"] else ""
        lines.append(f"{idx}. {it['title']}{hid_tag} (ID: {it['channel_id']})")
        lines.append(f"   Normal : {n_link}")
        lines.append(f"   Request: {r_link}")

    bio = io.BytesIO("\n".join(lines).encode("utf-8"))
    bio.name = "All_Channel_Links_AZ.txt"
    await client.send_document(
        chat_id=callback_query.message.chat.id,
        document=bio,
        caption=f"<blockquote><b>「 📄 𝗔-𝗭 𝗟𝗜𝗡𝗞𝗦 𝗘𝗫𝗣𝗢𝗥𝗧𝗘𝗗 ⚡ 」</b></blockquote>\n<blockquote><b>◍ ᴛᴏᴛᴀʟ ᴄʜᴀɴɴᴇʟs:</b> <code>{len(items)}</code></blockquote>"
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/addch -100xxxxxxxxxx</code></blockquote>",
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
            f"<blockquote><b>▸ {html.escape(chat.title)}</b>\n"
            f"<b>◍ ɪᴅ:</b> <code>{channel_id}</code>\n\n"
            f"<b>◍ ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"<b>◍ ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        return await reply_ui(message, reply_text, reply_markup=close_btn)

    except UserNotParticipant:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n"
            "<blockquote><b>◍ ɪ ᴀᴍ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ ᴛʜɪs ᴄʜᴀɴɴᴇʟ. ᴘʟᴇᴀsᴇ ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ғɪʀsᴛ.</b></blockquote>",
            reply_markup=close_btn
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await set_channel(client, message)
    except Exception as e:
        return await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n<blockquote><code>{html.escape(str(e))}</code></blockquote>",
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/delch -100xxxxxxxxxx</code></blockquote>",
            reply_markup=close_btn
        )

    await delete_channel(channel_id)
    remove_from_ram_index(channel_id)
    return await reply_ui(
        message,
        f"<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗥𝗘𝗠𝗢𝗩𝗘𝗗 」</b></blockquote>\n"
        f"<blockquote><b>◍ ɪᴅ:</b> <code>{channel_id}</code></blockquote>",
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
            "<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</b></blockquote>"
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
        "<blockquote><b>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ᴀɴ ɪɴsᴛᴀɴᴛ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</b></blockquote>"
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
            "<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴠᴀɪʟᴀʙʟᴇ. ᴜsᴇ <code>/addch</code> ᴛᴏ ᴀᴅᴅ ᴏɴᴇ.</b></blockquote>"
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
        "<blockquote><b>◍ sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇǫᴜᴇsᴛ ᴀ ᴛᴇᴍᴘᴏʀᴀʀʏ ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</b></blockquote>"
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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/bulklink &lt;id1&gt; &lt;id2&gt; ...</code></blockquote>",
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
                f"<blockquote><b>▸ {idx}. {html.escape(chat.title)}</b>\n"
                f"<b>◍ ɪᴅ:</b> <code>{channel_id}</code>\n"
                f"<b>◍ ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
                f"<b>◍ ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>\n"
            )
        except Exception as e:
            reply_text += f"<blockquote><b>▸ {idx}. {id_str}</b> (ᴇʀʀᴏʀ: <code>{html.escape(str(e))}</code>)</blockquote>\n"

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
            "<blockquote><b>◍ ᴜsᴀɢᴇ:</b> <code>/genlink &lt;url&gt;</code></blockquote>",
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
            f"<blockquote><b>◍ ɴᴏʀᴍᴀʟ:</b> <code>{normal_link}</code>\n"
            f"<b>◍ ʀᴇǫᴜᴇsᴛ:</b> <code>{request_link}</code></blockquote>"
        )
        await reply_ui(message, reply_text, reply_markup=close_btn)
    except Exception as e:
        await reply_ui(
            message,
            f"<blockquote><b>「 ➲ 𝗘𝗥𝗥𝗢𝗥 ❌ 」</b></blockquote>\n<blockquote><code>{html.escape(str(e))}</code></blockquote>",
            reply_markup=close_btn
        )

# ─── CONNECTED CHANNELS LIST (/channels) ───────────────────────────────
@Bot.on_message(filters.command('channels') & filters.private)
async def show_channel_ids(client: Bot, message: Message):
    if not await is_admin(message.from_user.id):
        return
    items = await get_all_channels_sorted_az(client)
    if not items:
        return await reply_ui(
            message,
            "<blockquote><b>「 ➲ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 」</b></blockquote>\n"
            "<blockquote><b>◍ ɴᴏ ᴄʜᴀɴɴᴇʟs ᴄᴏɴɴᴇᴄᴛᴇᴅ ʏᴇᴛ.</b></blockquote>"
        )
    await send_channel_ids_page(client, message, items, page=0)

async def send_channel_ids_page(client, message, items, page, edit=False):
    PER_PAGE = 12
    total_pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE

    text = f"<blockquote><b>「 ➲ 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 ({len(items)}) 」</b></blockquote>\n<blockquote expandable>"
    for idx, it in enumerate(items[start_idx:end_idx], start=start_idx + 1):
        hid = " 🙈" if it["hidden"] else ""
        text += f"<b>{idx}. {html.escape(it['title'])}{hid}</b>\n◍ <code>{it['channel_id']}</code>\n\n"
    text = text.rstrip() + f"</blockquote>\n<blockquote><b>◍ ᴘᴀɢᴇ <code>{page + 1}/{total_pages}</code></b></blockquote>"

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
    items = await get_all_channels_sorted_az(client)
    await send_channel_ids_page(client, callback_query.message, items, page, edit=True)
