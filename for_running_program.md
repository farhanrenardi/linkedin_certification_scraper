# Panduan Lengkap: Install & Jalankan Program End-to-End

Program ini menggunakan n8n workflow + FastAPI python_service + PostgreSQL + Chrome DevTools (CDP) untuk scraping LinkedIn certificates.

---

## Table of Contents
- [A. macOS](#a-macos)
- [Cleanup / Matikan Stack (macOS)](#cleanup-macos)
- [B. Windows](#b-windows)
- [Cleanup / Matikan Stack (Windows)](#cleanup-windows)
- [Troubleshooting](#troubleshooting)
- [Catatan Penting](#catatan-penting)

---

## **A. macOS**

### 1. **Install Dependencies**

- **Homebrew** (jika belum):
  ```sh
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

- **Docker Desktop**:  
  Download & install dari https://www.docker.com/products/docker-desktop/

- **socat** (untuk port forwarding Chrome DevTools):
  ```sh
  brew install socat
  ```

- **Make** (biasanya sudah ada, jika belum):
  ```sh
  brew install make
  ```

### 2. **Clone Repo & Setup Environment**

```sh
git clone <repo-url>
cd telkom_n8n
```

Pastikan file `.env` ada. Jika tidak, create/copy dari `.env.example`:
```sh
cp .env.example .env   # atau salin manual jika tidak ada
```

Edit `.env` jika perlu mengubah port, password, timezone, dsb.

### 3. **Start Chrome DevTools di Host**

Jalankan Chrome dengan remote debugging (di terminal baru):
```sh
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="/tmp/chrome_debug_profile"
```

Biarkan Chrome window terbuka. **Jangan tutup terminal ini** selama scraping.

### 4. **Setup Port Forwarding (socat)**

Jalankan di terminal baru (agar Chrome tetap aktif):
```sh
socat TCP-LISTEN:9223,bind=0.0.0.0,reuseaddr,fork TCP:localhost:9222
```

Ini relay port 9223 (dari container) ke 9222 (Chrome host).  
**Jangan tutup terminal ini** selama scraping.

### 5. **Jalankan Stack Docker**

Di terminal baru, jalankan:
```sh
make up
```

Atau manual:
```sh
docker compose -p n8n-stack up -d
```

Cek status container:
```sh
make ps
```

Seharusnya ada 3 container: `n8n_app`, `n8n_db`, `python_service` (semua `Up`).

### 6. **Test Koneksi Chrome DevTools**

Verifikasi Chrome DevTools bisa diakses:

- **Dari host**:
  ```sh
  curl http://localhost:9223/json/version/
  ```

- **Dari container** (pastikan `host.docker.internal` resolve):
  ```sh
  docker exec python_service curl http://host.docker.internal:9223/json/version/
  ```

Jika hasilnya JSON atau error "Host header is specified...", berarti koneksi OK.

### 7. **Login LinkedIn di Chrome Host**

- Buka Chrome window yang sudah berjalan (DevTools aktif).
- Login ke LinkedIn menggunakan akun Anda.
- Session ini akan digunakan oleh CDP saat scraping.

### 8. **Akses n8n & Setup Workflow**

Buka browser: http://localhost:5678

Login dengan credential di `.env`:
- **User**: `farhan`
- **Password**: `farhann8n` (atau sesuai `.env`)

#### Setup HTTP Request Node:
Pastikan node HTTP Request ke python_service sudah ada dengan konfigurasi:

- **URL**: `http://python_service:8000/scrape/linkedin`
- **Method**: `POST`
- **Body** (JSON):
  ```json
  {
    "url": "{{ $json.input_url }}",
    "use_cdp": true,
    "cdp_url": "http://host.docker.internal:9223",
    "headless": false,
    "max_wait": 30000,
    "debug": false
  }
  ```

### 9. **Eksekusi Workflow**

- Trigger workflow di n8n (misal, dengan button `Execute workflow`).
- Lihat Chrome window untuk proses scraping real-time.
- Hasil akan muncul di n8n nodes sebagai response.

### 10. **Debugging & Logs**

Jika ada error:

- **Logs python_service**:
  ```sh
  docker logs python_service -f
  ```

- **Logs n8n**:
  ```sh
  make logs
  ```

- **Check Docker resources**:
  ```sh
  docker stats
  ```

<a id="cleanup-macos"></a>
### 11. **Cleanup / Matikan Stack**

```sh
make down
pkill -f "Google Chrome.*9222"
pkill -f "socat.*9223"
```

---

## **B. Windows**

### 1. **Install Dependencies**

- **Docker Desktop**:  
  Download & install dari https://www.docker.com/products/docker-desktop/

- **Git Bash** (untuk terminal/make/bash command):  
  Download dari https://gitforwindows.org/

- **Make** (biasanya ada di Git Bash):  
  Jika tidak, buka Git Bash dan jalankan:
  ```sh
  pacman -S make
  ```

- **socat** (untuk port forwarding):  
  Download Windows binary dari https://github.com/andrew-d/socat-windows/releases  
  Ekstrak ke folder (misal: `C:\tools\socat\`), tambahkan ke Windows PATH.

### 2. **Clone Repo & Setup Environment**

Buka Git Bash atau PowerShell:

```sh
git clone <repo-url>
cd telkom_n8n
```

Copy `.env` (jika ada `.env.example`):
```cmd
copy .env.example .env
```

Edit `.env` dengan Notepad/VS Code jika perlu.

### 3. **Start Chrome DevTools di Host**

Jalankan di Command Prompt / PowerShell (terminal baru):

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\chrome_debug_profile"
```

Atau cari path Chrome jika lokasi berbeda:
```cmd
where chrome
```

Biarkan Chrome window terbuka. **Jangan tutup terminal ini** selama scraping.

### 4. **Setup Port Forwarding (socat)**

Jalankan di Command Prompt / PowerShell (terminal baru):

```cmd
C:\tools\socat\socat.exe TCP-LISTEN:9223,bind=0.0.0.0,reuseaddr,fork TCP:localhost:9222
```

(Sesuaikan path `socat.exe` dengan lokasi ekstraksi)

**Jangan tutup terminal ini** selama scraping.

### 5. **Jalankan Stack Docker**

Buka Git Bash atau PowerShell:

```sh
make up
```

Atau manual:
```sh
docker compose -p n8n-stack up -d
```

Cek status:
```sh
make ps
```

Seharusnya ada 3 container: `n8n_app`, `n8n_db`, `python_service` (semua `Up`).

### 6. **Test Koneksi Chrome DevTools**

- **Dari host** (PowerShell / Git Bash):
  ```sh
  curl http://localhost:9223/json/version/
  ```

- **Dari container**:
  ```sh
  docker exec python_service curl http://host.docker.internal:9223/json/version/
  ```

Jika hasilnya JSON atau error "Host header is specified...", koneksi OK.

### 7. **Login LinkedIn di Chrome Host**

- Buka Chrome window yang sudah berjalan (DevTools aktif).
- Login ke LinkedIn menggunakan akun Anda.
- Session ini akan digunakan oleh CDP saat scraping.

### 8. **Akses n8n & Setup Workflow**

Buka browser: http://localhost:5678

Login dengan credential di `.env`:
- **User**: `farhan`
- **Password**: `farhann8n` (atau sesuai `.env`)

#### Setup HTTP Request Node:
Pastikan node HTTP Request ke python_service sudah ada dengan konfigurasi:

- **URL**: `http://python_service:8000/scrape/linkedin`
- **Method**: `POST`
- **Body** (JSON):
  ```json
  {
    "url": "{{ $json.input_url }}",
    "use_cdp": true,
    "cdp_url": "http://host.docker.internal:9223",
    "headless": false,
    "max_wait": 30000,
    "debug": false
  }
  ```

### 9. **Eksekusi Workflow**

- Trigger workflow di n8n (misal, dengan button `Execute workflow`).
- Lihat Chrome window untuk proses scraping real-time.
- Hasil akan muncul di n8n nodes sebagai response.

### 10. **Debugging & Logs**

Jika ada error:

- **Logs python_service**:
  ```sh
  docker logs python_service -f
  ```

- **Logs n8n**:
  ```sh
  docker logs n8n_app -f
  ```

- **Check Docker resources**:
  ```sh
  docker stats
  ```

<a id="cleanup-windows"></a>
### 11. **Cleanup / Matikan Stack**

```sh
make down
```

Tutup Chrome & socat manual:
```cmd
taskkill /IM chrome.exe /F
taskkill /IM socat.exe /F
```

---

## **Troubleshooting**

| Masalah | Solusi |
|---------|--------|
| Chrome DevTools tidak connect | Pastikan `--remote-debugging-port=9222` aktif & socat berjalan |
| `host.docker.internal` tidak resolve | Update Docker Desktop ke versi terbaru |
| Port 5678 (n8n) sudah digunakan | Ubah `N8N_PORT` di `.env` |
| Port 8000 (python_service) sudah digunakan | Build ulang dengan port baru di `docker-compose.yml` |
| Container crash/error | Cek logs: `docker logs <container_name> -f` |
| Scraping timeout | Naikkan `max_wait` di request body n8n |

---

## **Catatan Penting**

- **Do NOT close** Chrome window, socat, atau any Docker containers selama scraping berjalan.
- Container akses Chrome via `host.docker.internal:9223` (bukan 9222).
- Chrome di host tetap listen di 9222; socat relay 9223 -> 9222.
- n8n URL: http://localhost:5678
- python_service URL: http://localhost:8000
- PostgreSQL: localhost:5432 (jika akses dari host)