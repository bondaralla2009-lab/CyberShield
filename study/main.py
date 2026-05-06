from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'cybershield_secret_key_2024'


def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  status TEXT DEFAULT 'Новичок',
                  checks_count INTEGER DEFAULT 0,
                  registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS phone_numbers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT UNIQUE,
                  phone_raw TEXT UNIQUE,
                  source TEXT DEFAULT 'database',
                  reports_count INTEGER DEFAULT 0,
                  first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  phone TEXT,
                  reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')

    conn.commit()
    conn.close()


init_db()


def format_phone_display(phone):
    if phone and len(phone) == 10:
        return f"+7 ({phone[:3]}) {phone[3:6]}-{phone[6:8]}-{phone[8:]}"
    return phone


def normalize_phone(phone):
    clean = re.sub(r'[^\d]', '', phone)
    if len(clean) == 11 and clean[0] in ('7', '8'):
        clean = clean[1:]
    return clean if len(clean) == 10 else None


def update_rankings():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''SELECT phone, reports_count FROM phone_numbers 
                 WHERE reports_count > 0 ORDER BY reports_count DESC''')
    ranked = c.fetchall()

    for idx, (phone, _) in enumerate(ranked, 1):
        c.execute("UPDATE phone_numbers SET reports_count = ? WHERE phone = ?", (idx, phone))

    conn.commit()
    conn.close()


@app.route('/')
def home():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''SELECT phone, reports_count, source, 
                 strftime('%d.%m.%Y', last_seen) as last_seen 
                 FROM phone_numbers 
                 ORDER BY reports_count DESC, last_seen DESC 
                 LIMIT 10''')
    phones = c.fetchall()

    conn.close()
    return render_template('index.html', phones=phones, now=datetime.now, format_phone=format_phone_display)


@app.route('/check', methods=['GET', 'POST'])
def check_phone():
    result = None
    message = None
    searched_phone = None

    if request.method == 'POST':
        raw_phone = request.form.get('phone')
        searched_phone = raw_phone

        clean_phone = normalize_phone(raw_phone)

        if clean_phone:
            conn = sqlite3.connect('database.db')
            c = conn.cursor()

            # ищем по красивому номеру
            c.execute('''SELECT phone, reports_count, source FROM phone_numbers 
                         WHERE phone_raw = ?''', (clean_phone,))
            result = c.fetchone()

            # жалобы от пользователя
            if session.get('user_id') and request.form.get('report') == 'yes':
                user_id = session['user_id']

                c.execute('''SELECT id FROM user_reports 
                             WHERE user_id = ? AND phone = ?''', (user_id, clean_phone))
                already_reported = c.fetchone()

                if already_reported:
                    message = "⚠️ Вы уже жаловались на этот номер ранее"
                else:
                    c.execute('''INSERT INTO user_reports (user_id, phone) 
                                 VALUES (?, ?)''', (user_id, clean_phone))

                    if result:
                        # обновляем рейтинг
                        new_count = result[1] + 1
                        c.execute('''UPDATE phone_numbers 
                                     SET reports_count = ?, 
                                         last_seen = CURRENT_TIMESTAMP 
                                     WHERE phone_raw = ?''', (new_count, clean_phone))
                        message = f"✅ Жалоба добавлена! Рейтинг увеличен до {new_count}"

                        # обнова реза
                        c.execute('''SELECT phone, reports_count, source FROM phone_numbers 
                                     WHERE phone_raw = ?''', (clean_phone,))
                        result = c.fetchone()
                    else:
                        # добав новый номера в бд
                        formatted_phone = format_phone_display(clean_phone)
                        c.execute('''INSERT INTO phone_numbers (phone, phone_raw, source, reports_count) 
                                     VALUES (?, ?, ?, ?)''', (formatted_phone, clean_phone, 'user', 1))
                        message = "✅ Новый номер добавлен в базу!"
                        # получаем новый номер
                        c.execute('''SELECT phone, reports_count, source FROM phone_numbers 
                                     WHERE phone_raw = ?''', (clean_phone,))
                        result = c.fetchone()

                    update_rankings()

            conn.commit()
            conn.close()

            if not result and not message:
                message = "ℹ️ Номер не найден в базе данных"
        else:
            message = "❌ Неверный формат номера"

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT phone, reports_count, source 
                 FROM phone_numbers 
                 ORDER BY reports_count DESC, last_seen DESC 
                 LIMIT 10''')
    top_phones = c.fetchall()
    conn.close()

    return render_template('check.html',
                           result=result,
                           message=message,
                           searched_phone=searched_phone,
                           top_phones=top_phones,
                           format_phone=format_phone_display)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                      (username, password))
            conn.commit()

            c.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_id = c.fetchone()[0]

            session['user_id'] = user_id
            session['username'] = username

            flash('Регистрация успешна!')
            return redirect('/account')

        except sqlite3.IntegrityError:
            flash('Логин уже занят')
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute("SELECT id FROM users WHERE username = ? AND password = ?",
                  (username, password))
        user = c.fetchone()

        conn.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = username
            flash('Вход выполнен')
            return redirect('/account')
        else:
            flash('Неверный логин или пароль')

    return render_template('login.html')


@app.route('/account')
def account():
    if 'user_id' not in session:
        flash('Сначала войдите в систему')
        return redirect('/login')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute("SELECT username, status, checks_count FROM users WHERE id = ?",
              (session['user_id'],))
    user = c.fetchone()

    c.execute('''SELECT phone, reported_date FROM user_reports 
                 WHERE user_id = ? ORDER BY reported_date DESC LIMIT 10''',
              (session['user_id'],))
    reports = c.fetchall()

    conn.close()

    return render_template('account.html', user=user, reports=reports)


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы')
    return redirect('/')


@app.context_processor
def utility_processor():
    return {'now': datetime.now}


                                                    #  ТРЕНАЖЕР
TRAINING_LETTERS = [
    {
        'id': 1,
        'from': 'support@secure-bank-verify.com',
        'to': 'client@example.com',
        'subject': '⚠️ СРОЧНО! Ваш аккаунт будет заблокирован',
        'body': '''
            <p>Уважаемый клиент!</p>
            <p>Наша система безопасности обнаружила: <span class="threat" data-threat="0">подозрительную активность в вашем аккаунте</span>. Если вы не <span class="threat" data-threat="1">подтвердите свою личность в течение 24 часов</span>, ваш аккаунт будет навсегда заблокирован.</p>
            <p>Пожалуйста, перейдите по ссылке: <span class="threat" data-threat="2">https://secure-bank-verify.com/confirm</span></p>
            <p>С уважением,<br>Служба безопасности банка</p>
        ''',
        'total_threats': 3
    },
    {
        'id': 2,
        'from': 'info@amazon-delivery-service.net',
        'to': 'client@example.com',
        'subject': 'Ваша посылка не может быть доставлена',
        'body': '''
            <p>Здравствуйте!</p>
            <p>Ваша посылка <span class="threat" data-threat="0">будет возвращена отправителю</span>, если вы не обновите адрес доставки <span class="threat" data-threat="1">в течение 12 часов</span>.</p>
            <p>Пожалуйста, <span class="threat" data-threat="2">перейдите по ссылке, чтобы обновить информацию</span> и оплатить небольшую сумму за пересылку — 2.99$.</p>
            <p>Если вы проигнорируете это сообщение, ваш заказ будет отменён.</p>
            <p>С уважением,<br>Служба доставки Amazon</p>
        ''',
        'total_threats': 3
    },
    {
        'id': 3,
        'from': 'security@apple.com',
        'to': 'client@example.com',
        'subject': 'Внимание! Ваш Apple ID взломан',
        'body': '''
            <p>Уважаемый пользователь Apple!</p>
            <p>У нас есть основания полагать, что <span class="threat" data-threat="0">ваш Apple ID был взломан</span> третьими лицами.</p>
            <p><span class="threat" data-threat="1">Вы должны немедленно подтвердить информацию об аккаунте</span>, чтобы избежать permanente блокировки.</p>
            <p>Подтвердите аккаунт здесь: <span class="threat" data-threat="2">https://appleid-verify-secure.com/login</span></p>
            <p>Если мы не получим от вас ответ <span class="threat" data-threat="3">в течение 48 часов</span>, ваш аккаунт будет навсегда заблокирован.</p>
            <p>Служба безопасности Apple</p>
        ''',
        'total_threats': 4
    }
]


def get_training_progress():
    current_letter = session.get('current_letter', 1)
    found = session.get('found', {})
    completed = session.get('completed', False)
    return current_letter, found, completed


def save_training_progress(current_letter, found, completed=False):
    session['current_letter'] = current_letter
    session['found'] = found
    session['completed'] = completed


@app.route('/training', methods=['GET', 'POST'])
def training():
    current_letter, found, completed = get_training_progress()

    if completed:
        return redirect(url_for('training_complete'))

    if current_letter > len(TRAINING_LETTERS):
        save_training_progress(current_letter, found, completed=True)
        return redirect(url_for('training_complete'))

    letter_data = TRAINING_LETTERS[current_letter - 1]

    if request.method == 'POST':
        threat_id = int(request.form.get('threat_id'))
        if str(threat_id) not in found:
            found[str(threat_id)] = True
            save_training_progress(current_letter, found)

        if len(found) == letter_data['total_threats']:
            if current_letter + 1 > len(TRAINING_LETTERS):
                save_training_progress(current_letter + 1, {}, completed=True)
                return redirect(url_for('training_complete'))
            else:
                save_training_progress(current_letter + 1, {})
                return redirect(url_for('training'))

    body_html = letter_data['body']
    for threat_id in range(letter_data['total_threats']):
        if str(threat_id) in found:
            body_html = body_html.replace(f'<span class="threat" data-threat="{threat_id}">',
                                          f'<span class="threat found" data-threat="{threat_id}">')

    found_count = len(found)

    return render_template('training.html',
                           letter=letter_data,
                           letter_num=current_letter,
                           total_letters=len(TRAINING_LETTERS),
                           body_html=body_html,
                           found_count=found_count,
                           total_threats=letter_data['total_threats'])


@app.route('/training-reset')
def training_reset():
    session.pop('current_letter', None)
    session.pop('found', None)
    session.pop('completed', None)
    return redirect(url_for('training'))


@app.route('/training-force-reset')
def training_force_reset():
    session.pop('current_letter', None)
    session.pop('found', None)
    session.pop('completed', None)
    return redirect(url_for('training'))


@app.route('/training-complete')
def training_complete():
    return render_template('training_complete.html')


@app.route('/api/phones', methods=['GET'])
def api_phones():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute("SELECT phone, reports_count, source FROM phone_numbers ORDER BY reports_count DESC")
    phones = c.fetchall()

    conn.close()

    result = []
    for phone in phones:
        result.append({
            'phone': phone[0],
            'reports': phone[1],
            'source': phone[2]
        })

    return jsonify({
        'status': 'success',
        'count': len(result),
        'data': result
    })


# ============= ЗАПУСК =============
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)