# LinkedIn Certificate Scraper

A powerful web scraping tool that automatically extracts professional certifications and licenses from LinkedIn profiles. Built with Python, Playwright, and FastAPI.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.40+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

- **Cross-Platform** - Works on Windows, macOS, and Linux
- **Web UI Interface** - Clean, intuitive browser-based interface
- **Batch Processing** - Upload CSV/Excel files with multiple LinkedIn URLs
- **Single URL Scraping** - Quick scraping of individual profiles
- **Persistent Session** - Uses persistent browser context to maintain login state across runs
- **CDP Integration** - Optional Chrome DevTools Protocol support for advanced use
- **SDUI Extraction** - Handles LinkedIn's new SDUI (Server-Driven UI) layout
- **Human-like Behavior** - Implements realistic scrolling and delays to avoid detection
- **Stealth Mode** - Bypasses bot detection with anti-automation techniques
- **Export to CSV** - Download results in CSV format for further analysis

## Demo

```
┌─────────────────────────────────────────────────────────────┐
│  LinkedIn Certificate Scraper                               │
│                                                             │
│  Step 1: Open LinkedIn                                      │
│  [Open LinkedIn in Chrome]                                  │
│                                                             │
│  Step 2: Scrape Certificates                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Upload CSV/Excel or enter LinkedIn URL              │   │
│  └─────────────────────────────────────────────────────┘   │
│  [Start Scraping]                                           │
│                                                             │
│  Results                               [Download CSV]       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ URL          │ Certificates                         │   │
│  │ linkedin.com │ [{name: "AWS", issuer: "Amazon"}]    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Browser Automation | Playwright, Playwright-Stealth |
| Data Processing | Pandas, BeautifulSoup4, lxml |
| Data Validation | Pydantic |
| Frontend | Embedded HTML/CSS/JavaScript |

## Installation

### Prerequisites

- Python 3.10 or higher
- Google Chrome browser installed
- Git (for cloning)

### Quick Setup

**macOS / Linux:**
```bash
# Clone the repository
git clone https://github.com/yourusername/linkedin_certification_scraper.git
cd linkedin_certification_scraper

# Run the installer
./install needs
```

**Windows (PowerShell):**
```powershell
# Clone the repository
git clone https://github.com/yourusername/linkedin_certification_scraper.git
cd linkedin_certification_scraper

# Run the installer
.\install.ps1 needs
```

The installer will:
1. Create a Python virtual environment
2. Install all required dependencies
3. Download Playwright browsers (Chromium)

## Usage

### Starting the Application

**macOS / Linux:**
```bash
./run application
```

**Windows (PowerShell):**
```powershell
.\run.ps1 application
```

This command will:
- Start Chrome with CDP (Chrome DevTools Protocol) on port 9222
- Launch the web UI server on http://127.0.0.1:8787
- Open the UI in your default browser

### Scraping Workflow

1. **Initial Login** - Run `save_cookies.py` once to log in to LinkedIn:
   ```bash
   python save_cookies.py
   ```
   A Chrome window will open. Log in to your LinkedIn account. The session will be saved to `browser_data/` automatically.
2. **Enter URLs** - Either:
   - Use the Web UI to upload a CSV/Excel file or enter URLs
   - Use the CLI: `python scraper.py "https://www.linkedin.com/in/username/"`
3. **Start Scraping** - Results are returned as JSON with certificate details
4. **Download** - View results in the web UI table and download as CSV

### CLI Usage

```bash
# Scrape a single profile
python scraper.py "https://www.linkedin.com/in/username/"

# The scraper will:
# 1. Use persistent session from browser_data/
# 2. Navigate to the profile
# 3. Extract all certificates with names, issuers, dates, and credential IDs
# 4. Output results as JSON
```

### Stopping the Application

**macOS / Linux:**
```bash
./stop
```

**Windows (PowerShell):**
```powershell
.\stop.ps1
```

## Project Structure

```
linkedin_certification_scraper/
├── linkedin_scraper_pkg/       # Core scraping modules
│   ├── __init__.py
│   ├── browser.py              # Browser launch & persistent context
│   ├── config.py               # Configuration settings
│   ├── cookies_auth.py         # Cookie-based authentication
│   ├── extraction.py           # Certificate data extraction (SDUI + legacy)
│   ├── models.py               # Pydantic data models
│   ├── navigation.py           # Page navigation & scrolling
│   ├── response.py             # Response formatting
│   ├── scraper_logging.py      # Debug logging utilities
│   └── selectors.py            # DOM element selectors
├── ui_app.py                   # FastAPI web UI application
├── run_ui.py                   # Application launcher with CDP
├── scraper.py                  # CLI interface
├── save_cookies.py             # Login helper (run once for initial setup)
├── install                     # Installation script (macOS/Linux)
├── install.ps1                 # Installation script (Windows)
├── run                         # Start script (macOS/Linux)
├── run.ps1                     # Start script (Windows)
├── stop                        # Stop script (macOS/Linux)
├── stop.ps1                    # Stop script (Windows)
├── example.csv                 # Example input file
└── requirements.txt            # Python dependencies
```

## Configuration

Environment variables can be used to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `UI_HOST` | `127.0.0.1` | Web UI host address |
| `UI_PORT` | `8787` | Web UI port |
| `SCRAPER_CDP_PORT` | `9222` | Chrome CDP port |
| `SCRAPER_USE_CDP` | `true` | Enable CDP mode |
| `CHROME_PATH` | Auto-detect | Custom Chrome executable path |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI interface |
| `POST` | `/api/open-linkedin` | Open LinkedIn in CDP browser |
| `POST` | `/api/scrape` | Scrape certificates from URLs |

### Example API Usage

```bash
# Open LinkedIn in Chrome
curl -X POST http://127.0.0.1:8787/api/open-linkedin

# Scrape a single profile
curl -X POST http://127.0.0.1:8787/api/scrape \
  -F "url=https://www.linkedin.com/in/username/"

# Scrape from file
curl -X POST http://127.0.0.1:8787/api/scrape \
  -F "file=@profiles.csv"
```

## Output Format

The scraper extracts the following certificate information:

```json
{
  "certificate_name": "AWS Certified Solutions Architect",
  "credential_id": "ABC123XYZ",
  "issuer": "Amazon Web Services",
  "issue_date": "Jan 2024",
  "expiry_date": "Jan 2027",
  "verify_link": "https://...",
  "source": "DetailView"
}
```

## Troubleshooting

### Chrome CDP not connecting

**macOS / Linux:**
```bash
./stop
pkill -f "Google Chrome"
./run application
```

**Windows (PowerShell):**
```powershell
.\stop.ps1
Get-Process chrome | Stop-Process -Force
.\run.ps1 application
```

### Port already in use

**macOS / Linux:**
```bash
lsof -i :8787
lsof -i :9222
./stop
./run application
```

**Windows (PowerShell):**
```powershell
netstat -ano | findstr :8787
netstat -ano | findstr :9222
.\stop.ps1
.\run.ps1 application
```

### LinkedIn blocking requests

- Ensure you're logged in to LinkedIn in the CDP Chrome window
- The scraper uses human-like behavior, but excessive scraping may trigger rate limits
- Wait a few minutes between large batch operations

### Windows: PowerShell Execution Policy

If you get an error about scripts being disabled, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Limitations

- Requires active LinkedIn login session
- Subject to LinkedIn's terms of service
- Rate limiting may apply for large-scale scraping
- Some profiles may have restricted visibility

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is intended for personal use and educational purposes only. Users are responsible for ensuring their use of this tool complies with LinkedIn's Terms of Service and applicable laws. The author is not responsible for any misuse of this tool.

## Author

**farhanrenardi**

- GitHub: [@farhanrenardi](https://github.com/farhanrenardi)
- LinkedIn: [Farhan Faiq Renardi](https://www.linkedin.com/in/farhanfaiq)

---

⭐ If you find this project useful, please consider giving it a star!
