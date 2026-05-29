import requests

# Make sure this points to your Render URL so it updates the live database!
API_URL = "https://rfid-toll-system.onrender.com/api/vehicles"
API_KEY = "toll2026"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Your 4 actual physical card UIDs
real_cards = [
    # 1. Keychain (Sufficient funds to pass)
    {"rfid_id": "12 21 51 06", "vehicle_no": "MH-04-AB-1234", "owner_name": "Fawwaz Mohd Ubaid", "wallet_bal": 1000},
    
    # 2. White Card (Set to ₹50 intentionally so you can demonstrate the 'Insufficient Funds' denied case to the panel)
    {"rfid_id": "52 E2 6E 5C", "vehicle_no": "DL-01-XY-9999", "owner_name": "Thanaphong T.", "wallet_bal": 50},  
    
    # 3. New Card 1
    {"rfid_id": "B7 46 42 80", "vehicle_no": "UP-32-CD-5678", "owner_name": "Ayyub Waqar Faridi", "wallet_bal": 1200},
    
    # 4. New Card 2 (7-byte UID)
    {"rfid_id": "05 8D 5A 01 CF B2 00", "vehicle_no": "KA-05-PQ-3344", "owner_name": "Madani Hassan", "wallet_bal": 3000}
]

print("Registering real cards into the system...")
for card in real_cards:
    response = requests.post(API_URL, json=card, headers=headers)
    result = response.json()
    if result.get("success"):
        print(f"[SUCCESS] Registered card {card['rfid_id']}!")
    else:
        print(f"[SKIPPED] Card {card['rfid_id']} -> {result.get('error')}")

print("\nDone! You can now refresh your Dashboard.")