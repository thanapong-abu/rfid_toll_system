# requirements: pip install Flask Flask-Cors
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import logging
import os

app = Flask(__name__)
CORS(app) # Allow cross-origin requests from your HTML frontend

DB_NAME = 'toll_system.db'
API_KEY = 'toll2026'

# ==========================================
# SERVE FRONTEND (DASHBOARD)
# ==========================================
@app.route('/')
def serve_dashboard():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
    return send_from_directory(frontend_path, 'dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
    return send_from_directory(frontend_path, path)

# ==========================================
# DATABASE HELPER
# ==========================================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_NAME)
        db.row_factory = sqlite3.Row # Return rows as dictionaries
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
# ==========================================
# AUTHENTICATION MIDDLEWARE
# ==========================================
@app.before_request
def require_api_key():
    # Allow CORS preflight requests
    if request.method == 'OPTIONS':
        return
    
    # EXCEPTION: Do not require API key for frontend files
    if request.path == '/' or request.path.startswith('/frontend') or '.' in request.path:
        return
    
    # Check for API key in headers for all /api/ requests
    key = request.headers.get('X-API-Key')
    if key != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized. Invalid or missing API Key."}), 401
# ==========================================
# ENDPOINTS
# ==========================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get high-level dashboard statistics."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Total Vehicles
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_vehicles = cursor.fetchone()['count']
        
        # Today's date string matching the DB format (YYYY-MM-DD)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Today's Transactions
        cursor.execute("SELECT COUNT(*) as count FROM transaction_log WHERE timestamp LIKE ?", (f"{today_str}%",))
        today_txns = cursor.fetchone()['count']
        
        # Today's Revenue
        cursor.execute("SELECT SUM(amount) as total FROM transaction_log WHERE timestamp LIKE ? AND status = 'AUTHORIZED'", (f"{today_str}%",))
        result = cursor.fetchone()['total']
        today_revenue = result if result else 0.0
        
        # Denied Today
        cursor.execute("SELECT COUNT(*) as count FROM transaction_log WHERE timestamp LIKE ? AND status = 'DENIED'", (f"{today_str}%",))
        denied_today = cursor.fetchone()['count']
        
        return jsonify({
            "success": True,
            "data": {
                "total_vehicles": total_vehicles,
                "today_transactions": today_txns,
                "today_revenue": today_revenue,
                "denied_today": denied_today
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    """List all registered vehicles."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users")
        vehicles = [dict(row) for row in cursor.fetchall()]
        return jsonify({"success": True, "data": vehicles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/vehicles', methods=['POST'])
def add_vehicle():
    """Register a new vehicle."""
    try:
        data = request.json
        db = get_db()
        cursor = db.cursor()
        
        # Validation
        if not all(k in data for k in ("rfid_id", "vehicle_no", "owner_name", "wallet_bal")):
            return jsonify({"success": False, "error": "Missing fields"}), 400
            
        cursor.execute('''
            INSERT INTO users (rfid_id, vehicle_no, owner_name, wallet_bal)
            VALUES (?, ?, ?, ?)
        ''', (data['rfid_id'], data['vehicle_no'], data['owner_name'], float(data['wallet_bal'])))
        db.commit()
        
        return jsonify({"success": True, "message": "Vehicle registered successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "RFID ID already exists"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/vehicles/<path:rfid_id>/topup', methods=['PATCH'])
def topup_vehicle(rfid_id):
    """Add balance to a vehicle's wallet."""
    try:
        data = request.json
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({"success": False, "error": "Top-up amount must be positive"}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        # Get current balance
        cursor.execute("SELECT wallet_bal FROM users WHERE rfid_id = ?", (rfid_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "Vehicle not found"}), 404
            
        new_balance = user['wallet_bal'] + amount
        cursor.execute("UPDATE users SET wallet_bal = ? WHERE rfid_id = ?", (new_balance, rfid_id))
        db.commit()
        
        return jsonify({"success": True, "new_balance": new_balance})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get paginated transaction logs."""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        status = request.args.get('status')
        
        db = get_db()
        cursor = db.cursor()
        
        query = '''
            SELECT t.*, u.vehicle_no, u.owner_name 
            FROM transaction_log t
            LEFT JOIN users u ON t.rfid_id = u.rfid_id
        '''
        params = []
        
        if status and status != 'All':
            query += " WHERE t.status = ?"
            params.append(status)
            
        query += " ORDER BY t.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        transactions = [dict(row) for row in cursor.fetchall()]
        
        # Get total count for pagination
        count_query = "SELECT COUNT(*) as total FROM transaction_log"
        if status and status != 'All':
            count_query += " WHERE status = ?"
            cursor.execute(count_query, (status,))
        else:
            cursor.execute(count_query)
            
        total_count = cursor.fetchone()['total']
        
        return jsonify({
            "success": True, 
            "data": transactions,
            "total": total_count
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reports/daily', methods=['GET'])
def get_daily_reports():
    """Get daily revenue and transaction counts for charts."""
    try:
        days = int(request.args.get('days', 7))
        db = get_db()
        cursor = db.cursor()
        
        # Calculate date N days ago
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT 
                substr(timestamp, 1, 10) as date,
                SUM(amount) as revenue,
                COUNT(*) as transactions,
                SUM(CASE WHEN status = 'DENIED' THEN 1 ELSE 0 END) as denied
            FROM transaction_log
            WHERE timestamp >= ?
            GROUP BY date
            ORDER BY date ASC
        ''', (start_date,))
        
        reports = [dict(row) for row in cursor.fetchall()]
        return jsonify({"success": True, "data": reports})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# NEW: RFID SCAN ENDPOINT (ระบบรับข้อมูลตัดเงินจากฮาร์ดแวร์)
# ==========================================
@app.route('/api/scan', methods=['POST'])
def process_scan():
    """Process a vehicle scan from the hardware/middleware."""
    try:
        data = request.json
        rfid_id = data.get('rfid_id')
        
        if not rfid_id:
            return jsonify({"success": False, "error": "Missing rfid_id"}), 400
            
        db = get_db()
        cursor = db.cursor()
        
        # Look up user
        cursor.execute("SELECT vehicle_no, owner_name, wallet_bal FROM users WHERE rfid_id = ?", (rfid_id,))
        user = cursor.fetchone()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        toll_fee = 100.00
        
        if not user:
            # Unknown tag (บัตรเถื่อน/ไม่ได้ลงทะเบียน)
            cursor.execute('''
                INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                VALUES (?, ?, 0, 'DENIED', 'UNKNOWN_TAG')
            ''', (rfid_id, timestamp))
            db.commit()
            return jsonify({"success": True, "authorized": False, "reason": "UNKNOWN_TAG"})
            
        vehicle_no, owner_name, wallet_bal = user
        
        if wallet_bal >= toll_fee:
            # Success! Deduct balance (เงินพอ ตัดเงิน 100 บาท)
            new_bal = wallet_bal - toll_fee
            cursor.execute("UPDATE users SET wallet_bal = ? WHERE rfid_id = ?", (new_bal, rfid_id))
            
            # Log successful transaction
            cursor.execute('''
                INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                VALUES (?, ?, ?, 'AUTHORIZED', 'SUCCESS')
            ''', (rfid_id, timestamp, toll_fee))
            
            db.commit()
            return jsonify({
                "success": True, 
                "authorized": True, 
                "vehicle_no": vehicle_no,
                "owner_name": owner_name,
                "deducted": toll_fee,
                "new_balance": new_bal
            })
        else:
            # Insufficient funds (เงินไม่พอ)
            cursor.execute('''
                INSERT INTO transaction_log (rfid_id, timestamp, amount, status, reason)
                VALUES (?, ?, 0, 'DENIED', 'INSUFFICIENT_FUNDS')
            ''', (rfid_id, timestamp))
            
            db.commit()
            return jsonify({
                "success": True, 
                "authorized": False, 
                "reason": "INSUFFICIENT_FUNDS",
                "current_balance": wallet_bal
            })
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Toll System API on port 5000...")
    print("API Key required: X-API-Key: toll2026")
    app.run(port=5000, debug=False)