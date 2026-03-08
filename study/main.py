from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import requests
import re
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'cybershield_secret_key_2024'

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  status TEXT DEFAULT 'Новичок',
                  checks_count INTEGER DEFAULT 0,
                  registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Таблица номеров (общая база)
    c.execute('''CREATE TABLE IF NOT EXISTS phone_numbers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT UNIQUE,
                  source TEXT DEFAULT 'user',
                  reports_count INTEGER DEFAULT 1,
                  first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Таблица жалоб пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS user_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  phone TEXT,
                  reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')

    conn.commit()
    conn.close()


init_db()


# ============= ПАРСИНГ НОМЕРОВ =============
def parse_mvd_numbers():
    """Парсит номера мошенников с сайта МВД"""
    numbers = []
    try:
        url = "https://мвд.рф/wanted"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            # Ищем номера в формате +7 XXX XXX-XX-XX или 8 XXX XXX-XX-XX
            phones = re.findall(r'\+7\d{10}|8\d{10}|7\d{10}', response.text)
            numbers.extend(phones)
    except Exception as e:
        print(f"Ошибка парсинга МВД: {e}")

    return list(set(numbers))


def parse_cbr_numbers():
    """Парсит номера с сайта ЦБ РФ"""
    numbers = []
    try:
        url = "https://cbr.ru/inside/warning-list/"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            phones = re.findall(r'\+7\d{10}|8\d{10}|7\d{10}', response.text)
            numbers.extend(phones)
    except Exception as e:
        print(f"Ошибка парсинга ЦБ РФ: {e}")

    return list(set(numbers))


def update_phone_database():
    """Обновляет базу номеров из всех источников"""
    all_numbers = []

    # Собираем номера из всех источников
    all_numbers.extend(parse_mvd_numbers())
    all_numbers.extend(parse_cbr_numbers())

    # Убираем дубликаты
    all_numbers = list(set(all_numbers))

    # Сохраняем в базу
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    for phone in all_numbers:
        # Очищаем номер
        clean_phone = re.sub(r'[^\d]', '', phone)
        if len(clean_phone) == 11:
            if clean_phone.startswith('8'):
                clean_phone = '7' + clean_phone[1:]

        try:
            c.execute('''INSERT INTO phone_numbers (phone, source, reports_count) 
                         VALUES (?, ?, ?)''',
                      (clean_phone, 'official', 1))
        except sqlite3.IntegrityError:
            # Номер уже есть, увеличиваем счетчик
            c.execute('''UPDATE phone_numbers 
                         SET reports_count = reports_count + 1, 
                             last_seen = CURRENT_TIMESTAMP 
                         WHERE phone = ?''', (clean_phone,))

    conn.commit()
    conn.close()

    return len(all_numbers)


# ============= МАРШРУТЫ =============
@app.route('/')
def home():
    """Главная страница с данными для таблицы номеров"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Получаем топ-10 самых часто встречающихся номеров
    c.execute('''SELECT phone, reports_count, source, 
                 strftime('%d.%m.%Y', last_seen) as last_seen 
                 FROM phone_numbers 
                 ORDER BY reports_count DESC, last_seen DESC 
                 LIMIT 10''')
    phones = c.fetchall()

    conn.close()

    return render_template('index.html', phones=phones, now=datetime.now)


@app.route('/phones')
def phones_page():
    """Страница с базой номеров мошенников"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Получаем топ-10 самых часто встречающихся номеров
    c.execute('''SELECT phone, reports_count, source, 
                 strftime('%d.%m.%Y', last_seen) as last_seen 
                 FROM phone_numbers 
                 ORDER BY reports_count DESC, last_seen DESC 
                 LIMIT 10''')
    phones = c.fetchall()

    conn.close()

    return render_template('phones.html', phones=phones, now=datetime.now)


@app.route('/check', methods=['GET', 'POST'])
def check_phone():
    """Страница проверки номера"""
    result = None
    if request.method == 'POST':
        phone = request.form.get('phone')

        # Очищаем номер
        clean_phone = re.sub(r'[^\d]', '', phone)
        if len(clean_phone) == 11 and clean_phone.startswith('8'):
            clean_phone = '7' + clean_phone[1:]

        # Проверяем в базе
        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute('''SELECT reports_count, source FROM phone_numbers 
                     WHERE phone = ?''', (clean_phone,))
        result = c.fetchone()

        # Если пользователь залогинен и хочет сообщить
        if session.get('user_id') and request.form.get('report') == 'yes':
            c.execute('''INSERT INTO user_reports (user_id, phone) 
                         VALUES (?, ?)''', (session['user_id'], clean_phone))

            # Обновляем счетчик в общей базе
            if result:
                c.execute('''UPDATE phone_numbers 
                             SET reports_count = reports_count + 1, 
                                 last_seen = CURRENT_TIMESTAMP 
                             WHERE phone = ?''', (clean_phone,))
            else:
                c.execute('''INSERT INTO phone_numbers (phone, source, reports_count) 
                             VALUES (?, ?, ?)''', (clean_phone, 'user', 1))

        conn.commit()
        conn.close()

    return render_template('check.html', result=result)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация пользователя"""
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
    """Вход пользователя"""
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
    """Личный кабинет"""
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
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы')
    return redirect('/')


@app.context_processor
def utility_processor():
    """Добавляет now во все шаблоны"""
    return {'now': datetime.now}



# ============= ЗАПУСК ПРИ ПЕРВОМ ЗАПУСКЕ =============
# Обновляем базу при старте
print("Обновление базы номеров...")
count = update_phone_database()
print(f"Добавлено {count} номеров")

if __name__ == '__main__':
    app.run(debug=True)