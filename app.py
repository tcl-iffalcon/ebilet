import os
import json
import logging
import smtplib
import requests
import threading
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tcdd-secret-key-2024')

CONFIG_FILE = 'config.json'
LOG_FILE = 'notifications.log'

def load_config():
    default = {
        "watches": [],
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "sender_email": "",
            "sender_password": "",
            "recipient_email": ""
        },
        "check_interval_minutes": 5,
        "render_url": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                for key in default:
                    if key not in saved:
                        saved[key] = default[key]
                return saved
        except:
            pass
    return default

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def log_notification(message, level="INFO"):
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    entry = f"[{timestamp}] [{level}] {message}\n"
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry)
    logger.info(message)

def send_email(subject, body, config):
    email_cfg = config.get('email', {})
    if not all([email_cfg.get('sender_email'), email_cfg.get('sender_password'), email_cfg.get('recipient_email')]):
        logger.warning("E-posta ayarları eksik, bildirim gönderilemiyor.")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = email_cfg['sender_email']
        msg['To'] = email_cfg['recipient_email']
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        with smtplib.SMTP(email_cfg['smtp_host'], email_cfg['smtp_port']) as server:
            server.starttls()
            server.login(email_cfg['sender_email'], email_cfg['sender_password'])
            server.send_message(msg)
        log_notification(f"E-posta gönderildi: {subject}")
        return True
    except Exception as e:
        log_notification(f"E-posta gönderilemedi: {e}", "ERROR")
        return False

def check_tcdd_availability(watch):
    """
    TCDD eBilet API'sini sorgular.
    watch: {from_code, to_code, from_name, to_name, date, seat_type}
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://ebilet.tcddtasimacilik.gov.tr',
        'Referer': 'https://ebilet.tcddtasimacilik.gov.tr/',
    }

    payload = {
        "seferSorgulamaKriterleri": {
            "binisIstasyon": watch['from_code'],
            "inisIstasyon": watch['to_code'],
            "gidisTarih": watch['date'],  # Format: "2024-12-25 00:00:00"
            "gidisDonusSecimi": 1,
            "yolcuSayisi": 1,
            "sonuc": "0"
        }
    }

    try:
        response = requests.post(
            'https://ebilet.tcddtasimacilik.gov.tr/view/eybis/tnmEybis/tcddWebApiProxy',
            headers=headers,
            json={
                "kanalKodu": "3",
                "dil": "0",
                "jsonFor": json.dumps(payload),
                "seyahatBilgisi": json.dumps(payload["seferSorgulamaKriterleri"]),
                "pageId": "SeferSorgula"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            trains = data.get('seferSorgulamaSonucList', [])
            available = []
            for train in trains:
                seats = train.get('vagonTiplerindeBosYerSayisi', {})
                total_available = sum(seats.values()) if isinstance(seats, dict) else 0
                if total_available > 0:
                    available.append({
                        'train_no': train.get('tren', {}).get('trenAdi', 'Bilinmiyor'),
                        'departure': train.get('binisTarihSaat', ''),
                        'arrival': train.get('inisTarihSaat', ''),
                        'seats': total_available,
                        'seat_types': seats
                    })
            return available
        else:
            log_notification(f"API yanıtı: {response.status_code}", "WARNING")
            return None
    except Exception as e:
        log_notification(f"Sorgulama hatası ({watch.get('from_name','?')} → {watch.get('to_name','?')}): {e}", "ERROR")
        return None

def check_all_watches():
    config = load_config()
    watches = config.get('watches', [])
    if not watches:
        return

    logger.info(f"Kontrol ediliyor: {len(watches)} takip kaydı")
    today = datetime.now().date()

    for watch in watches:
        if not watch.get('active', True):
            continue

        watch_date_str = watch.get('date', '')
        try:
            watch_date = datetime.strptime(watch_date_str[:10], '%Y-%m-%d').date()
            if watch_date < today:
                log_notification(f"Geçmiş tarih atlandı: {watch.get('from_name')} → {watch.get('to_name')} ({watch_date_str})", "WARNING")
                continue
        except:
            pass

        available = check_tcdd_availability(watch)

        if available is None:
            continue

        if available:
            train_list = ""
            for t in available:
                seat_detail = ", ".join([f"{k}: {v}" for k, v in t['seat_types'].items()]) if isinstance(t['seat_types'], dict) else str(t['seats'])
                train_list += f"""
                <tr>
                    <td style="padding:8px;border:1px solid #ddd;">{t['train_no']}</td>
                    <td style="padding:8px;border:1px solid #ddd;">{t['departure']}</td>
                    <td style="padding:8px;border:1px solid #ddd;">{t['arrival']}</td>
                    <td style="padding:8px;border:1px solid #ddd;">{t['seats']} boş yer</td>
                    <td style="padding:8px;border:1px solid #ddd;">{seat_detail}</td>
                </tr>"""

            subject = f"🚆 TCDD Bilet Bulundu! {watch['from_name']} → {watch['to_name']} ({watch_date_str[:10]})"
            body = f"""
            <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:#CC0000;color:white;padding:20px;border-radius:8px 8px 0 0;">
                <h2 style="margin:0;">🚆 TCDD Bilet Kontenjanı Açıldı!</h2>
            </div>
            <div style="background:#f9f9f9;padding:20px;border:1px solid #ddd;">
                <p><strong>Güzergah:</strong> {watch['from_name']} → {watch['to_name']}</p>
                <p><strong>Tarih:</strong> {watch_date_str[:10]}</p>
                <p><strong>Bulunan tren sayısı:</strong> {len(available)}</p>
                <table style="width:100%;border-collapse:collapse;margin-top:15px;">
                    <tr style="background:#CC0000;color:white;">
                        <th style="padding:8px;">Tren</th>
                        <th style="padding:8px;">Kalkış</th>
                        <th style="padding:8px;">Varış</th>
                        <th style="padding:8px;">Boş Yer</th>
                        <th style="padding:8px;">Detay</th>
                    </tr>
                    {train_list}
                </table>
                <div style="margin-top:20px;text-align:center;">
                    <a href="https://ebilet.tcddtasimacilik.gov.tr" 
                       style="background:#CC0000;color:white;padding:12px 24px;text-decoration:none;border-radius:5px;font-weight:bold;">
                        Hemen Bilet Al →
                    </a>
                </div>
            </div>
            <div style="background:#333;color:#aaa;padding:10px;text-align:center;font-size:12px;border-radius:0 0 8px 8px;">
                TCDD Bilet Takip Sistemi • {datetime.now().strftime('%d.%m.%Y %H:%M')}
            </div>
            </body></html>
            """
            send_email(subject, body, config)
            log_notification(f"✅ Bilet bulundu: {watch['from_name']} → {watch['to_name']} ({len(available)} tren)")
        else:
            log_notification(f"❌ Müsait sefer yok: {watch['from_name']} → {watch['to_name']} ({watch_date_str[:10]})")

def self_ping():
    """Render'ın ücretsiz tierda uyku moduna girmesini engeller."""
    config = load_config()
    render_url = config.get('render_url', '').strip()
    if render_url:
        try:
            requests.get(f"{render_url}/ping", timeout=10)
            logger.info("Self-ping başarılı")
        except Exception as e:
            logger.warning(f"Self-ping başarısız: {e}")

# Scheduler
scheduler = BackgroundScheduler()

def start_scheduler():
    config = load_config()
    interval = config.get('check_interval_minutes', 5)
    scheduler.add_job(check_all_watches, IntervalTrigger(minutes=interval), id='check_watches', replace_existing=True)
    scheduler.add_job(self_ping, IntervalTrigger(minutes=14), id='self_ping', replace_existing=True)
    if not scheduler.running:
        scheduler.start()

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    config = load_config()
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = f.readlines()[-50:]
        logs = list(reversed(logs))
    return render_template('index.html', config=config, logs=logs)

@app.route('/ping')
def ping():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/settings', methods=['POST'])
def save_settings():
    config = load_config()
    config['email'] = {
        'smtp_host': request.form.get('smtp_host', 'smtp.gmail.com'),
        'smtp_port': int(request.form.get('smtp_port', 587)),
        'sender_email': request.form.get('sender_email', ''),
        'sender_password': request.form.get('sender_password', ''),
        'recipient_email': request.form.get('recipient_email', ''),
    }
    config['check_interval_minutes'] = int(request.form.get('check_interval', 5))
    config['render_url'] = request.form.get('render_url', '')
    save_config(config)

    # Restart scheduler with new interval
    if scheduler.get_job('check_watches'):
        scheduler.remove_job('check_watches')
    scheduler.add_job(check_all_watches, IntervalTrigger(minutes=config['check_interval_minutes']), id='check_watches')

    flash('✅ Ayarlar kaydedildi!', 'success')
    return redirect(url_for('index'))

@app.route('/add_watch', methods=['POST'])
def add_watch():
    config = load_config()
    date_input = request.form.get('date', '')
    try:
        parsed = datetime.strptime(date_input, '%Y-%m-%d')
        date_formatted = parsed.strftime('%Y-%m-%d') + ' 00:00:00'
    except:
        date_formatted = date_input + ' 00:00:00'

    watch = {
        'id': int(datetime.now().timestamp()),
        'from_code': request.form.get('from_code', '').strip(),
        'from_name': request.form.get('from_name', '').strip(),
        'to_code': request.form.get('to_code', '').strip(),
        'to_name': request.form.get('to_name', '').strip(),
        'date': date_formatted,
        'active': True,
        'added': datetime.now().strftime('%d.%m.%Y %H:%M')
    }

    if not all([watch['from_code'], watch['to_code'], date_input]):
        flash('❌ Lütfen tüm alanları doldurun.', 'error')
        return redirect(url_for('index'))

    config['watches'].append(watch)
    save_config(config)
    flash(f"✅ Takip eklendi: {watch['from_name']} → {watch['to_name']}", 'success')
    return redirect(url_for('index'))

@app.route('/delete_watch/<int:watch_id>')
def delete_watch(watch_id):
    config = load_config()
    config['watches'] = [w for w in config['watches'] if w.get('id') != watch_id]
    save_config(config)
    flash('🗑️ Takip silindi.', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_watch/<int:watch_id>')
def toggle_watch(watch_id):
    config = load_config()
    for w in config['watches']:
        if w.get('id') == watch_id:
            w['active'] = not w.get('active', True)
    save_config(config)
    return redirect(url_for('index'))

@app.route('/check_now')
def check_now():
    threading.Thread(target=check_all_watches).start()
    flash('🔍 Kontrol başlatıldı! Birkaç saniye içinde sonuçlar logda görünecek.', 'info')
    return redirect(url_for('index'))

@app.route('/test_email')
def test_email():
    config = load_config()
    result = send_email(
        "🚆 TCDD Takip - Test E-postası",
        "<h2>Test başarılı!</h2><p>E-posta bildirimleri düzgün çalışıyor.</p>",
        config
    )
    if result:
        flash('✅ Test e-postası gönderildi!', 'success')
    else:
        flash('❌ Test e-postası gönderilemedi. E-posta ayarlarını kontrol edin.', 'error')
    return redirect(url_for('index'))

@app.route('/clear_logs')
def clear_logs():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    flash('🗑️ Loglar temizlendi.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    start_scheduler()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
