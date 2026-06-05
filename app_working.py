from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from datetime import datetime, timedelta
import sqlite3
import json
from werkzeug.security import generate_password_hash, check_password_hash
import os
import calendar

app = Flask(__name__)
app.secret_key = 'kwaya_bonifasi_system_2026'

# ============ SESSION TIMEOUT (DAKIKA 10) ============
app.permanent_session_lifetime = timedelta(minutes=10)
app.config['SESSION_PERMANENT'] = True

DATABASE = 'kwaya.db'

# Create uploads folder if not exists
os.makedirs('static/uploads', exist_ok=True)
os.makedirs('static/images', exist_ok=True)

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ============ ACTIVITY LOG FUNCTION ============
def log_activity(user_id, username, action, details=None):
    """Record user activity in the database"""
    try:
        with get_db() as conn:
            ip_address = ''
            user_agent = ''
            try:
                from flask import request
                ip_address = request.remote_addr if hasattr(request, 'remote_addr') else ''
                user_agent = request.headers.get('User-Agent', '') if hasattr(request, 'headers') else ''
            except:
                pass
            
            conn.execute('''INSERT INTO activity_log (user_id, username, action, details, ip_address, user_agent, activity_time)
                        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))''',
                        (user_id, username, action, details, ip_address, user_agent))
            conn.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")

# ============ PERMISSIONS DECORATOR ============
def has_permission(permission):
    """Check if current user has specific permission"""
    if 'user_id' not in session:
        return False
    
    with get_db() as conn:
        user = conn.execute('SELECT role_id FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        if not user:
            return False
        
        if user['role_id'] == 1:
            return True
        
        perm = conn.execute('SELECT id FROM user_permissions WHERE role_id = ? AND permission = ?', (user['role_id'], permission)).fetchone()
        return perm is not None

def require_permission(permission):
    """Decorator to require permission for a route"""
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Tafadhali ingia kwanza!', 'warning')
                return redirect(url_for('login'))
            
            if not has_permission(permission):
                flash('Huna ruhusa ya kufanya hii!', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============ EDIT PERMISSION CHECK ============
def require_edit_permission():
    """Check if current user can edit data"""
    if 'user_id' not in session:
        return False
    role_id = session.get('role_id', 5)
    return role_id in [1, 2, 4]

# ============ FIRST LOGIN CHECK DECORATOR ============
def require_password_changed(f):
    """Decorator to force users to change password before accessing any page"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            with get_db() as conn:
                user = conn.execute("SELECT is_first_login FROM watumiaji WHERE id = ?", (session['user_id'],)).fetchone()
                if user and user['is_first_login'] == 1:
                    flash('Kwa usalama wako, lazima ubadilishe password yako kwanza!', 'warning')
                    return redirect(url_for('change_password_first'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_role():
    """Get current user's role name"""
    if 'user_id' not in session:
        return None
    
    with get_db() as conn:
        user = conn.execute('''
            SELECT w.*, r.name as role_name, r.level 
            FROM watumiaji w
            JOIN user_roles r ON w.role_id = r.id
            WHERE w.id = ?
        ''', (session['user_id'],)).fetchone()
        return user

def init_db():
    with get_db() as conn:
        # Meza ya wanakwaya
        conn.execute('''CREATE TABLE IF NOT EXISTS wanakwaya (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jina TEXT NOT NULL,
            simu TEXT NOT NULL,
            sauti TEXT,
            anwani TEXT,
            tarehe_jiunga DATE DEFAULT CURRENT_DATE,
            status TEXT DEFAULT 'active'
        )''')
        
        # Meza ya mahudhurio ya awali (simple)
        conn.execute('''CREATE TABLE IF NOT EXISTS mahudhurio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            tarehe DATE NOT NULL,
            alihudhuria BOOLEAN DEFAULT 1,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id)
        )''')
        
        # Meza ya ada (old - tunabakisha kwa compatibility)
        conn.execute('''CREATE TABLE IF NOT EXISTS ada (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            kiasi REAL NOT NULL,
            mwezi TEXT NOT NULL,
            mwaka INTEGER NOT NULL,
            imelipwa BOOLEAN DEFAULT 0,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id)
        )''')
        
        # ============ MEZA MPYA ZA ADA (ENHANCED) ============
        conn.execute('''CREATE TABLE IF NOT EXISTS ada_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kiasi_kwa_mwezi REAL DEFAULT 5000,
            tarehe_penalty INTEGER DEFAULT 15,
            penalty_asilimia REAL DEFAULT 10,
            mwaka INTEGER,
            mwezi INTEGER,
            imeanzishwa DATE DEFAULT CURRENT_DATE
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS ada_monthly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            mwezi TEXT NOT NULL,
            mwaka INTEGER NOT NULL,
            kiasi_kinachotakiwa REAL DEFAULT 0,
            kiasi_kilicholipwa REAL DEFAULT 0,
            deni_awali REAL DEFAULT 0,
            penalty REAL DEFAULT 0,
            jumla_ya_deni REAL DEFAULT 0,
            imelipwa INTEGER DEFAULT 0,
            tarehe_malipo DATE,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS ada_malipo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            kiasi REAL NOT NULL,
            tarehe DATE DEFAULT CURRENT_DATE,
            maelezo TEXT,
            monthly_id INTEGER,
            receipt_no TEXT,
            imechapishwa INTEGER DEFAULT 0,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id),
            FOREIGN KEY (monthly_id) REFERENCES ada_monthly(id)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS ada_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            mwaka INTEGER NOT NULL,
            mwezi INTEGER NOT NULL,
            kiasi_kinachotakiwa REAL DEFAULT 0,
            kiasi_kilicholipwa REAL DEFAULT 0,
            overpayment REAL DEFAULT 0,
            imelipwa INTEGER DEFAULT 0,
            tarehe_malipo DATE,
            receipt_no TEXT,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id)
        )''')
        
        # Mapato (existing)
        conn.execute('''CREATE TABLE IF NOT EXISTS mapato (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chanzo TEXT NOT NULL,
            kiasi REAL NOT NULL,
            maelezo TEXT,
            tarehe DATE DEFAULT CURRENT_DATE
        )''')
        
        # Ratiba (events)
        conn.execute('''CREATE TABLE IF NOT EXISTS ratiba (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tukio TEXT NOT NULL,
            tarehe DATE NOT NULL,
            mahali TEXT,
            maelezo TEXT
        )''')
        
        # Albamu table (enhanced with media)
        conn.execute('''CREATE TABLE IF NOT EXISTS albamu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jina_albamu TEXT NOT NULL,
            aina TEXT DEFAULT 'audio',
            mwaka INTEGER,
            nyimbo TEXT,
            maelezo TEXT,
            cover_image TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        # Media files table (songs/tracks)
        conn.execute('''CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            albamu_id INTEGER NOT NULL,
            wimbo_jina TEXT NOT NULL,
            mtunzi TEXT,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            duration TEXT,
            size INTEGER,
            created_at DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (albamu_id) REFERENCES albamu(id) ON DELETE CASCADE
        )''')
        
        # Nyimbo
        conn.execute('''CREATE TABLE IF NOT EXISTS nyimbo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jina TEXT NOT NULL,
            mtunzi TEXT,
            maneno TEXT,
            key TEXT,
            time_signature TEXT,
            tempo TEXT,
            kundi TEXT NOT NULL,
            nota_pdf TEXT,
            midi_file TEXT,
            tarehe_ongezwa DATE DEFAULT CURRENT_DATE
        )''')
        
        # Watumiaji
        conn.execute('''CREATE TABLE IF NOT EXISTS watumiaji (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )''')
        
        # Timetable saved
        conn.execute('''CREATE TABLE IF NOT EXISTS timetable_saved (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tukio TEXT NOT NULL,
            tarehe TEXT NOT NULL,
            jumapili_ngapi TEXT,
            mwaka_kanisa TEXT,
            data TEXT NOT NULL,
            tarehe_kuundwa DATE DEFAULT CURRENT_DATE
        )''')
        
        # Mahudhurio detailed
        conn.execute('''CREATE TABLE IF NOT EXISTS mahudhurio_detailed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mwanakwaya_id INTEGER NOT NULL,
            mwanakwaya_jina TEXT NOT NULL,
            sauti TEXT NOT NULL,
            tukio TEXT NOT NULL,
            tarehe DATE DEFAULT CURRENT_DATE,
            status TEXT DEFAULT 'absent',
            dakika_chelewa INTEGER DEFAULT 0,
            penalty REAL DEFAULT 0,
            imelipwa BOOLEAN DEFAULT 0,
            tarehe_penalty_double DATE,
            FOREIGN KEY (mwanakwaya_id) REFERENCES wanakwaya(id)
        )''')
        
        # Penalty settings
        conn.execute('''CREATE TABLE IF NOT EXISTS penalty_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tukio TEXT UNIQUE NOT NULL,
            penalty_utoro REAL DEFAULT 20000,
            penalty_kwa_dakika REAL DEFAULT 1000,
            siku_za_kudouble INTEGER DEFAULT 10
        )''')
        
        # Current event
        conn.execute('''CREATE TABLE IF NOT EXISTS current_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tukio TEXT NOT NULL,
            tarehe DATE DEFAULT CURRENT_DATE
        )''')
        
        # Mahudhurio penalties
        conn.execute('''CREATE TABLE IF NOT EXISTS mahudhurio_penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            penalty_amount REAL DEFAULT 0,
            penalty_type TEXT,
            tukio TEXT,
            tarehe_penalty DATE DEFAULT CURRENT_DATE,
            imelipwa INTEGER DEFAULT 0,
            remaining_amount REAL DEFAULT 0,
            FOREIGN KEY (member_id) REFERENCES wanakwaya(id)
        )''')
        
        # Penalty payments
        conn.execute('''CREATE TABLE IF NOT EXISTS penalty_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            penalty_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            receipt_no TEXT,
            tarehe DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (penalty_id) REFERENCES mahudhurio_penalties(id),
            FOREIGN KEY (member_id) REFERENCES wanakwaya(id)
        )''')
        
        # Mapato sources
        conn.execute('''CREATE TABLE IF NOT EXISTS mapato_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT DEFAULT '#1a2a6e',
            target REAL DEFAULT 0,
            description TEXT,
            icon TEXT DEFAULT '💰',
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        # Mapato records
        conn.execute('''CREATE TABLE IF NOT EXISTS mapato_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date DATE DEFAULT CURRENT_DATE,
            note TEXT,
            FOREIGN KEY (source_id) REFERENCES mapato_sources(id)
        )''')
        
        # System settings
        conn.execute('''CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATE DEFAULT CURRENT_DATE
        )''')
        
        # User roles table
        conn.execute('''CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            level INTEGER DEFAULT 1
        )''')
        
        # User permissions table
        conn.execute('''CREATE TABLE IF NOT EXISTS user_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission TEXT NOT NULL,
            FOREIGN KEY (role_id) REFERENCES user_roles(id)
        )''')
        
        # Update watumiaji table to include role_id
        cursor = conn.execute("PRAGMA table_info(watumiaji)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'role_id' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN role_id INTEGER DEFAULT 1')
        if 'full_name' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN full_name TEXT')
        if 'last_login' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN last_login DATETIME')
        if 'is_first_login' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN is_first_login INTEGER DEFAULT 1')
        if 'profile_picture' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN profile_picture TEXT')
        
        # Insert default roles
        default_roles = [
            (1, 'Admin', 'Full access to everything', 100),
            (2, 'Treasurer', 'Manage income, ada, penalties', 80),
            (3, 'Conductor', 'Record attendance only', 50),
            (4, 'Viewer', 'View only', 10)
        ]
        for role in default_roles:
            conn.execute('INSERT OR IGNORE INTO user_roles (id, name, description, level) VALUES (?, ?, ?, ?)', role)
        
        # Insert default permissions
        default_permissions = [
            (1, 'view_dashboard'),
            (1, 'view_wanakwaya'), (1, 'edit_wanakwaya'), (1, 'delete_wanakwaya'),
            (1, 'view_mahudhurio'), (1, 'edit_mahudhurio'),
            (1, 'view_mapato'), (1, 'edit_mapato'), (1, 'delete_mapato'),
            (1, 'view_ada'), (1, 'edit_ada'), (1, 'delete_ada'),
            (1, 'view_penalty'), (1, 'edit_penalty'), (1, 'delete_penalty'),
            (1, 'view_ripoti'), (1, 'export_ripoti'),
            (1, 'manage_users'), (1, 'manage_roles'),
            (2, 'view_dashboard'),
            (2, 'view_wanakwaya'),
            (2, 'view_mahudhurio'), (2, 'edit_mahudhurio'),
            (2, 'view_mapato'), (2, 'edit_mapato'),
            (2, 'view_ada'), (2, 'edit_ada'),
            (2, 'view_penalty'), (2, 'edit_penalty'),
            (2, 'view_ripoti'), (2, 'export_ripoti'),
            (3, 'view_dashboard'),
            (3, 'view_wanakwaya'),
            (3, 'view_mahudhurio'), (3, 'edit_mahudhurio'),
            (4, 'view_dashboard'), (4, 'view_wanakwaya'), (4, 'view_mahudhurio'),
            (4, 'view_mapato'), (4, 'view_ada'), (4, 'view_penalty'), (4, 'view_ripoti')
        ]
        for perm in default_permissions:
            conn.execute('INSERT OR IGNORE INTO user_permissions (role_id, permission) VALUES (?, ?)', perm)
        
        # Update admin user to have role_id = 1
        conn.execute("UPDATE watumiaji SET role_id = 1 WHERE username = 'admin'")
        
        # Insert default penalty settings if not exists
        default_settings = [
            ('Misa', 20000, 1000, 10),
            ('Mazishi', 15000, 500, 10),
            ('Harusi', 25000, 1500, 10),
            ('Sherehe', 30000, 2000, 10),
            ('Mashindano', 50000, 3000, 10),
            ('Mazoezi', 5000, 500, 10),
            ('Mazoezi Ya Kwaya', 5000, 500, 10),
            ('Kwaya Ya Jumapili', 10000, 800, 10),
            ('Dominica', 10000, 800, 10)
        ]
        for setting in default_settings:
            conn.execute("INSERT OR IGNORE INTO penalty_settings (tukio, penalty_utoro, penalty_kwa_dakika, siku_za_kudouble) VALUES (?, ?, ?, ?)", setting)
        
        # Insert default mapato sources
        default_sources = [
            ('Ada za Kwaya', '#1a2a6e', 5000000, 'Ada za kila mwezi kwa wanakwaya', '💰'),
            ('Penalty (Utoro)', '#dc3545', 2000000, 'Faini za kutokuhudhuria (Mtoro)', '❌'),
            ('Penalty (Chelewa)', '#fd7e14', 1000000, 'Faini za kuchelewa', '⏱️'),
            ('Wafadhili', '#28a745', 3000000, 'Michango kutoka kwa wafadhili', '🤝'),
            ('Mauzo (T-Shirts)', '#17a2b8', 1500000, 'Mauzo ya T-Shirts', '👕'),
            ('Mauzo (CD/DVD)', '#9b59b6', 500000, 'Mauzo ya CD na DVD', '💿'),
            ('Digital Platforms', '#e83e8c', 1000000, 'YouTube, Spotify, TikTok', '📱'),
            ('Marafiki wa Kwaya', '#20c997', 1000000, 'Michango ya marafiki', '👥'),
            ('Faini za Nidhamu', '#6f42c1', 500000, 'Faini za mashauri ya nidhamu', '⚖️')
        ]
        for source in default_sources:
            conn.execute("INSERT OR IGNORE INTO mapato_sources (name, color, target, description, icon) VALUES (?, ?, ?, ?, ?)", source)
        
        # Insert default global target
        conn.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('global_target', '10000000')")
        
        # Check if current_event has data
        current = conn.execute("SELECT * FROM current_event").fetchone()
        if not current:
            conn.execute("INSERT INTO current_event (tukio, tarehe) VALUES (?, date('now'))", ('Misa',))
        
        # Insert default ada settings
        existing_settings = conn.execute("SELECT * FROM ada_settings LIMIT 1").fetchone()
        if not existing_settings:
            now = datetime.now()
            conn.execute("INSERT INTO ada_settings (kiasi_kwa_mwezi, tarehe_penalty, penalty_asilimia, mwaka, mwezi, imeanzishwa) VALUES (?, ?, ?, ?, ?, ?)", (5000, 15, 10, now.year, now.month, now.date()))
        
        # Ongeza admin default
        admin = conn.execute("SELECT * FROM watumiaji WHERE username = 'admin'").fetchone()
        if not admin:
            conn.execute("INSERT INTO watumiaji (username, password, role, is_first_login) VALUES (?, ?, ?, ?)", ('admin', generate_password_hash('admin123'), 'admin', 0))
            print("✅ Admin created!")
        
        # Ongeza wanakwaya wa mfano kama hakuna
        waliopo = conn.execute("SELECT COUNT(*) as idadi FROM wanakwaya").fetchone()
        if waliopo['idadi'] == 0:
            wanakwaya_mfano = [
                ('Maria John', '0712345678', 'Soprano', 'Sombetini', 'active'),
                ('Anna Peter', '0723456789', 'Alto', 'Kijenge', 'active'),
                ('John Mushi', '0734567890', 'Tenor', 'Sombetini', 'active'),
                ('Peter Massawe', '0745678901', 'Bass', 'Kaloleni', 'active'),
                ('Esther Joseph', '0756789012', 'Soprano', 'Njiro', 'active'),
                ('Grace Lucy', '0767890123', 'Alto', 'Sombetini', 'active'),
                ('James Mboi', '0771234567', 'Tenor', 'Sekei', 'active'),
                ('Hadii Jane', '0781234567', 'Soprano', 'Themi', 'active'),
                ('John Kasole', '0791234567', 'Bass', 'Levolosi', 'active'),
            ]
            for w in wanakwaya_mfano:
                conn.execute("INSERT INTO wanakwaya (jina, simu, sauti, anwani, status) VALUES (?, ?, ?, ?, ?)", w)
        
        # ============ ONGEZA HIZI HAPA ============
        # MAUZO YA BIDHAA (INVENTORY)
        conn.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            buying_price REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,
            quantity INTEGER DEFAULT 0,
            unit TEXT DEFAULT 'pcs',
            image TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            selling_price REAL NOT NULL,
            total_amount REAL NOT NULL,
            profit REAL DEFAULT 0,
            customer_name TEXT,
            customer_phone TEXT,
            sale_date DATE DEFAULT CURRENT_DATE,
            receipt_no TEXT,
            notes TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )''')
        
        # Insert default products
        default_products = [
            ('T-Shirt (White)', 'Mavazi', 'T-Shirt nyeupe ya kwaya', 8000, 15000, 50, 'pcs'),
            ('T-Shirt (Black)', 'Mavazi', 'T-Shirt nyeusi ya kwaya', 8000, 15000, 50, 'pcs'),
            ('CD - Album 2025', 'CD/DVD', 'Albamu ya kwaya 2025', 2000, 5000, 100, 'pcs'),
            ('DVD - Live Performance', 'CD/DVD', 'DVD ya maonyesho', 3000, 8000, 50, 'pcs'),
            ('Cap', 'Mavazi', 'Kofia ya kwaya', 5000, 10000, 30, 'pcs'),
            ('Scarf', 'Mavazi', 'Kitambaa cha shingo', 3000, 7000, 40, 'pcs')
        ]
        for product in default_products:
            conn.execute('''INSERT OR IGNORE INTO products (name, category, description, buying_price, selling_price, quantity, unit)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', product)
        
        # Assets table
        conn.execute('''CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            value REAL DEFAULT 0,
            purchase_date DATE,
            supplier TEXT,
            description TEXT,
            maintenance TEXT DEFAULT 'none',
            status TEXT DEFAULT 'good',
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        # Activity log table
        conn.execute('''CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            activity_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Login history table
        conn.execute('''CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT
        )''')
        
        # Self service requests table
        conn.execute('''CREATE TABLE IF NOT EXISTS self_service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            request_type TEXT NOT NULL,
            request_data TEXT,
            status TEXT DEFAULT 'pending',
            admin_response TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            FOREIGN KEY (member_id) REFERENCES wanakwaya(id)
        )''')
        
        # Kwaya content table
        conn.execute('''CREATE TABLE IF NOT EXISTS kwaya_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_name TEXT UNIQUE NOT NULL,
            title TEXT,
            content TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        )''')
        
        # Insert default content pages
        default_pages = [
            ('historia', 'Historia ya Kwaya', ''),
            ('somo_msimamizi', 'Somo kwa Msimamizi', ''),
            ('mwanzilishi', 'Mwanzilishi wa Kwaya', ''),
            ('sifa_mwanakwaya', 'Sifa za Kuwa Mwanakwaya', ''),
            ('malengo_mfupi', 'Malengo Mafupi', ''),
            ('malengo_kati', 'Malengo ya Kati', ''),
            ('malengo_mrefu', 'Malengo Marefu', '')
        ]
        for page in default_pages:
            conn.execute('INSERT OR IGNORE INTO kwaya_content (page_name, title, content) VALUES (?, ?, ?)', page)
        
        # Expenses table
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            expense_date DATE DEFAULT CURRENT_DATE,
            receipt_no TEXT,
            created_by INTEGER,
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        # Income targets table
        conn.execute('''CREATE TABLE IF NOT EXISTS income_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            source_id INTEGER,
            mwaka INTEGER NOT NULL,
            amount REAL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Mapato income table
        conn.execute('''CREATE TABLE IF NOT EXISTS mapato_income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date DATE DEFAULT CURRENT_DATE,
            note TEXT,
            created_by INTEGER,
            FOREIGN KEY (source_id) REFERENCES mapato_sources(id)
        )''')
        
        # Live stream schedules table
        conn.execute('''CREATE TABLE IF NOT EXISTS live_stream_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            schedule_date DATE NOT NULL,
            schedule_time TIME NOT NULL,
            duration INTEGER DEFAULT 60,
            youtube_url TEXT,
            notification_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'scheduled',
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.commit()
        print("✅ Database ready!")

init_db()

# ============ DATA VALIDATION FUNCTIONS ============
def validate_phone(phone):
    import re
    phone = re.sub(r'\D', '', str(phone))
    if len(phone) == 10 and phone.startswith('0'):
        return True, phone
    elif len(phone) == 9:
        return True, '0' + phone
    else:
        return False, phone

def validate_amount(amount):
    try:
        amount = float(amount)
        if amount <= 0:
            return False, "Kiasi lazima kiwe kikubwa kuliko 0"
        if amount > 999999999:
            return False, "Kiasi kikubwa sana"
        return True, amount
    except (ValueError, TypeError):
        return False, "Tafadhali weka namba sahihi"

def validate_name(name):
    import re
    if not name:
        return False, "Jina linahitajika"
    if len(name) < 2:
        return False, "Jina ni fupi sana"
    if len(name) > 100:
        return False, "Jina ni refu sana"
    if re.match(r'^[a-zA-Z\s\-\'\.]+$', name):
        return True, name
    return False, "Jina linapaswa kuwa na herufi tu"

# ============ SESSION TIMEOUT MIDDLEWARE ============
@app.before_request
def check_session_timeout():
    if 'user_id' in session:
        session.permanent = True
        pass

# ============ AUTHENTICATION ROUTES ============
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with get_db() as conn:
            user = conn.execute("SELECT * FROM watumiaji WHERE username = ?", (username,)).fetchone()
            
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role'] if 'role' in user.keys() else 'user'
                
                user_data = conn.execute("SELECT role_id, is_first_login FROM watumiaji WHERE id = ?", (user['id'],)).fetchone()
                session['role_id'] = user_data['role_id'] if user_data else 5
                is_first_login = user_data['is_first_login'] if user_data else 1
                
                if is_first_login == 1:
                    flash('Karibu! Tafadhali badilisha password yako kwa usalama.', 'warning')
                    return redirect(url_for('change_password_first'))
                
                user_agent = request.headers.get('User-Agent', 'Unknown')
                ip_address = request.remote_addr
                conn.execute("INSERT INTO login_history (user_id, username, login_time, ip_address, user_agent) VALUES (?, ?, datetime('now'), ?, ?)",
                            (user['id'], username, ip_address, user_agent))
                
                conn.execute("UPDATE watumiaji SET last_login = datetime('now') WHERE id = ?", (user['id'],))
                conn.commit()
                
                log_activity(user['id'], username, 'LOGIN', f'User logged in successfully from IP: {ip_address}')
                
                flash(f'Karibu {username}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Username au password si sahihi!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session and 'username' in session:
        try:
        log_activity(session['user_id'], session['username'], 'LOGOUT', 'User logged out')
        except:
            pass
    
    session.clear()
    flash('Umefanikiwa kutoka!', 'success')
    return redirect(url_for('login'))

# ============ DASHBOARD ============
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    from datetime import datetime
    now = datetime.now()
    
    with get_db() as conn:
        wanakwaya_count = conn.execute("SELECT COUNT(*) as count FROM wanakwaya WHERE status = 'active'").fetchone()
    
    return render_template('dashboard.html', wanakwaya_count=wanakwaya_count['count'], username=session['username'], now=now)

# ============ KWAYA YETU ROUTES ============
@app.route('/kwaya_yetu/historia')
def historia_kwaya():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('historia_kwaya.html')

@app.route('/kwaya_yetu/somo_msimamizi')
def somo_msimamizi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('somo_msimamizi.html')

@app.route('/kwaya_yetu/mwanzilishi')
def mwanzilishi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mwanzilishi.html')

@app.route('/kwaya_yetu/sifa/mwanakwaya')
def kuwa_mwanakwaya():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/sifa/mwalimu')
def kuwa_mwalimu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/sifa/kiongozi')
def kuwa_kiongozi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/sifa/mfadhili')
def kuwa_mfadhili():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/sifa/rafiki')
def kuwa_rafiki():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/sifa/mlezi')
def kuwa_mlezi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sifa_vigezo.html')

@app.route('/kwaya_yetu/malengo/mfupi')
def malengo_mfupi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('malengo.html')

@app.route('/kwaya_yetu/malengo/kati')
def malengo_kati():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('malengo.html')

@app.route('/kwaya_yetu/malengo/mrefu')
def malengo_mrefu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('malengo.html')

@app.route('/mission')
def mission():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/vision')
def vision():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/core-values')
def core_values():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/falsafa')
def falsafa():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/principles')
def principles():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/code-of-conduct')
def code_of_conduct():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mission_vision.html')

@app.route('/weekly-calendar')
def weekly_calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('calendar.html')

@app.route('/monthly-calendar')
def monthly_calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('calendar.html')

@app.route('/yearly-calendar')
def yearly_calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('calendar.html')

# ============ API ROUTES FOR WANAKWAYA ============
@app.route('/api/wanakwaya')
def api_wanakwaya():
    if 'user_id' not in session:
        return jsonify([])
    
    with get_db() as conn:
        wanakwaya = conn.execute("SELECT * FROM wanakwaya ORDER BY sauti, jina").fetchall()
        result = []
        
        voice_counts = {'Soprano': 0, 'Alto': 0, 'Tenor': 0, 'Bass': 0}
        for w in wanakwaya:
            if w['sauti'] in voice_counts:
                voice_counts[w['sauti']] += 1
        
        voice_current = {'Soprano': 0, 'Alto': 0, 'Tenor': 0, 'Bass': 0}
        
        current_user = conn.execute('SELECT role_id FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        is_admin = current_user and current_user['role_id'] == 1
        is_viewer = current_user and current_user['role_id'] == 5
        
        for w in wanakwaya:
            if w['sauti'] in voice_current:
                voice_current[w['sauti']] += 1
            
            prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(w['sauti'], 'X')
            member_number = f"{prefix}{str(voice_current[w['sauti']]).zfill(3)}"
            
            result.append({
                'id': w['id'],
                'jina': w['jina'],
                'simu': w['simu'],
                'sauti': w['sauti'],
                'anwani': w['anwani'],
                'tarehe_jiunga': w['tarehe_jiunga'],
                'member_number': member_number,
                'status': w['status'],
                'is_admin': is_admin,
                'is_viewer': is_viewer
            })
        return jsonify(result)

@app.route('/api/wanakwaya/save', methods=['POST'])
def api_save_wanakwaya():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    member_id = request.form.get('member_id')
    jina = request.form['jina']
    simu = request.form['simu']
    sauti = request.form['sauti']
    anwani = request.form.get('anwani', '')
    
    valid_name, name_result = validate_name(jina)
    if not valid_name:
        return jsonify({'success': False, 'message': name_result}), 400
    
    valid_phone, phone_result = validate_phone(simu)
    if not valid_phone:
        return jsonify({'success': False, 'message': 'Namba ya simu lazima iwe na tarakimu 10. Mfano: 0712345678'}), 400
    
    with get_db() as conn:
        if member_id:
            conn.execute("UPDATE wanakwaya SET jina=?, simu=?, sauti=?, anwani=? WHERE id=?", 
                        (name_result, phone_result, sauti, anwani, member_id))
        else:
            conn.execute("INSERT INTO wanakwaya (jina, simu, sauti, anwani, status) VALUES (?, ?, ?, ?, 'active')", 
                        (name_result, phone_result, sauti, anwani))
        conn.commit()
    return jsonify({'success': True, 'message': 'Mwanakwaya amehifadhiwa kikamilifu'})

@app.route('/api/wanakwaya/suspend', methods=['POST'])
def api_suspend_wanakwaya():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('id')
    status = data.get('status')
    
    with get_db() as conn:
        conn.execute("UPDATE wanakwaya SET status = ? WHERE id = ?", (status, member_id))
        conn.commit()
    
    status_text = 'activated' if status == 'active' else 'suspended'
    return jsonify({'success': True, 'message': f'Mwanakwaya ame{status_text} kikamilifu', 'new_status': status})

@app.route('/api/get_wimbo/<int:id>')
def api_get_wimbo(id):
    if 'user_id' not in session:
        return jsonify({})
    
    with get_db() as conn:
        wimbo = conn.execute("SELECT * FROM nyimbo WHERE id = ?", (id,)).fetchone()
        if wimbo:
            return jsonify({
                'id': wimbo['id'],
                'jina': wimbo['jina'],
                'mtunzi': wimbo['mtunzi'],
                'key': wimbo['key'],
                'time_signature': wimbo['time_signature'],
                'tempo': wimbo['tempo'],
                'kundi': wimbo['kundi']
            })
    return jsonify({})

# ============ WANAKWAYA ROUTES ============
@app.route('/wanakwaya', methods=['GET', 'POST'])
def wanakwaya():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        jina = request.form['jina']
        simu = request.form['simu']
        sauti = request.form['sauti']
        anwani = request.form.get('anwani', '')
        
        with get_db() as conn:
            conn.execute("INSERT INTO wanakwaya (jina, simu, sauti, anwani, status) VALUES (?, ?, ?, ?, 'active')", (jina, simu, sauti, anwani))
            conn.commit()
        flash('Mwanakwaya ameongezwa!', 'success')
        return redirect(url_for('wanakwaya'))
    
    with get_db() as conn:
        orodha = conn.execute("SELECT * FROM wanakwaya ORDER BY id DESC").fetchall()
    
    return render_template('wanakwaya.html', wanakwaya=orodha)

@app.route('/futa_mwanakwaya/<int:id>')
def futa_mwanakwaya(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        conn.execute("DELETE FROM wanakwaya WHERE id = ?", (id,))
        conn.commit()
    flash('Mwanakwaya amefutwa!', 'success')
    return redirect(url_for('wanakwaya'))

@app.route('/edit_wanakwaya', methods=['POST'])
def edit_wanakwaya():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    wanakwaya_id = request.form['wanakwaya_id']
    jina = request.form['jina']
    simu = request.form['simu']
    sauti = request.form['sauti']
    anwani = request.form.get('anwani', '')
    
    with get_db() as conn:
        conn.execute("UPDATE wanakwaya SET jina = ?, simu = ?, sauti = ?, anwani = ? WHERE id = ?", (jina, simu, sauti, anwani, wanakwaya_id))
        conn.commit()
    flash('Taarifa za mwanakwaya zimehaririwa!', 'success')
    return redirect(url_for('wanakwaya'))

# ============ MAHUDHURIO SIMPLE ROUTES ============
@app.route('/mahudhurio_simple', methods=['GET', 'POST'])
def mahudhurio_simple():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    tarehe_leo = datetime.now().strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        mwanakwaya_id = request.form['mwanakwaya_id']
        tarehe = request.form['tarehe']
        
        with get_db() as conn:
            kipo = conn.execute("SELECT * FROM mahudhurio WHERE mwanakwaya_id = ? AND tarehe = ?", (mwanakwaya_id, tarehe)).fetchone()
            if not kipo:
                conn.execute("INSERT INTO mahudhurio (mwanakwaya_id, tarehe) VALUES (?, ?)", (mwanakwaya_id, tarehe))
                conn.commit()
                flash('Mahudhurio yamerekodiwa!', 'success')
            else:
                flash('Mwanakwaya huyo amesharekodiwa kwa tarehe hii!', 'info')
        
        return redirect(url_for('mahudhurio_simple'))
    
    with get_db() as conn:
        wanakwaya = conn.execute("SELECT * FROM wanakwaya WHERE status = 'active'").fetchall()
        mahudhurio_leo = conn.execute("SELECT m.*, w.jina FROM mahudhurio m JOIN wanakwaya w ON m.mwanakwaya_id = w.id WHERE m.tarehe = ? ORDER BY w.jina", (tarehe_leo,)).fetchall()
    
    return render_template('mahudhurio_simple.html', wanakwaya=wanakwaya, mahudhurio=mahudhurio_leo, tarehe_leo=tarehe_leo)

# ============ MAHUDHURIO DETAILED ROUTES ============
@app.route('/mahudhurio')
def mahudhurio_enhanced():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        current_event = conn.execute("SELECT * FROM current_event ORDER BY id DESC LIMIT 1").fetchone()
        if not current_event:
            current_event = {'tukio': 'Misa', 'tarehe': datetime.now().strftime('%Y-%m-%d')}
        
        penalty_settings = conn.execute("SELECT * FROM penalty_settings").fetchall()
        
        wanakwaya_soprano = conn.execute("SELECT * FROM wanakwaya WHERE sauti = 'Soprano' AND status = 'active' ORDER BY jina").fetchall()
        wanakwaya_alto = conn.execute("SELECT * FROM wanakwaya WHERE sauti = 'Alto' AND status = 'active' ORDER BY jina").fetchall()
        wanakwaya_tenor = conn.execute("SELECT * FROM wanakwaya WHERE sauti = 'Tenor' AND status = 'active' ORDER BY jina").fetchall()
        wanakwaya_bass = conn.execute("SELECT * FROM wanakwaya WHERE sauti = 'Bass' AND status = 'active' ORDER BY jina").fetchall()
        
        today = datetime.now().strftime('%Y-%m-%d')
        attendance = {}
        records = conn.execute("SELECT * FROM mahudhurio_detailed WHERE tarehe = ? AND tukio = ?", (today, current_event['tukio'])).fetchall()
        for rec in records:
            attendance[rec['mwanakwaya_id']] = {
                'status': rec['status'],
                'dakika_chelewa': rec['dakika_chelewa'],
                'penalty': rec['penalty']
            }
    
    return render_template('mahudhurio.html', soprano=wanakwaya_soprano, alto=wanakwaya_alto, tenor=wanakwaya_tenor, bass=wanakwaya_bass, current_event=current_event, penalty_settings=penalty_settings, attendance=attendance)

@app.route('/api/mahudhurio/update', methods=['POST'])
def api_update_attendance():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    status = data.get('status')
    dakika_chelewa = data.get('dakika_chelewa', 0)
    tukio = data.get('tukio')
    member_name = data.get('member_name')
    sauti = data.get('sauti')
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM penalty_settings WHERE tukio = ?", (tukio,)).fetchone()
        if not settings:
            settings = {'penalty_utoro': 20000, 'penalty_kwa_dakika': 1000, 'siku_za_kudouble': 10}
        
        penalty = 0
        penalty_type = None
        
        if status == 'absent':
            penalty = settings['penalty_utoro']
            penalty_type = 'utoro'
        elif status == 'late' and dakika_chelewa > 0:
            penalty = dakika_chelewa * settings['penalty_kwa_dakika']
            penalty_type = 'chelewa'
        
        double_date = (datetime.now() + timedelta(days=settings['siku_za_kudouble'])).strftime('%Y-%m-%d')
        
        existing = conn.execute("SELECT * FROM mahudhurio_detailed WHERE mwanakwaya_id = ? AND tarehe = ? AND tukio = ?", (member_id, today, tukio)).fetchone()
        
        if existing:
            conn.execute("UPDATE mahudhurio_detailed SET status = ?, dakika_chelewa = ?, penalty = ?, tarehe_penalty_double = ? WHERE mwanakwaya_id = ? AND tarehe = ? AND tukio = ?", (status, dakika_chelewa, penalty, double_date, member_id, today, tukio))
        else:
            conn.execute("INSERT INTO mahudhurio_detailed (mwanakwaya_id, mwanakwaya_jina, sauti, tukio, tarehe, status, dakika_chelewa, penalty, tarehe_penalty_double) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (member_id, member_name, sauti, tukio, today, status, dakika_chelewa, penalty, double_date))
        
        if penalty > 0:
            existing_penalty = conn.execute("SELECT id FROM mahudhurio_penalties WHERE member_id = ? AND tukio = ? AND tarehe_penalty = ?", (member_id, tukio, today)).fetchone()
            if existing_penalty:
                conn.execute("UPDATE mahudhurio_penalties SET penalty_amount = ?, penalty_type = ?, remaining_amount = ?, imelipwa = 0 WHERE id = ?", (penalty, penalty_type, penalty, existing_penalty['id']))
            else:
                conn.execute("INSERT INTO mahudhurio_penalties (member_id, penalty_amount, penalty_type, tukio, tarehe_penalty, imelipwa, remaining_amount) VALUES (?, ?, ?, ?, ?, 0, ?)", (member_id, penalty, penalty_type, tukio, today, penalty))
        else:
            conn.execute("UPDATE mahudhurio_penalties SET imelipwa = 1, remaining_amount = 0 WHERE member_id = ? AND tukio = ? AND tarehe_penalty = ? AND imelipwa = 0", (member_id, tukio, today))
        
        conn.commit()
    
    return jsonify({'success': True, 'penalty': penalty, 'double_date': double_date})

@app.route('/api/mahudhurio/settings/update', methods=['POST'])
def api_update_penalty_settings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    tukio = data.get('tukio')
    penalty_utoro = data.get('penalty_utoro')
    penalty_kwa_dakika = data.get('penalty_kwa_dakika')
    siku_za_kudouble = data.get('siku_za_kudouble')
    
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO penalty_settings (tukio, penalty_utoro, penalty_kwa_dakika, siku_za_kudouble) VALUES (?, ?, ?, ?)", (tukio, penalty_utoro, penalty_kwa_dakika, siku_za_kudouble))
        conn.commit()
    
    return jsonify({'success': True})

@app.route('/api/mahudhurio/event/update', methods=['POST'])
def api_update_current_event():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    tukio = data.get('tukio')
    tarehe = data.get('tarehe')
    
    with get_db() as conn:
        conn.execute("DELETE FROM current_event")
        conn.execute("INSERT INTO current_event (tukio, tarehe) VALUES (?, ?)", (tukio, tarehe))
        conn.commit()
    
    return jsonify({'success': True})

@app.route('/api/mahudhurio/member/<int:id>')
def api_get_member_attendance(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        member = conn.execute("SELECT * FROM wanakwaya WHERE id = ?", (id,)).fetchone()
        records = conn.execute("SELECT * FROM mahudhurio_detailed WHERE mwanakwaya_id = ? ORDER BY tarehe DESC", (id,)).fetchall()
        
        total_penalty = 0
        for rec in records:
            if not rec['imelipwa']:
                total_penalty += rec['penalty']
        
        last_penalty_date = None
        if records:
            last_penalty_date = records[0]['tarehe']
            days_since = (datetime.now() - datetime.strptime(last_penalty_date, '%Y-%m-%d')).days
        else:
            days_since = 0
        
        records_list = []
        for rec in records:
            records_list.append({
                'id': rec['id'],
                'tukio': rec['tukio'],
                'tarehe': rec['tarehe'],
                'status': rec['status'],
                'dakika_chelewa': rec['dakika_chelewa'],
                'penalty': rec['penalty'],
                'imelipwa': rec['imelipwa'],
                'double_date': rec['tarehe_penalty_double']
            })
        
        return jsonify({
            'success': True,
            'member': {
                'id': member['id'],
                'jina': member['jina'],
                'sauti': member['sauti'],
                'status': member['status']
            },
            'records': records_list,
            'total_penalty': total_penalty,
            'days_since_last_penalty': days_since,
            'should_be_suspended': days_since >= 30 and total_penalty > 0
        })

# ============ RATIBA EVENTS ROUTES ============
@app.route('/ratiba_events', methods=['GET', 'POST'])
def ratiba_events():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        tukio = request.form['tukio']
        tarehe = request.form['tarehe']
        mahali = request.form.get('mahali', '')
        maelezo = request.form.get('maelezo', '')
        
        with get_db() as conn:
            conn.execute("INSERT INTO ratiba (tukio, tarehe, mahali, maelezo) VALUES (?, ?, ?, ?)", (tukio, tarehe, mahali, maelezo))
            conn.commit()
        flash('Ratiba imeongezwa!', 'success')
        return redirect(url_for('ratiba_events'))
    
    with get_db() as conn:
        orodha = conn.execute("SELECT * FROM ratiba WHERE tarehe >= DATE('now') ORDER BY tarehe ASC").fetchall()
    
    return render_template('ratiba_events.html', ratiba=orodha)

# ============ ADA OLD ROUTES (backward compatible) ============
@app.route('/ada_old', methods=['GET', 'POST'])
def ada_old():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        mwanakwaya_id = request.form['mwanakwaya_id']
        kiasi = request.form['kiasi']
        mwezi = request.form['mwezi']
        mwaka = request.form['mwaka']
        
        with get_db() as conn:
            conn.execute("INSERT INTO ada (mwanakwaya_id, kiasi, mwezi, mwaka) VALUES (?, ?, ?, ?)", (mwanakwaya_id, kiasi, mwezi, mwaka))
            conn.commit()
        flash('Ada imeongezwa!', 'success')
        return redirect(url_for('ada_old'))
    
    with get_db() as conn:
        wanakwaya = conn.execute("SELECT * FROM wanakwaya WHERE status = 'active'").fetchall()
        orodha_ada = conn.execute("SELECT a.*, w.jina FROM ada a JOIN wanakwaya w ON a.mwanakwaya_id = w.id ORDER BY a.id DESC").fetchall()
    
    return render_template('ada_old.html', wanakwaya=wanakwaya, ada=orodha_ada)

@app.route('/lipa_ada/<int:id>')
def lipa_ada(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        conn.execute("UPDATE ada SET imelipwa = 1 WHERE id = ?", (id,))
        conn.commit()
    flash('Ada imelipwa kikamilifu!', 'success')
    return redirect(url_for('ada_old'))

# ============ ADA ENHANCED ROUTES (NEW) ============
@app.route('/ada')
def ada_enhanced():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        if not settings:
            settings = {'kiasi_kwa_mwezi': 5000, 'tarehe_penalty': 15, 'penalty_asilimia': 10}
        
        now = datetime.now()
        current_mwezi = now.strftime('%B')
        current_mwaka = now.year
        
        existing = conn.execute("SELECT * FROM ada_monthly WHERE mwezi = ? AND mwaka = ? LIMIT 1", (current_mwezi, current_mwaka)).fetchone()
        if not existing:
            wanakwaya = conn.execute("SELECT id FROM wanakwaya WHERE status = 'active'").fetchall()
            for w in wanakwaya:
                conn.execute("INSERT INTO ada_monthly (mwanakwaya_id, mwezi, mwaka, kiasi_kinachotakiwa, jumla_ya_deni) VALUES (?, ?, ?, ?, ?)", (w['id'], current_mwezi, current_mwaka, settings['kiasi_kwa_mwezi'], settings['kiasi_kwa_mwezi']))
            conn.commit()
        
        ada_records = conn.execute("""
            SELECT w.id, w.jina, w.simu, w.sauti, w.status,
                   COALESCE(a.kiasi_kinachotakiwa, ?) as kinachotakiwa,
                   COALESCE(a.kiasi_kilicholipwa, 0) as imelipwa,
                   COALESCE(a.penalty, 0) as penalty,
                   COALESCE(a.jumla_ya_deni, ?) as deni,
                   a.id as monthly_id,
                   a.imelipwa as status_ada
            FROM wanakwaya w
            LEFT JOIN ada_monthly a ON w.id = a.mwanakwaya_id AND a.mwezi = ? AND a.mwaka = ?
            WHERE w.status = 'active'
            ORDER BY w.jina
        """, (settings['kiasi_kwa_mwezi'], settings['kiasi_kwa_mwezi'], current_mwezi, current_mwaka)).fetchall()
        
        total_kiasi = sum(r['kinachotakiwa'] for r in ada_records)
        total_kilolipwa = sum(r['imelipwa'] for r in ada_records)
        total_deni = sum(r['deni'] for r in ada_records)
        total_penalty = sum(r['penalty'] for r in ada_records)
        
        payment_history = conn.execute("""
            SELECT m.*, w.jina, w.sauti, w.simu
            FROM ada_malipo m
            JOIN wanakwaya w ON m.mwanakwaya_id = w.id
            ORDER BY m.tarehe DESC LIMIT 50
        """).fetchall()
    
    return render_template('ada.html', ada_records=ada_records, settings=settings, total_kiasi=total_kiasi, total_kilolipwa=total_kilolipwa, total_deni=total_deni, total_penalty=total_penalty, payment_history=payment_history, current_mwezi=current_mwezi, current_mwaka=current_mwaka)

@app.route('/ada_settings', methods=['GET', 'POST'])
def ada_settings_page():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Sehemu hii ni kwa admin pekee!', 'error')
        return redirect(url_for('ada_enhanced'))
    
    with get_db() as conn:
        if request.method == 'POST':
            kiasi = float(request.form['kiasi_kwa_mwezi'])
            tarehe_penalty = int(request.form['tarehe_penalty'])
            penalty_asilimia = float(request.form['penalty_asilimia'])
            
            now = datetime.now()
            conn.execute("INSERT INTO ada_settings (kiasi_kwa_mwezi, tarehe_penalty, penalty_asilimia, mwaka, mwezi, imeanzishwa) VALUES (?, ?, ?, ?, ?, ?)", (kiasi, tarehe_penalty, penalty_asilimia, now.year, now.month, now.date()))
            conn.commit()
            
            flash('Mpangilio wa ada umebadilishwa kikamilifu!', 'success')
            return redirect(url_for('ada_enhanced'))
        
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        if not settings:
            settings = {'kiasi_kwa_mwezi': 5000, 'tarehe_penalty': 15, 'penalty_asilimia': 10}
        
        history = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 10").fetchall()
    
    return render_template('ada_settings.html', settings=settings, history=history)

@app.route('/api/ada/make_payment', methods=['POST'])
def api_make_payment():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    kiasi = float(data.get('kiasi', 0))
    monthly_id = data.get('monthly_id')
    maelezo = data.get('maelezo', 'Malipo ya ada')
    
    if kiasi <= 0:
        return jsonify({'success': False, 'message': 'Kiasi lazima kiwe kikubwa kuliko sifuri'}), 400
    
    with get_db() as conn:
        ada_record = conn.execute("SELECT * FROM ada_monthly WHERE id = ?", (monthly_id,)).fetchone()
        if not ada_record:
            return jsonify({'success': False, 'message': 'Ada record haipatikani'}), 404
        
        new_paid = ada_record['kiasi_kilicholipwa'] + kiasi
        new_debt = ada_record['jumla_ya_deni'] - kiasi
        if new_debt < 0:
            new_debt = 0
        
        if new_debt <= 0:
            imelipwa = 1
            tarehe_malipo = datetime.now().date()
        else:
            imelipwa = 2
            tarehe_malipo = None
        
        conn.execute("UPDATE ada_monthly SET kiasi_kilicholipwa = ?, jumla_ya_deni = ?, imelipwa = ?, tarehe_malipo = ? WHERE id = ?", (new_paid, new_debt, imelipwa, tarehe_malipo, monthly_id))
        
        receipt_no = f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{member_id}"
        
        conn.execute("INSERT INTO ada_malipo (mwanakwaya_id, kiasi, tarehe, maelezo, monthly_id, receipt_no) VALUES (?, ?, ?, ?, ?, ?)", (member_id, kiasi, datetime.now().date(), maelezo, monthly_id, receipt_no))
        conn.execute("INSERT INTO mapato (chanzo, kiasi, maelezo, tarehe) VALUES (?, ?, ?, ?)", ('Ada - ' + ada_record['mwezi'] + ' ' + str(ada_record['mwaka']), kiasi, f"Malipo ya ada kutoka kwa member #{member_id}", datetime.now().date()))
        conn.commit()
        
        return jsonify({'success': True, 'message': f'Malipo ya TSh {kiasi:,.0f} yamekamilika!', 'receipt_no': receipt_no, 'new_debt': new_debt, 'imelipwa': imelipwa})

@app.route('/api/ada/apply_penalty', methods=['POST'])
def api_apply_penalty():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        penalty_asilimia = settings['penalty_asilimia'] / 100
        tarehe_penalty = settings['tarehe_penalty']
        
        now = datetime.now()
        today = now.day
        
        if today >= tarehe_penalty:
            records = conn.execute("SELECT * FROM ada_monthly WHERE imelipwa < 1 AND jumla_ya_deni > 0").fetchall()
            for rec in records:
                penalty_amount = rec['jumla_ya_deni'] * penalty_asilimia
                new_total = rec['jumla_ya_deni'] + penalty_amount
                new_penalty = rec['penalty'] + penalty_amount
                conn.execute("UPDATE ada_monthly SET penalty = ?, jumla_ya_deni = ? WHERE id = ?", (new_penalty, new_total, rec['id']))
            conn.commit()
            return jsonify({'success': True, 'message': f'Penalty imeongezwa kwa wanakwaya wote wanaodaiwa'})
        else:
            return jsonify({'success': False, 'message': f'Penalty inaanza tarehe {tarehe_penalty} ya kila mwezi'})

@app.route('/ada/receipt/<receipt_no>')
def ada_receipt(receipt_no):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        payment = conn.execute("""
            SELECT m.*, w.jina, w.simu, w.sauti, a.mwezi, a.mwaka, a.kiasi_kinachotakiwa
            FROM ada_malipo m
            JOIN wanakwaya w ON m.mwanakwaya_id = w.id
            LEFT JOIN ada_monthly a ON m.monthly_id = a.id
            WHERE m.receipt_no = ?
        """, (receipt_no,)).fetchone()
        
        if not payment:
            flash('Receipt haipatikani!', 'error')
            return redirect(url_for('ada_enhanced'))
    
    return render_template('ada_receipt_print.html', payment=payment)

@app.route('/ada/report')
def ada_report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', None)
    
    with get_db() as conn:
        if month:
            records = conn.execute("SELECT a.*, w.jina, w.sauti, w.simu FROM ada_monthly a JOIN wanakwaya w ON a.mwanakwaya_id = w.id WHERE a.mwaka = ? AND a.mwezi = ? ORDER BY a.jumla_ya_deni DESC", (year, month)).fetchall()
            summary = conn.execute("SELECT SUM(kiasi_kinachotakiwa) as total_expected, SUM(kiasi_kilicholipwa) as total_paid, SUM(jumla_ya_deni) as total_debt, SUM(penalty) as total_penalty, COUNT(CASE WHEN imelipwa = 1 THEN 1 END) as fully_paid, COUNT(CASE WHEN imelipwa = 2 THEN 1 END) as partial_paid, COUNT(CASE WHEN imelipwa = 0 THEN 1 END) as not_paid FROM ada_monthly WHERE mwaka = ? AND mwezi = ?", (year, month)).fetchone()
        else:
            records = conn.execute("SELECT a.*, w.jina, w.sauti, w.simu FROM ada_monthly a JOIN wanakwaya w ON a.mwanakwaya_id = w.id WHERE a.mwaka = ? ORDER BY a.mwezi, a.jumla_ya_deni DESC", (year,)).fetchall()
            summary = conn.execute("SELECT SUM(kiasi_kinachotakiwa) as total_expected, SUM(kiasi_kilicholipwa) as total_paid, SUM(jumla_ya_deni) as total_debt, SUM(penalty) as total_penalty FROM ada_monthly WHERE mwaka = ?", (year,)).fetchone()
        
        top_payers = conn.execute("SELECT w.jina, w.sauti, SUM(m.kiasi) as total_paid, COUNT(m.id) as payment_count FROM ada_malipo m JOIN wanakwaya w ON m.mwanakwaya_id = w.id WHERE strftime('%Y', m.tarehe) = ? GROUP BY m.mwanakwaya_id ORDER BY total_paid DESC LIMIT 10", (str(year),)).fetchall()
        
        months_list = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai', 'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']
    
    return render_template('ada_report.html', records=records, summary=summary, top_payers=top_payers, year=year, month=month, months=months_list)

@app.route('/api/ada/send_reminder', methods=['POST'])
def api_send_reminder():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    
    with get_db() as conn:
        if member_id:
            member = conn.execute("SELECT * FROM wanakwaya WHERE id = ?", (member_id,)).fetchone()
            debt = conn.execute("SELECT SUM(jumla_ya_deni) as total FROM ada_monthly WHERE mwanakwaya_id = ? AND imelipwa < 1", (member_id,)).fetchone()
            return jsonify({'success': True, 'message': f'Reminder imetumwa kwa {member["jina"]}', 'debt': debt['total'] or 0})
        else:
            debtors = conn.execute("SELECT w.id, w.jina, w.simu, SUM(a.jumla_ya_deni) as total_debt FROM wanakwaya w JOIN ada_monthly a ON w.id = a.mwanakwaya_id WHERE a.imelipwa < 1 AND a.jumla_ya_deni > 0 GROUP BY w.id").fetchall()
            return jsonify({'success': True, 'message': f'Reminder imetumwa kwa {len(debtors)} wanakwaya wanaodaiwa.', 'count': len(debtors)})

# ============ MAPATO ROUTES ============
@app.route('/mapato', methods=['GET', 'POST'])
def mapato():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        chanzo = request.form['chanzo']
        kiasi = request.form['kiasi']
        maelezo = request.form.get('maelezo', '')
        
        with get_db() as conn:
            conn.execute("INSERT INTO mapato (chanzo, kiasi, maelezo) VALUES (?, ?, ?)", (chanzo, kiasi, maelezo))
            conn.commit()
        flash('Mapato yameongezwa!', 'success')
        return redirect(url_for('mapato'))
    
    with get_db() as conn:
        orodha = conn.execute("SELECT * FROM mapato ORDER BY tarehe DESC").fetchall()
        jumla = conn.execute("SELECT SUM(kiasi) as jumla FROM mapato").fetchone()
    
    return render_template('mapato.html', mapato=orodha, jumla=jumla['jumla'] or 0)

# ============ ALBAMU ROUTES ============
@app.route('/albamu', methods=['GET', 'POST'])
def albamu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        jina_albamu = request.form['jina_albamu']
        mwaka = request.form['mwaka']
        nyimbo = request.form.get('nyimbo', '')
        maelezo = request.form.get('maelezo', '')
        
        with get_db() as conn:
            conn.execute("INSERT INTO albamu (jina_albamu, mwaka, nyimbo, maelezo) VALUES (?, ?, ?, ?)", (jina_albamu, mwaka, nyimbo, maelezo))
            conn.commit()
        flash('Albamu imeongezwa!', 'success')
        return redirect(url_for('albamu'))
    
    with get_db() as conn:
        orodha = conn.execute("SELECT * FROM albamu ORDER BY mwaka DESC").fetchall()
    
    return render_template('albamu.html', albamu=orodha)

# ============ UONGOZI, KAMATI KUU, ASSETS ============
@app.route('/uongozi')
def uongozi():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('uongozi.html')

@app.route('/kamati_kuu')
def kamati_kuu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('kamati_kuu.html')

@app.route('/assets')
def assets():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('assets.html')

# ============ RATIBA YA NYIMBO ROUTES ============
@app.route('/ratiba/mwaka/<mwaka>')
def ratiba_mwaka_kanisa(mwaka):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('mwaka_kanisa.html', mwaka=mwaka)

@app.route('/ratiba/makundi/<kundi>')
def ratiba_makundi_nyimbo(kundi):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        nyimbo = conn.execute("SELECT * FROM nyimbo WHERE kundi = ? ORDER BY id DESC", (kundi,)).fetchall()
    
    return render_template('makundi_nyimbo.html', kundi=kundi, nyimbo=nyimbo)

@app.route('/ratiba/tengeneza')
def ratiba_tengeneza():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        makundi_yote = ['Mwanzo', 'Shangilio', 'Zaburi', 'Maandamano', 'Misa', 'Antifona', 'Sadaka', 'Komunyo', 'Shukrani', 'Mwisho']
        nyimbo_kwa_kundi = {}
        for k in makundi_yote:
            nyimbo_kwa_kundi[k] = conn.execute("SELECT id, jina FROM nyimbo WHERE kundi = ? ORDER BY jina", (k,)).fetchall()
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('tengeneza_ratiba.html', nyimbo_kwa_kundi=nyimbo_kwa_kundi, today=today)

@app.route('/ratiba/ongezwa_wimbo', methods=['GET', 'POST'])
def ratiba_ongezwa_wimbo():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        jina = request.form['jina']
        mtunzi = request.form.get('mtunzi', '')
        maneno = request.form.get('maneno', '')
        key = request.form.get('key', '')
        time_signature = request.form.get('time_signature', '')
        tempo = request.form.get('tempo', '')
        kundi = request.form['kundi']
        
        nota_pdf = ''
        midi_file = ''
        
        if 'nota_pdf' in request.files and request.files['nota_pdf'].filename:
            nota_pdf = request.files['nota_pdf'].filename
            request.files['nota_pdf'].save(f'static/uploads/{nota_pdf}')
        
        if 'midi_file' in request.files and request.files['midi_file'].filename:
            midi_file = request.files['midi_file'].filename
            request.files['midi_file'].save(f'static/uploads/{midi_file}')
        
        with get_db() as conn:
            conn.execute("INSERT INTO nyimbo (jina, mtunzi, maneno, key, time_signature, tempo, kundi, nota_pdf, midi_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (jina, mtunzi, maneno, key, time_signature, tempo, kundi, nota_pdf, midi_file))
            conn.commit()
        
        flash('Wimbo umeongezwa kikamilifu!', 'success')
        return redirect(url_for('ratiba_makundi_nyimbo', kundi=kundi))
    
    return render_template('ongezwa_wimbo.html')

@app.route('/ratiba/wimbo/<int:id>')
def ratiba_view_wimbo(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        wimbo = conn.execute("SELECT * FROM nyimbo WHERE id = ?", (id,)).fetchone()
    
    return render_template('view_wimbo.html', wimbo=wimbo)

@app.route('/ratiba/futa_wimbo/<int:id>')
def ratiba_futa_wimbo(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        wimbo = conn.execute("SELECT kundi FROM nyimbo WHERE id = ?", (id,)).fetchone()
        kundi = wimbo['kundi']
        conn.execute("DELETE FROM nyimbo WHERE id = ?", (id,))
        conn.commit()
    
    flash('Wimbo umefutwa!', 'success')
    return redirect(url_for('ratiba_makundi_nyimbo', kundi=kundi))

# ============ API ROUTES FOR TIMETABLE ============
@app.route('/api/generate_timetable_v2', methods=['POST'])
def generate_timetable_v2():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    timetable = []
    
    section_names = {
        'mwanzo': 'MWANZO', 'kyrie': 'KYRIE', 'gloria': 'GLORIA',
        'sanctus': 'SANCTUS', 'agnus': 'AGNUS DEI', 'shangilio': 'SHANGILIO',
        'zaburi': 'ZABURI', 'sadaka': 'SADAKA', 'komunyo': 'KOMUNYO',
        'shukrani': 'SHUKRANI', 'mwisho': 'MWISHO'
    }
    
    songs_data = data.get('songsData', {})
    
    with get_db() as conn:
        for section, songs in songs_data.items():
            if songs and len(songs) > 0:
                for idx, song in enumerate(songs):
                    if 'mtunzi' in song and song['mtunzi']:
                        timetable.append({
                            'section': section,
                            'sehemu': section_names.get(section, section),
                            'wimbo_id': song['id'],
                            'wimbo_jina': song['jina'],
                            'number': idx + 1,
                            'mtunzi': song.get('mtunzi', '-'),
                            'key': song.get('key', '-'),
                            'time_sig': song.get('time_sig', '-'),
                            'tempo': song.get('tempo', '-')
                        })
                    else:
                        wimbo = conn.execute("SELECT jina, mtunzi, key, time_signature, tempo FROM nyimbo WHERE id = ?", (song['id'],)).fetchone()
                        if wimbo:
                            timetable.append({
                                'section': section,
                                'sehemu': section_names.get(section, section),
                                'wimbo_id': song['id'],
                                'wimbo_jina': song['jina'],
                                'number': idx + 1,
                                'mtunzi': wimbo['mtunzi'] or '-',
                                'key': wimbo['key'] or '-',
                                'time_sig': wimbo['time_signature'] or '-',
                                'tempo': wimbo['tempo'] or '-'
                            })
    
    tukio = data.get('tukio', '')
    tarehe = data.get('tarehe', '')
    jumapili = data.get('jumapili', '')
    mwaka = data.get('mwaka', '')
    tukio_text = data.get('tukioText', '')
    
    with get_db() as conn:
        conn.execute("INSERT INTO timetable_saved (tukio, tarehe, jumapili_ngapi, mwaka_kanisa, data) VALUES (?, ?, ?, ?, ?)", (tukio_text, tarehe, jumapili, mwaka, json.dumps(timetable)))
        conn.commit()
    
    return jsonify({'success': True, 'timetable': timetable, 'tukio_text': tukio_text, 'tarehe': tarehe})

@app.route('/api/generate_timetable', methods=['POST'])
def generate_timetable():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    timetable = []
    
    section_names = {
        'mwanzo': 'MWANZO', 'kyrie': 'KYRIE', 'gloria': 'GLORIA',
        'sanctus': 'SANCTUS', 'agnus': 'AGNUS DEI', 'shangilio': 'SHANGILIO',
        'zaburi': 'ZABURI', 'sadaka': 'SADAKA', 'komunyo': 'KOMUNYO',
        'shukrani': 'SHUKRANI', 'mwisho': 'MWISHO'
    }
    
    with get_db() as conn:
        for section, songs in data.items():
            if songs and len(songs) > 0:
                for idx, song in enumerate(songs):
                    wimbo = conn.execute("SELECT jina, mtunzi, key, time_signature, tempo FROM nyimbo WHERE id = ?", (song['id'],)).fetchone()
                    if wimbo:
                        timetable.append({
                            'section': section,
                            'sehemu': section_names.get(section, section),
                            'wimbo_id': song['id'],
                            'wimbo_jina': song['jina'],
                            'number': idx + 1,
                            'mtunzi': wimbo['mtunzi'] or '-',
                            'key': wimbo['key'] or '-',
                            'time_sig': wimbo['time_signature'] or '-',
                            'tempo': wimbo['tempo'] or '-'
                        })
    
    return jsonify({'success': True, 'timetable': timetable})

@app.route('/ratiba/view_only')
def ratiba_view_only():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('view_only_timetable.html')

# ============ API MAPATO SOURCES ============
@app.route('/api/mapato/source/add', methods=['POST'])
def api_add_mapato_source():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    name = data.get('name')
    color = data.get('color', '#1a2a6e')
    target = data.get('target', 0)
    description = data.get('description', '')
    
    with get_db() as conn:
        conn.execute("INSERT INTO mapato_sources (name, color, target, description) VALUES (?, ?, ?, ?)", (name, color, target, description))
        conn.commit()
        return jsonify({'success': True, 'message': 'Chanzo kimeongezwa'})

@app.route('/api/mapato/settings/get', methods=['GET'])
def api_get_target_settings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        global_target = conn.execute('SELECT value FROM system_settings WHERE key = "global_target"').fetchone()
        global_value = global_target[0] if global_target else 10000000
        return jsonify({'success': True, 'global_target': global_value})

@app.route('/api/mapato/settings/save', methods=['POST'])
def api_save_target_settings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    global_target = data.get('global_target', 10000000)
    source_targets = data.get('source_targets', [])
    
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('global_target', ?)", (global_target,))
        for st in source_targets:
            conn.execute("UPDATE mapato_sources SET target = ? WHERE id = ?", (st.get('target', 0), st.get('source_id')))
        conn.commit()
        return jsonify({'success': True, 'message': 'Malengo yamehifadhiwa'})

@app.route('/api/mapato/data')
def api_mapato_data():
    from datetime import datetime
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    mwaka = request.args.get('mwaka', datetime.now().year, type=int)
    
    with get_db() as conn:
        sources = conn.execute("SELECT * FROM mapato_sources ORDER BY id").fetchall()
        sources_list = []
        for s in sources:
            sources_list.append({
                'id': s['id'],
                'name': s['name'],
                'color': s['color'],
                'target': s['target'] or 0,
                'description': s['description'],
                'icon': s['icon'] if 'icon' in s.keys() else '💰'
            })
        
        records_list = []
        
        custom_records = conn.execute("""
            SELECT r.id, r.source_id, r.amount, r.date, r.note, s.name as source_name 
            FROM mapato_records r 
            JOIN mapato_sources s ON r.source_id = s.id 
            WHERE strftime('%Y', r.date) = ?
            ORDER BY r.date DESC
        """, (str(mwaka),)).fetchall()
        for r in custom_records:
            records_list.append({'id': r['id'], 'source_id': r['source_id'], 'source_name': r['source_name'], 'amount': r['amount'], 'date': r['date'], 'note': r['note']})
        
        penalty_payments = conn.execute("""
            SELECT pp.id, pp.member_id, pp.amount, pp.tarehe as date, pp.note, p.penalty_type 
            FROM penalty_payments pp 
            JOIN mahudhurio_penalties p ON pp.penalty_id = p.id 
            WHERE pp.amount > 0 AND strftime('%Y', pp.tarehe) = ?
            ORDER BY pp.tarehe DESC
        """, (str(mwaka),)).fetchall()
        
        utoro_source = conn.execute("SELECT id FROM mapato_sources WHERE name = 'Penalty (Utoro)'").fetchone()
        chelewa_source = conn.execute("SELECT id FROM mapato_sources WHERE name = 'Penalty (Chelewa)'").fetchone()
        utoro_id = utoro_source[0] if utoro_source else 2
        chelewa_id = chelewa_source[0] if chelewa_source else 3
        
        for p in penalty_payments:
            source_id = utoro_id if p['penalty_type'] == 'utoro' else chelewa_id
            source_name = 'Penalty (Utoro)' if p['penalty_type'] == 'utoro' else 'Penalty (Chelewa)'
            records_list.append({'id': f'penalty_{p["id"]}', 'source_id': source_id, 'source_name': source_name, 'amount': p['amount'], 'date': p['date'], 'note': p['note'] or f'Malipo ya {source_name}'})
        
        ada_payments = conn.execute("""
            SELECT am.id, am.kiasi_kilicholipwa as amount, am.tarehe_malipo as date, am.mwezi || ' ' || am.mwaka as note 
            FROM ada_monthly am 
            WHERE am.kiasi_kilicholipwa > 0 AND am.tarehe_malipo IS NOT NULL AND strftime('%Y', am.tarehe_malipo) = ?
            ORDER BY am.tarehe_malipo DESC
        """, (str(mwaka),)).fetchall()
        
        ada_source = conn.execute("SELECT id FROM mapato_sources WHERE name = 'Ada za Kwaya'").fetchone()
        ada_id = ada_source[0] if ada_source else 1
        for a in ada_payments:
            records_list.append({'id': f'ada_{a["id"]}', 'source_id': ada_id, 'source_name': 'Ada za Kwaya', 'amount': a['amount'], 'date': a['date'], 'note': f'Malipo ya ada - {a["note"]}'})
        
        unique_records = {}
        for r in records_list:
            key = f"{r['source_id']}_{r['amount']}_{r['date']}"
            if key not in unique_records:
                unique_records[key] = r
        records_list = list(unique_records.values())
        records_list.sort(key=lambda x: x['date'], reverse=True)
        
        total_income = sum(r['amount'] for r in records_list)
        
        months = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 
                  'Julai', 'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']
        monthly_totals = [0] * 12
        
        for r in records_list:
            if r['date']:
                try:
                    month = int(r['date'].split('-')[1]) - 1
                    if 0 <= month < 12:
                        monthly_totals[month] += r['amount']
                except:
                    pass
        
        monthly_trend = []
        for i, month in enumerate(months):
            monthly_trend.append({
                'mwezi': i + 1,
                'jina': month,
                'kiasi': monthly_totals[i]
            })
        
        income_by_source = {}
        for r in records_list:
            source = r['source_name']
            if source not in income_by_source:
                income_by_source[source] = 0
            income_by_source[source] += r['amount']
        
        global_target = conn.execute("SELECT value FROM system_settings WHERE key = 'global_target'").fetchone()
        global_target_value = float(global_target[0]) if global_target and global_target[0] else 10000000
        
        from datetime import datetime, timedelta
        week_ago = datetime.now() - timedelta(days=7)
        weekly_income = 0
        for r in records_list:
            if r['date']:
                try:
                    date_obj = datetime.strptime(r['date'], '%Y-%m-%d')
                    if date_obj >= week_ago:
                        weekly_income += r['amount']
                except:
                    pass
        
        current_month = datetime.now().month
        current_month_income = monthly_totals[current_month - 1] if current_month - 1 < len(monthly_totals) else 0
        
        return jsonify({
            'success': True,
            'total': total_income,
            'monthly': current_month_income,
            'weekly': weekly_income,
            'monthly_trend': monthly_trend,
            'income_labels': list(income_by_source.keys()),
            'income_by_source': list(income_by_source.values()),
            'by_source': income_by_source,
            'sources': sources_list,
            'records': records_list,
            'global_target': global_target_value
        })

# ============ PENALTY APIs ============
@app.route('/api/mahudhurio/penalty_settings')
def api_get_penalty_settings():
    if 'user_id' not in session:
        return jsonify([]), 401
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM penalty_settings").fetchall()
        result = [{'tukio': s['tukio'], 'penalty_utoro': s['penalty_utoro'], 'penalty_kwa_dakika': s['penalty_kwa_dakika'], 'siku_za_kudouble': s['siku_za_kudouble']} for s in settings]
        return jsonify(result)

@app.route('/api/mahudhurio/penalty_list')
def api_penalty_list():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    with get_db() as conn:
        conn.execute("DELETE FROM mahudhurio_penalties WHERE id NOT IN (SELECT MIN(id) FROM mahudhurio_penalties GROUP BY member_id, tarehe_penalty, tukio)")
        conn.commit()
        
        penalties = conn.execute("""
            SELECT p.id as penalty_id, p.member_id, p.penalty_amount, p.penalty_type, p.tukio,
                   p.tarehe_penalty, p.remaining_amount, w.jina, w.sauti,
                   (10 - CAST((julianday('now') - julianday(p.tarehe_penalty)) AS INTEGER)) as days_until_double
            FROM mahudhurio_penalties p JOIN wanakwaya w ON p.member_id = w.id
            WHERE (p.imelipwa = 0 OR p.imelipwa IS NULL) AND (p.remaining_amount > 0 OR p.remaining_amount IS NULL)
            GROUP BY p.member_id, p.tukio ORDER BY p.tarehe_penalty DESC
        """).fetchall()
        
        all_penalties = []
        for p in penalties:
            remaining = p['remaining_amount'] if p['remaining_amount'] and p['remaining_amount'] > 0 else p['penalty_amount']
            voice = p['sauti']
            prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
            count = conn.execute("SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ? AND status = 'active'", (voice, p['member_id'])).fetchone()
            member_number = f"{prefix}{str(count['c']).zfill(3)}"
            days_until = p['days_until_double'] if p['days_until_double'] and p['days_until_double'] >= 0 else 10
            
            all_penalties.append({
                'penalty_id': p['penalty_id'], 'member_id': p['member_id'], 'jina': p['jina'],
                'sauti': p['sauti'], 'member_number': member_number, 'penalty_amount': p['penalty_amount'],
                'penalty_type': p['penalty_type'], 'tukio': p['tukio'], 'tarehe_penalty': p['tarehe_penalty'],
                'days_until_double': days_until, 'remaining_amount': remaining
            })
        
        return jsonify({'success': True, 'penalties': all_penalties})

@app.route('/api/mahudhurio/pay_penalty', methods=['POST'])
def api_pay_penalty():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    data = request.json
    penalty_id = data.get('penalty_id')
    member_id = data.get('member_id')
    amount = float(data.get('amount', 0))
    note = data.get('note', 'Malipo ya penalty')
    
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Kiasi lazima kiwe kikubwa'})
    
    with get_db() as conn:
        penalty = conn.execute("SELECT id, penalty_amount, remaining_amount, imelipwa FROM mahudhurio_penalties WHERE id = ?", (penalty_id,)).fetchone()
        if not penalty:
            return jsonify({'success': False, 'message': 'Penalty haipatikani'})
        if penalty['imelipwa'] == 1:
            return jsonify({'success': False, 'message': 'Penalty tayari imelipwa'})
        
        remaining = penalty['remaining_amount'] or penalty['penalty_amount']
        if amount >= remaining:
            new_remaining, imelipwa, message = 0, 1, f'Penalty imelipwa kikamilifu! TSh {amount:,.0f}'
        else:
            new_remaining, imelipwa, message = remaining - amount, 0, f'Malipo ya TSh {amount:,.0f} yamepokelewa. Deni: TSh {new_remaining:,.0f}'
        
        conn.execute("UPDATE mahudhurio_penalties SET remaining_amount = ?, imelipwa = ? WHERE id = ?", (new_remaining, imelipwa, penalty_id))
        receipt_no = f'PNL-{datetime.now().strftime("%Y%m%d%H%M%S")}-{member_id}'
        conn.execute("INSERT INTO penalty_payments (penalty_id, member_id, amount, note, receipt_no, tarehe) VALUES (?, ?, ?, ?, ?, date('now'))", (penalty_id, member_id, amount, note, receipt_no))
        conn.execute("INSERT INTO mapato (chanzo, kiasi, maelezo, tarehe) VALUES (?, ?, ?, date('now'))", (f'Penalty - {receipt_no}', amount, f'Malipo ya penalty kutoka member #{member_id}'))
        conn.commit()
        
        return jsonify({'success': True, 'message': message, 'remaining': new_remaining, 'receipt_no': receipt_no})

@app.route('/api/mahudhurio/frequent_offenders')
def api_frequent_offenders():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    with get_db() as conn:
        offenders_by_voice = {}
        for voice in ['Soprano', 'Alto', 'Tenor', 'Bass']:
            offenders = conn.execute("""
                SELECT w.id, w.jina, w.sauti, COUNT(p.id) as offence_count, SUM(p.penalty_amount) as total_penalty, SUM(p.remaining_amount) as remaining_debt
                FROM wanakwaya w JOIN mahudhurio_penalties p ON w.id = p.member_id
                WHERE w.sauti = ? AND p.imelipwa = 0 GROUP BY w.id
                ORDER BY offence_count DESC, remaining_debt DESC LIMIT 5
            """, (voice,)).fetchall()
            if len(offenders) == 0:
                offenders = conn.execute("""
                    SELECT w.id, w.jina, w.sauti, COUNT(d.id) as offence_count, SUM(d.penalty) as total_penalty, SUM(d.penalty) as remaining_debt
                    FROM wanakwaya w JOIN mahudhurio_detailed d ON w.id = d.mwanakwaya_id
                    WHERE w.sauti = ? AND d.penalty > 0 AND d.penalty IS NOT NULL GROUP BY w.id
                    ORDER BY offence_count DESC, remaining_debt DESC LIMIT 5
                """, (voice,)).fetchall()
            offenders_by_voice[voice] = [dict(o) for o in offenders]
        
        return jsonify({'success': True, 'offenders': offenders_by_voice})

# ============ ADA CALENDAR ROUTES ============
@app.route('/ada/calendar')
def ada_calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    year = request.args.get('year', type=int)
    if not year:
        year = datetime.now().year
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        if not settings:
            settings = {'kiasi_kwa_mwezi': 5000, 'tarehe_penalty': 15, 'penalty_asilimia': 10}
        
        for month in range(1, 13):
            existing = conn.execute("SELECT * FROM ada_calendar WHERE mwaka = ? AND mwezi = ? LIMIT 1", (year, month)).fetchone()
            if not existing:
                wanakwaya = conn.execute("SELECT id FROM wanakwaya WHERE status = 'active'").fetchall()
                for w in wanakwaya:
                    conn.execute("INSERT INTO ada_calendar (mwanakwaya_id, mwaka, mwezi, kiasi_kinachotakiwa, imelipwa) VALUES (?, ?, ?, ?, 0)", (w['id'], year, month, settings['kiasi_kwa_mwezi']))
                conn.commit()
        
        members_by_voice = {}
        for voice in ['Soprano', 'Alto', 'Tenor', 'Bass']:
            members = conn.execute("SELECT w.id, w.jina, w.simu, w.sauti FROM wanakwaya w WHERE w.sauti = ? AND w.status = 'active' ORDER BY w.jina", (voice,)).fetchall()
            members_list = []
            for idx, m in enumerate(members, 1):
                prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
                member_number = f"{prefix}{str(idx).zfill(3)}"
                members_list.append({'id': m['id'], 'jina': m['jina'], 'simu': m['simu'], 'sauti': m['sauti'], 'member_number': member_number})
            members_by_voice[voice] = members_list
        
        payment_data = {}
        records = conn.execute("SELECT mwanakwaya_id, mwezi, kiasi_kilicholipwa, imelipwa, overpayment, receipt_no, tarehe_malipo FROM ada_calendar WHERE mwaka = ?", (year,)).fetchall()
        for rec in records:
            if rec['mwanakwaya_id'] not in payment_data:
                payment_data[rec['mwanakwaya_id']] = {}
            payment_data[rec['mwanakwaya_id']][rec['mwezi']] = {
                'kilicholipwa': rec['kiasi_kilicholipwa'], 'imelipwa': rec['imelipwa'],
                'overpayment': rec['overpayment'], 'receipt_no': rec['receipt_no'], 'tarehe_malipo': rec['tarehe_malipo']
            }
        
        months = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 'Julai', 'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba']
    
    return render_template('ada_calendar.html', members_by_voice=members_by_voice, payment_data=payment_data, months=months, current_year=year, settings=settings)

@app.route('/api/ada/get_month_data', methods=['POST'])
def api_get_month_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    mwaka = data.get('mwaka')
    mwezi = data.get('mwezi')
    
    with get_db() as conn:
        record = conn.execute("SELECT * FROM ada_calendar WHERE mwanakwaya_id = ? AND mwaka = ? AND mwezi = ?", (member_id, mwaka, mwezi)).fetchone()
        member = conn.execute("SELECT id, jina, sauti, simu FROM wanakwaya WHERE id = ?", (member_id,)).fetchone()
        
        voice = member['sauti']
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        count = conn.execute("SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ? AND status = 'active'", (voice, member_id)).fetchone()
        member_number = f"{prefix}{str(count['c']).zfill(3)}"
        
        if not record:
            settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
            kiasi = settings['kiasi_kwa_mwezi'] if settings else 5000
            return jsonify({'success': True, 'member': {'jina': member['jina'], 'sauti': member['sauti'], 'simu': member['simu'], 'member_number': member_number}, 'record': {'kiasi_kinachotakiwa': kiasi, 'kiasi_kilicholipwa': 0, 'imelipwa': 0, 'overpayment': 0}, 'previous_debt': 0})
        
        previous_debt = conn.execute("SELECT SUM(kiasi_kinachotakiwa - kiasi_kilicholipwa) as debt FROM ada_calendar WHERE mwanakwaya_id = ? AND mwaka = ? AND mwezi < ? AND (kiasi_kinachotakiwa - kiasi_kilicholipwa) > 0", (member_id, mwaka, mwezi)).fetchone()
        
        return jsonify({
            'success': True,
            'member': {'jina': member['jina'], 'sauti': member['sauti'], 'simu': member['simu'], 'member_number': member_number},
            'record': {'id': record['id'], 'kiasi_kinachotakiwa': record['kiasi_kinachotakiwa'], 'kiasi_kilicholipwa': record['kiasi_kilicholipwa'], 'imelipwa': record['imelipwa'], 'overpayment': record['overpayment'], 'receipt_no': record['receipt_no'], 'tarehe_malipo': record['tarehe_malipo']},
            'previous_debt': previous_debt['debt'] if previous_debt and previous_debt['debt'] else 0
        })

@app.route('/api/ada/pay_month', methods=['POST'])
def api_pay_month():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    member_id = data.get('member_id')
    mwaka = data.get('mwaka')
    mwezi = data.get('mwezi')
    kiasi = float(data.get('kiasi', 0))
    maelezo = data.get('maelezo', 'Malipo ya ada')
    
    if kiasi <= 0:
        return jsonify({'success': False, 'message': 'Kiasi lazima kiwe kikubwa kuliko sifuri'}), 400
    
    with get_db() as conn:
        member = conn.execute("SELECT jina FROM wanakwaya WHERE id = ?", (member_id,)).fetchone()
        member_name = member['jina'] if member else f"Member #{member_id}"
        
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        kiasi_kwa_mwezi = settings['kiasi_kwa_mwezi'] if settings else 5000
        
        current = conn.execute("""
            SELECT * FROM ada_calendar 
            WHERE mwanakwaya_id = ? AND mwaka = ? AND mwezi = ?
        """, (member_id, mwaka, mwezi)).fetchone()
        
        if not current:
            conn.execute("""
                INSERT INTO ada_calendar (mwanakwaya_id, mwaka, mwezi, kiasi_kinachotakiwa, kiasi_kilicholipwa, imelipwa, overpayment)
                VALUES (?, ?, ?, ?, 0, 0, 0)
            """, (member_id, mwaka, mwezi, kiasi_kwa_mwezi))
            current = conn.execute("""
                SELECT * FROM ada_calendar 
                WHERE mwanakwaya_id = ? AND mwaka = ? AND mwezi = ?
            """, (member_id, mwaka, mwezi)).fetchone()
        
        receipt_no = f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{member_id}"
        
        all_months = conn.execute("""
            SELECT id, mwezi, kiasi_kinachotakiwa, kiasi_kilicholipwa, overpayment, imelipwa
            FROM ada_calendar 
            WHERE mwanakwaya_id = ? AND mwaka = ? 
            ORDER BY mwezi ASC
        """, (member_id, mwaka)).fetchall()
        
        if len(all_months) == 0:
            for m in range(1, 13):
                conn.execute("""
                    INSERT INTO ada_calendar (mwanakwaya_id, mwaka, mwezi, kiasi_kinachotakiwa, kiasi_kilicholipwa, imelipwa, overpayment)
                    VALUES (?, ?, ?, ?, 0, 0, 0)
                """, (member_id, mwaka, m, kiasi_kwa_mwezi))
            all_months = conn.execute("""
                SELECT id, mwezi, kiasi_kinachotakiwa, kiasi_kilicholipwa, overpayment, imelipwa
                FROM ada_calendar 
                WHERE mwanakwaya_id = ? AND mwaka = ? 
                ORDER BY mwezi ASC
            """, (member_id, mwaka)).fetchall()
        
        month_debts = []
        for month_data in all_months:
            paid = month_data['kiasi_kilicholipwa']
            debt = month_data['kiasi_kinachotakiwa'] - paid
            if debt < 0:
                debt = 0
            month_debts.append({
                'id': month_data['id'],
                'mwezi': month_data['mwezi'],
                'kinachotakiwa': month_data['kiasi_kinachotakiwa'],
                'kilicholipwa': paid,
                'debt': debt,
                'overpayment': month_data['overpayment'] or 0
            })
        
        remaining_amount = kiasi
        payment_distribution = []
        
        for month in month_debts:
            if remaining_amount <= 0:
                break
            
            if month['debt'] > 0:
                if remaining_amount >= month['debt']:
                    paid_this_month = month['debt']
                    remaining_amount -= month['debt']
                    month['debt'] = 0
                    month['kilicholipwa'] = month['kinachotakiwa']
                    payment_distribution.append({
                        'mwezi': month['mwezi'],
                        'kilicholipwa': paid_this_month,
                        'status': 'full'
                    })
                else:
                    paid_this_month = remaining_amount
                    month['kilicholipwa'] += remaining_amount
                    month['debt'] -= remaining_amount
                    payment_distribution.append({
                        'mwezi': month['mwezi'],
                        'kilicholipwa': paid_this_month,
                        'status': 'partial'
                    })
                    remaining_amount = 0
        
        overpayment_amount = remaining_amount
        
        if overpayment_amount > 0:
            for month in month_debts:
                if overpayment_amount <= 0:
                    break
                if month['debt'] == 0 and month['mwezi'] >= mwezi:
                    month['kilicholipwa'] += overpayment_amount
                    month['overpayment'] = overpayment_amount
                    payment_distribution.append({
                        'mwezi': month['mwezi'],
                        'kilicholipwa': overpayment_amount,
                        'status': 'overpayment'
                    })
                    overpayment_amount = 0
                    break
        
        for month in month_debts:
            if month['debt'] <= 0 and month['kilicholipwa'] >= month['kinachotakiwa']:
                if month['kilicholipwa'] > month['kinachotakiwa']:
                    imelipwa = 3
                else:
                    imelipwa = 1
            elif month['kilicholipwa'] > 0 and month['kilicholipwa'] < month['kinachotakiwa']:
                imelipwa = 2
            else:
                imelipwa = 0
            
            overpayment = month['kilicholipwa'] - month['kinachotakiwa']
            if overpayment < 0:
                overpayment = 0
            
            conn.execute("""
                UPDATE ada_calendar 
                SET kiasi_kilicholipwa = ?, 
                    imelipwa = ?, 
                    overpayment = ?,
                    tarehe_malipo = CASE 
                        WHEN ? > 0 AND imelipwa = 0 THEN ?
                        ELSE tarehe_malipo 
                    END,
                    receipt_no = CASE 
                        WHEN ? > 0 AND (receipt_no IS NULL OR receipt_no = '') THEN ?
                        ELSE receipt_no 
                    END
                WHERE id = ?
            """, (
                month['kilicholipwa'],
                imelipwa,
                overpayment,
                month['kilicholipwa'], datetime.now().date().isoformat(),
                month['kilicholipwa'], receipt_no,
                month['id']
            ))
        
        conn.execute("""
            INSERT INTO mapato (chanzo, kiasi, maelezo, tarehe) 
            VALUES (?, ?, ?, ?)
        """, (
            f"Ada - Mwezi {mwezi}/{mwaka}", 
            kiasi, 
            f"Malipo kutoka {member_name} (#{member_id})", 
            datetime.now().date().isoformat()
        ))
        
        log_activity(session['user_id'], session['username'], 'PAY_ADA', 
                    f'Member: {member_name} (ID: {member_id}) paid TSh {kiasi:,.0f} for {mwaka}-{mwezi}')
        
        conn.commit()
        
        distribution_text = []
        for dist in payment_distribution:
            month_name = ['Januari', 'Februari', 'Machi', 'Aprili', 'Mei', 'Juni', 
                         'Julai', 'Agosti', 'Septemba', 'Oktoba', 'Novemba', 'Desemba'][dist['mwezi'] - 1]
            if dist['status'] == 'full':
                distribution_text.append(f"✓ {month_name}: Imelipwa kamili TSh {dist['kilicholipwa']:,.0f}")
            elif dist['status'] == 'partial':
                distribution_text.append(f"🟡 {month_name}: Imelipwa sehemu TSh {dist['kilicholipwa']:,.0f}")
            elif dist['status'] == 'overpayment':
                distribution_text.append(f"🔵 {month_name}: Ziada TSh {dist['kilicholipwa']:,.0f} (Advance)")
        
        message = f"Malipo ya TSh {kiasi:,.0f} yamekamilika!\n\n"
        message += "\n".join(distribution_text)
        
        return jsonify({
            'success': True,
            'message': message,
            'payment_id': current['id'],
            'receipt_no': receipt_no,
            'distribution': payment_distribution,
            'overpayment': overpayment_amount
        })

@app.route('/api/ada/get_voice_stats', methods=['POST'])
def api_get_voice_stats():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    voice = data.get('voice')
    mwaka = data.get('mwaka')
    mwezi = data.get('mwezi')
    
    with get_db() as conn:
        members = conn.execute("SELECT id FROM wanakwaya WHERE sauti = ? AND status = 'active'", (voice,)).fetchall()
        total_members = len(members)
        if total_members == 0:
            return jsonify({'success': True, 'percentage': 0, 'total_members': 0})
        
        paid_count = partial_count = unpaid_count = 0
        total_amount = paid_amount = 0
        
        for member in members:
            record = conn.execute("SELECT kiasi_kinachotakiwa, kiasi_kilicholipwa, imelipwa FROM ada_calendar WHERE mwanakwaya_id = ? AND mwaka = ? AND mwezi = ?", (member['id'], mwaka, mwezi)).fetchone()
            if record:
                total_amount += record['kiasi_kinachotakiwa']
                paid_amount += record['kiasi_kilicholipwa']
                if record['imelipwa'] == 1:
                    paid_count += 1
                elif record['imelipwa'] == 2:
                    partial_count += 1
                else:
                    unpaid_count += 1
            else:
                unpaid_count += 1
                settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
                default_amount = settings['kiasi_kwa_mwezi'] if settings else 5000
                total_amount += default_amount
        
        percentage = (paid_amount / total_amount * 100) if total_amount > 0 else 0
        
        return jsonify({'success': True, 'percentage': percentage, 'total_members': total_members, 'paid_count': paid_count, 'partial_count': partial_count, 'unpaid_count': unpaid_count, 'total_amount': total_amount, 'paid_amount': paid_amount})

@app.route('/api/ada/get_settings', methods=['GET'])
def api_get_settings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        settings = conn.execute("SELECT * FROM ada_settings ORDER BY id DESC LIMIT 1").fetchone()
        if not settings:
            settings = {'kiasi_kwa_mwezi': 5000, 'tarehe_penalty': 15, 'penalty_asilimia': 10}
        return jsonify({'kiasi_kwa_mwezi': settings['kiasi_kwa_mwezi'], 'tarehe_penalty': settings['tarehe_penalty'], 'penalty_asilimia': settings['penalty_asilimia']})

@app.route('/api/ada/update_settings', methods=['POST'])
def api_update_settings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    kiasi_kwa_mwezi = data.get('kiasi_kwa_mwezi')
    tarehe_penalty = data.get('tarehe_penalty')
    penalty_asilimia = data.get('penalty_asilimia')
    
    with get_db() as conn:
        now = datetime.now()
        conn.execute("INSERT INTO ada_settings (kiasi_kwa_mwezi, tarehe_penalty, penalty_asilimia, mwaka, mwezi, imeanzishwa) VALUES (?, ?, ?, ?, ?, ?)", (kiasi_kwa_mwezi, tarehe_penalty, penalty_asilimia, now.year, now.month, now.date()))
        conn.commit()
        return jsonify({'success': True, 'message': 'Mipangilio imehifadhiwa'})

@app.route('/api/wanakwaya/details/<int:id>')
def api_wanakwaya_details(id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    with get_db() as conn:
        member = conn.execute("""
            SELECT w.*, COALESCE(SUM(a.kiasi_kinachotakiwa), 0) as total_fees, COALESCE(SUM(m.kiasi), 0) as paid_fees
            FROM wanakwaya w
            LEFT JOIN ada_monthly a ON a.mwanakwaya_id = w.id AND a.mwaka = strftime('%Y', 'now')
            LEFT JOIN ada_malipo m ON m.mwanakwaya_id = w.id
            WHERE w.id = ? GROUP BY w.id
        """, (id,)).fetchone()
        
        if member:
            return jsonify(dict(member))
        return jsonify({'error': 'Member not found'}), 404

# ============ RIPOTI NA ANALYTICS ============
@app.route('/ripoti')
def ripoti_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('ripoti.html')

@app.route('/api/ripoti/data')
def api_ripoti_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    start_date = request.args.get('start', '2026-01-01')
    end_date = request.args.get('end', '2026-12-31')
    voice = request.args.get('voice', 'all')
    
    with get_db() as conn:
        voice_filter = ""
        if voice != 'all':
            voice_filter = f"AND w.sauti = '{voice}'"
        
        attendance_data = conn.execute(f"""
            SELECT strftime('%Y-%m', d.tarehe) as month,
                   COUNT(*) as total_attendance,
                   SUM(CASE WHEN d.status = 'present' THEN 1 ELSE 0 END) as present_count,
                   ROUND(CAST(SUM(CASE WHEN d.status = 'present' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as percentage
            FROM mahudhurio_detailed d
            JOIN wanakwaya w ON d.mwanakwaya_id = w.id
            WHERE d.tarehe BETWEEN ? AND ? AND w.status = 'active' {voice_filter}
            GROUP BY strftime('%Y-%m', d.tarehe)
            ORDER BY month
        """, (start_date, end_date)).fetchall()
        
        income_data = conn.execute("""
            SELECT strftime('%Y-%m', date) as month, SUM(amount) as total_income
            FROM mapato_records r
            JOIN mapato_sources s ON r.source_id = s.id
            WHERE date BETWEEN ? AND ?
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month
        """, (start_date, end_date)).fetchall()
        
        source_income = conn.execute("""
            SELECT s.name, SUM(r.amount) as total
            FROM mapato_records r
            JOIN mapato_sources s ON r.source_id = s.id
            WHERE date BETWEEN ? AND ?
            GROUP BY s.name
            ORDER BY total DESC
        """, (start_date, end_date)).fetchall()
        
        active_members = conn.execute("SELECT COUNT(*) as count FROM wanakwaya WHERE status = 'active'").fetchone()
        
        months = sorted(list(set([a['month'] for a in attendance_data] + [i['month'] for i in income_data])))
        attendance_dict = {a['month']: {'total': a['total_attendance'], 'percentage': a['percentage']} for a in attendance_data}
        income_dict = {i['month']: i['total_income'] for i in income_data}
        
        attendance_vals = []
        income_vals = []
        monthly_data = []
        
        for month in months:
            att = attendance_dict.get(month, {'total': 0, 'percentage': 0})
            inc = income_dict.get(month, 0)
            attendance_vals.append(att['total'])
            income_vals.append(inc)
            monthly_data.append({
                'month': month,
                'attendance': att['total'],
                'percentage': att['percentage'],
                'income': inc,
                'penalty': 0
            })
        
        total_attendance = sum(attendance_vals)
        total_income = sum(income_vals)
        
        return jsonify({
            'success': True,
            'months': months,
            'attendance_data': attendance_vals,
            'income_data': income_vals,
            'income_labels': [s['name'] for s in source_income],
            'income_by_source': [s['total'] for s in source_income],
            'monthly_data': monthly_data,
            'stats': {
                'total_attendance': total_attendance,
                'total_income': total_income,
                'total_penalty': 0,
                'active_members': active_members['count']
            }
        })

@app.template_filter('format_number')
def format_number(value):
    try:
        return f"{int(value):,}"
    except:
        return str(value)


# ============ USER MANAGEMENT APIs ============
@app.route('/users')
def users_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('users.html')

@app.route('/api/users')
def api_get_users():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        users = conn.execute('''
            SELECT w.id, w.username, COALESCE(w.full_name, w.username) as full_name, 
                   w.role_id, COALESCE(r.name, 'User') as role_name, w.last_login
            FROM watumiaji w 
            LEFT JOIN user_roles r ON w.role_id = r.id 
            ORDER BY w.id
        ''').fetchall()
        
        result = []
        for u in users:
            result.append({
                'id': u['id'],
                'username': u['username'],
                'full_name': u['full_name'],
                'role_id': u['role_id'],
                'role_name': u['role_name'],
                'last_login': u['last_login']
            })
        
        return jsonify({'success': True, 'users': result})

@app.route('/api/users/<int:id>')
def api_get_user(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        user = conn.execute('SELECT id, username, full_name, role_id FROM watumiaji WHERE id = ?', (id,)).fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        return jsonify({'success': True, 'user': dict(user)})

@app.route('/api/users', methods=['POST'])
def api_create_user():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name', '')
    role_id = data.get('role_id', 5)

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username na password zinahitajika'}), 400

    with get_db() as conn:
        existing = conn.execute('SELECT id FROM watumiaji WHERE username = ?', (username,)).fetchone()
        if existing:
            return jsonify({'success': False, 'message': 'Username tayari ipo'}), 400

        hashed = generate_password_hash(password)
        cursor = conn.execute('INSERT INTO watumiaji (username, password, full_name, role_id) VALUES (?, ?, ?, ?)',
                    (username, hashed, full_name, role_id))
        user_id = cursor.lastrowid
        conn.commit()

        log_activity(session['user_id'], session['username'], 'CREATE_USER', f'Created user: {username} (ID: {user_id}) with role_id: {role_id}')

        return jsonify({'success': True, 'message': f'Mtumiaji {username} ameongezwa!', 'user_id': user_id})

@app.route('/api/users/<int:id>', methods=['PUT'])
def api_update_user(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.json
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name', '')
    role_id = data.get('role_id', 4)

    with get_db() as conn:
        if password:
            conn.execute('UPDATE watumiaji SET username = ?, password = ?, full_name = ?, role_id = ? WHERE id = ?',
                        (username, generate_password_hash(password), full_name, role_id, id))
        else:
            conn.execute('UPDATE watumiaji SET username = ?, full_name = ?, role_id = ? WHERE id = ?',
                        (username, full_name, role_id, id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Mtumiaji amehaririwa'})

@app.route('/api/admin/clear_data', methods=['POST'])
def api_clear_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        current_user = conn.execute('SELECT role_id, username FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        if not current_user or current_user['role_id'] != 1:
            return jsonify({'success': False, 'message': 'Admin rights required'}), 403
    
    data = request.json
    clear_type = data.get('type')
    
    with get_db() as conn:
        try:
            if clear_type == 'ada':
                conn.execute("DELETE FROM ada_malipo")
                conn.execute("DELETE FROM ada_monthly")
                conn.execute("DELETE FROM ada_settings")
                message = "Rekodi zote za ADA zimefutwa!"
        log_activity(session['user_id'], session['username'], 'CLEAR_DATA', 'Cleared ADA data')
                
            elif clear_type == 'penalty':
                conn.execute("DELETE FROM mahudhurio_penalties")
                conn.execute("DELETE FROM penalty_payments")
                message = "Rekodi zote za PENALTY zimefutwa!"
        log_activity(session['user_id'], session['username'], 'CLEAR_DATA', 'Cleared PENALTY data')
                
            elif clear_type == 'mahudhurio':
                conn.execute("DELETE FROM mahudhurio_detailed")
                message = "Rekodi zote za MAHUDHURIO zimefutwa!"
        log_activity(session['user_id'], session['username'], 'CLEAR_DATA', 'Cleared MAHUDHURIO data')
                
            elif clear_type == 'mapato':
                conn.execute("DELETE FROM mapato")
                conn.execute("DELETE FROM mapato_target")
                message = "Rekodi zote za MAPATO zimefutwa!"
        log_activity(session['user_id'], session['username'], 'CLEAR_DATA', 'Cleared MAPATO data')
                
            elif clear_type == 'all':
                conn.execute("DELETE FROM ada_malipo")
                conn.execute("DELETE FROM ada_monthly")
                conn.execute("DELETE FROM mahudhurio_penalties")
                conn.execute("DELETE FROM penalty_payments")
                conn.execute("DELETE FROM mahudhurio_detailed")
                conn.execute("DELETE FROM mapato")
                conn.execute("DELETE FROM mapato_target")
                message = "DATA ZOTE (Ada, Penalty, Mahudhurio, Mapato) zimefutwa!"
        log_activity(session['user_id'], session['username'], 'CLEAR_DATA', 'Cleared ALL data')
                
            else:
                return jsonify({'success': False, 'message': 'Invalid clear type'}), 400
            
            conn.commit()
            return jsonify({'success': True, 'message': message})
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

# ============ INCOME TARGETS APIs ============
@app.route('/api/mapato/targets/get', methods=['GET'])
def api_get_income_targets():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    mwaka = request.args.get('mwaka', datetime.now().year)
    
    with get_db() as conn:
        global_target = conn.execute('''
            SELECT amount FROM income_targets 
            WHERE target_type = 'global' AND mwaka = ?
        ''', (mwaka,)).fetchone()
        
        source_targets = conn.execute('''
            SELECT source_id, amount FROM income_targets 
            WHERE target_type = 'source' AND mwaka = ?
        ''', (mwaka,)).fetchall()
        
        sources = conn.execute('''
            SELECT id, name, color, icon FROM mapato_sources 
            WHERE is_active = 1
        ''').fetchall()
        
        if not sources:
            sources = []
        
        return jsonify({
            'success': True,
            'global_target': global_target['amount'] if global_target else 10000000,
            'source_targets': [dict(st) for st in source_targets],
            'sources': [dict(s) for s in sources],
            'mwaka': int(mwaka)
        })

@app.route('/api/mapato/targets/save', methods=['POST'])
def api_save_income_targets():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    mwaka = data.get('mwaka', datetime.now().year)
    global_target = data.get('global_target', 0)
    source_targets = data.get('source_targets', [])
    
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO income_targets (target_type, source_id, mwaka, amount, updated_at)
            VALUES ('global', NULL, ?, ?, CURRENT_TIMESTAMP)
        ''', (mwaka, global_target))
        
        for st in source_targets:
            conn.execute('''
                INSERT OR REPLACE INTO income_targets (target_type, source_id, mwaka, amount, updated_at)
                VALUES ('source', ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (st.get('source_id'), mwaka, st.get('amount', 0)))
        
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Malengo yamehifadhiwa kwenye database'})

@app.route('/api/mapato/sources/list', methods=['GET'])
def api_get_income_sources():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        sources = conn.execute('''
            SELECT id, name, color, icon, target, description, is_active
            FROM mapato_sources
            ORDER BY name
        ''').fetchall()
        
        return jsonify({
            'success': True,
            'sources': [dict(s) for s in sources]
        })

@app.route('/api/mapato/sources/add', methods=['POST'])
def api_add_income_source():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    name = data.get('name')
    color = data.get('color', '#1a2a6e')
    icon = data.get('icon', '💰')
    target = data.get('target', 0)
    description = data.get('description', '')
    
    if not name:
        return jsonify({'success': False, 'message': 'Jina la chanzo linahitajika'})
    
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO mapato_sources (name, color, icon, target, description, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (name, color, icon, target, description))
        
        source_id = cursor.lastrowid
        
        mwaka = datetime.now().year
        conn.execute('''
            INSERT INTO income_targets (target_type, source_id, mwaka, amount)
            VALUES ('source', ?, ?, ?)
        ''', (source_id, mwaka, target))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Chanzo kimeongezwa',
            'source_id': source_id
        })

@app.route('/api/mapato/data', methods=['GET'])
def api_get_mapato_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    mwaka = request.args.get('mwaka', datetime.now().year)
    
    with get_db() as conn:
        records = conn.execute('''
            SELECT i.*, s.name as source_name, s.color as source_color, s.icon as source_icon
            FROM mapato_income i
            JOIN mapato_sources s ON i.source_id = s.id
            WHERE strftime('%Y', i.date) = ?
            ORDER BY i.date DESC
        ''', (mwaka,)).fetchall()
        
        sources = conn.execute('''
            SELECT * FROM mapato_sources WHERE is_active = 1
        ''').fetchall()
        
        total = sum(r['amount'] for r in records)
        
        by_source = {}
        for r in records:
            if r['source_name'] not in by_source:
                by_source[r['source_name']] = 0
            by_source[r['source_name']] += r['amount']
        
        monthly_trend = []
        for month in range(1, 13):
            month_total = sum(r['amount'] for r in records if int(r['date'].split('-')[1]) == month)
            monthly_trend.append({'mwezi': month, 'kiasi': month_total})
        
        global_target = conn.execute('''
            SELECT amount FROM income_targets 
            WHERE target_type = 'global' AND mwaka = ?
        ''', (mwaka,)).fetchone()
        
        return jsonify({
            'success': True,
            'total': total,
            'monthly': sum(r['amount'] for r in records if datetime.now().strftime('%Y-%m') in r['date']),
            'weekly': sum(r['amount'] for r in records if is_within_week(r['date'])),
            'by_source': by_source,
            'monthly_trend': monthly_trend,
            'sources': [dict(s) for s in sources],
            'records': [dict(r) for r in records],
            'global_target': global_target['amount'] if global_target else 10000000
        })

def is_within_week(date_str):
    from datetime import datetime, timedelta
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    return date_obj >= week_ago

# ============ INVENTORY (MAUZO NA BIDHAA) APIs ============
@app.route('/inventory')
def inventory_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('inventory.html')

@app.route('/api/products')
def api_get_products():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        products = conn.execute('SELECT * FROM products ORDER BY id').fetchall()
        return jsonify({'success': True, 'products': [dict(p) for p in products]})

@app.route('/api/products', methods=['POST'])
def api_add_product():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    with get_db() as conn:
        conn.execute('''INSERT INTO products (name, category, description, buying_price, selling_price, quantity)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (data['name'], data['category'], data.get('description', ''), 
                     data['buying_price'], data['selling_price'], data['quantity']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Bidhaa imeongezwa'})

@app.route('/api/sales')
def api_get_sales():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        sales = conn.execute('''
            SELECT s.*, p.name as product_name 
            FROM sales s 
            JOIN products p ON s.product_id = p.id 
            ORDER BY s.sale_date DESC
        ''').fetchall()
        return jsonify({'success': True, 'sales': [dict(s) for s in sales]})

@app.route('/api/sales', methods=['POST'])
def api_add_sale():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    product_id = data['product_id']
    quantity = data['quantity']
    selling_price = data['selling_price']
    total_amount = quantity * selling_price
    customer_name = data.get('customer_name', '')
    customer_phone = data.get('customer_phone', '')
    notes = data.get('notes', '')
    
    with get_db() as conn:
        product = conn.execute('SELECT buying_price, quantity, name FROM products WHERE id = ?', (product_id,)).fetchone()
        if not product:
            return jsonify({'success': False, 'message': 'Bidhaa haipo'}), 404
        
        if product['quantity'] < quantity:
            return jsonify({'success': False, 'message': f'Idadi haitoshi. Zilizobaki: {product["quantity"]}'}), 400
        
        profit = (selling_price - product['buying_price']) * quantity
        
        receipt_no = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{product_id}"
        
        cursor = conn.execute('''
            INSERT INTO sales (product_id, quantity, selling_price, total_amount, profit, 
                              customer_name, customer_phone, receipt_no, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (product_id, quantity, selling_price, total_amount, profit, 
              customer_name, customer_phone, receipt_no, notes))
        
        sale_id = cursor.lastrowid
        
        new_quantity = product['quantity'] - quantity
        conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, product_id))
        
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Mauzo yamekamilika', 
            'sale_id': sale_id,
            'receipt_no': receipt_no
        })

@app.route('/api/products/<int:id>', methods=['DELETE'])
def api_delete_product(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        sales_count = conn.execute('SELECT COUNT(*) as count FROM sales WHERE product_id = ?', (id,)).fetchone()
        if sales_count['count'] > 0:
            return jsonify({'success': False, 'message': f'Bidhaa imeuzwa {sales_count["count"]} mara, haiwezi kufutwa'}), 400
        
        conn.execute('DELETE FROM products WHERE id = ?', (id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Bidhaa imefutwa'})

@app.route('/api/products/<int:id>', methods=['PUT'])
def api_update_product(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    with get_db() as conn:
        conn.execute('''UPDATE products 
                        SET name = ?, category = ?, description = ?, 
                            buying_price = ?, selling_price = ?, quantity = ?
                        WHERE id = ?''',
                    (data['name'], data['category'], data.get('description', ''), 
                     data['buying_price'], data['selling_price'], data['quantity'], id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Bidhaa imesasishwa'})

# ============ MENU PERMISSIONS APIs ============
@app.route('/api/user/<int:user_id>/menus')
def api_get_user_menus(user_id):
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        menus = conn.execute('SELECT menu_name, can_view FROM user_menu_permissions WHERE user_id = ?', (user_id,)).fetchall()
        return jsonify({'success': True, 'menus': [dict(m) for m in menus]})

@app.route('/api/user/<int:user_id>/menus', methods=['POST'])
def api_update_user_menus(user_id):
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    menus = data.get('menus', [])
    
    with get_db() as conn:
        conn.execute('DELETE FROM user_menu_permissions WHERE user_id = ?', (user_id,))
        
        for menu in menus:
            conn.execute('INSERT INTO user_menu_permissions (user_id, menu_name, can_view) VALUES (?, ?, 1)', (user_id, menu))
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Menu permissions updated!'})

@app.route('/api/menus/list')
def api_get_menus_list():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    menus = [
        {'name': 'dashboard', 'label': '🏠 Dashboard', 'default': True},
        {'name': 'wanakwaya', 'label': '👥 Wanakwaya', 'default': True},
        {'name': 'mahudhurio', 'label': '📋 Mahudhurio', 'default': False},
        {'name': 'ada_calendar', 'label': '💰 Ada', 'default': False},
        {'name': 'mapato', 'label': '📈 Mapato', 'default': False},
        {'name': 'uongozi', 'label': '👑 Uongozi', 'default': False},
        {'name': 'kamati_kuu', 'label': '🤝 Kamati Kuu', 'default': False},
        {'name': 'assets', 'label': '📦 Assets', 'default': False},
        {'name': 'inventory_page', 'label': '📦 Inventory', 'default': False},
        {'name': 'users_page', 'label': '👥 Users', 'default': False}
    ]
    return jsonify({'success': True, 'menus': menus})

@app.route('/change-password-first', methods=['GET', 'POST'])
def change_password_first():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('Password hazifanani!', 'error')
            return redirect(url_for('change_password_first'))
        
        if len(new_password) < 4:
            flash('Password lazima iwe na herufi 4 au zaidi!', 'error')
            return redirect(url_for('change_password_first'))
        
        with get_db() as conn:
            hashed = generate_password_hash(new_password)
            conn.execute("UPDATE watumiaji SET password = ?, is_first_login = 0 WHERE id = ?", 
                        (hashed, session['user_id']))
            conn.commit()
        
        session.clear()
        flash('✅ Password yako imebadilishwa! Tafadhali ingia tena.', 'success')
        return redirect(url_for('login'))
    
    return render_template('change_password_first.html')

@app.route('/api/login-history')
def api_login_history():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        history = conn.execute('SELECT * FROM login_history ORDER BY login_time DESC LIMIT 100').fetchall()
        return jsonify({'success': True, 'history': [dict(h) for h in history]})

@app.route('/login-history')
def login_history_page():
    if 'user_id' not in session or session.get('role_id') != 1:
        flash('Sehemu hii ni kwa Admin pekee!', 'error')
        return redirect(url_for('dashboard'))
    return render_template('login_history.html')

# ============ RESET PASSWORD API ============
@app.route('/api/users/<int:id>/reset_password', methods=['POST'])
def api_reset_user_password(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        current_user = conn.execute('SELECT role_id FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        if not current_user or current_user['role_id'] != 1:
            return jsonify({'success': False, 'message': 'Only admin can reset passwords!'}), 403
    
    data = request.json
    new_password = data.get('password')
    
    if not new_password or len(new_password) < 4:
        return jsonify({'success': False, 'message': 'Password lazima iwe na herufi 4 au zaidi'}), 400
    
    with get_db() as conn:
        user = conn.execute('SELECT username FROM watumiaji WHERE id = ?', (id,)).fetchone()
        
        if user:
        log_activity(session['user_id'], session['username'], 'RESET_PASSWORD', f'Reset password for user: {user["username"]} (ID: {id})')
        
        hashed = generate_password_hash(new_password)
        conn.execute('UPDATE watumiaji SET password = ?, is_first_login = 1 WHERE id = ?', (hashed, id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Password imebadilishwa kikamilifu!'})

# ============ ACTIVITY LOG API ============
@app.route('/api/activity-log')
def api_activity_log():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    filter_user = request.args.get('user')
    filter_action = request.args.get('action')
    
    with get_db() as conn:
        query = "SELECT * FROM activity_log WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date(activity_time) >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date(activity_time) <= ?"
            params.append(end_date)
        if filter_user:
            query += " AND username LIKE ?"
            params.append(f'%{filter_user}%')
        if filter_action:
            query += " AND action = ?"
            params.append(filter_action)
        
        query += " ORDER BY activity_time DESC LIMIT 500"
        
        logs = conn.execute(query, params).fetchall()
        
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN date(activity_time) = date('now') THEN 1 ELSE 0 END) as today,
                SUM(CASE WHEN date(activity_time) >= date('now', '-7 days') THEN 1 ELSE 0 END) as week,
                SUM(CASE WHEN date(activity_time) >= date('now', 'start of month') THEN 1 ELSE 0 END) as month
            FROM activity_log
        ''').fetchone()
        
        return jsonify({
            'success': True, 
            'logs': [dict(l) for l in logs],
            'stats': dict(stats)
        })

@app.route('/activity-log')
def activity_log_page():
    if 'user_id' not in session or session.get('role_id') != 1:
        flash('Sehemu hii ni kwa Admin pekee!', 'error')
        return redirect(url_for('dashboard'))
    return render_template('activity_log.html')

# ============ EXPORT REPORTS (IMPROVED) ============
import io
import csv
from datetime import datetime, timedelta

@app.route('/reports-export')
def reports_export_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('reports_export.html')

@app.route('/api/export/<report_type>')
def export_report(report_type):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    format_type = request.args.get('format', 'pdf')
    start_date = request.args.get('start', (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    with get_db() as conn:
        if report_type == 'ada':
            data = conn.execute('''
                SELECT 
                    w.id, w.jina, w.sauti, w.simu, w.status,
                    COALESCE(a.mwezi, '') as mwezi, 
                    COALESCE(a.mwaka, '') as mwaka,
                    COALESCE(a.kiasi_kinachotakiwa, 0) as kinachotakiwa,
                    COALESCE(a.kiasi_kilicholipwa, 0) as kilicholipwa,
                    COALESCE(a.jumla_ya_deni, 0) as deni,
                    COALESCE(a.penalty, 0) as penalty,
                    CASE 
                        WHEN a.imelipwa = 1 THEN 'IMELIPWA'
                        WHEN a.imelipwa = 2 THEN 'SEHEMU'
                        ELSE 'HAJALIPA'
                    END as status_ada
                FROM wanakwaya w
                LEFT JOIN ada_monthly a ON w.id = a.mwanakwaya_id
                WHERE w.status = 'active'
                ORDER BY w.sauti, w.jina
            ''').fetchall()
            
            total_expected = sum(d['kinachotakiwa'] for d in data)
            total_paid = sum(d['kilicholipwa'] for d in data)
            total_debt = sum(d['deni'] for d in data)
            total_penalty = sum(d['penalty'] for d in data)
            summary = {'total_expected': total_expected, 'total_paid': total_paid, 'total_debt': total_debt, 'total_penalty': total_penalty}
            filename = f"Ada_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        elif report_type == 'mapato':
            data = conn.execute('''
                SELECT 
                    s.name as chanzo, s.color, s.icon,
                    COALESCE(SUM(r.amount), 0) as total_income,
                    COUNT(r.id) as transaction_count,
                    s.target as target
                FROM mapato_sources s
                LEFT JOIN mapato_records r ON s.id = r.source_id AND r.date BETWEEN ? AND ?
                GROUP BY s.id
                ORDER BY total_income DESC
            ''', (start_date, end_date)).fetchall()
            
            records = conn.execute('''
                SELECT r.*, s.name as source_name, s.icon, s.color
                FROM mapato_records r
                JOIN mapato_sources s ON r.source_id = s.id
                WHERE r.date BETWEEN ? AND ?
                ORDER BY r.date DESC
                LIMIT 200
            ''', (start_date, end_date)).fetchall()
            
            total_income = sum(d['total_income'] for d in data)
            filename = f"Mapato_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            summary = {'total_income': total_income, 'record_count': len(records), 'period_start': start_date, 'period_end': end_date}
            
        elif report_type == 'mahudhurio':
            data = conn.execute('''
                SELECT 
                    d.id, d.tukio, d.tarehe, d.mwanakwaya_jina as jina, d.sauti, 
                    d.status, d.dakika_chelewa, d.penalty,
                    CASE 
                        WHEN d.status = 'present' THEN '✅ Amehudhuria'
                        WHEN d.status = 'absent' THEN '❌ Mtoro'
                        WHEN d.status = 'late' THEN '⚠️ Amechelewa'
                        ELSE '📝 Ruhusa'
                    END as status_display
                FROM mahudhurio_detailed d
                WHERE d.tarehe BETWEEN ? AND ?
                ORDER BY d.tarehe DESC, d.tukio
                LIMIT 500
            ''', (start_date, end_date)).fetchall()
            
            total_records = len(data)
            present = sum(1 for d in data if d['status'] == 'present')
            absent = sum(1 for d in data if d['status'] == 'absent')
            late = sum(1 for d in data if d['status'] == 'late')
            attendance_rate = (present / total_records * 100) if total_records > 0 else 0
            total_penalty = sum(d['penalty'] for d in data if d['penalty'])
            
            filename = f"Mahudhurio_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            summary = {'total_records': total_records, 'present': present, 'absent': absent, 'late': late, 'attendance_rate': attendance_rate, 'total_penalty': total_penalty}
        else:
            return jsonify({'error': 'Invalid report type'}), 400
    
    if format_type == 'excel':
        output = io.StringIO()
        writer = csv.writer(output)
        
        if report_type == 'ada':
            writer.writerow(['Jina', 'Sauti', 'Simu', 'Mwezi', 'Mwaka', 'Kinachotakiwa (TSh)', 'Kilicholipwa (TSh)', 'Deni (TSh)', 'Penalty (TSh)', 'Status'])
            for row in data:
                writer.writerow([row['jina'], row['sauti'], row['simu'], row['mwezi'], row['mwaka'], f"{row['kinachotakiwa']:,.0f}", f"{row['kilicholipwa']:,.0f}", f"{row['deni']:,.0f}", f"{row['penalty']:,.0f}", row['status_ada']])
            
            writer.writerow([])
            writer.writerow(['MUHTASARI', '', '', '', '', '', '', '', '', ''])
            writer.writerow(['Jumla Inayotakiwa', f"TSh {summary['total_expected']:,.0f}"])
            writer.writerow(['Jumla Iliyolipwa', f"TSh {summary['total_paid']:,.0f}"])
            writer.writerow(['Jumla ya Deni', f"TSh {summary['total_debt']:,.0f}"])
            writer.writerow(['Jumla ya Penalty', f"TSh {summary['total_penalty']:,.0f}"])
            
        elif report_type == 'mapato':
            writer.writerow(['Chanzo', 'Kiasi (TSh)', 'Idadi ya Malipo', 'Lengo (TSh)', 'Ufanisi (%)'])
            for row in data:
                progress = (row['total_income'] / row['target'] * 100) if row['target'] > 0 else 0
                writer.writerow([row['chanzo'], f"{row['total_income']:,.0f}", row['transaction_count'], f"{row['target']:,.0f}", f"{progress:.1f}%"])
            
            writer.writerow([])
            writer.writerow(['MUHTASARI'])
            writer.writerow(['Jumla ya Mapato', f"TSh {summary['total_income']:,.0f}"])
            writer.writerow(['Kipindi', f"{summary['period_start']} hadi {summary['period_end']}"])
            
            writer.writerow([])
            writer.writerow(['MAELEZO YA MAPATO (Hivi Karibuni)'])
            writer.writerow(['Tarehe', 'Chanzo', 'Kiasi (TSh)', 'Maelezo'])
            for rec in records[:50]:
                writer.writerow([rec['date'], rec['source_name'], f"{rec['amount']:,.0f}", rec['note'] or ''])
        
        else:
            writer.writerow(['Tukio', 'Tarehe', 'Jina', 'Sauti', 'Status', 'Dakika Chelewa', 'Penalty (TSh)'])
            for row in data:
                writer.writerow([row['tukio'], row['tarehe'], row['jina'], row['sauti'], row['status_display'], row['dakika_chelewa'] or 0, f"{row['penalty'] or 0:,.0f}"])
            
            writer.writerow([])
            writer.writerow(['MUHTASARI WA MAHUDHURIO'])
            writer.writerow(['Jumla ya Rekodi', summary['total_records']])
            writer.writerow(['Waliohudhuria', f"{summary['present']} ({summary['attendance_rate']:.1f}%)"])
            writer.writerow(['Watoro', summary['absent']])
            writer.writerow(['Waliochelewa', summary['late']])
            writer.writerow(['Jumla ya Penalty', f"TSh {summary['total_penalty']:,.0f}"])
        
        response = app.response_class(response=output.getvalue(), mimetype='text/csv')
        response.headers.set('Content-Disposition', 'attachment', filename=f'{filename}.csv')
        return response
    
    else:
        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{filename}</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; background: #f5f7fa; }}
                .report-container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #FFD700; }}
                .header h1 {{ color: #1a2a6e; margin: 0; font-size: 28px; }}
                .header p {{ color: #666; margin: 5px 0 0; }}
                .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
                .summary-card {{ background: linear-gradient(135deg, #1a2a6e, #2a3a7e); border-radius: 16px; padding: 20px; text-align: center; color: white; }}
                .summary-number {{ font-size: 28px; font-weight: bold; color: #FFD700; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #1a2a6e; color: #FFD700; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888; }}
                @media print {{
                    body {{ padding: 0; background: white; }}
                    .no-print {{ display: none; }}
                }}
            </style>
        </head>
        <body>
            <div class="report-container">
                <div class="header">
                    <h1>🎵 KWAYA MT. BONIFASI</h1>
                    <p>{report_type.upper()} REPORT</p>
                    <p>Tarehe: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Kipindi: {start_date} hadi {end_date}</p>
                </div>
                
                <div class="summary-cards">
        '''
        
        if report_type == 'ada':
            html += f'''
                <div class="summary-card"><div class="summary-number">TSh {summary['total_expected']:,.0f}</div><div>Jumla Inayotakiwa</div></div>
                <div class="summary-card"><div class="summary-number">TSh {summary['total_paid']:,.0f}</div><div>Jumla Iliyolipwa</div></div>
                <div class="summary-card"><div class="summary-number">TSh {summary['total_debt']:,.0f}</div><div>Jumla ya Deni</div></div>
                <div class="summary-card"><div class="summary-number">TSh {summary['total_penalty']:,.0f}</div><div>Jumla ya Penalty</div></div>
            </div>
            <h3>📋 ORODHA YA ADA</h3>
            <table><thead><tr><th>Jina</th><th>Sauti</th><th>Mwezi</th><th>Kinachotakiwa</th><th>Kilicholipwa</th><th>Deni</th><th>Status</th></tr></thead>
            <tbody>'''
            for row in data[:100]:
                html += f'<tr><td>{row["jina"]}</td><td>{row["sauti"]}</td><td>{row["mwezi"]} {row["mwaka"]}</td><td>TSh {row["kinachotakiwa"]:,.0f}</td><td>TSh {row["kilicholipwa"]:,.0f}</td><td>TSh {row["deni"]:,.0f}</td><td>{row["status_ada"]}</td></tr>'
        
        elif report_type == 'mapato':
            html += f'''
                <div class="summary-card"><div class="summary-number">TSh {summary['total_income']:,.0f}</div><div>Jumla ya Mapato</div></div>
                <div class="summary-card"><div class="summary-number">{summary['record_count']}</div><div>Idadi ya Malipo</div></div>
            </div>
            <h3>💰 MAPATO KWA KILA CHANZO</h3>
            <table><thead><tr><th>Chanzo</th><th>Kiasi (TSh)</th><th>Idadi ya Malipo</th><th>Ufanisi</th></tr></thead>
            <tbody>'''
            for row in data:
                progress = (row['total_income'] / row['target'] * 100) if row['target'] > 0 else 0
                html += f'<tr><td>{row["chanzo"]}</td><td>TSh {row["total_income"]:,.0f}</td><td>{row["transaction_count"]}</td><td>{progress:.1f}%</td></tr>'
        
        else:
            html += f'''
                <div class="summary-card"><div class="summary-number">{summary['attendance_rate']:.1f}%</div><div>Mahudhurio</div></div>
                <div class="summary-card"><div class="summary-number">{summary['present']}</div><div>Waliohudhuria</div></div>
                <div class="summary-card"><div class="summary-number">{summary['absent']}</div><div>Watoro</div></div>
                <div class="summary-card"><div class="summary-number">TSh {summary['total_penalty']:,.0f}</div><div>Penalty</div></div>
            </div>
            <h3>📋 ORODHA YA MAHUDHURIO</h3>
            <table><thead><tr><th>Tukio</th><th>Tarehe</th><th>Jina</th><th>Sauti</th><th>Status</th><th>Penalty</th></table></thead>
            <tbody>'''
            for row in data[:100]:
                html += f'<tr><td>{row["tukio"]}</td><td>{row["tarehe"]}</td><td>{row["jina"]}</td><td>{row["sauti"]}</td><td>{row["status_display"]}</td><td>TSh {row["penalty"] or 0:,.0f}</td></tr>'
        
        html += f'''
            </tbody>
            </table>
            <div class="footer">
                <p>Generated by Kwaya Mt. Bonifasi Management System</p>
                <p>"Utukufu wa Mungu kwa sauti za malaika"</p>
            </div>
            </div>
            <div style="text-align: center; margin-top: 20px;" class="no-print">
                <button onclick="window.print()" style="background: #1a2a6e; color: #FFD700; padding: 10px 20px; border: none; border-radius: 30px; cursor: pointer;">🖨️ Print / Save as PDF</button>
                <button onclick="window.close()" style="background: #6c757d; color: white; padding: 10px 20px; border: none; border-radius: 30px; cursor: pointer;">✖ Close</button>
            </div>
        </body>
        </html>
        '''
        return html

@app.route('/api/export/wanakwaya')
def export_wanakwaya():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    format_type = request.args.get('format', 'pdf')
    
    with get_db() as conn:
        wanakwaya = conn.execute('SELECT * FROM wanakwaya ORDER BY sauti, jina').fetchall()
        
        soprano = sum(1 for w in wanakwaya if w['sauti'] == 'Soprano')
        alto = sum(1 for w in wanakwaya if w['sauti'] == 'Alto')
        tenor = sum(1 for w in wanakwaya if w['sauti'] == 'Tenor')
        bass = sum(1 for w in wanakwaya if w['sauti'] == 'Bass')
    
    if format_type == 'excel':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['WANAKWAYA REPORT'])
        writer.writerow(['Tarehe', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow(['MUHTASARI'])
        writer.writerow(['Jumla ya Wanakwaya', len(wanakwaya)])
        writer.writerow(['Soprano', soprano])
        writer.writerow(['Alto', alto])
        writer.writerow(['Tenor', tenor])
        writer.writerow(['Bass', bass])
        writer.writerow([])
        writer.writerow(['ORODHA YA WANAKWAYA'])
        writer.writerow(['ID', 'Jina', 'Simu', 'Sauti', 'Anwani', 'Tarehe ya Kujiunga', 'Status'])
        for w in wanakwaya:
            writer.writerow([w['id'], w['jina'], w['simu'], w['sauti'], w['anwani'] or '', w['tarehe_jiunga'], w['status']])
        
        response = app.response_class(response=output.getvalue(), mimetype='text/csv')
        response.headers.set('Content-Disposition', 'attachment', filename=f'Wanakwaya_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        return response
    else:
        html = f'''
        <html>
        <head><title>Wanakwaya Report</title><style>body{{font-family:Arial}} th{{background:#1a2a6e;color:#FFD700}}</style></head>
        <body><h1>👥 WANAKWAYA REPORT</h1>
        <p>Jumla: {len(wanakwaya)} | Soprano: {soprano} | Alto: {alto} | Tenor: {tenor} | Bass: {bass}</p>
        <table border="1"><tr><th>Jina</th><th>Sauti</th><th>Simu</th><th>Status</th></tr>
        {''.join(f'<tr><td>{w["jina"]}</td><td>{w["sauti"]}</td><td>{w["simu"]}</td><td>{w["status"]}</td>?' for w in wanakwaya)}
        </table><button onclick="window.print()">Print</button></body></html>
        '''
        return html

@app.route('/api/export/assets')
def export_assets():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    format_type = request.args.get('format', 'pdf')
    
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            value REAL DEFAULT 0,
            purchase_date DATE,
            supplier TEXT,
            description TEXT,
            maintenance TEXT DEFAULT 'none',
            status TEXT DEFAULT 'good',
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        assets = conn.execute('SELECT * FROM assets ORDER BY category, name').fetchall()
        
        if len(assets) == 0:
            sample_assets = [
                ('Piano / Keyboard (Yamaha)', 'Vyombo vya Muziki', 850000, '2022-01-15', 'Music Store', 'Piano ya kwaya', 'none', 'good'),
                ('Gitaa (Acoustic)', 'Vyombo vya Muziki', 250000, '2023-03-10', 'Guitar Center', 'Gitaa ya acoustic', 'none', 'good'),
                ('Kanzu za Kwaya', 'Mavazi', 750000, '2023-06-15', 'Tailor Shop', 'Kanzu 25 za wanakwaya', 'soon', 'good'),
                ('Mikrofoni (Shure)', 'Vifaa vya Sauti', 120000, '2024-01-10', 'SoundTech', 'Mikrofoni za wireless', 'none', 'good'),
            ]
            for a in sample_assets:
                conn.execute('INSERT INTO assets (name, category, value, purchase_date, supplier, description, maintenance, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', a)
            conn.commit()
            assets = conn.execute('SELECT * FROM assets ORDER BY category, name').fetchall()
    
    if format_type == 'excel':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ASSETS REPORT - KWAYA MT. BONIFASI'])
        writer.writerow(['Tarehe', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow(['ORODHA YA ASSETS'])
        writer.writerow(['Jina', 'Aina', 'Thamani (TSh)', 'Tarehe ya Kununua', 'Chanzo', 'Maintenance', 'Status'])
        for a in assets:
            writer.writerow([a['name'], a['category'], f"{a['value']:,.0f}", a['purchase_date'] or '-', a['supplier'] or '-', a['maintenance'] or 'none', a['status'] or 'good'])
        
        response = app.response_class(response=output.getvalue(), mimetype='text/csv')
        response.headers.set('Content-Disposition', 'attachment', filename=f'Assets_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        return response
    else:
        total_value = sum(a['value'] for a in assets)
        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Assets Report - Kwaya Mt. Bonifasi</title>
            <meta charset="UTF-8">
            {get_pdf_style()}
        </head>
        <body>
            <div class="report-container">
                <div class="header">
                    <h1>🎵 KWAYA YA MTAKATIFU BONIFASI 🎵</h1>
                    <div class="subtitle">ASSETS REPORT</div>
                    <div class="gold-line"></div>
                    <p>Tarehe: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="summary-cards">
                    <div class="summary-card"><div class="summary-number">{len(assets)}</div><div>Jumla ya Assets</div></div>
                    <div class="summary-card"><div class="summary-number">TSh {total_value:,.0f}</div><div>Thamani Jumla</div></div>
                </div>
                
                <h3>📋 ORODHA YA ASSETS</h3>
                <table>
                    <thead><tr><th>Jina</th><th>Aina</th><th>Thamani (TSh)</th><th>Tarehe ya Kununua</th><th>Status</th></tr></thead>
                    <tbody>'''
        for a in assets:
            html += f'<tr><td>{a["name"]}</td><td>{a["category"]}</td><td>{a["value"]:,.0f}</td><td>{a["purchase_date"] or "-"}</td><td>{a["status"] or "good"}</td></tr>'
        html += f'''
                    </tbody>
                </table>
                
                <div class="footer">
                    <p>Generated by Kwaya Mt. Bonifasi Management System</p>
                    <p class="bible-verse">"Utukufu wa Mungu kwa sauti za malaika"</p>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px;" class="no-print">
                <button onclick="window.print()" style="background: #1a2a6e; color: #FFD700; padding: 10px 25px; border: none; border-radius: 30px; cursor: pointer; font-weight: bold;">🖨️ Save as PDF</button>
                <button onclick="window.close()" style="background: #6c757d; color: white; padding: 10px 25px; border: none; border-radius: 30px; cursor: pointer; margin-left: 10px;">✖ Close</button>
            </div>
        </body>
        </html>
        '''
        return html

# ============ PDF STYLE FUNCTION ============
def get_pdf_style():
    return '''
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Times New Roman', Times, serif; 
            padding: 30px; 
            background: white;
            color: #333;
        }
        .report-container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 3px solid #FFD700;
        }
        .header h1 {
            color: #1a2a6e;
            font-size: 28px;
            margin-bottom: 5px;
        }
        .header .subtitle {
            color: #FFD700;
            font-size: 14px;
            letter-spacing: 2px;
        }
        .header p {
            color: #666;
            font-size: 12px;
            margin-top: 10px;
        }
        .gold-line {
            width: 80px;
            height: 2px;
            background: #FFD700;
            margin: 15px auto;
        }
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .summary-card {
            background: linear-gradient(135deg, #1a2a6e, #2a3a7e);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
            color: white;
        }
        .summary-number {
            font-size: 28px;
            font-weight: bold;
            color: #FFD700;
        }
        h3 {
            color: #1a2a6e;
            margin: 20px 0 15px 0;
            border-left: 4px solid #FFD700;
            padding-left: 15px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 13px;
        }
        th {
            background: linear-gradient(135deg, #1a2a6e, #2a3a7e);
            color: #FFD700;
            padding: 12px;
            text-align: left;
        }
        td {
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 11px;
            color: #888;
        }
        .bible-verse {
            font-style: italic;
            color: #1a2a6e;
            margin-top: 10px;
        }
        @media print {
            body { padding: 0; }
            .no-print { display: none; }
            .summary-card { break-inside: avoid; }
            table { break-inside: avoid; }
        }
    </style>
    '''

# ============ USER PROFILE (KAMILI) ============
@app.route('/profile')
def profile_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('profile.html')

@app.route('/api/profile')
def api_get_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        user = conn.execute('''
            SELECT w.id, w.username, w.full_name, w.role_id, w.last_login,
                   r.name as role_name
            FROM watumiaji w
            LEFT JOIN user_roles r ON w.role_id = r.id
            WHERE w.id = ?
        ''', (session['user_id'],)).fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        member = None
        if user['full_name']:
            member = conn.execute('''
                SELECT sauti, simu, anwani, tarehe_jiunga 
                FROM wanakwaya 
                WHERE jina LIKE ?
                LIMIT 1
            ''', (f'%{user["full_name"]}%',)).fetchone()
        
        debt = conn.execute('''
            SELECT COALESCE(SUM(kiasi_kinachotakiwa - kiasi_kilicholipwa), 0) as total 
            FROM ada_calendar 
            WHERE mwanakwaya_id = ? AND imelipwa < 1
        ''', (session['user_id'],)).fetchone()
        
        if not debt or debt['total'] == 0:
            debt = conn.execute('''
                SELECT COALESCE(SUM(jumla_ya_deni), 0) as total 
                FROM ada_monthly 
                WHERE mwanakwaya_id = ? AND imelipwa < 1
            ''', (session['user_id'],)).fetchone()
        
        penalty = conn.execute('''
            SELECT COALESCE(SUM(remaining_amount), 0) as total 
            FROM mahudhurio_penalties 
            WHERE member_id = ? AND imelipwa = 0
        ''', (session['user_id'],)).fetchone()
        
        if not penalty or penalty['total'] == 0:
            penalty = conn.execute('''
                SELECT COALESCE(SUM(penalty), 0) as total 
                FROM mahudhurio_detailed 
                WHERE mwanakwaya_id = ? AND imelipwa = 0 AND penalty > 0
            ''', (session['user_id'],)).fetchone()
        
        attendance = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present
            FROM mahudhurio_detailed 
            WHERE mwanakwaya_id = ? 
                AND strftime('%Y-%m', tarehe) = strftime('%Y-%m', 'now')
        ''', (session['user_id'],)).fetchone()
        
        attendance_rate = 0
        if attendance and attendance['total'] > 0:
            attendance_rate = round((attendance['present'] / attendance['total']) * 100)
        
        chart_data = conn.execute('''
            SELECT 
                strftime('%Y-%m', tarehe) as month,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present
            FROM mahudhurio_detailed 
            WHERE mwanakwaya_id = ? 
                AND tarehe >= date('now', '-6 months')
            GROUP BY strftime('%Y-%m', tarehe)
            ORDER BY month ASC
        ''', (session['user_id'],)).fetchall()
        
        months = []
        attendance_chart = []
        for row in chart_data:
            months.append(row['month'])
            rate = round((row['present'] / row['total']) * 100) if row['total'] > 0 else 0
            attendance_chart.append(rate)
        
        voice = member['sauti'] if member else None
        member_number = ''
        if voice:
            voice_count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND status = "active"', (voice,)).fetchone()
            prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
            member_number = f"{prefix}{voice_count['c']:03d}"
        
        profile_pic = conn.execute('SELECT profile_picture FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'] or user['username'],
                'role_name': user['role_name'] or 'User',
                'sauti': member['sauti'] if member else 'Hajabainishwa',
                'simu': member['simu'] if member else '-',
                'anwani': member['anwani'] if member else '-',
                'tarehe_jiunga': member['tarehe_jiunga'] if member else '-',
                'last_login': user['last_login'] if user['last_login'] else '-',
                'member_number': member_number,
                'deni': float(debt['total'] or 0),
                'attendance': attendance_rate,
                'penalty': float(penalty['total'] or 0),
                'profile_picture': profile_pic['profile_picture'] if profile_pic else None,
                'chart_months': months,
                'chart_attendance': attendance_chart
            }
        })

@app.route('/api/change-password', methods=['POST'])
def api_change_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Tafadhali weka password zote!'}), 400
    
    with get_db() as conn:
        user = conn.execute('SELECT password FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        
        if not check_password_hash(user['password'], current_password):
            return jsonify({'success': False, 'message': 'Password ya sasa si sahihi!'}), 400
        
        if len(new_password) < 4:
            return jsonify({'success': False, 'message': 'Password mpya lazima iwe na herufi 4 au zaidi!'}), 400
        
        if new_password == current_password:
            return jsonify({'success': False, 'message': 'Password mpya haiwezi kuwa sawa na password ya sasa!'}), 400
        
        hashed = generate_password_hash(new_password)
        conn.execute('UPDATE watumiaji SET password = ? WHERE id = ?', (hashed, session['user_id']))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Password imebadilishwa kikamilifu!'})

# ============ AVATAR UPLOAD ============
import base64

@app.route('/api/upload-avatar', methods=['POST'])
def api_upload_avatar():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        cursor = conn.execute("PRAGMA table_info(watumiaji)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'profile_picture' not in columns:
            conn.execute('ALTER TABLE watumiaji ADD COLUMN profile_picture TEXT')
            conn.commit()
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'message': 'Hakuna picha iliyochaguliwa'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Hakuna picha iliyochaguliwa'}), 400
    
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 2 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'Picha ni kubwa sana! Chagua picha chini ya 2MB'}), 400
    
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed_types:
        return jsonify({'success': False, 'message': 'Aina ya faili haikubaliki. Tumia JPG, PNG, au GIF'}), 400
    
    file_data = file.read()
    base64_data = base64.b64encode(file_data).decode('utf-8')
    mime_type = file.content_type
    avatar_data = f"data:{mime_type};base64,{base64_data}"
    
    with get_db() as conn:
        conn.execute('UPDATE watumiaji SET profile_picture = ? WHERE id = ?', (avatar_data, session['user_id']))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Picha imehifadhiwa kikamilifu!', 'avatar': avatar_data})

@app.route('/api/get-avatar')
def api_get_avatar():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        user = conn.execute('SELECT profile_picture FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        avatar = user['profile_picture'] if user and user['profile_picture'] else None
        return jsonify({'success': True, 'avatar': avatar})

# ============ NOTIFICATIONS API ============
@app.route('/api/notifications')
def api_get_notifications():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        notifications = conn.execute('''
            SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50
        ''', (session['user_id'],)).fetchall()
        
        return jsonify({'success': True, 'notifications': [dict(n) for n in notifications]})

@app.route('/api/notifications/mark-read', methods=['POST'])
def api_mark_notification_read():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    notification_id = data.get('notification_id')
    
    with get_db() as conn:
        if notification_id:
            conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?', 
                        (notification_id, session['user_id']))
        else:
            conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Notifikation imesomwa'})

@app.route('/api/notifications/create', methods=['POST'])
def api_create_notification():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    user_id = data.get('user_id')
    title = data.get('title')
    message = data.get('message')
    
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id inahitajika!'}), 400
    
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.execute('''
            INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)
        ''', (user_id, title, message))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Notifikation imetumwa'})

@app.route('/api/notifications/broadcast', methods=['POST'])
def api_broadcast_notification():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        user = conn.execute('SELECT role_id FROM watumiaji WHERE id = ?', (session['user_id'],)).fetchone()
        if user['role_id'] != 1:
            return jsonify({'success': False, 'message': 'Admin pekee ndio anaweza kutuma matangazo!'}), 403
    
    data = request.json
    title = data.get('title')
    message = data.get('message')
    target = data.get('target', 'all')
    
    with get_db() as conn:
        if target == 'all':
            users = conn.execute('SELECT id FROM watumiaji').fetchall()
        elif target == 'wanakwaya_all':
            users = conn.execute('''
                SELECT w.id FROM watumiaji w
                INNER JOIN wanakwaya m ON w.full_name LIKE '%' || m.jina || '%'
                GROUP BY w.id
            ''').fetchall()
        elif target == 'soprano':
            users = conn.execute('''
                SELECT w.id FROM watumiaji w
                INNER JOIN wanakwaya m ON w.full_name LIKE '%' || m.jina || '%'
                WHERE m.sauti = 'Soprano'
                GROUP BY w.id
            ''').fetchall()
        elif target == 'alto':
            users = conn.execute('''
                SELECT w.id FROM watumiaji w
                INNER JOIN wanakwaya m ON w.full_name LIKE '%' || m.jina || '%'
                WHERE m.sauti = 'Alto'
                GROUP BY w.id
            ''').fetchall()
        elif target == 'tenor':
            users = conn.execute('''
                SELECT w.id FROM watumiaji w
                INNER JOIN wanakwaya m ON w.full_name LIKE '%' || m.jina || '%'
                WHERE m.sauti = 'Tenor'
                GROUP BY w.id
            ''').fetchall()
        elif target == 'bass':
            users = conn.execute('''
                SELECT w.id FROM watumiaji w
                INNER JOIN wanakwaya m ON w.full_name LIKE '%' || m.jina || '%'
                WHERE m.sauti = 'Bass'
                GROUP BY w.id
            ''').fetchall()
        elif target == 'walimu':
            users = conn.execute('SELECT id FROM watumiaji WHERE role_id = 3').fetchall()
        elif target == 'wafadhili':
            users = conn.execute('SELECT id FROM watumiaji WHERE role_id = 5').fetchall()
        elif target == 'viongozi':
            users = conn.execute('SELECT id FROM watumiaji WHERE role_id IN (1, 2)').fetchall()
        elif target == 'admin':
            users = conn.execute('SELECT id FROM watumiaji WHERE role_id = 1').fetchall()
        else:
            users = conn.execute('SELECT id FROM watumiaji').fetchall()
        
        count = 0
        for user in users:
            conn.execute('''
                INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)
            ''', (user['id'], title, message))
            count += 1
        
        conn.commit()
    
    return jsonify({'success': True, 'message': f'Tangazo limetumwa kwa watu {count}'})

@app.route('/api/mapato/income/add', methods=['POST'])
def api_add_income():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    source_id = data.get('source_id')
    amount = data.get('amount')
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    note = data.get('note', '')
    
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO mapato_income (source_id, amount, date, note, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_id, amount, date, note, session['user_id']))
        payment_id = cursor.lastrowid
        conn.commit()
        
        source = conn.execute('SELECT name FROM mapato_sources WHERE id = ?', (source_id,)).fetchone()
        if source:
            conn.execute('''
                INSERT INTO mapato (chanzo, kiasi, maelezo, tarehe)
                VALUES (?, ?, ?, ?)
            ''', (source['name'], amount, note, date))
            conn.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Mapato ya TSh {amount:,.0f} yameongezwa!',
            'payment_id': payment_id
        })

# ============ RECEIPTS ROUTES ============
@app.route('/receipt/penalty/<int:penalty_id>')
def view_penalty_receipt(penalty_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        penalty = conn.execute('''
            SELECT p.*, w.jina as member_name, w.sauti as member_voice
            FROM mahudhurio_penalties p
            JOIN wanakwaya w ON p.member_id = w.id
            WHERE p.id = ?
        ''', (penalty_id,)).fetchone()
        
        if not penalty:
            return f'<h3>Risiti ya Penalty haipatikani! ID: {penalty_id}</h3>', 404
        
        penalty_amount = penalty['penalty_amount'] if penalty['penalty_amount'] else 0
        remaining_amount = penalty['remaining_amount'] if penalty['remaining_amount'] else 0
        amount = penalty_amount if penalty_amount > 0 else remaining_amount
        
        voice = penalty['member_voice']
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        
        count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ?', (voice, penalty['member_id'])).fetchone()
        member_number = f"{prefix}{count['c']:03d}"
        
        receipt_data = {
            'receipt_number': f'PNL-{penalty_id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'receipt_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'member_name': penalty['member_name'],
            'member_number': member_number,
            'member_voice': penalty['member_voice'],
            'amount': float(amount),
            'receipt_type': 'penalty',
            'penalty_type': penalty['penalty_type'] if penalty['penalty_type'] else 'General',
            'penalty_date': penalty['tarehe_penalty'] if penalty['tarehe_penalty'] else '',
            'payment_method': 'CASH',
            'received_by': session['username'],
            'auto_print': request.args.get('print', 'false').lower() == 'true'
        }
        
        return render_template('receipt_print.html', **receipt_data)

# ============ KWAYA CONTENT MANAGEMENT (ADMIN) ============
@app.route('/admin/kwaya-content')
def admin_kwaya_content():
    if 'user_id' not in session or session.get('role_id') != 1:
        flash('Sehemu hii ni kwa Admin pekee!', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin_kwaya_content.html')

@app.route('/api/kwaya/content/pages')
def api_kwaya_pages():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        pages = conn.execute('SELECT page_name, title, last_updated FROM kwaya_content ORDER BY title').fetchall()
        return jsonify({
            'success': True,
            'pages': [{'page_name': p['page_name'], 'title': p['title'], 'last_updated': p['last_updated']} for p in pages]
        })

@app.route('/api/kwaya/content/<page_name>')
def api_kwaya_content(page_name):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        content = conn.execute('SELECT content, title, last_updated, updated_by FROM kwaya_content WHERE page_name = ?', (page_name,)).fetchone()
        if content:
            return jsonify({
                'success': True, 
                'content': content['content'], 
                'title': content['title'],
                'last_updated': content['last_updated'],
                'updated_by': content['updated_by']
            })
        return jsonify({'success': False, 'message': 'Page not found'}), 404

@app.route('/api/kwaya/content/save', methods=['POST'])
def api_kwaya_save_content():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    page_name = data.get('page_name')
    content = data.get('content')
    
    with get_db() as conn:
        conn.execute('''
            UPDATE kwaya_content 
            SET content = ?, last_updated = CURRENT_TIMESTAMP, updated_by = ?
            WHERE page_name = ?
        ''', (content, session['username'], page_name))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Maudhui yamehifadhiwa!'})

@app.route('/receipt/ada/<int:payment_id>')
def view_ada_receipt(payment_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        payment = conn.execute('''
            SELECT ac.*, w.jina as member_name, w.sauti as member_voice
            FROM ada_calendar ac
            JOIN wanakwaya w ON ac.mwanakwaya_id = w.id
            WHERE ac.id = ?
        ''', (payment_id,)).fetchone()
        
        if not payment:
            return f'<h3>Risiti ya ADA haipatikani! ID: {payment_id}</h3>', 404
        
        voice = payment['member_voice']
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ?', (voice,)).fetchone()
        member_number = f"{prefix}{count['c']:03d}"
        
        test_data = {
            'receipt_number': f'ADA-{payment_id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'receipt_date': payment['tarehe_malipo'] if payment['tarehe_malipo'] else datetime.now().strftime("%Y-%m-%d"),
            'member_name': payment['member_name'],
            'member_number': member_number,
            'member_voice': payment['member_voice'],
            'amount': float(payment['kiasi_kilicholipwa']),
            'receipt_type': 'ada',
            'month': payment['mwezi'],
            'year': payment['mwaka'],
            'ada_amount': float(payment['kiasi_kinachotakiwa']),
            'payment_method': 'CASH',
            'received_by': session['username'],
            'auto_print': request.args.get('print', 'false').lower() == 'true'
        }
        
        return render_template('receipt_print.html', **test_data)

@app.route('/receipt/income/<int:payment_id>')
def view_income_receipt(payment_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        payment = conn.execute('''
            SELECT i.*, s.name as source_name
            FROM mapato_income i
            JOIN mapato_sources s ON i.source_id = s.id
            WHERE i.id = ?
        ''', (payment_id,)).fetchone()
        
        if not payment:
            return f'<h3>Risiti ya Mapato haipatikani! ID: {payment_id}</h3>', 404
        
        donor_name = request.args.get('donor_name', payment['note'] if payment['note'] else 'Mfadhili')
        is_donor = 'Wafadhili' in payment['source_name']
        
        test_data = {
            'receipt_number': f'INV-{payment_id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'receipt_date': payment['date'],
            'member_name': donor_name,
            'member_number': '-',
            'member_voice': payment['source_name'],
            'amount': float(payment['amount']),
            'receipt_type': 'income',
            'source_name': payment['source_name'],
            'description': payment['note'] if payment['note'] else 'Shukrani kwa mchango',
            'payment_method': 'CASH',
            'received_by': session['username'],
            'auto_print': request.args.get('print', 'false').lower() == 'true',
            'is_donor': is_donor
        }
        
        return render_template('receipt_print.html', **test_data)

@app.route('/receipt/sale/<int:sale_id>')
def view_sale_receipt(sale_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        sale = conn.execute('''
            SELECT s.*, p.name as product_name
            FROM sales s
            JOIN products p ON s.product_id = p.id
            WHERE s.id = ?
        ''', (sale_id,)).fetchone()
        
        if not sale:
            return f'<h3>Risiti ya Mauzo haipatikani! ID: {sale_id}</h3>', 404
        
        receipt_data = {
            'receipt_number': sale['receipt_no'],
            'receipt_date': sale['sale_date'],
            'member_name': sale.get('customer_name', 'Mteja wa Kawaida'),
            'member_number': sale.get('customer_phone', '-'),
            'member_voice': sale['product_name'],
            'amount': float(sale['total_amount']),
            'receipt_type': 'sale',
            'items': f"{sale['quantity']} x {sale['product_name']}",
            'quantity': sale['quantity'],
            'unit_price': float(sale['selling_price']),
            'payment_method': 'CASH',
            'received_by': session['username'],
            'auto_print': request.args.get('print', 'false').lower() == 'true'
        }
        
        return render_template('receipt_print.html', **receipt_data)

@app.route('/receipt/test')
def test_receipt():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    test_data = {
        'receipt_number': f'TEST-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'receipt_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'member_name': session.get('username', 'Test Member'),
        'member_number': 'T001',
        'member_voice': 'Soprano',
        'amount': 50000,
        'receipt_type': 'income',
        'source_name': 'Ada za Kwaya',
        'description': 'Malipo ya ada ya mwezi Juni 2026',
        'payment_method': 'CASH',
        'received_by': session.get('username', 'admin'),
        'auto_print': request.args.get('print', 'false').lower() == 'true',
        'is_donor': False
    }
    
    return render_template('receipt_print.html', **test_data)

# ============ EXCEL IMPORT/EXPORT ============
@app.route('/api/export/wanakwaya/excel')
def export_wanakwaya_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        wanakwaya = conn.execute('SELECT id, jina, simu, sauti, anwani, tarehe_jiunga, status FROM wanakwaya ORDER BY jina').fetchall()
        data = [dict(w) for w in wanakwaya]
    
    try:
        from excel_utils import export_wanakwaya_to_excel
        excel_data = export_wanakwaya_to_excel(data)
    except:
        import pandas as pd
        import io
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Wanakwaya', index=False)
        excel_data = output.getvalue()
    
    return Response(
        excel_data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=wanakwaya_{datetime.now().strftime("%Y%m%d")}.xlsx'}
    )

@app.route('/api/export/mapato/excel')
def export_mapato_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        mapato = conn.execute('''
            SELECT i.id, s.name as chanzo, i.amount, i.date, i.note
            FROM mapato_income i
            JOIN mapato_sources s ON i.source_id = s.id
            ORDER BY i.date DESC
        ''').fetchall()
        data = [{'ID': m['id'], 'Chanzo': m['chanzo'], 'Kiasi': m['amount'], 'Tarehe': m['date'], 'Maelezo': m['note']} for m in mapato]
    
    import pandas as pd
    import io
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Mapato', index=False)
    excel_data = output.getvalue()
    
    return Response(
        excel_data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=mapato_{datetime.now().strftime("%Y%m%d")}.xlsx'}
    )

# ============ PDF STATEMENT ============
@app.route('/api/member/statement/<int:member_id>')
def member_statement_pdf(member_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with get_db() as conn:
        member = conn.execute('SELECT * FROM wanakwaya WHERE id = ?', (member_id,)).fetchone()
        if not member:
            flash('Mwanakwaya haipatikani!', 'error')
            return redirect(url_for('wanakwaya'))
        
        ada_records = conn.execute('''
            SELECT mwezi, mwaka, kiasi_kinachotakiwa, kiasi_kilicholipwa, 
                   (kiasi_kinachotakiwa - kiasi_kilicholipwa) as deni
            FROM ada_calendar
            WHERE mwanakwaya_id = ? AND mwaka = ?
            ORDER BY mwezi
        ''', (member_id, datetime.now().year)).fetchall()
        
        penalty_records = conn.execute('''
            SELECT tukio, tarehe_penalty as tarehe, penalty_type, penalty_amount
            FROM mahudhurio_penalties
            WHERE member_id = ? AND imelipwa = 0
        ''', (member_id,)).fetchall()
        
        voice = member['sauti']
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ?', (voice, member_id)).fetchone()
        member_number = f"{prefix}{count['c']:03d}"
        
        member_data = {
            'jina': member['jina'],
            'member_number': member_number,
            'sauti': member['sauti'],
            'simu': member['simu']
        }
        
        ada_list = [dict(r) for r in ada_records]
        penalty_list = [dict(r) for r in penalty_records]
    
    try:
        from pdf_utils import generate_member_statement
        pdf_data = generate_member_statement(member_data, ada_list, penalty_list, [])
    except:
        html = f"<h1>Member Statement</h1><p>Member: {member['jina']}</p><p>Member Number: {member_number}</p>"
        return html
    
    return Response(
        pdf_data,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=statement_{member_number}_{datetime.now().strftime("%Y%m%d")}.pdf'}
    )

# ============ FINANCIAL SUMMARY REPORT ============
@app.route('/api/financial/summary')
def financial_summary_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    year = request.args.get('year', datetime.now().year)
    period = f"Mwaka {year}"
    
    with get_db() as conn:
        income_data = conn.execute('''
            SELECT s.name, SUM(i.amount) as amount
            FROM mapato_income i
            JOIN mapato_sources s ON i.source_id = s.id
            WHERE strftime('%Y', i.date) = ?
            GROUP BY s.name
            ORDER BY amount DESC
        ''', (str(year),)).fetchall()
        
        income_list = [{'name': r['name'], 'amount': r['amount'] or 0} for r in income_data]
        
        ada_summary = conn.execute('''
            SELECT 
                SUM(kiasi_kinachotakiwa) as total_expected,
                SUM(kiasi_kilicholipwa) as total_paid,
                SUM(kiasi_kinachotakiwa - kiasi_kilicholipwa) as total_debt
            FROM ada_calendar
            WHERE mwaka = ?
        ''', (year,)).fetchone()
        
        penalty_summary = conn.execute('''
            SELECT 
                SUM(penalty_amount) as total_penalty,
                SUM(CASE WHEN imelipwa = 1 THEN penalty_amount ELSE 0 END) as total_paid,
                SUM(CASE WHEN imelipwa = 0 THEN penalty_amount ELSE 0 END) as total_unpaid
            FROM mahudhurio_penalties
            WHERE strftime('%Y', tarehe_penalty) = ?
        ''', (str(year),)).fetchone()
        
        ada_data = {
            'total_expected': ada_summary['total_expected'] or 0,
            'total_paid': ada_summary['total_paid'] or 0,
            'total_debt': ada_summary['total_debt'] or 0
        }
        
        penalty_data = {
            'total_penalty': penalty_summary['total_penalty'] or 0,
            'total_paid': penalty_summary['total_paid'] or 0,
            'total_unpaid': penalty_summary['total_unpaid'] or 0
        }
    
    try:
        from pdf_utils import generate_financial_summary
        pdf_data = generate_financial_summary(income_list, ada_data, penalty_data, period)
    except:
        html = f"<h1>Financial Summary {year}</h1><p>Total Income: {sum(i['amount'] for i in income_list)}</p>"
        return html
    
    return Response(
        pdf_data,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=financial_summary_{year}.pdf'}
    )

# ============ MEMBER SELF-SERVICE PORTAL ============
@app.route('/member/profile')
def member_self_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('member_profile.html')

@app.route('/api/member/self/profile')
def api_member_self_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        username = session['username']
        
        member = conn.execute('''
            SELECT * FROM wanakwaya 
            WHERE jina LIKE ? OR simu = ?
            LIMIT 1
        ''', (f'%{username}%', username)).fetchone()
        
        if not member:
            member = conn.execute('SELECT * FROM wanakwaya WHERE status = "active" LIMIT 1').fetchone()
        
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'}), 404
        
        voice = member['sauti']
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ?', (voice, member['id'])).fetchone()
        member_number = f"{prefix}{count['c']:03d}"
        
        attendance = conn.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present
            FROM mahudhurio_detailed
            WHERE mwanakwaya_id = ? AND strftime('%Y-%m', tarehe) = strftime('%Y-%m', 'now')
        ''', (member['id'],)).fetchone()
        
        attendance_rate = round((attendance['present'] / attendance['total'] * 100)) if attendance['total'] and attendance['total'] > 0 else 0
        
        debt = conn.execute('''
            SELECT COALESCE(SUM(kiasi_kinachotakiwa - kiasi_kilicholipwa), 0) as total
            FROM ada_calendar
            WHERE mwanakwaya_id = ? AND imelipwa < 1
        ''', (member['id'],)).fetchone()
        
        penalty = conn.execute('''
            SELECT COALESCE(SUM(remaining_amount), 0) as total
            FROM mahudhurio_penalties
            WHERE member_id = ? AND imelipwa = 0
        ''', (member['id'],)).fetchone()
        
        attendance_history = conn.execute('''
            SELECT tarehe, tukio, status, dakika_chelewa
            FROM mahudhurio_detailed
            WHERE mwanakwaya_id = ?
            ORDER BY tarehe DESC LIMIT 10
        ''', (member['id'],)).fetchall()
        
        penalties = conn.execute('''
            SELECT penalty_type, penalty_amount, remaining_amount, tarehe_penalty, tukio
            FROM mahudhurio_penalties
            WHERE member_id = ? AND imelipwa = 0
            ORDER BY tarehe_penalty DESC
        ''', (member['id'],)).fetchall()
        
        requests = conn.execute('''
            SELECT * FROM self_service_requests
            WHERE member_id = ?
            ORDER BY created_at DESC
        ''', (member['id'],)).fetchall()
        
        return jsonify({
            'success': True,
            'member': {
                'id': member['id'],
                'jina': member['jina'],
                'simu': member['simu'],
                'sauti': member['sauti'],
                'anwani': member['anwani'],
                'tarehe_jiunga': member['tarehe_jiunga'],
                'member_number': member_number
            },
            'stats': {
                'attendance': attendance_rate,
                'debt': float(debt['total'] or 0),
                'penalty': float(penalty['total'] or 0)
            },
            'attendance': [dict(a) for a in attendance_history],
            'penalties': [dict(p) for p in penalties],
            'requests': [dict(r) for r in requests]
        })

@app.route('/api/member/self/update', methods=['POST'])
def api_member_self_update():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    simu = data.get('simu')
    anwani = data.get('anwani')
    password = data.get('password')
    
    with get_db() as conn:
        username = session['username']
        member = conn.execute('''
            SELECT * FROM wanakwaya 
            WHERE jina LIKE ? OR simu = ?
            LIMIT 1
        ''', (f'%{username}%', username)).fetchone()
        
        if not member:
            member = conn.execute('SELECT * FROM wanakwaya WHERE status = "active" LIMIT 1').fetchone()
        
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'}), 404
        
        if simu:
            conn.execute('UPDATE wanakwaya SET simu = ? WHERE id = ?', (simu, member['id']))
        if anwani:
            conn.execute('UPDATE wanakwaya SET anwani = ? WHERE id = ?', (anwani, member['id']))
        
        if password and len(password) >= 4:
            from werkzeug.security import generate_password_hash
            hashed = generate_password_hash(password)
            conn.execute('UPDATE watumiaji SET password = ? WHERE id = ?', (hashed, session['user_id']))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Taarifa zimehifadhiwa'})

# ============ ADVANCED ANALYTICS ============
@app.route('/analytics')
def analytics_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('analytics_dashboard.html')

@app.route('/api/analytics/data')
def api_analytics_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        monthly_income = conn.execute('''
            SELECT strftime('%m', date) as month, SUM(amount) as total
            FROM mapato_income
            WHERE date >= date('now', '-11 months')
            GROUP BY month
            ORDER BY month
        ''').fetchall()
        
        income_by_month = [0] * 12
        for m in monthly_income:
            idx = int(m['month']) - 1
            income_by_month[idx] = float(m['total'] or 0)
        
        voice_attendance = []
        for voice in ['Soprano', 'Alto', 'Tenor', 'Bass']:
            total = conn.execute('''
                SELECT COUNT(*) as c FROM mahudhurio_detailed d
                JOIN wanakwaya w ON d.mwanakwaya_id = w.id
                WHERE w.sauti = ? AND strftime('%Y-%m', d.tarehe) = strftime('%Y-%m', 'now')
            ''', (voice,)).fetchone()
            present = conn.execute('''
                SELECT COUNT(*) as c FROM mahudhurio_detailed d
                JOIN wanakwaya w ON d.mwanakwaya_id = w.id
                WHERE w.sauti = ? AND d.status = 'present' AND strftime('%Y-%m', d.tarehe) = strftime('%Y-%m', 'now')
            ''', (voice,)).fetchone()
            rate = (present['c'] / total['c'] * 100) if total['c'] > 0 else 0
            voice_attendance.append(rate)
        
        top_donors = conn.execute('''
            SELECT i.note as name, SUM(i.amount) as total
            FROM mapato_income i
            JOIN mapato_sources s ON i.source_id = s.id
            WHERE s.name LIKE '%Wafadhili%'
            GROUP BY i.note
            ORDER BY total DESC
            LIMIT 5
        ''').fetchall()
        
        actual = income_by_month[-6:] if len(income_by_month) >= 6 else income_by_month
        forecast = [actual[-1] * 1.05] if actual else [0]
        
        return jsonify({
            'success': True,
            'monthly_labels': ['Jan', 'Feb', 'Mac', 'Apr', 'Mei', 'Jun', 'Jul', 'Ago', 'Sep', 'Okt', 'Nov', 'Des'],
            'actual_income': income_by_month,
            'forecast_income': income_by_month + forecast,
            'voice_attendance': voice_attendance,
            'top_donors': [{'name': d['name'] or 'Anonymous', 'amount': d['total']} for d in top_donors],
            'actual_penalty': [0]*12,
            'forecast_penalty': [0]*13,
            'predictions': {
                'next_month_income': income_by_month[-1] * 1.05 if income_by_month[-1] else 500000,
                'next_month_attendance': 75,
                'next_month_penalty': 50000
            },
            'trends': {
                'income_trend': 5.2,
                'attendance_trend': 2.5
            }
        })

@app.route('/api/member/self/request', methods=['POST'])
def api_member_self_request():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    request_type = data.get('type', 'permission')
    request_date = data.get('date', '')
    reason = data.get('reason', '')
    
    with get_db() as conn:
        username = session['username']
        member = conn.execute('''
            SELECT id FROM wanakwaya 
            WHERE jina LIKE ? OR simu = ?
            LIMIT 1
        ''', (f'%{username}%', username)).fetchone()
        
        if not member:
            member = conn.execute('SELECT id FROM wanakwaya WHERE status = "active" LIMIT 1').fetchone()
        
        if not member:
            return jsonify({'success': False, 'message': 'Member not found'}), 404
        
        request_data = f"Date: {request_date}, Reason: {reason}" if request_type == 'permission' else f"Complaint/Feedback: {reason}"
        
        conn.execute('''
            INSERT INTO self_service_requests (member_id, request_type, request_data)
            VALUES (?, ?, ?)
        ''', (member['id'], request_type, request_data))
        conn.commit()
        
        log_activity(session['user_id'], session['username'], f'REQUEST_{request_type.upper()}', request_data)
        
        return jsonify({'success': True, 'message': 'Ombi limetumwa'})

# ============ ADMIN MANAGEMENT OF REQUESTS ============
@app.route('/admin/requests')
def admin_requests_page():
    if 'user_id' not in session or session.get('role_id') != 1:
        flash('Sehemu hii ni kwa Admin pekee!', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin_requests.html')

@app.route('/api/admin/requests')
def api_admin_requests():
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        try:
            conn.execute('ALTER TABLE self_service_requests ADD COLUMN admin_response TEXT')
        except:
            pass
        try:
            conn.execute('ALTER TABLE self_service_requests ADD COLUMN admin_response_date DATETIME')
        except:
            pass
        
        requests = conn.execute('''
            SELECT r.*, w.jina as member_name, w.sauti, w.simu
            FROM self_service_requests r
            JOIN wanakwaya w ON r.member_id = w.id
            ORDER BY r.created_at DESC
        ''').fetchall()
        
        result = []
        for req in requests:
            voice = req['sauti']
            prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
            count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ?', (voice, req['member_id'])).fetchone()
            member_number = f"{prefix}{count['c']:03d}"
            
            result.append({
                'id': req['id'],
                'member_id': req['member_id'],
                'member_name': req['member_name'],
                'member_number': member_number,
                'member_voice': req['sauti'],
                'member_phone': req['simu'],
                'request_type': req['request_type'],
                'request_data': req['request_data'],
                'status': req['status'],
                'admin_response': req['admin_response'] if 'admin_response' in req.keys() else '',
                'created_at': req['created_at'],
                'resolved_at': req['resolved_at']
            })
        
        return jsonify({'success': True, 'requests': result})

@app.route('/api/admin/request/<int:request_id>/respond', methods=['POST'])
def api_admin_respond_request(request_id):
    if 'user_id' not in session or session.get('role_id') != 1:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    action = data.get('action')
    response_text = data.get('response', '')
    
    with get_db() as conn:
        try:
            conn.execute('ALTER TABLE self_service_requests ADD COLUMN admin_response TEXT')
        except:
            pass
        try:
            conn.execute('ALTER TABLE self_service_requests ADD COLUMN admin_response_date DATETIME')
        except:
            pass
        
        if action == 'approve':
            status = 'approved'
            message = 'Ombi limekubaliwa'
        elif action == 'reject':
            status = 'rejected'
            message = 'Ombi limekataliwa'
        else:
            status = 'responded'
            message = 'Jibu limeongezwa'
        
        conn.execute('''
            UPDATE self_service_requests 
            SET status = ?, admin_response = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, response_text, request_id))
        
        req = conn.execute('SELECT member_id, request_type FROM self_service_requests WHERE id = ?', (request_id,)).fetchone()
        
        conn.execute('''
            INSERT INTO notifications (user_id, title, message, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (req['member_id'], f'📢 Majibu ya {req["request_type"]}', f'{message}\n\nAdmin: {response_text}'))
        
        conn.commit()
        
        return jsonify({'success': True, 'message': message})

# ============ MEMBER DIRECTORY PDF ============
@app.route('/member-directory')
def member_directory_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('member_directory.html')

@app.route('/api/member-directory')
def api_member_directory():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        members = conn.execute('''
            SELECT id, jina, simu, sauti, anwani, tarehe_jiunga, status
            FROM wanakwaya 
            WHERE status = 'active'
            ORDER BY sauti, jina
        ''').fetchall()
        
        members_by_voice = {
            'Soprano': [], 'Alto': [], 'Tenor': [], 'Bass': []
        }
        
        for m in members:
            voice = m['sauti'] if m['sauti'] in members_by_voice else 'Nyingine'
            if voice not in members_by_voice:
                members_by_voice[voice] = []
            members_by_voice[voice].append(dict(m))
        
        return jsonify({
            'success': True,
            'members_by_voice': members_by_voice,
            'total_members': len(members),
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

@app.route('/api/export/member-directory')
def export_member_directory():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    format_type = request.args.get('format', 'pdf')
    
    with get_db() as conn:
        members = conn.execute('''
            SELECT id, jina, simu, sauti, anwani, tarehe_jiunga, status
            FROM wanakwaya 
            WHERE status = 'active'
            ORDER BY sauti, jina
        ''').fetchall()
        
        soprano = [m for m in members if m['sauti'] == 'Soprano']
        alto = [m for m in members if m['sauti'] == 'Alto']
        tenor = [m for m in members if m['sauti'] == 'Tenor']
        bass = [m for m in members if m['sauti'] == 'Bass']
    
    if format_type == 'excel':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['MEMBER DIRECTORY - KWAYA MT. BONIFASI'])
        writer.writerow(['Tarehe', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow(['ORODHA YA WANAKWAYA'])
        writer.writerow(['ID', 'Jina Kamili', 'Simu', 'Sauti', 'Anwani', 'Tarehe ya Kujiunga', 'Status'])
        for m in members:
            writer.writerow([m['id'], m['jina'], m['simu'], m['sauti'], m['anwani'] or '-', m['tarehe_jiunga'], m['status']])
        
        response = app.response_class(response=output.getvalue(), mimetype='text/csv')
        response.headers.set('Content-Disposition', 'attachment', filename=f'Member_Directory_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        return response
    else:
        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Member Directory - Kwaya Mt. Bonifasi</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Times New Roman', Times, serif; padding: 30px; }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #FFD700; }}
                .header h1 {{ color: #1a2a6e; }}
                .voice-section {{ margin-bottom: 30px; }}
                .voice-title {{ background: #1a2a6e; color: #FFD700; padding: 10px 15px; border-radius: 10px; margin-bottom: 15px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                th {{ background: #2a3a7e; color: #FFD700; padding: 10px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #888; }}
                @media print {{ body {{ padding: 0; }} .no-print {{ display: none; }} }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎵 KWAYA YA MTAKATIFU BONIFASI 🎵</h1>
                <h2>ORODHA YA WANAKWAYA</h2>
                <p>Tarehe: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Jumla ya Wanakwaya: {len(members)}</p>
            </div>
            
            <div class="voice-section">
                <div class="voice-title">🎤 SOPRANO ({len(soprano)})</div>
                <table>
                    <thead><tr><th>#</th><th>Jina</th><th>Simu</th><th>Anwani</th></tr></thead>
                    <tbody>
                        {''.join(f'<tr><td>{i+1}</td><td>{m["jina"]}</td><td>{m["simu"]}</td><td>{m["anwani"] or "-"}</td></tr>' for i, m in enumerate(soprano))}
                    </tbody>
                </table>
            </div>
            
            <div class="voice-section">
                <div class="voice-title">🎤 ALTO ({len(alto)})</div>
                <table>
                    <thead><tr><th>#</th><th>Jina</th><th>Simu</th><th>Anwani</th></tr></thead>
                    <tbody>
                        {''.join(f'<tr><td>{i+1}</td><td>{m["jina"]}</td><td>{m["simu"]}</td><td>{m["anwani"] or "-"}</td></tr>' for i, m in enumerate(alto))}
                    </tbody>
                </table>
            </div>
            
            <div class="voice-section">
                <div class="voice-title">🎤 TENOR ({len(tenor)})</div>
                </table>
                    <thead><tr><th>#</th><th>Jina</th><th>Simu</th><th>Anwani</th></tr></thead>
                    <tbody>
                        {''.join(f'<tr><td>{i+1}</td><td>{m["jina"]}</td><td>{m["simu"]}</td><td>{m["anwani"] or "-"}</td></tr>' for i, m in enumerate(tenor))}
                    </tbody>
                </table>
            </div>
            
            <div class="voice-section">
                <div class="voice-title">🎤 BASS ({len(bass)})</div>
                <table>
                    <thead><tr><th>#</th><th>Jina</th><th>Simu</th><th>Anwani</th></tr></thead>
                    <tbody>
                        {''.join(f'<tr><td>{i+1}</td><td>{m["jina"]}</td><td>{m["simu"]}</td><td>{m["anwani"] or "-"}</td></tr>' for i, m in enumerate(bass))}
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>© {datetime.now().year} Kwaya Mt. Bonifasi - Sombetini, Arusha</p>
                <p>"Utukufu wa Mungu kwa sauti za malaika"</p>
            </div>
            <div class="no-print" style="text-align: center; margin-top: 20px;">
                <button onclick="window.print()" style="background: #1a2a6e; color: #FFD700; padding: 10px 20px; border: none; border-radius: 30px; cursor: pointer;">🖨️ Print / Save as PDF</button>
                <button onclick="window.close()" style="background: #6c757d; color: white; padding: 10px 20px; border: none; border-radius: 30px; cursor: pointer;">✖ Close</button>
            </div>
        </body>
        </html>
        '''
        return html

# ============ EVENT CALENDAR ============
@app.route('/event-calendar')
def event_calendar_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('event_calendar.html')

@app.route('/api/events')
def api_get_events():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        events = conn.execute('''
            SELECT id, tukio as title, tarehe as start, mahali as location, maelezo as description
            FROM ratiba 
            WHERE tarehe >= date('now', '-1 month')
            ORDER BY tarehe ASC
        ''').fetchall()
        
        rehearsals = conn.execute('''
            SELECT 'Mazoezi ya Kwaya' as title, tarehe as start, 'Sombetini' as location, 
                   'Mazoezi ya sauti' as description
            FROM mahudhurio_detailed 
            WHERE tukio LIKE '%Mazoezi%' AND tarehe >= date('now', '-1 month')
            GROUP BY tarehe
            LIMIT 20
        ''').fetchall()
        
        all_events = []
        for e in events:
            all_events.append({
                'id': e['id'],
                'title': e['title'],
                'start': e['start'],
                'location': e['location'] or 'Kanisa',
                'description': e['description'] or '',
                'type': 'event'
            })
        
        for r in rehearsals:
            all_events.append({
                'id': f"rehearsal_{r['start']}",
                'title': r['title'],
                'start': r['start'],
                'location': r['location'],
                'description': r['description'],
                'type': 'rehearsal'
            })
        
        return jsonify({'success': True, 'events': all_events})

@app.route('/api/events/add', methods=['POST'])
def api_add_event():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    title = data.get('title')
    start_date = data.get('start')
    location = data.get('location', '')
    description = data.get('description', '')
    
    if not title or not start_date:
        return jsonify({'success': False, 'message': 'Tafadhali weka jina na tarehe ya tukio'}), 400
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO ratiba (tukio, tarehe, mahali, maelezo)
            VALUES (?, ?, ?, ?)
        ''', (title, start_date, location, description))
        conn.commit()
        
        log_activity(session['user_id'], session['username'], 'ADD_EVENT', f'Added event: {title} on {start_date}')
        
        return jsonify({'success': True, 'message': 'Tukio limeongezwa kikamilifu!'})

@app.route('/api/events/<int:id>', methods=['DELETE'])
def api_delete_event(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        event = conn.execute('SELECT tukio FROM ratiba WHERE id = ?', (id,)).fetchone()
        if event:
            conn.execute('DELETE FROM ratiba WHERE id = ?', (id,))
            conn.commit()
        log_activity(session['user_id'], session['username'], 'DELETE_EVENT', f'Deleted event: {event["tukio"]}')
            return jsonify({'success': True, 'message': 'Tukio limefutwa!'})
        else:
            return jsonify({'success': False, 'message': 'Tukio halipatikani'}), 404

# ============ FINANCIAL REPORTS (P&L) ============
@app.route('/financial-reports')
def financial_reports_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('financial_reports.html')

@app.route('/api/financial/data')
def api_financial_data():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', None, type=int)
    
    with get_db() as conn:
        all_income = []
        
        try:
            mapato_records = conn.execute('''
                SELECT r.amount, r.date, s.name as source
                FROM mapato_records r
                JOIN mapato_sources s ON r.source_id = s.id
                WHERE strftime('%Y', r.date) = ?
            ''', (str(year),)).fetchall()
            for r in mapato_records:
                all_income.append({'amount': r['amount'], 'date': r['date'], 'source': r['source']})
        except:
            pass
        
        try:
            ada_payments = conn.execute('''
                SELECT kiasi_kilicholipwa as amount, tarehe_malipo as date, 'Ada za Kwaya' as source
                FROM ada_monthly
                WHERE kiasi_kilicholipwa > 0 AND strftime('%Y', tarehe_malipo) = ?
            ''', (str(year),)).fetchall()
            for a in ada_payments:
                if a['date']:
                    all_income.append({'amount': a['amount'], 'date': a['date'], 'source': a['source']})
        except:
            pass
        
        try:
            penalty_payments = conn.execute('''
                SELECT pp.amount, pp.tarehe as date, 'Penalty' as source
                FROM penalty_payments pp
                WHERE strftime('%Y', pp.tarehe) = ?
            ''', (str(year),)).fetchall()
            for p in penalty_payments:
                all_income.append({'amount': p['amount'], 'date': p['date'], 'source': p['source']})
        except:
            pass
        
        try:
            old_mapato = conn.execute('''
                SELECT kiasi as amount, tarehe as date, chanzo as source
                FROM mapato
                WHERE strftime('%Y', tarehe) = ?
            ''', (str(year),)).fetchall()
            for o in old_mapato:
                all_income.append({'amount': o['amount'], 'date': o['date'], 'source': o['source']})
        except:
            pass
        
        total_income = sum(i['amount'] for i in all_income)
        
        income_by_source = {}
        for i in all_income:
            source = i['source']
            if source not in income_by_source:
                income_by_source[source] = 0
            income_by_source[source] += i['amount']
        
        monthly_income = {}
        for i in all_income:
            if i['date']:
                month_key = i['date'][:7]
                if month_key:
                    if month_key not in monthly_income:
                        monthly_income[month_key] = 0
                    monthly_income[month_key] += i['amount']
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL,
                expense_date DATE DEFAULT CURRENT_DATE,
                receipt_no TEXT,
                created_by INTEGER,
                created_at DATE DEFAULT CURRENT_DATE
            )
        ''')
        
        expenses = conn.execute('''
            SELECT id, category, description, amount, expense_date, receipt_no
            FROM expenses
            WHERE strftime('%Y', expense_date) = ?
            ORDER BY expense_date DESC
        ''', (str(year),)).fetchall()
        
        total_expenses = sum(e['amount'] for e in expenses)
        
        expenses_by_category = {}
        for e in expenses:
            cat = e['category']
            if cat not in expenses_by_category:
                expenses_by_category[cat] = 0
            expenses_by_category[cat] += e['amount']
        
        monthly_expenses = {}
        for e in expenses:
            month_key = e['expense_date'][:7] if e['expense_date'] else ''
            if month_key:
                if month_key not in monthly_expenses:
                    monthly_expenses[month_key] = 0
                monthly_expenses[month_key] += e['amount']
        
        net_profit = total_income - total_expenses
        profit_margin = (net_profit / total_income * 100) if total_income > 0 else 0
        
        prev_year = year - 1
        prev_income = 0
        try:
            prev_mapato = conn.execute('''
                SELECT COALESCE(SUM(amount), 0) as total
                FROM mapato_records
                WHERE strftime('%Y', date) = ?
            ''', (str(prev_year),)).fetchone()
            prev_income = prev_mapato['total'] if prev_mapato else 0
        except:
            pass
        
        expense_categories = [
            'Vifaa vya Muziki', 'Mavazi (Kanzu, T-Shirts)', 'Usafiri na Mafuta',
            'Matengenezo', 'Chakula na Vinywaji', 'Kodi na Bili', 'Matangazo',
            'CD/DVD Printing', 'Mafunzo na Semina', 'Nyingine'
        ]
        
        all_months = sorted(list(set(list(monthly_income.keys()) + list(monthly_expenses.keys()))))
        
        return jsonify({
            'success': True,
            'summary': {
                'total_income': total_income,
                'total_expenses': total_expenses,
                'net_profit': net_profit,
                'profit_margin': round(profit_margin, 1),
                'prev_year_income': prev_income,
                'income_change': total_income - prev_income,
                'year': year
            },
            'income_by_source': income_by_source,
            'expenses_by_category': expenses_by_category,
            'monthly_income': monthly_income,
            'monthly_expenses': monthly_expenses,
            'expenses': [dict(e) for e in expenses],
            'expense_categories': expense_categories,
            'all_months': all_months
        })

@app.route('/api/expenses/add', methods=['POST'])
def api_add_expense():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    category = data.get('category')
    description = data.get('description', '')
    amount = data.get('amount')
    expense_date = data.get('expense_date', datetime.now().strftime('%Y-%m-%d'))
    receipt_no = data.get('receipt_no', '')
    
    if not category or not amount or amount <= 0:
        return jsonify({'success': False, 'message': 'Tafadhali weka aina na kiasi cha gharama'}), 400
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO expenses (category, description, amount, expense_date, receipt_no, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (category, description, amount, expense_date, receipt_no, session['user_id']))
        conn.commit()
        
        log_activity(session['user_id'], session['username'], 'ADD_EXPENSE', 
                    f'Added expense: {category} - TSh {amount:,.0f}')
        
        return jsonify({'success': True, 'message': 'Gharama imeongezwa kikamilifu!'})

@app.route('/api/expenses/<int:id>', methods=['DELETE'])
def api_delete_expense(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        expense = conn.execute('SELECT category, amount FROM expenses WHERE id = ?', (id,)).fetchone()
        if expense:
            conn.execute('DELETE FROM expenses WHERE id = ?', (id,))
            conn.commit()
        log_activity(session['user_id'], session['username'], 'DELETE_EXPENSE', 
                        f'Deleted expense: {expense["category"]} - TSh {expense["amount"]:,.0f}')
            return jsonify({'success': True, 'message': 'Gharama imefutwa!'})
        else:
            return jsonify({'success': False, 'message': 'Gharama haipatikani'}), 404

# ============ MEDIA / ALBAMU ROUTES (SAFI) ============
import os
from werkzeug.utils import secure_filename

ALLOWED_AUDIO = {'mp3', 'wav', 'ogg', 'm4a', 'webm'}
ALLOWED_VIDEO = {'mp4', 'webm', 'avi', 'mov', 'mkv', 'mpg'}

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'media')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename, file_type):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if file_type == 'audio':
        return ext in ALLOWED_AUDIO
    elif file_type == 'video':
        return ext in ALLOWED_VIDEO
    return False

@app.route('/albamu')
def albamu_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('albamu.html')

@app.route('/api/albamu')
def api_get_albamu():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        try:
            albums = conn.execute('''
                SELECT a.*, COUNT(m.id) as track_count
                FROM albamu_new a
                LEFT JOIN media_files m ON a.id = m.albamu_id
                GROUP BY a.id
                ORDER BY a.mwaka DESC, a.id DESC
            ''').fetchall()
        except:
            albums = conn.execute('''
                SELECT a.*, 0 as track_count
                FROM albamu a
                ORDER BY a.mwaka DESC, a.id DESC
            ''').fetchall()
        
        result = []
        for a in albums:
            result.append({
                'id': a['id'],
                'jina_albamu': a['jina_albamu'],
                'aina': a['aina'] if 'aina' in a.keys() else 'audio',
                'mwaka': a['mwaka'],
                'maelezo': a['maelezo'] if 'maelezo' in a.keys() else '',
                'track_count': a['track_count']
            })
        return jsonify({'success': True, 'albums': result})

@app.route('/api/albamu/<int:id>')
def api_get_album_details(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        album = conn.execute('SELECT * FROM albamu_new WHERE id = ?', (id,)).fetchone()
        if not album:
            album = conn.execute('SELECT *, "audio" as aina FROM albamu WHERE id = ?', (id,)).fetchone()
        
        if not album:
            return jsonify({'success': False, 'message': 'Album not found'}), 404
        
        tracks = conn.execute('SELECT * FROM media_files WHERE albamu_id = ? ORDER BY id', (id,)).fetchall()
        
        return jsonify({
            'success': True,
            'album': dict(album),
            'tracks': [dict(t) for t in tracks]
        })

@app.route('/api/albamu/add', methods=['POST'])
def api_add_album():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.json
    jina_albamu = data.get('jina_albamu')
    aina = data.get('aina', 'audio')
    mwaka = data.get('mwaka', datetime.now().year)
    maelezo = data.get('maelezo', '')
    
    if not jina_albamu:
        return jsonify({'success': False, 'message': 'Jina la albamu linahitajika'}), 400
    
    with get_db() as conn:
        try:
            cursor = conn.execute('''
                INSERT INTO albamu_new (jina_albamu, aina, mwaka, maelezo)
                VALUES (?, ?, ?, ?)
            ''', (jina_albamu, aina, mwaka, maelezo))
            album_id = cursor.lastrowid
        except:
            cursor = conn.execute('''
                INSERT INTO albamu (jina_albamu, mwaka, maelezo)
                VALUES (?, ?, ?)
            ''', (jina_albamu, mwaka, maelezo))
            album_id = cursor.lastrowid
            try:
                conn.execute("ALTER TABLE albamu ADD COLUMN aina TEXT DEFAULT 'audio'")
            except:
                pass
        
        conn.commit()
        log_activity(session['user_id'], session['username'], 'ADD_ALBUM', f'Added album: {jina_albamu}')
        
        return jsonify({'success': True, 'message': 'Albamu imeongezwa!', 'album_id': album_id})

@app.route('/api/albums/<int:id>', methods=['DELETE'])
def api_delete_album(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        album = conn.execute('SELECT jina_albamu FROM albamu_new WHERE id = ?', (id,)).fetchone()
        if not album:
            album = conn.execute('SELECT jina_albamu FROM albamu WHERE id = ?', (id,)).fetchone()
        
        if album:
            files = conn.execute('SELECT file_path FROM media_files WHERE albamu_id = ?', (id,)).fetchall()
            for f in files:
                file_path = os.path.join(UPLOAD_FOLDER, f['file_path'])
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            conn.execute('DELETE FROM media_files WHERE albamu_id = ?', (id,))
            conn.execute('DELETE FROM albamu_new WHERE id = ?', (id,))
            conn.execute('DELETE FROM albamu WHERE id = ?', (id,))
            conn.commit()
            return jsonify({'success': True, 'message': 'Albamu imefutwa!'})
        else:
            return jsonify({'success': False, 'message': 'Albamu haipatikani'}), 404

@app.route('/api/media/upload', methods=['POST'])
def api_upload_media():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    album_id = request.form.get('album_id')
    wimbo_jina = request.form.get('wimbo_jina')
    mtunzi = request.form.get('mtunzi', '')
    file_type = request.form.get('file_type')
    
    if not album_id:
        return jsonify({'success': False, 'message': 'Album ID haijatumwa!'}), 400
    
    if not wimbo_jina:
        return jsonify({'success': False, 'message': 'Jina la wimbo linahitajika!'}), 400
    
    if 'media_file' not in request.files:
        return jsonify({'success': False, 'message': 'Hakuna faili iliyochaguliwa!'}), 400
    
    file = request.files['media_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Hakuna faili iliyochaguliwa!'}), 400
    
    with get_db() as conn:
        album = conn.execute('SELECT id, jina_albamu FROM albamu_new WHERE id = ?', (album_id,)).fetchone()
        if not album:
            album = conn.execute('SELECT id, jina_albamu FROM albamu WHERE id = ?', (album_id,)).fetchone()
        
        if not album:
            return jsonify({'success': False, 'message': f'Albamu ID {album_id} haipatikani!'}), 404
    
    filename = secure_filename(file.filename)
    name_parts = filename.rsplit('.', 1)
    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name_parts[0]}.{name_parts[1]}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(file_path)
    
    file_size = os.path.getsize(file_path)
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO media_files (albamu_id, wimbo_jina, mtunzi, file_path, file_type, size)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (album_id, wimbo_jina, mtunzi, unique_filename, file.content_type, file_size))
        conn.commit()
        
        log_activity(session['user_id'], session['username'], 'UPLOAD_MEDIA', 
                    f'Uploaded: {wimbo_jina} to album: {album["jina_albamu"]}')
        
        return jsonify({'success': True, 'message': 'Faili imepakiwa kikamilifu!', 'filename': unique_filename})

@app.route('/api/media/<int:id>', methods=['DELETE'])
def api_delete_media(id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        media = conn.execute('SELECT file_path, wimbo_jina FROM media_files WHERE id = ?', (id,)).fetchone()
        if media:
            file_path = os.path.join(UPLOAD_FOLDER, media['file_path'])
            if os.path.exists(file_path):
                os.remove(file_path)
            
            conn.execute('DELETE FROM media_files WHERE id = ?', (id,))
            conn.commit()
            return jsonify({'success': True, 'message': 'Faili imefutwa!'})
        else:
            return jsonify({'success': False, 'message': 'Faili haipatikani'}), 404

# ============ MEMBER ID CARDS ============
@app.route('/member-id-card')
def member_id_card_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('member_id_card.html')

@app.route('/api/member-id-card/<int:member_id>')
def api_get_member_id_card(member_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        member = conn.execute('''
            SELECT id, jina, sauti, simu, anwani, tarehe_jiunga, profile_picture 
            FROM wanakwaya 
            WHERE id = ?
        ''', (member_id,)).fetchone()
        
        if not member:
            return jsonify({'success': False, 'message': 'Mwanakwaya hapatikani'}), 404
        
        voice = member['sauti']
        voice_count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ? AND status = "active"', (voice, member_id)).fetchone()
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        member_number = f"{prefix}{voice_count['c']:03d}"
        
        profile_picture = member['profile_picture'] if member['profile_picture'] else None
        
        return jsonify({
            'success': True,
            'member': {
                'id': member['id'],
                'jina': member['jina'],
                'sauti': member['sauti'],
                'simu': member['simu'],
                'anwani': member['anwani'],
                'tarehe_jiunga': member['tarehe_jiunga'],
                'profile_picture': profile_picture
            },
            'member_number': member_number,
            'qr_data': f"KWAYA-{member_number}-{member['jina']}",
            'generated_date': datetime.now().strftime('%Y-%m-%d')
        })

# ============ CHOIR PRACTICE SCHEDULE ============
@app.route('/practice-schedule')
def practice_schedule_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('practice_schedule.html')

@app.route('/api/practice-schedule')
def api_get_practice_schedule():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        practices = conn.execute('''
            SELECT * FROM ratiba 
            WHERE tukio LIKE '%Mazoezi%' OR tukio LIKE '%Practice%' OR tukio LIKE '%Mazoezi ya Kwaya%'
            ORDER BY tarehe ASC LIMIT 30
        ''').fetchall()
        
        voice_practices = {}
        for voice in ['Soprano', 'Alto', 'Tenor', 'Bass']:
            voice_practices[voice] = []
        
        general_practices = [dict(p) for p in practices if 'Soprano' not in p['tukio'] and 'Alto' not in p['tukio'] and 'Tenor' not in p['tukio'] and 'Bass' not in p['tukio']]
        
        return jsonify({
            'success': True,
            'general_practices': general_practices,
            'voice_practices': voice_practices
        })

# ============ ATTENDANCE CERTIFICATE ============
@app.route('/attendance-certificate')
def attendance_certificate_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('attendance_certificate.html')

@app.route('/api/attendance-certificate/<int:member_id>')
def api_get_attendance_certificate(member_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    year = request.args.get('year', datetime.now().year, type=int)
    
    with get_db() as conn:
        member = conn.execute('SELECT id, jina, sauti, simu, anwani, tarehe_jiunga, profile_picture FROM wanakwaya WHERE id = ?', (member_id,)).fetchone()
        if not member:
            return jsonify({'success': False, 'message': 'Mwanakwaya hapatikani'}), 404
        
        voice = member['sauti']
        voice_count = conn.execute('SELECT COUNT(*) as c FROM wanakwaya WHERE sauti = ? AND id <= ?', (voice, member_id)).fetchone()
        prefix = {'Soprano': 'S', 'Alto': 'A', 'Tenor': 'T', 'Bass': 'B'}.get(voice, 'X')
        member_number = f"{prefix}{voice_count['c']:03d}"
        
        attendance = conn.execute('''
            SELECT 
                COUNT(*) as total_events,
                SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) as present_count
            FROM mahudhurio_detailed 
            WHERE mwanakwaya_id = ? AND strftime('%Y', tarehe) = ?
        ''', (member_id, str(year))).fetchone()
        
        total_events = attendance['total_events'] if attendance['total_events'] else 1
        present_count = attendance['present_count'] if attendance['present_count'] else 0
        percentage = round((present_count / total_events) * 100) if total_events > 0 else 0
        
        penalty = conn.execute('''
            SELECT COALESCE(SUM(remaining_amount), 0) as total
            FROM mahudhurio_penalties 
            WHERE member_id = ? AND imelipwa = 0
        ''', (member_id,)).fetchone()
        
        logo = conn.execute("SELECT value FROM system_settings WHERE key = 'kwaya_logo'").fetchone()
        logo_type = conn.execute("SELECT value FROM system_settings WHERE key = 'kwaya_logo_type'").fetchone()
        
        voice_colors = {
            'Soprano': {'bg': 'rgba(233, 30, 99, 0.15)', 'border': '#e91e63', 'text': '#e91e63'},
            'Alto': {'bg': 'rgba(156, 39, 176, 0.15)', 'border': '#9c27b0', 'text': '#9c27b0'},
            'Tenor': {'bg': 'rgba(33, 150, 243, 0.15)', 'border': '#2196f3', 'text': '#2196f3'},
            'Bass': {'bg': 'rgba(76, 175, 80, 0.15)', 'border': '#4caf50', 'text': '#4caf50'}
        }
        color = voice_colors.get(voice, {'bg': 'rgba(255, 215, 0, 0.1)', 'border': '#FFD700', 'text': '#1a2a6e'})
        
        return jsonify({
            'success': True,
            'member': {
                'id': member['id'],
                'jina': member['jina'],
                'sauti': member['sauti'],
                'simu': member['simu'],
                'anwani': member['anwani'],
                'tarehe_jiunga': member['tarehe_jiunga'],
                'profile_picture': member['profile_picture'],
                'member_number': member_number
            },
            'attendance': {
                'total_events': total_events,
                'present_count': present_count,
                'percentage': percentage,
                'year': year
            },
            'penalty': penalty['total'] if penalty else 0,
            'generated_date': datetime.now().strftime('%Y-%m-%d'),
            'logo': logo['value'] if logo else None,
            'logo_type': logo_type['value'] if logo_type else None,
            'voice_color': color
        })

# ============ UPLOAD MEMBER PHOTO ============
@app.route('/api/member/upload-photo/<int:member_id>', methods=['POST'])
def api_upload_member_photo(member_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'Hakuna picha iliyochaguliwa'}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Hakuna picha iliyochaguliwa'}), 400
    
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 2 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'Picha ni kubwa sana! Chagua picha chini ya 2MB'}), 400
    
    import base64
    file_data = file.read()
    base64_data = base64.b64encode(file_data).decode('utf-8')
    mime_type = file.content_type
    photo_data = f"data:{mime_type};base64,{base64_data}"
    
    with get_db() as conn:
        conn.execute('UPDATE wanakwaya SET profile_picture = ? WHERE id = ?', (photo_data, member_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Picha imehifadhiwa!', 'photo': photo_data})

# ============ UPLOAD KWAYA LOGO ============
@app.route('/api/kwaya/upload-logo', methods=['POST'])
def api_upload_kwaya_logo():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if 'logo' not in request.files:
        return jsonify({'success': False, 'message': 'Hakuna logo iliyochaguliwa'}), 400
    
    file = request.files['logo']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Hakuna logo iliyochaguliwa'}), 400
    
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 1 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'Logo ni kubwa sana! Chagua picha chini ya 1MB'}), 400
    
    import base64
    file_data = file.read()
    base64_data = base64.b64encode(file_data).decode('utf-8')
    mime_type = file.content_type
    logo_data = f"data:{mime_type};base64,{base64_data}"
    
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('kwaya_logo', ?)", (logo_data,))
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('kwaya_logo_type', ?)", (mime_type,))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Logo imehifadhiwa!', 'logo': logo_data})

@app.route('/api/kwaya/get-logo')
def api_get_kwaya_logo():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        logo = conn.execute("SELECT value FROM system_settings WHERE key = 'kwaya_logo'").fetchone()
        return jsonify({'success': True, 'logo': logo['value'] if logo else None})

@app.route('/api/live/recordings', methods=['GET'])
def api_get_live_recordings():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    with get_db() as conn:
        try:
            conn.execute('DROP TABLE IF EXISTS live_stream_recordings')
            conn.execute('''
                CREATE TABLE live_stream_recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id INTEGER,
                    title TEXT NOT NULL,
                    youtube_url TEXT,
                    recording_date DATE,
                    duration INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                INSERT INTO live_stream_recordings (title, youtube_url, recording_date)
                VALUES (?, ?, date('now'))
            ''', ('Misa ya Jumapili - Kwaya Mt. Bonifasi', 'https://www.youtube.com/@kmb_sombetini'))
            conn.commit()
        except Exception as e:
            print(f"Table creation error: {e}")
        
        recordings = conn.execute('''
            SELECT id, title, youtube_url, recording_date 
            FROM live_stream_recordings 
            ORDER BY recording_date DESC
            LIMIT 5
        ''').fetchall()
        
        return jsonify({'success': True, 'recordings': [dict(r) for r in recordings]})

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("🚀 MFUMO WA KWAYA MT. BONIFASI")
    print("📍 http://127.0.0.1:5000")
    print("👤 admin | 🔑 admin123")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)
