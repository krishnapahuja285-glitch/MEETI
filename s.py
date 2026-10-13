# retro_interactive_saver.py
from cloakbrowser import launch
import json
import time
import os
from datetime import datetime

def save_single_session(access_key, session_number):
    """Save session for one retrostress account"""
    browser = None
    
    try:
        print(f"\n{'='*60}")
        print(f"SESSION {session_number}")
        print('='*60)
        
        print("🚀 Starting browser...")
        browser = launch(headless=True)
        page = browser.new_page()
        
        # Open auth page
        print("📋 Opening https://retrostress.st/auth ...")
        page.goto("https://retrostress.net/auth", wait_until="domcontentloaded", timeout=40000)
        
        print("⏳ Waiting for page load...")
        time.sleep(5)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ===== Wait for access key field (NEW SELECTOR) =====
        print("⏳ Waiting for access key field...")
        try:
            page.wait_for_selector('#access-key', timeout=15000)
        except:
            print("❌ Access key field not found!")
            page.screenshot(path=f"error_retro_{session_number}_{timestamp}.png")
            return False
        
        # ===== Fill access key (NEW SELECTOR) =====
        print(f"✏️ Filling access key...")
        page.locator('#access-key').fill(access_key)
        time.sleep(1)
        
        # ===== Click Sign in button (NEW SELECTOR) =====
        print("🖱️ Clicking Sign in...")
        page.locator('button.button.primary[type="submit"]').click()
        time.sleep(8)
        
        # Check current URL
        current_url = page.url
        print(f"🔍 Current URL: {current_url}")
        
        # Take screenshot after login
        after_file = f"retro_after_login_{session_number}_{timestamp}.png"
        page.screenshot(path=after_file, full_page=True)
        
        # Save cookies
        cookies = page.context.cookies()
        print(f"🍪 Cookies found: {len(cookies)}")
        
        session_file = f"retro_session_{session_number}.json"
        with open(session_file, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"💾 Session saved: {session_file}")
        
        # Test panel access
        print("🧪 Testing panel access...")
        page.goto("https://retrostress.st/panel", wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        
        panel_url = page.url
        panel_file = f"retro_panel_{session_number}_{timestamp}.png"
        page.screenshot(path=panel_file, full_page=True)
        
        if "panel" in panel_url:
            print(f"✅ SUCCESS! Session {session_number} is valid!")
            return True
        else:
            print(f"❌ FAILED! Session {session_number} is invalid!")
            print(f"   Panel URL: {panel_url}")
            return False
            
    except Exception as e:
        print(f"❌ Error for session {session_number}: {e}")
        return False
        
    finally:
        if browser:
            browser.close()
            print("🔒 Browser closed!")

def collect_access_keys(count):
    """Collect access keys from user"""
    print(f"\n📝 Please enter {count} access keys:")
    print("=" * 60)
    
    access_keys = []
    
    for i in range(1, count + 1):
        while True:
            print(f"\n🔑 Access Key #{i}/{count}:")
            key = input("   Enter 64-character key: ").strip()
            
            # Validate key length
            if len(key) == 64:
                access_keys.append(key)
                print(f"   ✅ Key #{i} accepted!")
                break
            else:
                print(f"   ❌ Invalid! Key must be 64 characters (you entered {len(key)})")
                retry = input("   Try again? (yes/no): ").strip().lower()
                if retry not in ['yes', 'y']:
                    print("   ⚠️ Skipping this key...")
                    break
    
    return access_keys

def main():
    print("\n" + "="*60)
    print("🔥 RETROSTRESS INTERACTIVE SESSION SAVER")
    print("="*60)
    print("🌐 Target: https://retrostress.st")
    print("="*60)
    
    # Ask how many accounts
    print("\n📊 How many accounts do you want to save?")
    
    while True:
        try:
            count_input = input("👉 Enter number (e.g., 50): ").strip()
            account_count = int(count_input)
            
            if account_count < 1:
                print("❌ Please enter a number greater than 0!")
                continue
            
            if account_count > 100:
                print("⚠️  That's a lot of accounts!")
                confirm = input(f"   Are you sure you want to add {account_count} accounts? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    continue
            
            break
            
        except ValueError:
            print("❌ Please enter a valid number!")
    
    print(f"\n✅ You selected: {account_count} accounts")
    print(f"⏱️  Estimated time: ~{account_count * 20} seconds ({account_count * 20 / 60:.1f} minutes)")
    
    # Collect all access keys first
    print("\n" + "="*60)
    print("STEP 1: COLLECTING ACCESS KEYS")
    print("="*60)
    
    access_keys = collect_access_keys(account_count)
    
    if len(access_keys) == 0:
        print("\n❌ No valid keys collected! Exiting...")
        return
    
    print(f"\n✅ Collected {len(access_keys)} valid access keys")
    
    # Create accounts structure
    accounts = []
    for i, key in enumerate(access_keys, 1):
        accounts.append({
            "session_number": i,
            "access_key": key
        })
    
    # Save accounts to file
    with open("retro_accounts.json", "w") as f:
        json.dump(accounts, f, indent=2)
    print(f"💾 Accounts saved to: retro_accounts.json")
    
    # Confirm before processing
    print("\n" + "="*60)
    print("STEP 2: SAVE SESSIONS")
    print("="*60)
    print(f"⚠️  About to process {len(accounts)} accounts")
    print(f"⚠️  This will take approximately {len(accounts) * 20} seconds")
    
    confirm = input("\n👉 Start processing? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled! Your accounts are saved in retro_accounts.json")
        print("   Run this script again to continue.")
        return
    
    # Process each account
    print(f"\n⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    success_count = 0
    failed_count = 0
    results = []
    
    for i, account in enumerate(accounts, 1):
        session_num = account["session_number"]
        access_key = account["access_key"]
        
        print(f"\n{'='*60}")
        print(f"📌 Processing Account {i}/{len(accounts)}")
        print(f"   Session Number: {session_num}")
        print(f"   Access Key: {access_key[:10]}...{access_key[-10:]}")
        print('='*60)
        
        result = save_single_session(access_key, session_num)
        
        results.append({
            "session_number": session_num,
            "success": result
        })
        
        if result:
            success_count += 1
        else:
            failed_count += 1
        
        # Show progress
        progress = (i / len(accounts)) * 100
        print(f"\n📊 Progress: {i}/{len(accounts)} ({progress:.1f}%)")
        print(f"   ✅ Success: {success_count} | ❌ Failed: {failed_count}")
        
        # Wait between accounts (except last one)
        if i < len(accounts):
            wait_time = 5
            print(f"\n⏳ Waiting {wait_time}s before next account...")
            for j in range(wait_time, 0, -1):
                print(f"   {j}s...", end='\r')
                time.sleep(1)
            print()
    
    # Final summary
    print("\n" + "="*60)
    print("🎉 PROCESSING COMPLETE!")
    print("="*60)
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📊 Total: {len(accounts)}")
    print(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Detailed results
    print("\n📋 Detailed Results:")
    print("-" * 60)
    for r in results:
        status = "✅ SUCCESS" if r["success"] else "❌ FAILED"
        session_file = f"retro_session_{r['session_number']}.json"
        exists = "✓" if os.path.exists(session_file) else "✗"
        print(f"   Session #{r['session_number']:3d}: {status} | File: {exists}")
    print("-" * 60)
    
    # Save summary
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(accounts),
        "successful": success_count,
        "failed": failed_count,
        "results": results
    }
    
    summary_file = f"retro_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n💾 Summary saved: {summary_file}")
    
    # List saved session files
    print("\n📁 Saved Session Files:")
    session_files = [f for f in os.listdir('.') if f.startswith('retro_session_') and f.endswith('.json')]
    for sf in sorted(session_files):
        print(f"   ✓ {sf}")
    
    if success_count > 0:
        print(f"\n✅ {success_count} session(s) saved successfully!")
        print("\n🚀 Next Steps:")
        print("   1. Run: python api2.py")
        print("   2. Start attacking!")
    else:
        print("\n❌ No sessions saved! Please check the errors above.")
        print("   You can run this script again to retry.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user!")
        print("   Your progress has been saved in retro_accounts.json")
        print("   Run the script again to continue.")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        print("   Please report this issue.")
