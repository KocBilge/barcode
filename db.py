import sqlite3
from datetime import datetime

DB_PATH = 'barcodes.db'

# Veritabanını başlat (tablo yoksa oluşturur)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS barcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            code TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Yeni barkod ekle
def insert_barcode(section, code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Aynı barkod aynı bölümde varsa tekrar eklenmesin
    c.execute("SELECT COUNT(*) FROM barcodes WHERE section = ? AND LOWER(code) = LOWER(?)", (section, code))
    exists = c.fetchone()[0]

    if exists == 0:
        c.execute("INSERT INTO barcodes (section, code) VALUES (?, ?)", (section, code))
        conn.commit()

    conn.close()

# Tüm barkodları al (liste olarak)
def get_all_barcodes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT section, code, timestamp FROM barcodes ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()

    # Listeyi sözlük yapısına çevir
    data = {}
    for section, code, timestamp in rows:
        if section not in data:
            data[section] = []
        data[section].append({'code': code, 'timestamp': timestamp})
    
    return data