from __future__ import annotations

import asyncio
import io
import json
import csv
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from scraper import scrape_linkedin
from linkedin_scraper_pkg.models import LinkedInRequest
from linkedin_scraper_pkg.config import CDP_URL
from linkedin_scraper_pkg.browser import connect_over_cdp


app = FastAPI(title="LinkedIn Certificate Scraper UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LinkedIn Certificate Scraper</title>
  <style>
    :root {
      --bg: #f8fafc;
      --surface: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --primary: #2563eb;
      --secondary: #16a34a;
      --accent: #7c3aed;
      --border: #e2e8f0;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 0;
    }
    .page {
      max-width: 700px;
      margin: 0 auto;
      padding: 32px 20px 60px;
    }
    .hero {
      text-align: center;
      margin-bottom: 24px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 28px;
      color: var(--primary);
    }
    .hero p {
      margin: 0;
      color: var(--muted);
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .card h2 {
      margin: 0 0 16px;
      font-size: 18px;
    }
    .field {
      margin-bottom: 16px;
    }
    .field label {
      display: block;
      font-weight: 600;
      margin-bottom: 6px;
      font-size: 14px;
    }
    .field input[type="text"],
    .field input[type="url"],
    .field input[type="file"] {
      width: 100%;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
    }
    .field .hint {
      font-size: 12px;
      color: var(--muted);
      margin-top: 4px;
    }
    .divider {
      text-align: center;
      color: var(--muted);
      font-weight: 600;
      padding: 8px 0;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    button {
      padding: 12px 24px;
      border: none;
      border-radius: 8px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    button:hover { opacity: 0.9; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-primary { background: var(--primary); color: white; }
    .btn-accent { background: var(--accent); color: white; }
    .btn-secondary { background: var(--secondary); color: white; }
    
    #status {
      margin-top: 16px;
      padding: 12px;
      border-radius: 8px;
      font-weight: 500;
      display: none;
    }
    #status.show { display: block; }
    #status.info { background: #dbeafe; color: #1e40af; }
    #status.error { background: #fee2e2; color: #991b1b; }
    #status.success { background: #dcfce7; color: #166534; }
    
    #loading {
      display: none;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      color: var(--primary);
      font-weight: 500;
    }
    #loading.show { display: flex; }
    .spinner {
      width: 20px;
      height: 20px;
      border: 3px solid var(--border);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    #result-section {
      display: none;
    }
    #result-section.show { display: block; }
    
    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .result-header h2 { margin: 0; }
    
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border: 1px solid var(--border);
      padding: 10px;
      text-align: left;
      vertical-align: top;
    }
    th {
      background: #f1f5f9;
      font-weight: 600;
    }
    td pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
      max-height: 200px;
      overflow-y: auto;
    }
    .table-wrapper {
      max-height: 400px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>LinkedIn Certificate Scraper</h1>
      <p>Extract certificates from LinkedIn profiles easily.</p>
    </div>

    <div class="card">
      <h2>Step 1: Open LinkedIn</h2>
      <p style="color: var(--muted); margin: 0 0 16px; font-size: 14px;">
        Click the button below to open LinkedIn in the Chrome CDP window. Log in if needed.
      </p>
      <button type="button" id="btn-open-linkedin" class="btn-accent">Open LinkedIn in Chrome</button>
      <div id="linkedin-status" class="status"></div>
    </div>

    <div class="card">
      <h2>Step 2: Scrape Certificates</h2>
      <form id="scrape-form">
        <div class="field">
          <label>Upload CSV or Excel file</label>
          <input type="file" id="file-input" name="file" accept=".csv,.xlsx,.xls" />
          <div class="hint">File should contain LinkedIn profile URLs</div>
        </div>
        <div class="divider">OR</div>
        <div class="field">
          <label>LinkedIn Profile URL</label>
          <input type="url" id="url-input" name="url" placeholder="https://www.linkedin.com/in/username/" />
        </div>
        <div class="actions">
          <button type="submit" id="btn-scrape" class="btn-primary">Start Scraping</button>
        </div>
      </form>
      <div id="status"></div>
      <div id="loading"><span class="spinner"></span> Scraping in progress... Please wait.</div>
    </div>

    <div id="result-section" class="card">
      <div class="result-header">
        <h2>Results</h2>
        <button type="button" id="btn-download" class="btn-secondary">Download CSV</button>
      </div>
      <div class="table-wrapper">
        <table id="result-table">
          <thead>
            <tr><th>LinkedIn URL</th><th>Certificates</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const btnOpenLinkedin = document.getElementById('btn-open-linkedin');
    const btnScrape = document.getElementById('btn-scrape');
    const btnDownload = document.getElementById('btn-download');
    const scrapeForm = document.getElementById('scrape-form');
    const fileInput = document.getElementById('file-input');
    const urlInput = document.getElementById('url-input');
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');
    const resultSection = document.getElementById('result-section');
    const resultTableBody = document.querySelector('#result-table tbody');
    
    let lastResults = [];

    function showStatus(msg, type = 'info') {
      statusEl.textContent = msg;
      statusEl.className = 'show ' + type;
    }

    function hideStatus() {
      statusEl.className = '';
    }

    function showLoading(show) {
      loadingEl.className = show ? 'show' : '';
    }

    function showResults(rows) {
      lastResults = rows;
      resultTableBody.innerHTML = '';
      if (!rows || rows.length === 0) {
        resultTableBody.innerHTML = '<tr><td colspan="2">No certificates found.</td></tr>';
      } else {
        rows.forEach(row => {
          const tr = document.createElement('tr');
          const certs = typeof row.certificate_list === 'string' 
            ? row.certificate_list 
            : JSON.stringify(row.certificate_list, null, 2);
          tr.innerHTML = '<td>' + (row.url_linkedin || row.url || '-') + '</td><td><pre>' + certs + '</pre></td>';
          resultTableBody.appendChild(tr);
        });
      }
      resultSection.className = 'card show';
    }

    // Open LinkedIn button
    btnOpenLinkedin.addEventListener('click', async () => {
      btnOpenLinkedin.disabled = true;
      btnOpenLinkedin.textContent = 'Opening...';
      try {
        const res = await fetch('/api/open-linkedin', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          btnOpenLinkedin.textContent = 'LinkedIn Opened ✓';
          setTimeout(() => {
            btnOpenLinkedin.textContent = 'Open LinkedIn in Chrome';
            btnOpenLinkedin.disabled = false;
          }, 2000);
        } else {
          btnOpenLinkedin.textContent = 'Failed - Try Again';
          setTimeout(() => {
            btnOpenLinkedin.textContent = 'Open LinkedIn in Chrome';
            btnOpenLinkedin.disabled = false;
          }, 2000);
          console.error(data.error);
        }
      } catch (err) {
        btnOpenLinkedin.textContent = 'Error - Try Again';
        setTimeout(() => {
          btnOpenLinkedin.textContent = 'Open LinkedIn in Chrome';
          btnOpenLinkedin.disabled = false;
        }, 2000);
        console.error(err);
      }
    });

    // Scrape form submit
    scrapeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const hasFile = fileInput.files && fileInput.files.length > 0;
      const hasUrl = urlInput.value.trim() !== '';
      
      if (!hasFile && !hasUrl) {
        showStatus('Please upload a file or enter a LinkedIn URL.', 'error');
        return;
      }
      
      hideStatus();
      showLoading(true);
      btnScrape.disabled = true;
      resultSection.className = 'card';
      
      try {
        const formData = new FormData();
        if (hasFile) {
          formData.append('file', fileInput.files[0]);
        }
        if (hasUrl) {
          formData.append('url', urlInput.value.trim());
        }
        
        const res = await fetch('/api/scrape', {
          method: 'POST',
          body: formData
        });
        
        if (!res.ok) {
          const err = await res.json();
          showStatus(err.error || 'Scraping failed.', 'error');
          showLoading(false);
          btnScrape.disabled = false;
          return;
        }
        
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('text/csv')) {
          // File upload returns CSV directly - convert to display
          const text = await res.text();
          const lines = text.trim().split('\\n');
          const rows = [];
          for (let i = 1; i < lines.length; i++) {
            const parts = lines[i].split(',');
            rows.push({
              url_linkedin: parts[0] || '',
              certificate_list: parts.slice(1).join(',') || ''
            });
          }
          showResults(rows);
          showStatus('Scraping completed! ' + rows.length + ' profile(s) processed.', 'success');
        } else {
          const data = await res.json();
          showResults(data.rows || []);
          showStatus('Scraping completed!', 'success');
        }
      } catch (err) {
        showStatus('Unexpected error: ' + err.message, 'error');
        console.error(err);
      } finally {
        showLoading(false);
        btnScrape.disabled = false;
      }
    });

    // Download CSV button
    btnDownload.addEventListener('click', () => {
      if (!lastResults || lastResults.length === 0) {
        alert('No results to download.');
        return;
      }
      
      let csvContent = 'url_linkedin,certificate_list\\n';
      lastResults.forEach(row => {
        const url = row.url_linkedin || row.url || '';
        let certs = row.certificate_list || '';
        if (typeof certs !== 'string') {
          certs = JSON.stringify(certs);
        }
        // Escape quotes and wrap in quotes
        certs = '"' + certs.replace(/"/g, '""') + '"';
        csvContent += url + ',' + certs + '\\n';
      });
      
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'linkedin_certificates.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  </script>
</body>
</html>
"""


def _extract_urls_from_dataframe(df: pd.DataFrame) -> List[str]:
    if df.empty:
        return []
    candidate_columns = [c for c in df.columns if "url" in c.lower() or "linkedin" in c.lower()]
    col = candidate_columns[0] if candidate_columns else df.columns[0]
    series = df[col].dropna().astype(str)
    urls = []
    for raw in series:
        value = raw.strip()
        if not value or value.lower() == 'nan':
            continue
        if "linkedin.com" not in value.lower():
            continue
        if not value.startswith("http"):
            value = f"https://{value}"
        urls.append(value)
    return urls


async def _scrape_single_url(url: str) -> dict:
    req = LinkedInRequest(
        url=url,
        debug=False,
        headless=False,
        max_wait=30000,
        detail_only=False,
        use_cdp=True,
        cdp_url=CDP_URL,
    )
    result = await scrape_linkedin(req)
    certs = result.get("certificates_list", [])
    return {
        "url_linkedin": url,
        "certificate_list": certs if certs != "not found" else []
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(HTML_PAGE)


@app.post("/api/open-linkedin")
async def open_linkedin() -> JSONResponse:
    try:
        browser = await asyncio.wait_for(connect_over_cdp(CDP_URL), timeout=10)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=15000)
        return JSONResponse({"ok": True})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=500, content={"error": "Connection timeout. Make sure Chrome CDP is running."})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/scrape")
async def scrape(
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
) -> JSONResponse:
    urls_to_scrape = []
    
    # Handle file upload
    if file and file.filename:
        try:
            content = await file.read()
            if file.filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(content))
            else:
                df = pd.read_excel(io.BytesIO(content))
            urls_to_scrape = _extract_urls_from_dataframe(df)
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Failed to parse file: {str(e)}"})
    
    # Handle single URL
    if url and url.strip():
        clean_url = url.strip()
        if not clean_url.startswith("http"):
            clean_url = f"https://{clean_url}"
        if clean_url not in urls_to_scrape:
            urls_to_scrape.append(clean_url)
    
    if not urls_to_scrape:
        return JSONResponse(status_code=400, content={"error": "No valid LinkedIn URLs found."})
    
    # Scrape all URLs
    results = []
    for u in urls_to_scrape:
        try:
            result = await _scrape_single_url(u)
            results.append(result)
        except Exception as e:
            results.append({
                "url_linkedin": u,
                "certificate_list": f"Error: {str(e)}"
            })
    
    return JSONResponse({"rows": results})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
