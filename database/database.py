import motor.motor_asyncio
import base64
from config import DB_URI, DB_NAME, ADMINS, OWNER_ID
from datetime import datetime
from typing import List, Optional, Union

dbclient = motor.motor_asyncio.AsyncIOMotorClient(DB_URI)
database = dbclient[DB_NAME]

# Collections
user_data = database['users']
channels_collection = database['channels']
fsub_channels_collection = database['fsub_channels']
admins_collection = database['admins']
removed_admins_collection = database['removed_admins']
settings_collection = database['settings']

# --- MEMORY CACHE ---
_cached_user_count = 0
_last_count_update = None
_cache_expiry_seconds = 300

async def add_user(user_id: int) -> bool:
    global _cached_user_count
    if not isinstance(user_id, int) or user_id <= 0:
        return False
    try:
        result = await user_data.update_one(
            {'_id': user_id},
            {'$setOnInsert': {'created_at': datetime.utcnow()}},
            upsert=True
        )
        if result.upserted_id is not None:
            if isinstance(_cached_user_count, int) and _cached_user_count > 0:
                _cached_user_count += 1
            return True
        return False
    except Exception:
        return False

async def present_user(user_id: int) -> bool:
    if not isinstance(user_id, int):
        return False
    return bool(await user_data.find_one({'_id': user_id}, projection={'_id': 1}))

async def total_users_count() -> Union[int, str]:
    global _cached_user_count, _last_count_update
    now = datetime.utcnow()
    if _last_count_update and (now - _last_count_update).total_seconds() < _cache_expiry_seconds:
        return _cached_user_count
    try:
        count = await user_data.count_documents({})
        _cached_user_count = count
        _last_count_update = now
        return count
    except Exception:
        if _cached_user_count > 0:
            return _cached_user_count
        return "Checking..."

async def full_userbase() -> List[int]:
    try:
        user_docs = user_data.find({}, projection={'_id': 1})
        return [doc['_id'] async for doc in user_docs]
    except Exception:
        return []

async def del_user(user_id: int) -> bool:
    try:
        result = await user_data.delete_one({'_id': user_id})
        return result.deleted_count > 0
    except Exception:
        return False

# ─── FIXED ADMIN MANAGEMENT (WORKS EVEN FOR CONFIG ADMINS) ─────────────
async def is_admin(user_id: int) -> bool:
    uid = int(user_id)
    if uid == OWNER_ID:
        return True
    try:
        if await removed_admins_collection.find_one({'_id': uid}):
            return False
        if uid in ADMINS:
            return True
        return bool(await admins_collection.find_one({'_id': uid}))
    except Exception:
        return uid in ADMINS

async def add_admin(user_id: int) -> bool:
    uid = int(user_id)
    try:
        await removed_admins_collection.delete_one({'_id': uid})
        await admins_collection.update_one({'_id': uid}, {'$set': {'_id': uid}}, upsert=True)
        if uid not in ADMINS:
            ADMINS.append(uid)
        return True
    except Exception:
        return False

async def remove_admin(user_id: int) -> bool:
    uid = int(user_id)
    if uid == OWNER_ID:
        return False
    try:
        res_del = await admins_collection.delete_one({'_id': uid})
        was_in_config = uid in ADMINS
        if was_in_config:
            while uid in ADMINS:
                ADMINS.remove(uid)
        await removed_admins_collection.update_one({'_id': uid}, {'$set': {'_id': uid}}, upsert=True)
        return (res_del.deleted_count > 0) or was_in_config
    except Exception:
        return False

async def list_admins() -> list:
    try:
        db_admins = [doc['_id'] for doc in await admins_collection.find().to_list(None)]
        removed = {doc['_id'] for doc in await removed_admins_collection.find().to_list(None)}
        combined = set(ADMINS + db_admins) - removed
        combined.add(OWNER_ID)
        return sorted(list(combined))
    except Exception:
        return list(set(ADMINS + [OWNER_ID]))

# ─── HIDE / UNHIDE CHANNELS FROM /get + TRENDING CLICKS ────────────────
async def set_channel_hidden(channel_id: int, hidden: bool = True) -> bool:
    try:
        await channels_collection.update_one(
            {"channel_id": int(channel_id)},
            {"$set": {"hidden_from_get": hidden}},
            upsert=True
        )
        return True
    except Exception:
        return False

async def get_hidden_channels() -> List[dict]:
    try:
        return await channels_collection.find({"hidden_from_get": True}).to_list(None)
    except Exception:
        return []

async def increment_channel_clicks(channel_id: int):
    try:
        await channels_collection.update_one(
            {"channel_id": int(channel_id)},
            {"$inc": {"clicks": 1}},
            upsert=False
        )
    except Exception:
        pass

async def get_top_channels(limit: int = 5) -> List[dict]:
    try:
        cursor = channels_collection.find({
            "status": "active",
            "hidden_from_get": {"$ne": True},
            "original_link": {"$exists": False},
            "title": {"$exists": True}
        }).sort("clicks", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception:
        return []

# ─── FSUB MODE & CHANNELS ──────────────────────────────────────────────
async def get_fsub_mode() -> str:
    try:
        data = await settings_collection.find_one({'_id': 'fsub_mode'})
        return data.get('mode', 'request') if data else 'request'
    except Exception:
        return 'request'

async def set_fsub_mode(mode: str) -> bool:
    try:
        await settings_collection.update_one({'_id': 'fsub_mode'}, {'$set': {'mode': mode}}, upsert=True)
        return True
    except Exception:
        return False

async def add_fsub_channel(channel_id: int) -> bool:
    try:
        await fsub_channels_collection.update_one(
            {'channel_id': int(channel_id)},
            {'$set': {'channel_id': int(channel_id), 'status': 'active'}, '$setOnInsert': {'created_at': datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception:
        return False

async def remove_fsub_channel(channel_id: int) -> bool:
    try:
        result = await fsub_channels_collection.delete_one({'channel_id': int(channel_id)})
        return result.deleted_count > 0
    except Exception:
        return False

async def get_fsub_channels() -> List[int]:
    try:
        channels = await fsub_channels_collection.find({'status': 'active'}).to_list(None)
        return [ch['channel_id'] for ch in channels]
    except Exception:
        return []

# ─── CHANNELS & ENCODED LINKS ───────────────────────────────────────────
async def save_channel(channel_id: int) -> bool:
    try:
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"channel_id": channel_id, "status": "active", "created_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception:
        return False

async def get_channels() -> List[int]:
    try:
        channels = await channels_collection.find({"status": "active"}).to_list(None)
        return [c["channel_id"] for c in channels if isinstance(c, dict) and "channel_id" in c]
    except Exception:
        return []

async def delete_channel(channel_id: int) -> bool:
    try:
        result = await channels_collection.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0
    except Exception:
        return False

async def save_encoded_link(channel_id: int) -> Optional[str]:
    try:
        encoded_link = base64.urlsafe_b64encode(str(channel_id).encode()).decode()
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"encoded_link": encoded_link, "status": "active", "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return encoded_link
    except Exception:
        return None

async def get_channel_by_encoded_link(encoded_link: str) -> Optional[int]:
    if not isinstance(encoded_link, str):
        return None
    try:
        channel = await channels_collection.find_one({"encoded_link": encoded_link, "status": "active"})
        if channel and "channel_id" in channel:
            return channel["channel_id"]
        padded = encoded_link + "=" * ((4 - len(encoded_link) % 4) % 4)
        return int(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return None

async def save_encoded_link2(channel_id: int, encoded_link: str) -> Optional[str]:
    try:
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"req_encoded_link": encoded_link, "status": "active", "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return encoded_link
    except Exception:
        return None

async def get_channel_by_encoded_link2(encoded_link: str) -> Optional[int]:
    if not isinstance(encoded_link, str):
        return None
    try:
        channel = await channels_collection.find_one({"req_encoded_link": encoded_link, "status": "active"})
        if channel and "channel_id" in channel:
            return channel["channel_id"]
        padded = encoded_link + "=" * ((4 - len(encoded_link) % 4) % 4)
        return int(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return None

async def save_invite_link(channel_id: int, invite_link: str, is_request: bool) -> bool:
    try:
        await channels_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"current_invite_link": invite_link, "is_request_link": is_request, "invite_link_created_at": datetime.utcnow(), "status": "active"}},
            upsert=True
        )
        return True
    except Exception:
        return False

async def get_current_invite_link(channel_id: int) -> Optional[dict]:
    try:
        channel = await channels_collection.find_one({"channel_id": channel_id, "status": "active"})
        if channel and "current_invite_link" in channel:
            return {"invite_link": channel["current_invite_link"], "is_request": channel.get("is_request_link", False)}
        return None
    except Exception:
        return None

async def get_original_link(channel_id: int) -> Optional[str]:
    try:
        channel = await channels_collection.find_one({"channel_id": channel_id, "status": "active"})
        return channel.get("original_link") if channel else None
    except Exception:
        return None

async def set_approval_off(channel_id: int, off: bool = True) -> bool:
    try:
        await channels_collection.update_one({"channel_id": channel_id}, {"$set": {"approval_off": off}}, upsert=True)
        return True
    except Exception:
        return False

async def is_approval_off(channel_id: int) -> bool:
    try:
        channel = await channels_collection.find_one({"channel_id": channel_id})
        return bool(channel and channel.get("approval_off", False))
    except Exception:
        return False
