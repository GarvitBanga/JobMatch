# JobMatch Chrome Extension Deployment Guide

## 🚀 Complete Deployment Steps

### Phase 1: Backend Deployment Options

#### Option A: Railway (Recommended - Easy & Free)
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login to Railway
railway login

# 3. Initialize project
railway init

# 4. Deploy
railway up
```

**Pros**: Free tier, automatic HTTPS, easy setup
**Cons**: Limited free hours (500/month)

#### Option B: Render (Alternative - Free)
1. Go to [render.com](https://render.com)
2. Connect your GitHub repository
3. Create new "Web Service"
4. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main_simple.py`
   - **Environment**: Python 3

#### Option C: DigitalOcean App Platform
1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Create new app from GitHub
3. Configure:
   - **Source**: Your GitHub repo
   - **Type**: Web Service
   - **Run Command**: `python main_simple.py`

#### Option D: Heroku (Paid)
```bash
# 1. Install Heroku CLI
# 2. Create Procfile
echo "web: python main_simple.py" > Procfile

# 3. Deploy
heroku create jobmatch-backend
git push heroku main
```

### Phase 2: Backend Configuration Changes

#### 1. Update CORS Settings

In `main_simple.py`, change the CORS configuration for production:

```python
# BEFORE (Development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AFTER (Production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://*",  # Allow all Chrome extensions
        "https://your-domain.com",  # Your website if any
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

#### 2. Update Server Configuration

Add this to the end of `main_simple.py`:

```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
```

#### 3. Create Environment Variables

Create `.env` file for local testing:
```bash
# .env
OPENAI_API_KEY=your_openai_key_here
PORT=8000
HOST=0.0.0.0
```

For production deployment, set these environment variables in your hosting platform.

### Phase 3: Chrome Extension Configuration

#### 1. Update Extension Manifest

Update `extension/public/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "JobMatch - AI Resume Matcher",
  "version": "1.0.0",
  "description": "AI-powered job matching that analyzes career sites and matches positions to your resume",
  "permissions": [
    "activeTab",
    "storage",
    "scripting"
  ],
  "host_permissions": [
    "https://your-backend-domain.com/*"
  ],
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content.js"]
    }
  ],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "index.html",
    "default_title": "JobMatch",
    "default_icon": {
      "16": "logo192.png",
      "48": "logo192.png",
      "128": "logo512.png"
    }
  },
  "icons": {
    "16": "logo192.png",
    "48": "logo192.png",
    "128": "logo512.png"
  }
}
```

#### 2. Update Backend URL in Extension

Find and update the backend URL in your extension files:

**In `extension/public/content.js`:**
```javascript
// BEFORE
const API_BASE_URL = 'http://localhost:8000';

// AFTER
const API_BASE_URL = 'https://your-backend-domain.com';
```

**In `extension/public/popup.js` and other files:**
```javascript
// Update all instances of localhost:8000 to your production URL
const BACKEND_URL = 'https://your-backend-domain.com';
```

### Phase 4: Repository Cleanup

#### 1. Run Cleanup Script
```bash
chmod +x cleanup_repository.sh
./cleanup_repository.sh
```

#### 2. Create Production Files

**Create `Procfile` for Heroku:**
```
web: python main_simple.py
```

**Create `runtime.txt` for Python version:**
```
python-3.10.9
```

**Update `.gitignore`:**
```
# Environment variables
.env
.env.local
.env.production

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Test files
test_*.py
debug_*.py
```

### Phase 5: Deployment Steps

#### Step 1: Deploy Backend

**Option A: Railway (Recommended)**
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize and deploy
railway init
railway up

# 4. Set environment variables
railway variables set OPENAI_API_KEY=your_key_here
```

**Option B: Render**
1. Push code to GitHub
2. Go to [render.com](https://render.com)
3. Create "New Web Service"
4. Connect GitHub repo
5. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main_simple.py`
   - **Environment Variables**: Add `OPENAI_API_KEY`

#### Step 2: Test Backend Deployment

```bash
# Test health endpoint
curl https://your-backend-domain.com/health

# Test API endpoint
curl -X POST https://your-backend-domain.com/api/v1/scan/page \
  -H "Content-Type: application/json" \
  -d '{"url": "test", "user_id": "test", "page_content": {"title": "Test"}}'
```

#### Step 3: Update Extension Configuration

1. Update all backend URLs in extension files
2. Test extension locally with production backend
3. Package extension for Chrome Web Store

#### Step 4: Package Chrome Extension

```bash
cd extension/public
zip -r ../../jobmatch-extension.zip \
  manifest.json \
  content.js \
  background.js \
  popup.js \
  options.js \
  storage-manager.js \
  index.html \
  options.html \
  *.png \
  favicon.ico
```

### Phase 6: Chrome Web Store Submission

#### 1. Developer Account Setup
1. Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. Pay $5 one-time registration fee
3. Verify your identity

#### 2. Prepare Store Assets

**Required Assets:**
- **Extension ZIP**: `jobmatch-extension.zip`
- **Screenshots**: 1280x800 pixels (at least 1, max 5)
- **Icons**: 128x128 pixels
- **Privacy Policy**: Required for data handling
- **Detailed Description**: Clear explanation of functionality

**Store Listing Example:**
```
Name: JobMatch - AI Resume Matcher
Category: Productivity
Summary: AI-powered job matching for career sites

Description:
JobMatch automatically analyzes job postings on career websites and matches them against your resume using advanced AI. Get instant compatibility scores, skill matching, and personalized recommendations.

Features:
• AI-powered job analysis
• Resume compatibility scoring
• Skills gap identification
• Works on major job sites
• Privacy-focused design

How to use:
1. Upload your resume in extension settings
2. Visit any career website
3. Click the JobMatch extension
4. Get instant job compatibility analysis
```

#### 3. Privacy Policy (Required)

Create a privacy policy covering:
- What data is collected (resume content, job descriptions)
- How data is used (AI matching, analysis)
- Data storage (temporary processing only)
- Third-party services (OpenAI API)
- User rights and contact information

#### 4. Submit for Review

1. Upload extension ZIP file
2. Add store listing information
3. Upload screenshots and assets
4. Submit for review (1-3 days processing time)

### Phase 7: User API Key Strategy

#### Option A: User-Provided API Keys (Recommended)

**Extension Settings Page:**
```html
<!-- In options.html -->
<div class="api-key-section">
  <h3>OpenAI API Configuration</h3>
  <p>To use AI-powered job matching, please provide your OpenAI API key:</p>
  <input type="password" id="openai-api-key" placeholder="sk-...">
  <button id="save-api-key">Save API Key</button>
  <p class="help-text">
    <a href="https://platform.openai.com/api-keys" target="_blank">
      Get your API key from OpenAI
    </a>
  </p>
</div>
```

**Update Extension to Use User API Keys:**
```javascript
// In content.js or popup.js
async function getApiKey() {
  const result = await chrome.storage.sync.get(['openai_api_key']);
  return result.openai_api_key;
}

async function makeApiRequest(data) {
  const apiKey = await getApiKey();
  if (!apiKey) {
    throw new Error('Please configure your OpenAI API key in extension settings');
  }
  
  return fetch(`${BACKEND_URL}/api/v1/scan/page`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...data,
      user_api_key: apiKey
    })
  });
}
```

### Phase 8: Testing & Launch

#### Pre-Launch Checklist
- [ ] Backend deployed and accessible
- [ ] Extension connects to production backend
- [ ] Rate limiting working properly
- [ ] User API key flow functional
- [ ] Privacy policy published
- [ ] Store assets prepared
- [ ] Extension tested on major job sites

#### Launch Strategy
1. **Soft Launch**: Submit to Chrome Web Store (private testing)
2. **Beta Testing**: Share with 10-20 users for feedback
3. **Public Launch**: Make extension public on Chrome Web Store
4. **Marketing**: Share on relevant communities and social media

### Phase 9: Monitoring & Maintenance

#### Set Up Monitoring
```python
# Add to main_simple.py
import logging
from datetime import datetime

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# Track usage metrics
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(f"Request: {request.method} {request.url} - "
               f"Status: {response.status_code} - "
               f"Time: {process_time:.3f}s")
    
    return response
```

#### Regular Maintenance Tasks
- Monitor server logs and performance
- Update dependencies regularly
- Respond to user feedback and bug reports
- Monitor Chrome Web Store reviews
- Track usage analytics

## 🎯 Quick Start Commands

```bash
# 1. Clean repository
./cleanup_repository.sh

# 2. Deploy to Railway
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set OPENAI_API_KEY=your_key

# 3. Update extension backend URL
# Edit extension/public/content.js and other files

# 4. Package extension
cd extension/public
zip -r ../../jobmatch-extension.zip manifest.json *.js *.html *.png favicon.ico

# 5. Submit to Chrome Web Store
# Go to https://chrome.google.com/webstore/devconsole
```

## 💰 Cost Estimates

**Free Tier Deployment:**
- Railway: 500 hours/month free
- Render: 750 hours/month free
- User-provided OpenAI keys: $0 cost to you

**Expected Usage:**
- 1000 users × 10 requests/day = 10,000 requests/day
- Server cost: ~$5-10/month after free tier
- OpenAI cost: $0 (users pay directly)

Your JobMatch extension is now ready for public deployment! 🚀 