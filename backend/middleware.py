# requirements: pip install pyserial
import serial
import sqlite3
import time
from datetime import datetime
import sys
import logging

# ==========================================
# CONFIGURATION
# ==========================================
COM_PORT = 'COM3'  # Change this to match your Arduino's COM port
BAUD_RATE = 9600
TOLL_FEE = 100.00
ANTI_PASSBACK_SECONDS = 10
DB_NAME = 'toll_system.db'

# Set up error logging
logging.basicConfig(filename='error.log', level=logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ANSI escape codes for colored console output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    AMBER = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

# In-memory dictionary to track recent scans to prevent double-charging
recent_scans = {}

# ==========================================
# DATABASE SETUP
# ==========================================
def setup_database():
    """Initialize the SQLite DB, create tables, and insert seed data if empty."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # Create Users Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    rfid_id TEXT PRIMARY KEY,
                    vehicle_no TEXT,
                    owner_name TEXT,
                    wallet_bal REAL
                )
            ''')
            
            # Create Transaction Log Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transaction_log (
                    txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfid_id TEXT,
                    timestamp TEXT,
                    amount REAL,
                    status TEXT,
                    reason TEXT
                )
            ''')
            
            # Seed Data (The 5 mock vehicles for your BCA project)
            seed_data = [
                ('8D 20 06 85', 'MH-04-AB-1234', 'Fawwaz Mohd Ubaid', 1000.00),
                ('A1 B2 C3 D4', 'UP-32-CD-5678', 'Ayyub Waqar Faridi', 1200.00),
                ('F1 E2 D3 C4', 'DL-01-XY-9999', 'Thanaphong T.', 200.00),
                ('12 34 56 78', 'KA-05-PQ-3344', 'Madani Hassan', 3000.00),
                ('AA BB CC DD', 'TN-11-ZZ-7788', 'Abdalla Haroun', 560.00)
            ]
            
            # Insert only if the users table is empty
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                cursor.executemany('''
                    INSERT INTO users (rfid_id, vehicle_no, owner_name, wallet_bal) 
                    VALUES (?, ?, ?, ?)
                ''', seed_data)
                print(f"{Colors.CYAN}[SYSTEM] Database initialized with seed data.{Colors.RESET}")
            else:
                print(f"{Colors.CYAN}[SYSTEM] Database loaded successfully.{Colors.RESET}")
                
    except Exception as e:
        logging.error(f"Database setup failed: {e}")
        print(f"{Colors.RED}[ERROR] Database setup failed. Check error.log{Colors.RESET}")
        sys.exit(1)

# ==========================================
# CORE LOGIC
# ==========================================
def process_scan(uid, ser):
    """Handle the DB lookup, balance check, deduction, and Arduino response."""
    current_time = time.time()
    
    # 1. Check Anti-Passback
    if uid in recent_scans:
        if (current_time - recent_scans[uid]) < ANTI_PASSBACK_SECONDS:
            print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Reason: Anti-passback cooldown active.{Colors.RESET}")
            ser.write(b'0\n')  # Tell Arduino to keep gate closed
            return
            
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # 2. Look up the user
            cursor.execute("SELECT vehicle_no, owner_name, wallet_bal FROM users WHERE rfid_id = ?", (uid,))
            user = cursor.fetchone()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if not user:
                # User not found
                print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Reason: Unknown Tag{Colors.RESET}")
                ser.write(b'0\n')
                cursor.execute('''
                    INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                    VALUES (?, ?, 0, 'DENIED', 'UNKNOWN_TAG')
                ''', (uid, timestamp))
                return
                
            vehicle_no, owner_name, wallet_bal = user
            
            # 3. Check Balance
            if wallet_bal >= TOLL_FEE:
                # 4a. Success: Deduct balance
                new_bal = wallet_bal - TOLL_FEE
                cursor.execute("UPDATE users SET wallet_bal = ? WHERE rfid_id = ?", (new_bal, uid))
                
                # Log transaction
                cursor.execute('''
                    INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                    VALUES (?, ?, ?, 'AUTHORIZED', 'SUCCESS')
                ''', (uid, timestamp, TOLL_FEE))
                
                # Update cooldown dictionary
                recent_scans[uid] = current_time
                
                # Command Arduino to open gate
                ser.write(b'1\n')
                
                print(f"{Colors.GREEN}[✓ AUTHORIZED] UID: {uid} | Vehicle: {vehicle_no} | "
                      f"Owner: {owner_name} | Deducted: \u20b9{TOLL_FEE} | New Balance: \u20b9{new_bal}{Colors.RESET}")
            else:
                # 4b. Failure: Insufficient funds
                ser.write(b'0\n')
                cursor.execute('''
                    INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                    VALUES (?, ?, 0, 'DENIED', 'INSUFFICIENT_FUNDS')
                ''', (uid, timestamp))
                
                print(f"{Colors.RED}[✗ DENIED] UID: {uid} | Vehicle: {vehicle_no} | "
                      f"Reason: Insufficient Funds (Bal: \u20b9{wallet_bal}){Colors.RESET}")
                      
    except Exception as e:
        logging.error(f"Error processing transaction for UID {uid}: {e}")
        print(f"{Colors.RED}[ERROR] Internal error processing scan. Check logs.{Colors.RESET}")
        ser.write(b'0\n') # Fail safe: don't open gate on error

# ==========================================
# MAIN LOOP
# ==========================================
def main():
    setup_database()
    
    print(f"{Colors.AMBER}[SYSTEM] Starting RFID Middleware...{Colors.RESET}")
    print(f"{Colors.AMBER}[SYSTEM] Toll Fee set to: \u20b9{TOLL_FEE}{Colors.RESET}")
    
    while True:
        try:
            # Connect to Arduino
            print(f"{Colors.CYAN}[SYSTEM] Attempting to connect to {COM_PORT}...{Colors.RESET}")
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            print(f"{Colors.GREEN}[SYSTEM] Connected to {COM_PORT} successfully.{Colors.RESET}")
            print(f"{Colors.AMBER}[SYSTEM] Waiting for RFID scans... (Press Ctrl+C to exit){Colors.RESET}")
            
            while True:
                if ser.in_waiting > 0:
                    raw_data = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    # Look for the specific string format from the Arduino RC522 sketch
                    if "UID tag :" in raw_data:
                        # Extract just the hex string (e.g., "8D 20 06 85")
                        uid = raw_data.split(":")[1].strip().upper()
                        process_scan(uid, ser)
                        
        except serial.SerialException:
            print(f"{Colors.RED}[ERROR] Connection lost or could not connect to {COM_PORT}. Retrying in 3 seconds...{Colors.RESET}")
            time.sleep(3)
        except KeyboardInterrupt:
            print(f"\n{Colors.CYAN}[SYSTEM] Shutting down middleware gracefully.{Colors.RESET}")
            sys.exit(0)

if __name__ == '__main__':
    main()