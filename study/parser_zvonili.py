import requests
from bs4 import BeautifulSoup
import sqlite3
import re

def format_phone(digits):
    """делает красивый вид"""
    if digits and len(digits) == 10:
        return f"+7 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"
    return digits

conn = sqlite3.connect('database.db')
c = conn.cursor()

url = "https://zvonili.com/"
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)

soup = BeautifulSoup(response.text, 'html.parser')
text = soup.get_text()

# ТОЛЬКО десяти знач. числа
raw_phones = re.findall(r'\b\d{10}\b', text)
raw_phones = list(set(raw_phones))

print(f"🔍 Найдено номеров: {len(raw_phones)}")

added = 0
for raw in raw_phones:
    formatted = format_phone(raw)  # уже красивый вид
    try:
        c.execute("INSERT INTO phone_numbers (phone, source, reports_count) VALUES (?, ?, ?)",
                 (formatted, 'zvonili.com', 0))
        print(f"➕ Добавлен: {formatted}")
        added += 1
    except sqlite3.IntegrityError:
        print(f"⏩ Уже есть: {formatted}")

conn.commit()
conn.close()

print(f"✅ Добавлено {added} номеров")