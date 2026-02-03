# LinkedIn Certificate Scraper

Service Python FastAPI untuk scraping data sertifikat dari profil LinkedIn dengan pendekatan modular yang aman dan efisien.

## 📋 Daftar Isi

- [Arsitektur](#arsitektur)
- [Instalasi](#instalasi)
- [Konfigurasi](#konfigurasi)
- [Menjalankan Service](#menjalankan-service)
- [Integrasi dengan n8n](#integrasi-dengan-n8n)
- [Struktur Modular](#struktur-modular)
- [Keamanan & Best Practices](#keamanan--best-practices)
- [Troubleshooting](#troubleshooting)

---

## Arsitektur

Service ini menggunakan **modular architecture** untuk meningkatkan reliability, maintainability, dan testing. Setiap modul memiliki tanggung jawab yang jelas dan terisolasi.

```
python_service/
├── app.py                      # FastAPI endpoint orchestrator
├── cookies.json                # LinkedIn session cookies (REQUIRED)
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container configuration
└── scraper/                    # Modular scraper package
    ├── __init__.py
    ├── models.py               # Request/response schemas
    ├── config.py               # Configuration & constants
    ├── browser.py              # Browser launch & stealth
    ├── cookies_auth.py         # Cookie handling & auth detection
    ├── navigation.py           # Navigation & human behavior simulation
    ├── selectors.py            # Section & element finding strategies
    ├── extraction.py           # Certificate data extraction
    ├── response.py             # Response building
    └── logging.py              # Debug artifacts & logging
```

---

## Instalasi

### Prasyarat
- Python 3.11+
- Docker & Docker Compose (untuk deployment)
- LinkedIn account dengan cookies valid

### Local Development

```bash
cd python_service

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Docker Deployment

```bash
# Build dan run dengan docker-compose
docker compose up --build

# Atau build manual
docker build -t linkedin-scraper .
docker run -p 8000:8000 linkedin-scraper
```

---

## Konfigurasi

### 1. Setup Cookies (WAJIB)

**PENTING**: Service ini membutuhkan cookies LinkedIn yang valid untuk akses authenticated.

#### Cara mendapatkan cookies:

1. Login ke LinkedIn di browser (Chrome/Firefox)
2. Buka Developer Tools (F12) → Application/Storage → Cookies
3. Export semua cookies untuk domain `linkedin.com`
4. Simpan sebagai `cookies.json` di folder `python_service/`

**Format cookies.json:**

```json
[
  {
    "name": "li_at",
    "value": "AQEDAxxxxxxxxxxxxxxxxxxxxxxxxx",
    "domain": ".linkedin.com",
    "path": "/",
    "expires": 1735689600,
    "httpOnly": true,
    "secure": true,
    "sameSite": "None"
  },
  {
    "name": "JSESSIONID",
    "value": "ajax:xxxxxxxxxxxxxxxxxx",
    "domain": ".linkedin.com",
    "path": "/",
    "secure": true
  }
]
```

**⚠️ Perhatian:**
- Cookie `li_at` adalah yang PALING PENTING untuk autentikasi
- Jangan share cookies ke pihak lain (rahasia perusahaan!)
- Cookies akan expire, perlu di-refresh berkala
- Gunakan akun dengan LinkedIn Premium/Sales Navigator untuk hasil terbaik

### 2. Environment Variables (Opsional)

Buat file `.env` di root project:

```env
# Cookie file path
LINKEDIN_COOKIES_PATH=cookies.json

# Default settings (bisa di-override lewat request body)
SCRAPER_HEADLESS_DEFAULT=true
SCRAPER_MAX_WAIT=25000
SCRAPER_TZ=Asia/Jakarta

# Proxy (jika diperlukan untuk production scale)
SCRAPER_PROXY=http://your-residential-proxy:port
```

---

## Menjalankan Service

### Local (Development)

```bash
cd python_service
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Service akan berjalan di `http://localhost:8000`

### Docker Compose (Production)

```bash
docker compose up -d
```

### Health Check

```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

---

## Integrasi dengan n8n

### 1. Setup HTTP Request Node

Di n8n workflow, tambahkan **HTTP Request** node dengan konfigurasi:

**Method**: `POST`  
**URL**: `http://python_service:8000/scrape/linkedin` (jika satu network Docker)  
atau `http://localhost:8000/scrape/linkedin` (jika n8n di host lain)

**Headers**:
```json
{
  "Content-Type": "application/json"
}
```

**Body** (JSON):
```json
{
  "url": "https://www.linkedin.com/in/username",
  "keyword": null,
  "debug": false,
  "headless": true,
  "max_wait": 25000,
  "detail_only": false,
  "click_show_all": true,
  "proxy": null
}
```

### 2. Request Fields Explanation

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ Yes | - | LinkedIn profile URL |
| `keyword` | string | ❌ No | null | (Reserved for future filtering) |
| `debug` | boolean | ❌ No | false | Enable debug screenshots/HTML |
| `headless` | boolean | ❌ No | true | Run browser in headless mode |
| `max_wait` | integer | ❌ No | 25000 | Max wait time in milliseconds |
| `detail_only` | boolean | ❌ No | false | Jump directly to details page |
| `click_show_all` | boolean | ❌ No | true | Try to expand full certificate list |
| `proxy` | string | ❌ No | null | Proxy server URL |

### 3. Response Format

**Success Response:**
```json
{
  "url": "https://www.linkedin.com/in/username",
  "keyword": null,
  "found": true,
  "total_certificates": 5,
  "certificates_list": [
    {
      "certificate_name": "AWS Certified Solutions Architect",
      "credential_id": "ABC123XYZ",
      "issuer": "Amazon Web Services",
      "issue_date": "Issued Jan 2024",
      "expiry_date": "Expires Jan 2027",
      "verify_link": "https://www.credly.com/badges/...",
      "source": "DetailView"
    }
  ],
  "cookies_loaded": true,
  "guest_mode": false,
  "debug": "LOGGED_IN | FindSection:HeaderHas | Scraped:DetailView | FinalURL:..."
}
```

**Error Response:**
```json
{
  "url": "https://www.linkedin.com/in/invalid",
  "found": false,
  "error": "Navigation failed: Timeout",
  "certificates_list": "error",
  "debug": "..."
}
```

### 4. n8n Expression untuk Extract Data

Setelah HTTP Request node, gunakan expressions:

```javascript
// Check if scraping succeeded
{{ $json.found }}

// Get total certificates
{{ $json.total_certificates }}

// Loop through certificates
{{ $json.certificates_list }}

// Get first certificate name
{{ $json.certificates_list[0].certificate_name }}

// Check if guest mode (limited access)
{{ $json.guest_mode }}
```

---

## Struktur Modular

### `scraper/models.py`
**Pydantic schemas untuk validasi request dan response**

- `LinkedInRequest`: Input payload
- `CertificateItem`: Single certificate entity
- `ScrapeResult`: Internal result structure

### `scraper/config.py`
**Konstanta dan konfigurasi global**

- `COOKIES_FILE`: Path ke file cookies
- `user_agents()`: Pool user agent untuk rotasi
- `random_user_agent()`: Pick random UA

### `scraper/browser.py`
**Browser setup dan stealth configuration**

- `launch_browser()`: Launch Chromium dengan flags anti-detection
- `new_context()`: Create browser context dengan headers realistis
- `apply_stealth()`: Inject script untuk patch fingerprints

### `scraper/cookies_auth.py`
**Cookie management dan auth detection**

- `load_cookies()`: Load dan sanitize cookies dari file
- `apply_cookies()`: Apply ke browser context
- `check_login_status()`: Deteksi authwall/guest mode

### `scraper/navigation.py`
**Navigation helpers dan human behavior simulation**

- `goto_with_retry()`: Navigate dengan retry logic
- `human_behavior()`: Simulasi gerakan mouse dan scroll
- `smooth_scroll_to()`: Scroll ke elemen tertentu
- `stabilize_detail_view()`: Trigger lazy-loading dengan scroll incremental

### `scraper/selectors.py`
**Strategi menemukan section dan button**

- `find_cert_section()`: Find "Licenses & Certifications" section dengan multiple fallbacks
- `find_show_all_button()`: Find tombol "Show all" yang visible

### `scraper/extraction.py`
**Parse dan extract certificate data**

- `extract_items()`: Extract certificates dari scope tertentu
- Filter visible elements (avoid honeypots)
- Normalisasi dates, issuer, verify links

### `scraper/response.py`
**Response builder untuk API contract**

- `build_response()`: Compose success response
- `build_error()`: Compose error response

### `scraper/logging.py`
**Debug utilities**

- `add_debug()`: Append debug tag
- `save_debug_files()`: Save screenshot + HTML ke `/tmp`

---

## Keamanan & Best Practices

### 🔒 Security Considerations

#### 1. Cookie Protection
- ✅ Cookies TIDAK pernah di-log ke console atau file
- ✅ Restrict domain ke `.linkedin.com` only
- ✅ Sanitize whitespace/newlines dari cookie values
- ❌ JANGAN commit `cookies.json` ke Git (sudah di `.gitignore`)
- ❌ JANGAN share cookies dengan pihak eksternal

#### 2. Rate Limiting & Commercial Use
LinkedIn membatasi jumlah profile view:
- **Akun Gratis**: ~300-500 views/month
- **Premium**: ~1000+ views/month
- **Sales Navigator**: Unlimited commercial use

**Rekomendasi:**
- Gunakan akun Sales Navigator untuk production
- Implement rate limiting di n8n workflow (delay antar request)
- Monitor "Commercial Use Limit" warning

#### 3. IP & Proxy Strategy
- Gunakan **Residential Proxies** untuk scale (bukan Data Center IPs)
- Rotate proxies per request via `proxy` field
- Hindari scraping dari IP Telkom corporate langsung (bisa di-block)

### 🛡️ Anti-Detection Best Practices

#### 1. Avoid Honeypots
- ✅ Module `extraction.py` filter elemen dengan `is_visible()`
- ✅ Skip elemen dengan `display:none` atau `opacity:0`

#### 2. Dynamic Class Names
- ✅ Gunakan text-based selectors (`get_by_text`, `has_text`)
- ✅ Gunakan aria-label, data attributes, role
- ❌ JANGAN rely on generated class names (`.artdeco-btn__xyz123`)

#### 3. Lazy Loading
- ✅ `stabilize_detail_view()` scroll incremental (1/3, 2/3, bottom)
- ✅ Wait for `networkidle` + element visibility
- ❌ JANGAN instant scroll ke footer

#### 4. Browser Fingerprinting
- ✅ `apply_stealth()` patch `navigator.webdriver`
- ✅ Mock plugins, languages, permissions
- ✅ Random user agent per request

#### 5. Human Behavior Simulation
- ✅ Random mouse movements sebelum scroll
- ✅ Random delays antar actions
- ✅ Smooth scroll dengan animation

### ⚖️ Legal & Compliance

**PENTING**: Scraping LinkedIn melanggar Terms of Service mereka.

- ✅ **Hanya gunakan untuk internal research** (bukan komersial)
- ✅ **Data harus diamankan** (sesuai kebijakan rahasia perusahaan)
- ✅ **Jangan re-publish** data ke public
- ✅ **Respect rate limits** dan jangan overload server LinkedIn
- ❌ **JANGAN jual data** hasil scraping

---

## Troubleshooting

### ❌ Problem: "li_at cookie not found"

**Cause**: File `cookies.json` tidak ada atau tidak mengandung cookie `li_at`

**Solution**:
1. Pastikan file `cookies.json` ada di folder `python_service/`
2. Check format JSON valid
3. Pastikan ada cookie dengan `name: "li_at"`
4. Re-export cookies dari browser yang sudah login

### ❌ Problem: "GUEST_MODE - Limited access"

**Cause**: Cookies expired atau invalid

**Solution**:
1. Login ulang ke LinkedIn di browser
2. Export cookies baru
3. Replace `cookies.json` dengan cookies fresh
4. Restart service

### ❌ Problem: "Certificate section not found"

**Cause**: 
- Profile tidak punya section sertifikat
- Selector berubah (LinkedIn update UI)
- Page belum fully loaded

**Solution**:
1. Enable `debug: true` untuk lihat screenshots di `/tmp/`
2. Check apakah profile memang punya certificates
3. Increase `max_wait` jadi 30000-40000
4. Try `detail_only: true` untuk langsung ke detail page

### ❌ Problem: "Navigation failed: Timeout"

**Cause**: Network slow atau LinkedIn down

**Solution**:
1. Check internet connection
2. Try dengan proxy
3. Increase `max_wait`
4. Coba beberapa kali (retry logic)

### ❌ Problem: Captcha atau Auth Wall

**Cause**: Terlalu banyak request atau IP suspicious

**Solution**:
1. **Tunggu 24 jam** sebelum retry
2. Gunakan residential proxy
3. Reduce scraping frequency
4. Check "Commercial Use Limit" di LinkedIn account

### ❌ Problem: Hasil kosong padahal ada certificates

**Cause**: Lazy loading belum triggered atau selector miss

**Solution**:
1. Set `detail_only: true` untuk force detail page
2. Increase `max_wait` jadi 35000+
3. Enable `debug: true` dan check HTML output
4. Report selector issue (LinkedIn mungkin update UI)

---

## Development & Testing

### Run Tests (Future)

```bash
# Unit tests
pytest tests/test_selectors.py -v

# Integration tests
pytest tests/test_integration.py -v
```

### Debug Mode

Enable debug untuk mendapatkan screenshots dan HTML:

```json
{
  "url": "https://www.linkedin.com/in/username",
  "debug": true
}
```

Artifacts akan disimpan di `/tmp/`:
- `/tmp/landing_[timestamp].png`
- `/tmp/landing_[timestamp].html`
- `/tmp/guest_mode_[timestamp].png` (jika guest)
- `/tmp/no_results_[timestamp].png` (jika empty)

---

## Roadmap & Future Improvements

- [ ] Add fixtures untuk regression testing
- [ ] Metrics & observability (Prometheus/Grafana)
- [ ] Support multiple LinkedIn locales (EN, ID, etc)
- [ ] Batch processing endpoint (multiple profiles)
- [ ] Redis cache untuk hasil scraping
- [ ] Webhook callback untuk async processing
- [ ] Auto cookie refresh mechanism

---

## Support & Contact

Untuk pertanyaan atau issue:
1. Check troubleshooting section di atas
2. Enable `debug: true` untuk diagnostics
3. Review `/tmp/` screenshots
4. Contact tim development Telkom

---

## License

Internal use only - Telkom Indonesia  
Confidential & Proprietary

**⚠️ DO NOT DISTRIBUTE OUTSIDE ORGANIZATION**
