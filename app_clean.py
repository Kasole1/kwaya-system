# -*- coding: utf-8 -*-
import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'kwaya_mt_bonifasi_secret_key_2026'

# Database path - works both locally and on hosting
if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER'):
    DATABASE_PATH = '/app/kwaya.db'
else:
    DATABASE_PATH = 'kwaya.db'

def get_db():
    """Pata connection ya database"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

# ==================== ROUTES ZA MSINGI ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?", 
            (username, password)
        ).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user.get('role', 'admin')
            return redirect('/dashboard')
        
        return render_template('login.html', error='Username au password si sahihi')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==================== API ZA MSINGI ====================

@app.route('/api/notifications')
def get_notifications():
    conn = get_db()
    notifications = conn.execute(
        "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(n) for n in notifications])

@app.route('/api/wanakwaya')
def get_wanakwaya():
    conn = get_db()
    wanakwaya = conn.execute(
        "SELECT * FROM wanakwaya ORDER BY jina LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(w) for w in wanakwaya])

@app.route('/api/mapato/data')
def get_mapato():
    mwaka = request.args.get('mwaka', '2026')
    conn = get_db()
    mapato = conn.execute(
        "SELECT * FROM mapato WHERE strftime('%Y', tarehe) = ? ORDER BY tarehe DESC",
        (mwaka,)
    ).fetchall()
    conn.close()
    return jsonify([dict(m) for m in mapato])

@app.route('/api/mahudhurio/penalty_list')
def get_penalty_list():
    conn = get_db()
    penalties = conn.execute(
        "SELECT * FROM mahudhurio WHERE penalty > 0 ORDER BY tarehe DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(p) for p in penalties])

@app.route('/api/activity-log')
def get_activity_log():
    conn = get_db()
    logs = conn.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

@app.route('/api/events')
def get_events():
    conn = get_db()
    events = conn.execute(
        "SELECT * FROM events ORDER BY start_date DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([dict(e) for e in events])

@app.route('/api/dashboard/widgets')
def get_widgets():
    conn = get_db()
    
    wanakwaya_count = conn.execute("SELECT COUNT(*) as count FROM wanakwaya").fetchone()['count']
    mapato = conn.execute(
        "SELECT SUM(kiasi) as jumla FROM mapato WHERE strftime('%Y', tarehe) = strftime('%Y', 'now')"
    ).fetchone()['jumla'] or 0
    leo = datetime.now().strftime('%Y-%m-%d')
    mahudhurio = conn.execute(
        "SELECT COUNT(*) as count FROM mahudhurio WHERE tarehe = ?", (leo,)
    ).fetchone()['count']
    
    conn.close()
    
    return jsonify({
        'wanakwaya_total': wanakwaya_count,
        'mapato_mwaka': mapato,
        'mahudhurio_leo': mahudhurio
    })

@app.route('/api/live/schedules')
def get_live_schedules():
    conn = get_db()
    schedules = conn.execute(
        "SELECT * FROM live_stream_schedules ORDER BY scheduled_time DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(s) for s in schedules])

@app.route('/api/live/viewers/<int:schedule_id>')
def get_live_viewers(schedule_id):
    return jsonify({'viewers': 0})

@app.route('/api/live/recordings')
def get_live_recordings():
    conn = get_db()
    recordings = conn.execute(
        "SELECT * FROM live_stream_recordings ORDER BY recording_date DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in recordings])

@app.route('/api/albamu')
def get_albamu():
    conn = get_db()
    albamu = conn.execute("SELECT * FROM albamu ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(a) for a in albamu])

@app.route('/api/albamu/<int:id>')
def get_albamu_by_id(id):
    conn = get_db()
    albamu = conn.execute("SELECT * FROM albamu WHERE id = ?", (id,)).fetchone()
    media = conn.execute("SELECT * FROM media WHERE albamu_id = ?", (id,)).fetchall()
    conn.close()
    
    if not albamu:
        return jsonify({'error': 'Albamu haipo'}), 404
    
    result = dict(albamu)
    result['media'] = [dict(m) for m in media]
    return jsonify(result)

@app.route('/api/albamu/<int:id>', methods=['DELETE'])
def delete_albamu(id):
    """Futa albamu kwa ID"""
    try:
        conn = get_db()
        
        albamu = conn.execute("SELECT * FROM albamu WHERE id = ?", (id,)).fetchone()
        if not albamu:
            conn.close()
            return jsonify({'error': 'Albamu haipo'}), 404
        
        conn.execute("DELETE FROM media WHERE albamu_id = ?", (id,))
        conn.execute("DELETE FROM albamu WHERE id = ?", (id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Albamu imefutwa'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/kwaya/get-logo')
def get_logo():
    return jsonify({'logo': '/static/img/logo.png'})

@app.route('/api/member-id-card/<int:user_id>')
def get_member_id_card(user_id):
    conn = get_db()
    member = conn.execute("SELECT * FROM wanakwaya WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if member:
        return jsonify(dict(member))
    return jsonify({'error': 'Member not found'}), 404

@app.route('/api/attendance-certificate/<int:user_id>')
def get_attendance_certificate(user_id):
    year = request.args.get('year', '2026')
    conn = get_db()
    mahudhurio = conn.execute(
        "SELECT COUNT(*) as count FROM mahudhurio WHERE mwanakwaya_id = ? AND strftime('%Y', tarehe) = ?",
        (user_id, year)
    ).fetchone()
    conn.close()
    return jsonify({'attendance_count': mahudhurio['count'], 'year': year})

@app.route('/api/financial/data')
def get_financial_data():
    year = request.args.get('year', '2026')
    conn = get_db()
    mapato = conn.execute(
        "SELECT strftime('%m', tarehe) as month, SUM(kiasi) as total FROM mapato WHERE strftime('%Y', tarehe) = ? GROUP BY month",
        (year,)
    ).fetchall()
    conn.close()
    return jsonify([dict(m) for m in mapato])

# ==================== PAGE ROUTES ====================

@app.route('/member-id-card')
def member_id_card_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('member_id_card.html')

@app.route('/attendance-certificate')
def attendance_certificate_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('attendance_certificate.html')

@app.route('/albamu')
def albamu_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('albamu.html')

@app.route('/practice-schedule')
def practice_schedule_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('practice_schedule.html')

@app.route('/financial-reports')
def financial_reports_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('financial_reports.html')

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("🚀 MFUMO WA KWAYA MT. BONIFASI")
    print("📍 http://127.0.0.1:5000")
    print("👤 admin | 🔑 admin123")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)