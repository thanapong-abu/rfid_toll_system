# requirements: pip install pyserial requests
import serial
import time
import sys
import requests

# ==========================================
# CLOUD CONFIGURATION
# ==========================================
API_URL = 'https://rfid-toll-system.onrender.com/api/scan' # <-- เปลี่ยนเป็นลิงก์ Render ของคุณ!
API_KEY = 'toll2026'

# ==========================================
# HARDWARE CONFIGURATION
# ==========================================
COM_PORT = 'COM5'  # เปลี่ยนให้ตรงกับพอร์ต Arduino ของคุณ (เช่น COM3, COM4)
BAUD_RATE = 9600
ANTI_PASSBACK_SECONDS = 10

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    AMBER = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

recent_scans = {}

def process_scan(uid, ser):
    """ส่งข้อมูล UID ไปเช็คและตัดเงินที่เซิร์ฟเวอร์บน Render"""
    current_time = time.time()
    
    # 1. Check Anti-Passback (ป้องกันการสแกนซ้ำติดๆ กัน)
    if uid in recent_scans and (current_time - recent_scans[uid]) < ANTI_PASSBACK_SECONDS:
        print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Reason: Anti-passback cooldown active.{Colors.RESET}")
        if ser: ser.write(b'0\n')
        return
        
    print(f"{Colors.CYAN}[SYSTEM] Sending UID: {uid} to Cloud Server...{Colors.RESET}")
    
    # 2. ส่งข้อมูลไปที่ Render API
    try:
        headers = {'X-API-Key': API_KEY, 'Content-Type': 'application/json'}
        payload = {'rfid_id': uid}
        
        # ส่ง POST Request ไปตัดเงิน
        response = requests.post(API_URL, json=payload, headers=headers, timeout=5)
        result = response.json()
        
        if result.get('success'):
            if result.get('authorized'):
                # ถ้าระบบอนุญาต (เงินพอ)
                recent_scans[uid] = current_time
                if ser: ser.write(b'1\n') # สั่ง Arduino เปิดไม้กั้น
                print(f"{Colors.GREEN}[✓ AUTHORIZED] UID: {uid} | Vehicle: {result['vehicle_no']} | Owner: {result['owner_name']} | Deducted: \u20b9{result['deducted']} | New Balance: \u20b9{result['new_balance']}{Colors.RESET}")
            else:
                # ถ้าระบบไม่อนุญาต (เงินไม่พอ / บัตรเถื่อน)
                if ser: ser.write(b'0\n') # สั่ง Arduino ปิดไม้กั้น
                reason = result.get('reason', 'UNKNOWN')
                if reason == "INSUFFICIENT_FUNDS":
                    bal = result.get('current_balance', 'N/A')
                    print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Reason: Insufficient Funds (Bal: \u20b9{bal}){Colors.RESET}")
                else:
                    print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Reason: Unknown Tag{Colors.RESET}")
        else:
            print(f"{Colors.RED}[ERROR] Server Error: {result.get('error')}{Colors.RESET}")
            if ser: ser.write(b'0\n')
            
    except requests.exceptions.RequestException as e:
        print(f"{Colors.RED}[ERROR] Network Error (No Internet or Server Down): {e}{Colors.RESET}")
        if ser: ser.write(b'0\n')

def main():
    print(f"{Colors.AMBER}[SYSTEM] Starting Cloud-Connected RFID Middleware...{Colors.RESET}")
    
    # ====================================================
    # โหมดจำลอง (ถ้าไม่ได้ต่อบอร์ด Arduino ให้เอาเครื่องหมาย # ด้านล่างออกเพื่อทดสอบ)
    # process_scan("8D 20 06 85", None)
    # return
    # ====================================================

    while True:
        try:
            print(f"{Colors.CYAN}[SYSTEM] Attempting to connect to Arduino on {COM_PORT}...{Colors.RESET}")
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            print(f"{Colors.GREEN}[SYSTEM] Connected successfully.{Colors.RESET}")
            print(f"{Colors.AMBER}[SYSTEM] Waiting for RFID scans... (Press Ctrl+C to exit){Colors.RESET}")
            
            while True:
                if ser.in_waiting > 0:
                    raw_data = ser.readline().decode('utf-8', errors='ignore').strip()
                    if "UID tag :" in raw_data:
                        uid = raw_data.split(":")[1].strip().upper()
                        process_scan(uid, ser)
                        
        except serial.SerialException:
            print(f"{Colors.RED}[ERROR] Could not connect to {COM_PORT}. Retrying in 3 seconds...{Colors.RESET}")
            time.sleep(3)
        except KeyboardInterrupt:
            print(f"\n{Colors.CYAN}[SYSTEM] Shutting down middleware.{Colors.RESET}")
            sys.exit(0)

if __name__ == '__main__':
    main()