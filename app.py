import os
import json
import logging
import smtplib
import requests
import threading
import secrets
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'bilet-secret-key-2024')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

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

def send_email(subject, body, config, to_email=None):
    email_cfg = config.get('email', {})
    recipient = to_email or email_cfg.get('recipient_email', '')
    if not all([email_cfg.get('sender_email'), email_cfg.get('sender_password'), recipient]):
        logger.warning("E-posta ayarları eksik.")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = email_cfg['sender_email']
        msg['To'] = recipient
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        with smtplib.SMTP(email_cfg['smtp_host'], email_cfg['smtp_port']) as server:
            server.starttls()
            server.login(email_cfg['sender_email'], email_cfg['sender_password'])
            server.send_message(msg)
        log_notification(f"E-posta gönderildi: {subject} → {recipient}")
        return True
    except Exception as e:
        log_notification(f"E-posta gönderilemedi: {e}", "ERROR")
        return False

def check_availability(watch):
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
            "gidisTarih": watch['date'],
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

    logger.info(f"Kontrol ediliyor: {len(watches)} takip")
    today = datetime.now().date()
    base_url = config.get('render_url', '').strip().rstrip('/')

    for watch in watches:
        if not watch.get('active', True):
            continue

        watch_date_str = watch.get('date', '')
        try:
            watch_date = datetime.strptime(watch_date_str[:10], '%Y-%m-%d').date()
            if watch_date < today:
                log_notification(f"Geçmiş tarih atlandı: {watch.get('from_name')} → {watch.get('to_name')}", "WARNING")
                continue
        except:
            pass

        available = check_availability(watch)
        if available is None:
            continue

        user_email = watch.get('user_email') or config['email'].get('recipient_email', '')
        cancel_token = watch.get('cancel_token', '')
        cancel_link = f"{base_url}/iptal/{cancel_token}" if base_url and cancel_token else ''

        if available:
            train_rows = ""
            for t in available:
                train_rows += f"""
                <tr>
                  <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;">{t['train_no']}</td>
                  <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;">{t['departure']}</td>
                  <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;">{t['arrival']}</td>
                  <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#16A34A;font-weight:600;">{t['seats']} boş</td>
                </tr>"""

            cancel_html = f'<div style="margin-top:20px;padding-top:16px;border-top:1px solid #f0f0f0;text-align:center;"><a href="{cancel_link}" style="font-size:12px;color:#9CA3AF;text-decoration:underline;">Takibi iptal et</a></div>' if cancel_link else ''

            subject = f"🎉 Bilet Bulundu! {watch['from_name']} → {watch['to_name']}"
            body = f"""
            <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#F8F9FB;margin:0;padding:32px 16px;">
            <div style="max-width:520px;margin:0 auto;">
              <div style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                <div style="background:#2563EB;padding:24px 28px;">
                  <div style="font-size:28px;margin-bottom:6px;">🎉</div>
                  <h2 style="margin:0;color:#fff;font-size:20px;font-weight:700;">Bilet Kontenjanı Açıldı!</h2>
                  <p style="margin:6px 0 0;color:#BFDBFE;font-size:14px;">{watch['from_name']} → {watch['to_name']} · {watch_date_str[:10]}</p>
                </div>
                <div style="padding:24px 28px;">
                  <p style="margin:0 0 16px;font-size:14px;color:#374151;">{len(available)} tren için müsait koltuk bulundu:</p>
                  <table style="width:100%;border-collapse:collapse;">
                    <tr style="background:#F8F9FB;">
                      <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Tren</th>
                      <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Kalkış</th>
                      <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Varış</th>
                      <th style="padding:8px 12px;text-align:left;color:#6B7280;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Boş Yer</th>
                    </tr>
                    {train_rows}
                  </table>
                  <div style="margin-top:20px;text-align:center;">
                    <a href="https://ebilet.tcddtasimacilik.gov.tr" style="display:inline-block;background:#2563EB;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Hemen Bilet Al →</a>
                  </div>
                  {cancel_html}
                </div>
              </div>
              <p style="text-align:center;font-size:11px;color:#9CA3AF;margin-top:16px;">Bilet Takip · {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            </div>
            </body></html>"""
            send_email(subject, body, config, to_email=user_email)
            log_notification(f"✅ Bilet bulundu: {watch['from_name']} → {watch['to_name']} ({len(available)} tren) → {user_email}")
        else:
            log_notification(f"❌ Müsait sefer yok: {watch['from_name']} → {watch['to_name']} ({watch_date_str[:10]})")

def self_ping():
    config = load_config()
    render_url = config.get('render_url', '').strip()
    if render_url:
        try:
            requests.get(f"{render_url}/ping", timeout=10)
            logger.info("Self-ping başarılı")
        except Exception as e:
            logger.warning(f"Self-ping başarısız: {e}")

scheduler = BackgroundScheduler()

def start_scheduler():
    config = load_config()
    interval = config.get('check_interval_minutes', 5)
    scheduler.add_job(check_all_watches, IntervalTrigger(minutes=interval), id='check_watches', replace_existing=True)
    scheduler.add_job(self_ping, IntervalTrigger(minutes=14), id='self_ping', replace_existing=True)
    if not scheduler.running:
        scheduler.start()

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('ayarlar'))
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('ayarlar'))
        error = 'Şifre yanlış.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    # Her ziyaretçiye benzersiz bir session ID ver
    if 'user_id' not in session:
        session['user_id'] = secrets.token_hex(16)
        session.permanent = True

    config = load_config()
    user_id = session['user_id']

    # Admin tüm takipleri görür, kullanıcı sadece kendinkini
    if session.get('logged_in'):
        user_watches = config.get('watches', [])
    else:
        user_watches = [w for w in config.get('watches', []) if w.get('user_id') == user_id]

    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = f.readlines()[-50:]
        logs = list(reversed(logs))
    return render_template('index.html', config=config, user_watches=user_watches, logs=logs)

@app.route('/ping')
def ping():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/ayarlar', methods=['GET', 'POST'])
@login_required
def ayarlar():
    config = load_config()
    if request.method == 'POST':
        config['email'] = {
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': request.form.get('sender_email', ''),
            'sender_password': request.form.get('sender_password', ''),
            'recipient_email': request.form.get('recipient_email', ''),
        }
        config['check_interval_minutes'] = int(request.form.get('check_interval', 5))
        config['render_url'] = request.form.get('render_url', '')
        save_config(config)
        if scheduler.get_job('check_watches'):
            scheduler.remove_job('check_watches')
        scheduler.add_job(check_all_watches, IntervalTrigger(minutes=config['check_interval_minutes']), id='check_watches')
        flash('✅ Ayarlar kaydedildi!', 'success')
        return redirect(url_for('ayarlar'))
    return render_template('settings.html', config=config)

ISTASYONLAR = [
    {"ad": "Adana", "kod": "99806"},
    {"ad": "Adana Havalimanı", "kod": "99814"},
    {"ad": "Afyonkarahisar", "kod": "99807"},
    {"ad": "Alayunt", "kod": "99808"},
    {"ad": "Aliağa", "kod": "99851"},
    {"ad": "Ankara Gar", "kod": "99828"},
    {"ad": "Arifiye", "kod": "99801"},
    {"ad": "Balıkesir", "kod": "99802"},
    {"ad": "Bandırma", "kod": "99803"},
    {"ad": "Bilecik", "kod": "99804"},
    {"ad": "Bostankaya", "kod": "99815"},
    {"ad": "Bozüyük", "kod": "99805"},
    {"ad": "Büyükçekmece", "kod": "99847"},
    {"ad": "Cerkezkoy", "kod": "99809"},
    {"ad": "Ceyhan", "kod": "99810"},
    {"ad": "Çankırı", "kod": "99811"},
    {"ad": "Çerkezköy", "kod": "99809"},
    {"ad": "Denizli", "kod": "99812"},
    {"ad": "Derince", "kod": "99813"},
    {"ad": "Divriği", "kod": "99816"},
    {"ad": "Diyarbakır", "kod": "99817"},
    {"ad": "Dumlupınar", "kod": "99818"},
    {"ad": "Elazığ", "kod": "99819"},
    {"ad": "Erzincan", "kod": "99820"},
    {"ad": "Erzurum", "kod": "99821"},
    {"ad": "Eskişehir", "kod": "99840"},
    {"ad": "Gaziantep", "kod": "99822"},
    {"ad": "Gebze", "kod": "99848"},
    {"ad": "Halkalı", "kod": "99846"},
    {"ad": "Haydarpaşa", "kod": "99823"},
    {"ad": "İstanbul(Halkalı)", "kod": "99846"},
    {"ad": "İstanbul(Pendik)", "kod": "99849"},
    {"ad": "İstanbul(Söğütlüçeşme)", "kod": "99845"},
    {"ad": "İzmir(Alsancak)", "kod": "99830"},
    {"ad": "İzmir(Basmane)", "kod": "99831"},
    {"ad": "Kars", "kod": "99824"},
    {"ad": "Kayseri", "kod": "99834"},
    {"ad": "Kırıkkale", "kod": "99841"},
    {"ad": "Kırşehir", "kod": "99842"},
    {"ad": "Konya", "kod": "99832"},
    {"ad": "Kütahya", "kod": "99833"},
    {"ad": "Malatya", "kod": "99835"},
    {"ad": "Manisa", "kod": "99836"},
    {"ad": "Mersin", "kod": "99837"},
    {"ad": "Muş", "kod": "99838"},
    {"ad": "Nallıhan", "kod": "99843"},
    {"ad": "Niğde", "kod": "99839"},
    {"ad": "Osmaneli", "kod": "99827"},
    {"ad": "Pendik", "kod": "99849"},
    {"ad": "Polatlı", "kod": "99844"},
    {"ad": "Sakarya(Arifiye)", "kod": "99801"},
    {"ad": "Samsun", "kod": "99850"},
    {"ad": "Selçuk", "kod": "99852"},
    {"ad": "Sivas", "kod": "99825"},
    {"ad": "Söğütlüçeşme", "kod": "99845"},
    {"ad": "Şanlıurfa", "kod": "99853"},
    {"ad": "Tatvan", "kod": "99826"},
    {"ad": "Tekirdağ", "kod": "99854"},
    {"ad": "Uşak", "kod": "99855"},
    {"ad": "Van", "kod": "99856"},
    {"ad": "Yerköy", "kod": "99857"},
    {"ad": "Zonguldak", "kod": "99858"},
]

@app.route('/istasyon-ara')
def istasyon_ara():
    q = request.args.get('q', '').strip().lower()
    if len(q) < 2:
        return jsonify([])
    return jsonify([i for i in ISTASYONLAR if q in i['ad'].lower()][:10])

@app.route('/add_watch', methods=['POST'])
def add_watch():
    config = load_config()
    date_input = request.form.get('date', '')
    try:
        parsed = datetime.strptime(date_input, '%Y-%m-%d')
        date_formatted = parsed.strftime('%Y-%m-%d') + ' 00:00:00'
    except:
        date_formatted = date_input + ' 00:00:00'

    user_email = request.form.get('user_email', '').strip()

    # Session ID yoksa oluştur
    if 'user_id' not in session:
        session['user_id'] = secrets.token_hex(16)
        session.permanent = True

    watch = {
        'id': int(datetime.now().timestamp()),
        'cancel_token': secrets.token_urlsafe(24),
        'user_id': session['user_id'],
        'from_code': request.form.get('from_code', '').strip(),
        'from_name': request.form.get('from_name', '').strip(),
        'to_code': request.form.get('to_code', '').strip(),
        'to_name': request.form.get('to_name', '').strip(),
        'date': date_formatted,
        'user_email': user_email,
        'active': True,
        'added': datetime.now().strftime('%d.%m.%Y %H:%M')
    }

    if not all([watch['from_code'], watch['to_code'], date_input, user_email]):
        flash('❌ Lütfen tüm alanları doldurun.', 'error')
        return redirect(url_for('index'))

    config['watches'].append(watch)
    save_config(config)
    flash(f"✅ Takip eklendi: {watch['from_name']} → {watch['to_name']} · Bildirim: {user_email}", 'success')
    return redirect(url_for('index'))

@app.route('/iptal/<token>')
def iptal_watch(token):
    config = load_config()
    watch = next((w for w in config['watches'] if w.get('cancel_token') == token), None)
    if not watch:
        return render_template('cancel.html', success=False, message='Takip bulunamadı veya zaten iptal edilmiş.')
    config['watches'] = [w for w in config['watches'] if w.get('cancel_token') != token]
    save_config(config)
    msg = f"{watch['from_name']} → {watch['to_name']} ({watch['date'][:10]}) takibi iptal edildi."
    return render_template('cancel.html', success=True, message=msg)

@app.route('/delete_watch/<int:watch_id>')
@login_required
def delete_watch(watch_id):
    config = load_config()
    config['watches'] = [w for w in config['watches'] if w.get('id') != watch_id]
    save_config(config)
    flash('🗑️ Takip silindi.', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_watch/<int:watch_id>')
@login_required
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
    flash('🔍 Kontrol başlatıldı!', 'info')
    return redirect(url_for('index'))

@app.route('/test_email')
@login_required
def test_email():
    config = load_config()
    result = send_email(
        "Bilet Takip - Test E-postası",
        "<h2 style='font-family:sans-serif'>Test başarılı! ✅</h2><p style='font-family:sans-serif'>E-posta bildirimleri düzgün çalışıyor.</p>",
        config
    )
    flash('✅ Test e-postası gönderildi!' if result else '❌ Gönderilemedi. Ayarları kontrol edin.', 'success' if result else 'error')
    return redirect(url_for('ayarlar'))

@app.route('/clear_logs')
@login_required
def clear_logs():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    flash('🗑️ Loglar temizlendi.', 'success')
    return redirect(url_for('ayarlar'))

if __name__ == '__main__':
    start_scheduler()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
