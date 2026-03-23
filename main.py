from flask import Flask, render_template, redirect, request, url_for, session, make_response, jsonify, flash
from markupsafe import escape
from flask_session import Session
from datetime import datetime, timedelta, date
import sqlite3, os, secrets, uuid, re, csv, io
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
from base_ai.psycho import PsychoAnalyzer
from flask_wtf import CSRFProtect
from google.oauth2 import id_token
from google.auth.transport import requests
from cryptography.fernet import Fernet

load_dotenv()

conn = sqlite3.connect('iv_moha_2FK.db', check_same_thread=False)
conn.row_factory = sqlite3.Row
db = conn.cursor()

db.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT,
    state TEXT,
    sec_key TEXT
)''')

db.execute('''CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anxiety INTEGER,
    stress INTEGER,
    depression INTEGER,
    trigger_words TEXT,
    danger TEXT,
    advice TEXT,
    inneed INTEGER,
    recommend TEXT,
    tasks TEXT,
    date TEXT,
    user_id INTEGER,
    day TEXT,
    usr_req TEXT,
    cht_rr_tk TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)''')

conn.commit()

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['SECRET_KEY'] = str(uuid.uuid4())
Session(app)
csrf = CSRFProtect(app)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
FERNET_KEY = os.getenv("FERNET_KEY")
cipher = Fernet(FERNET_KEY.encode())

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False
)


@app.route('/')
def main():
    return render_template('home.html')

@app.route('/<x>/chat', methods=['GET', 'POST'])
def chat(x):
    id = session.get('user_id')
    if id:
        if request.method == 'POST':
            return redirect(url_for('dashboard'))
        
        db.execute('SELECT full_name, email, state, sec_key FROM users WHERE id = ?', (id,))
        row = db.fetchone()
        has_api_key = bool(row[3])

        if not has_api_key:
            return redirect('/setup-api-key')

        if x == 'n':
            return render_template('chat.html', name=row[0], email=row[1], state=row[2])
        elif x == 'p':
            cht_rr_tk = request.args.get('chpaV1')
            db.execute('SELECT * FROM history WHERE cht_rr_tk = ?', (cht_rr_tk,))
            data = db.fetchone()
            if id == data['user_id']:
                return render_template('chat.html', name=row[0], email=row[1], state=row[2], data=data)
            else:
                return render_template('chat.html', name=row[0], email=row[1], state=row[2], error=f"Unable to load conversation {cht_rr_tk}")
    else:
        return redirect('/login')

@app.route('/dashboard')
@app.route('/settings')
def settings():
    id = session.get('user_id')
    if id:
        db.execute('SELECT full_name, email, state FROM users WHERE id = ?', (id,))
        row = db.fetchone()
        return render_template('sittings.html', name=row[0], email=row[1], state=row[2])
    else:
        return redirect('/login')

@app.route('/edit', methods=['GET', 'POST'])
def edit():
    id = session.get('user_id')
    if id:
        if request.method == 'POST':
            name = request.form.get('name').strip('''
            "<>!'
            ''')
            email = request.form.get('email').strip('''
            "<>!'
            ''')
            if not name or len(name) < 3:
                flash('Name must be at least 3 characters', 'danger')
                return redirect(url_for('settings'))
            if not re.match(r'^[A-Za-z\s]+$', name):
                flash('Name must contain letters only', 'danger')
                return redirect(url_for('settings'))
            email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(email_regex, email):
                flash('Invalid email format', 'danger')
                return redirect(url_for('settings'))
            db.execute('UPDATE users SET full_name = ? , email = ? WHERE id = ?', (name, email, id))
            conn.commit()
            flash('Profile updated successfully', 'success')
            return redirect(url_for('settings'))
    else:
        return redirect('/login')

@app.route('/history')
def history():
    id = session.get('user_id')
    if id:
        name = db.execute('SELECT full_name FROM users WHERE id = ?', (id,)).fetchone()
        sessions = db.execute('SELECT * FROM history WHERE user_id = ? ORDER BY id DESC', (id,)).fetchall()
        return render_template('history.html', name=name[0], sessions=sessions)
    else:
        return redirect('/logout')

@app.route('/setup-api-key', methods=['GET', 'POST'])
def setup_api_key():
    id = session.get('user_id')
    if not id:
        return redirect('/login')
    if request.method == 'GET':
        return render_template('api_setup.html')
    else:
        api_key = request.form.get('api_key', '').strip()
        if not api_key:
            flash('الرجاء إدخال مفتاح API', 'error')
            return redirect('/setup-api-key')
        if len(api_key) < 10:
            flash('مفتاح API غير صالح', 'error')
            return redirect('/setup-api-key')
        encrypted_key = cipher.encrypt(api_key.encode()).decode()
        db.execute('UPDATE users SET sec_key = ? WHERE id = ?', (encrypted_key, id))
        conn.commit()
        flash('تم حفظ مفتاح API بنجاح!', 'success')
        return redirect('/n/chat')

@app.route('/analyze', methods=['POST','GET'])
def analyze():
    id = session.get('user_id')
    if not id:
        return redirect('/login')
    sec_key = db.execute('SELECT sec_key FROM users WHERE id = ?', (id,)).fetchone()
    if not sec_key or not sec_key[0]:
        return jsonify({'error': 'no_api_key', 'redirect': '/setup-api-key'}), 403
    decrypted_key = cipher.decrypt(sec_key[0].encode()).decode()
    analyzer = PsychoAnalyzer(api_key=decrypted_key)
    data = request.json
    user_text = data.get('text')
    sleep_h = data.get('sleep_hours', 7)
    energy_lvl = data.get('energy_level', 'Medium')
    appetite = data.get('appetite', 'Normal')
    symptoms = data.get('symptoms', '')
    try:
        if user_text and sleep_h and energy_lvl and appetite:
            result = analyzer.analyze(
                f"""
        Clinical Data:

        - Sleep hours: {sleep_h}

        - Energy level: {energy_lvl} (out of 3)

        - Appetite: {appetite}

        - Physical symptoms they complain of: {', '.join(symptoms) if symptoms else 'None'}

        Diary Text:"{user_text}"
                """
            )
            user_text = escape(user_text)
            ac_tsk = ''
            now_date = date.today()
            now = datetime.now()
            day = now.strftime("%A")
            tr_word = ''
            id = session.get('user_id')
            for i in result.actionable_tasks:
                ac_tsk = i+'!%b^&!'+ac_tsk
            for i in result.trigger_words:
                tr_word = i+'!%r^&!'+tr_word
            db.execute("""INSERT INTO history(anxiety, stress, depression, trigger_words, danger, advice, inneed, recommend, tasks, date, user_id, day, usr_req, cht_rr_tk)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                        (result.anxiety,result.stress,result.depression,tr_word,result.risk_level,result.advice,result.need_doctor,
                        result.doctor_recommendation,ac_tsk,now_date, id, day, user_text, secrets.token_urlsafe(36)))
            conn.commit()
            return jsonify(result.model_dump())
        return jsonify({'error':'Fill All Data'}), 400
    except Exception as e:
        return jsonify({'error':str(e)}),400



@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'GET':
        return render_template('register.html',cli_id=GOOGLE_CLIENT_ID)

    try:
        name = request.form.get('name').strip()
        email = request.form.get('email').strip()
        password = request.form.get('password')

        if not name or len(name) < 3:
            flash('Name must be at least 3 characters', 'error')
            return render_template('register.html')
        if not re.match(r'^[A-Za-z\s]+$', name):
            flash('Name must contain letters only', 'error')
            return render_template('register.html')

        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, email):
            flash('Invalid email format', 'error')
            return render_template('register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('register.html')
        if not re.search(r'[A-Z]', password):
            flash('Password must contain at least one uppercase letter', 'error')
            return render_template('register.html')
        if not re.search(r'[0-9]', password):
            flash('Password must contain at least one number', 'error')
            return render_template('register.html')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            flash('Password must contain at least one symbol', 'error')
            return render_template('register.html')

        db.execute('SELECT email FROM users WHERE email = ?', (email,))
        if db.fetchone():
            flash('This email already exists', 'error')
            return render_template('register.html')

        db.execute('SELECT full_name FROM users WHERE full_name = ?', (name,))
        if db.fetchone():
            flash('This name already exists', 'error')
            return render_template('register.html')
    
        hashed = generate_password_hash(password)
        db.execute(
            'INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)',
            (name, email, hashed)
        )
        conn.commit()

        flash('Account Created Successfully', 'success')
        return redirect('/login')

    except Exception as e:
        conn.rollback()
        return f"Database Error: {e}"

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'GET':
        user_id = request.cookies.get("user_id")
        if user_id:
            session["user_id"] = user_id
            return redirect('/dashboard')
        return render_template('login.html', cli_id=GOOGLE_CLIENT_ID)
    else:
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember')
        db.execute('SELECT id, password FROM users WHERE email = ?', (email,))
        user = db.fetchone()
        if user:
            if user[1] and check_password_hash(user[1], password):
                resp = make_response(redirect("/dashboard"))
                if remember == "on":
                    expire_date = datetime.now() + timedelta(days=30)
                    resp.set_cookie("user_id", str(user[0]), expires=expire_date)
                    session["user_id"] = user[0]
                else:
                    session["user_id"] = user[0]
                return resp
            elif user[0] and not user[1]:
                flash('Please Log-in With Google Instead', 'warning')
                return redirect('/login')
            else:
                flash('Passwodrd or Email is incorrect', 'warning')
                return redirect('/login') 
        else:
            flash('Can\'t Find This Email', 'warning')
            return redirect('/login') 

@app.route('/test')
def test():
    return render_template('test.html',client_id=GOOGLE_CLIENT_ID)
        
@app.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect('/'))
    resp.delete_cookie("user_id")
    return resp

@app.route('/delete-ac', methods=['POST'])
def delete_account():
    id = session.get('user_id')
    if id:
        try:

            db.execute('DELETE FROM history WHERE user_id = ?', (id,))

            db.execute('DELETE FROM users WHERE id = ?', (id,))
            conn.commit()
            

            session.clear()
            resp = make_response(redirect('/'))
            resp.delete_cookie("user_id")
            flash('Account deleted', 'info')
            return resp
        except Exception as e:
            conn.rollback()
            flash(f'Error deleting account: {str(e)}', 'danger')
            return redirect('/settings')
    else:
        return redirect('/login')



@app.route('/google-register', methods=['POST'])
@app.route('/google-login', methods=['POST'])
@csrf.exempt
def google_register_login():
    token = request.json.get('credential')
    
    try:
        idinfo = id_token.verify_oauth2_token(
                token,
                requests.Request(), 
                GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=10 
            )
        user_email = idinfo['email']
        user_name = idinfo['name']


        db.execute('SELECT id FROM users WHERE email = ?',(user_email,))
        res = db.fetchone()
        resp = make_response(redirect("/dashboard"))
        if not re.match(r'^[A-Za-z\s]+$', user_name):
            user_name_n = ''
            for i in user_name:
                if i.isalpha() or i == ' ':
                    user_name_n += i
            user_name = user_name_n

        if len(user_name) < 3:
            user_name = user_name + ' PSY'

        if not res:

            db.execute(
                'INSERT INTO users (full_name, email) VALUES (?, ?)',
                (user_name, user_email)
            )
            conn.commit()
            new_user_id = db.lastrowid
            
            expire_date = datetime.now() + timedelta(days=30)
            resp.set_cookie("user_id", str(new_user_id), expires=expire_date)
            session["user_id"] = new_user_id
            
            flash('Account Created Successfully', 'success')
            return jsonify({
                'success': True, 
                'redirect_url': url_for('login'),
                'message': 'Account Created Successfully'
            })
        else:
            expire_date = datetime.now() + timedelta(days=30)
            resp.set_cookie("user_id", str(res['id']), expires=expire_date)
            session["user_id"] = res['id']
            flash('Account Log-in Successfully', 'success')
            return jsonify({
                'success': True, 
                'redirect_url': '/dashboard',
                'message': 'Logged in successfully'
            })

    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid token: {str(e)}'}), 400




@app.route('/download_history')
def download_history():
    id = session.get('user_id')
    if not id:
        return redirect('/login')
    

    sessions = db.execute('SELECT * FROM history WHERE user_id = ? ORDER BY id DESC', (id,)).fetchall()
    

    output = io.StringIO()
    writer = csv.writer(output)
    

    writer.writerow(['Date', 'Day', 'Anxiety', 'Stress', 'Depression', 'Risk Level', 'User Request', 'Advice'])
    

    for s in sessions:
        writer.writerow([
            s['date'], 
            s['day'], 
            s['anxiety'], 
            s['stress'], 
            s['depression'], 
            s['danger'], 
            s['usr_req'], 
            s['advice']
        ])
        
    output.seek(0)
    
    resp = make_response(output.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=history.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        if session.get('admin_logged_in'):
            return redirect('/admin-dashboard')
        return render_template('admin_login.html')
    else:
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Hardcoded Admin Credentials
        if email == 'admin@psychoai.com' and password == 'admin':
            session['admin_logged_in'] = True
            return redirect('/admin-dashboard')
        else:
            flash('بيانات تسجيل الدخول غير صحيحة', 'error')
            return redirect('/admin-login')

@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    db.execute('SELECT COUNT(id) FROM users')
    users_count = db.fetchone()[0]
    db.execute('SELECT COUNT(id) FROM history')
    history_count = db.fetchone()[0]
    db.execute('SELECT full_name, email FROM users LIMIT 3')
    users = db.fetchall()
    today_date = date.today().strftime("%Y-%m-%d")
    
    return render_template('admin_dashboard.html', today_date=today_date, users_count=users_count, history_count=history_count, users=users)

@app.route('/admin-users')
def admin_users():
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    
    query = request.args.get('q')
    if query:
        search_term = f"%{query}%"
        db.execute('SELECT * FROM users WHERE full_name LIKE ? OR email LIKE ? ORDER BY id DESC', (search_term, search_term))
    else:
        db.execute('SELECT * FROM users ORDER BY id DESC')
        
    users = db.fetchall()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin-delete-user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin-login')
    
    try:
        # Delete user's history first (foreign key constraint usually handles this but good to be explicit)
        db.execute('DELETE FROM history WHERE user_id = ?', (user_id,))
        # Delete user
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        flash('User deleted successfully', 'success')
        session.clear()
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        
    return redirect('/admin-users')

@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin-login')

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

if __name__ == '__main__':
    app.run(debug=True)