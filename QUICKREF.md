# LinkedIn Scraper - Quick Reference

## Quick Start

### Test the Three Provided URLs
```bash
python3 test_scraper_urls.py
```

### Scrape a Single Profile
```bash
python3 scraper.py "https://www.linkedin.com/in/username/" --output result.json
```

### Diagnose Issues
```bash
python3 diagnose.py "https://www.linkedin.com/in/username/"
```

### Use Web Interface
```bash
./run application
# Opens http://127.0.0.1:8787
```

## Common Issues & Solutions

### "No certificates found"
**Try:**
1. Run diagnostic: `python3 diagnose.py "URL"`
2. Check if login required (see screenshots)
3. Use CDP mode with manual login

### "Connection refused" (CDP mode)
**Solution:**
```bash
./stop
./run application
```

### "Name resolution failed"
**Check:**
```bash
ping linkedin.com
# If fails, check firewall/network
```

## Output Files

### Test Script
- `/tmp/linkedin_scraper_test_results.json` - Test results

### Diagnostic Tool
- `/tmp/{profile}_main.png` - Main page screenshot
- `/tmp/{profile}_main.html` - Main page HTML
- `/tmp/{profile}_details.png` - Details page screenshot
- `/tmp/{profile}_diagnostic.json` - Full diagnostic report

## Success Indicators

### Good Signs
```
✅ Landed on Details Page
✅ Section Found via: Header_Text
🔥 Locked on selector: li.pvs-list__paged-list-item
✅ Extracted item 0: Certificate Name
🎉 SUCCESS: Found N items
```

### Warning Signs
```
⚠️ Redirect detected
⚠️ Guest Mode Detected
⚠️ No items found
❌ All section detection strategies failed
```

## Files to Check

| Issue | Check This File |
|-------|-----------------|
| No certificates found | `IMPROVEMENTS.md` → Troubleshooting |
| Script errors | `SUMMARY.md` → Testing Instructions |
| Technical details | `IMPROVEMENTS.md` → Full documentation |
| General usage | `README.md` → User guide |

## Configuration

### Environment Variables
```bash
# Optional: Custom CDP port
export SCRAPER_CDP_PORT=9222

# Optional: Custom cookies file
export LINKEDIN_COOKIES_PATH="./cookies.json"

# Optional: Enable CDP by default
export SCRAPER_USE_CDP=true
```

### Command Line Options
```bash
# Scraper CLI
python3 scraper.py <URL> \
  --output result.json \
  --cookies ./cookies.json
```

## Important Notes

⚠️ **Authentication:** Most profiles require LinkedIn login for full data
⚠️ **Rate Limits:** Don't scrape too aggressively
⚠️ **Terms of Service:** Ensure compliance with LinkedIn ToS
✅ **Multiple Strategies:** Scraper tries 15+ different detection methods
✅ **Fallbacks:** 3 strategies: details page → main profile → show all

## Getting Help

1. **Run Diagnostic First:**
   ```bash
   python3 diagnose.py "URL"
   ```

2. **Check Output:**
   - Screenshots show what LinkedIn returned
   - HTML file shows actual page structure
   - JSON report shows what was attempted

3. **Read Documentation:**
   - `IMPROVEMENTS.md` - Detailed troubleshooting
   - `SUMMARY.md` - Implementation overview
   - `README.md` - User guide

4. **Report Issues:**
   Include diagnostic JSON and screenshots

## Test URLs

The scraper was improved to handle these specific profiles:
1. https://www.linkedin.com/in/bella-harum-ashari-2ba7b7115/
2. https://www.linkedin.com/in/dimas-ewin-ashari-b4aba9138/
3. https://www.linkedin.com/in/najibfaqihfathan/

## Improvements Summary

| Feature | Improvement |
|---------|-------------|
| Item Selectors | 9 → 12 (+33%) |
| Name Strategies | 1 → 6 (+500%) |
| Section Patterns | ~3 → ~15 (+400%) |
| Scroll Time | ~5s → ~13s (+160%) |

## Quick Troubleshooting

```bash
# 1. Is LinkedIn accessible?
ping linkedin.com

# 2. Are dependencies installed?
pip3 install -r requirements.txt
playwright install chromium

# 3. Does test work?
python3 test_scraper_urls.py

# 4. What's wrong with specific URL?
python3 diagnose.py "URL"

# 5. Check the output
ls -la /tmp/*diagnostic* /tmp/*_main.png
```

## Pro Tips

💡 Use CDP mode with manual login for best results
💡 Run diagnostic tool before asking for help  
💡 Check screenshots to see what LinkedIn shows
💡 Wait 2-3 seconds between profile scrapes
💡 The scraper tries multiple strategies automatically

---

**For detailed information, see:**
- `IMPROVEMENTS.md` - Full technical documentation
- `SUMMARY.md` - Implementation overview
- `README.md` - Complete user guide
