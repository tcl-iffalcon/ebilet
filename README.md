# 🚆 TCDD Bilet Takip Sistemi

TCDD eBilet üzerinde seçtiğiniz güzergahlarda kontenjan açıldığında **otomatik e-posta bildirimi** gönderen web uygulaması.

---

## ✨ Özellikler

- 🎯 Birden fazla güzergah/tarih takibi
- ✉️ Gmail ile otomatik e-posta bildirimi
- ⏱ Ayarlanabilir kontrol aralığı (2-60 dakika)
- 💤 Render ücretsiz tier için self-ping (uyku modu engeli)
- 📋 Canlı log görüntüleme
- 🌙 Koyu tema web arayüzü

---

## 🚀 Kurulum (GitHub + Render)

### 1. Repoyu Fork/Clone Edin

```bash
git clone https://github.com/KULLANICI_ADINIZ/tcdd-bilet-takip
cd tcdd-bilet-takip
```

### 2. GitHub'a Push Edin

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/KULLANICI_ADINIZ/tcdd-bilet-takip.git
git push -u origin main
```

### 3. Render'da Deploy Edin

1. [render.com](https://render.com) → Sign Up (GitHub ile giriş yapın)
2. **New +** → **Web Service**
3. GitHub reponuzu bağlayın
4. Ayarlar otomatik algılanır (`render.yaml` sayesinde)
5. **Create Web Service** butonuna basın
6. ~2 dakika bekleyin, uygulamanız hazır!

---

## ⚙️ İlk Yapılandırma

Deploy sonrası `https://uygulamaadi.onrender.com` adresinizi açın.

### Gmail Uygulama Şifresi Alma

> ⚠️ Normal Gmail şifreniz çalışmaz!

1. [myaccount.google.com/security](https://myaccount.google.com/security)
2. **2 Adımlı Doğrulama** → Açık olmalı
3. **Uygulama şifreleri** → Uygulama: "Posta" → Oluştur
4. 16 haneli şifreyi kopyalayın

### Ayarları Girin

Web arayüzünde **E-posta Ayarları** bölümüne:
- Gönderen Gmail adresinizi
- Uygulama şifresini (boşluksuz 16 hane)
- Bildirim alacak e-posta adresini
- Render URL'nizi (`https://uygulamaadi.onrender.com`)
- Kontrol aralığını (önerilen: 5 dakika)

---

## 📍 İstasyon Kodları

| İstasyon | Kod |
|----------|-----|
| Ankara Gar | 99828 |
| İstanbul Pendik | 99849 |
| İstanbul Halkalı | 99846 |
| İzmir Alsancak | 99830 |
| Konya | 99832 |
| Eskişehir | 99840 |
| Sivas | 99836 |
| Kayseri | 99834 |

### Diğer İstasyon Kodlarını Bulma

1. [ebilet.tcddtasimacilik.gov.tr](https://ebilet.tcddtasimacilik.gov.tr) adresine gidin
2. Tarayıcıda **F12** → **Network** sekmesini açın
3. Güzergah araması yapın
4. `seferSorgula` isteğini bulun → `binisIstasyon` / `inisIstasyon` değerleri

---

## 🔔 Bildirim Nasıl Çalışır?

```
Uygulama başlar
    ↓
Her N dakikada bir TCDD API'si sorgulanır
    ↓
Müsait koltuk bulunursa
    ↓
E-posta gönderilir 📧
    ↓
Log'a yazılır
```

---

## 💤 Render Ücretsiz Tier Notu

Render ücretsiz planda uygulamalar **15 dakika aktivite olmazsa uyku moduna** girer. Bunu engellemek için:

- Web arayüzünde **Render URL** alanını doldurun
- Uygulama her 14 dakikada kendini ping'ler
- İlk istek yavaş gelebilir (cold start ~30sn)

Sürekli 7/24 çalışması için Render Starter planı ($7/ay) kullanın.

---

## 📁 Proje Yapısı

```
tcdd-bilet-takip/
├── app.py              # Ana uygulama
├── requirements.txt    # Python bağımlılıkları
├── Procfile           # Render/Heroku başlatma komutu
├── render.yaml        # Render yapılandırması
├── .gitignore
├── templates/
│   └── index.html     # Web arayüzü
└── README.md
```

---

## ⚠️ Önemli Notlar

- Bu uygulama TCDD'nin public web API'sini kullanır
- Çok sık sorgu (1 dk altı) IP bloğuna yol açabilir; 5 dakika önerilir
- `config.json` ve `notifications.log` dosyaları `.gitignore`'da; şifreleriniz GitHub'a gitmez
- Render ücretsiz tier disk storage kalıcı değildir; uygulama yeniden deploy edilirse ayarlar sıfırlanır. Kalıcılık için environment variable kullanmayı düşünün.

---

## 🐛 Sorun Giderme

**E-posta gitmiyor:**
- "Uygulama şifresi" mi yoksa normal şifre mi girdiniz?
- Gmail hesabında 2FA açık mı?
- Spam klasörüne düşmüş olabilir

**API yanıt vermiyor:**
- TCDD sitesi bakımda olabilir
- IP'niz geçici olarak engellenmiş olabilir, aralığı artırın

**Render'da çalışmıyor:**
- Logları kontrol edin: Render Dashboard → Logs
- `requirements.txt` tam mı?

---

*TCDD Bilet Takip • Kişisel kullanım amaçlıdır*
