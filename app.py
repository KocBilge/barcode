from flask import Flask, render_template, Response, request, redirect, url_for, flash, make_response, jsonify
import cv2
from pyzbar import pyzbar
import json
import os
import time
import csv
import io
from datetime import datetime
from werkzeug.utils import secure_filename
from db import init_db, insert_barcode, get_all_barcodes

# Flask uygulaması
app = Flask(__name__)
app.secret_key = '9bd167e94fe0f733c63b4d89636d321243bbc10a409f3ca66fa48863a942e9ab'

# Mac için pyzbar kütüphane yolu
os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'

# Klasör ve dosya ayarları
UPLOAD_FOLDER = 'uploads'
DATA_FILE = 'data.json'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Veritabanını başlat
init_db()

# Kamera ayarları
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

# Tekrar okuma filtresi
last_seen = {}

# JSON veri işlemleri
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"bölüm1": [], "bölüm2": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

sections = load_data()
current_section = "bölüm1"

def is_new_barcode(data, cooldown=3):
    now = time.time()
    if data not in last_seen or now - last_seen[data] > cooldown:
        last_seen[data] = now
        return True
    return False

# Ana Sayfa
@app.route('/', methods=['GET', 'POST'])
def index():
    global current_section
    if request.method == 'POST':
        sec = request.form.get('section')
        if sec:
            sec = sec.strip()
            # Tüm mevcut bölüm adlarını küçük harfe çevirerek karşılaştır
            if sec.lower() in (s.lower() for s in sections):
                flash(f'"{sec}" adlı bölüm zaten mevcut. Lütfen farklı bir isim girin.')
            else:
                sections[sec] = []
                save_data(sections)
                flash(f'"{sec}" adlı yeni bölüm başarıyla eklendi ve aktif edildi.')
                current_section = sec
    return render_template('index.html.jinja', sections=sections, current_section=current_section, current_year=datetime.now().year)

@app.route('/delete_section', methods=['POST'])
def delete_section():
    section = request.form.get('section')
    if section in sections:
        del sections[section]
        save_data(sections)
        flash(f'"{section}" adlı bölüm silindi.')
        # Aktif bölüm silinirse ilk kalan bölüm varsayılacak
        global current_section
        current_section = next(iter(sections), '')
    else:
        flash("Silinemedi: Bölüm bulunamadı.")
    return redirect(url_for('index'))

# Kamera akışı
@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.bilateralFilter(gray, 11, 17, 17)
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, 10)

        barcodes = pyzbar.decode(thresh)

        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
            x, y, w, h = barcode.rect

            if is_new_barcode(barcode_data):
                if barcode_data not in sections[current_section]:
                    print(f"Yeni barkod eklendi: {barcode_data}")
                    sections[current_section].append(barcode_data)
                    insert_barcode(current_section, barcode_data)
                    save_data(sections)

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, barcode_data, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# Görselden barkod okuma
@app.route('/upload', methods=['POST'])
def upload():
    global current_section

    if 'image' not in request.files:
        flash('Dosya bulunamadı.')
        return redirect(url_for('index'))

    file = request.files['image']
    if file.filename == '':
        flash('Dosya seçilmedi.')
        return redirect(url_for('index'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    image = cv2.imread(filepath)
    if image is None:
        flash("Görsel açılamadı.")
        return redirect(url_for('index'))

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    barcodes = pyzbar.decode(gray)

    new_codes = []
    for barcode in barcodes:
        code = barcode.data.decode('utf-8')
        if code not in sections[current_section]:
            sections[current_section].append(code)
            insert_barcode(current_section, code)
            new_codes.append(code)

    save_data(sections)

    if new_codes:
        flash(f'{len(new_codes)} yeni barkod eklendi.')
    else:
        flash('Yeni barkod bulunamadı ya da zaten kayıtlı.')

    return redirect(url_for('index'))

# Tekli barkod silme
@app.route('/delete_code', methods=['POST'])
def delete_code():
    section = request.form.get('section')
    code = request.form.get('code')

    data = get_all_barcodes()
    if section in data:
        # Yeni liste: sadece silinmeyenleri tut
        updated = [item for item in data[section] if item['code'] != code]
        data[section] = updated

        # JSON'a veya DB'ye kaydet
        save_data(data)

        flash(f"{code} barkodu silindi.")
    else:
        flash("Bölüm bulunamadı.")

    return redirect(url_for('index'))

# Mobil cihazdan gelen barkodları işleme
@app.route('/scan', methods=['POST'])
def scan_from_mobile():
    global current_section
    data = request.json
    code = data.get('code')
    section = data.get('section', current_section)

    if section not in sections:
        return 'INVALID SECTION', 400

    if code and code not in sections[section]:
        sections[section].append(code)
        insert_barcode(section, code)
        save_data(sections)
        return 'OK', 200
    return 'ALREADY EXISTS', 200

# Çoklu barkod silme
@app.route('/bulk_delete', methods=['POST'])
def bulk_delete():
    section = request.form.get('section')
    codes_to_delete = request.form.getlist('codes')

    if section in sections:
        original_count = len(sections[section])
        sections[section] = [code for code in sections[section] if code not in codes_to_delete]
        save_data(sections)
        flash(f"{original_count - len(sections[section])} barkod silindi.")
    else:
        flash("Bölüm bulunamadı.")
    return redirect(url_for('index'))

# Güncel barkod verilerini JSON olarak verir
@app.route('/get_latest_barcodes')
def get_latest_barcodes():
    """
    JSON yapısı:
    {
        "Depo1": [
            {"code": "ABC123", "timestamp": "2025-07-15T21:03:45"},
            ...
        ],
        "Manav": [
            {"code": "XYZ789", "timestamp": "2025-07-15T21:04:10"},
            ...
        ]
    }
    """
    data = get_all_barcodes()
    results = {}

    for section, barcodes in data.items():
        results[section] = []
        for entry in barcodes:
            code = entry.get('code')
            timestamp = entry.get('timestamp')

            # ISO formatta tarih olmalı ki JavaScript Date ile karşılaştırılabilsin
            if isinstance(timestamp, datetime):
                timestamp = timestamp.isoformat()
            elif isinstance(timestamp, str):
                try:
                    # Tarih formatı yanlışsa hata vermesin
                    datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp = None

            results[section].append({
                'code': code,
                'timestamp': timestamp
            })

    return jsonify(results)

# CSV dışa aktarma
@app.route('/export_csv')
def export_csv():
    rows = get_all_barcodes()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bölüm', 'Barkod', 'Tarih'])
    for row in rows:
        writer.writerow(row)

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=barkodlar.csv"
    response.headers["Content-type"] = "text/csv"
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

