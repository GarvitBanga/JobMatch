# 🔄 **Bulk-Scanner Complete Workflow & Architecture**

## 📋 **System Overview**

The Bulk-Scanner Résumé Matcher is a **Chrome Extension + FastAPI Backend** system that:
1. **Scans** company career pages
2. **Extracts** job listings automatically  
3. **Matches** jobs against user's résumé
4. **Ranks** results by relevance score
5. **Displays** top matches with one-click links

---

## 🏗 **Complete Architecture**

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   CHROME BROWSER    │     │    BACKEND API      │     │   DATA PROCESSING   │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│                     │     │                     │     │                     │
│ ┌─────────────────┐ │     │ ┌─────────────────┐ │     │ ┌─────────────────┐ │
│ │  React Popup    │ │────▶│ │  FastAPI Server │ │────▶│ │ Job Extraction  │ │
│ │  (Extension UI) │ │     │ │  (Port 8000)    │ │     │ │ Content Script  │ │
│ └─────────────────┘ │     │ └─────────────────┘ │     │ └─────────────────┘ │
│         │           │     │         │           │     │         │           │
│ ┌─────────────────┐ │     │ ┌─────────────────┐ │     │ ┌─────────────────┐ │
│ │ Background      │ │◄────│ │ CORS Middleware │ │◄────│ │ Resume Matching │ │
│ │ Service Worker  │ │     │ │ Request Handler │ │     │ │ Skill Analysis  │ │
│ └─────────────────┘ │     │ └─────────────────┘ │     │ └─────────────────┘ │
│         │           │     │         │           │     │         │           │
│ ┌─────────────────┐ │     │ ┌─────────────────┐ │     │ ┌─────────────────┐ │
│ │ Content Script  │ │     │ │ Mock Data       │ │     │ │ Score Ranking   │ │
│ │ (Page Scanner)  │ │     │ │ Response JSON   │ │     │ │ Results Format  │ │
│ └─────────────────┘ │     │ └─────────────────┘ │     │ └─────────────────┘ │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

---

## 🔄 **Complete Workflow - Step by Step**

### **Phase 1: Extension Setup & Initialization**

#### 1.1 Extension Installation
```javascript
// When user installs extension
chrome.runtime.onInstalled.addListener((details) => {
  // Set default configuration
  chrome.storage.sync.set({
    apiEndpoint: 'http://localhost:8000/api/v1',
    autoScan: false,
    matchThreshold: 70
  });
});
```

#### 1.2 Backend Server Startup
```bash
# Terminal Command
cd backend/
python main_simple.py

# Server Process
uvicorn.run("main_simple:app", host="0.0.0.0", port=8000, reload=True)
```

**API Endpoints Available:**
- `GET /` - Root endpoint
- `GET /health` - Health check  
- `POST /api/v1/scan/page` - Job scanning endpoint
- `GET /docs` - Interactive API documentation

---

### **Phase 2: User Interaction Flow**

#### 2.1 User Opens Career Page
```
User navigates to: https://careers.google.com/jobs
```

#### 2.2 User Clicks Extension Icon
```javascript
// Extension popup opens (React app loads)
// App.tsx component mounts and calls:
useEffect(() => {
  getCurrentTab();
}, []);

const getCurrentTab = async () => {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  setCurrentUrl(tabs[0].url);
};
```

#### 2.3 User Clicks "Scan This Page"
```javascript
const handleScanPage = async () => {
  setIsScanning(true);
  
  // Step 1: Get current tab
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const currentTab = tabs[0];
  
  // Step 2: Inject content script
  await chrome.scripting.executeScript({
    target: { tabId: currentTab.id },
    files: ['content.js']
  });
  
  // Step 3: Send message to content script
  const response = await chrome.tabs.sendMessage(currentTab.id, {
    type: 'EXTRACT_CONTENT'
  });
  
  // Step 4: Send to background script for API call
  const matchResult = await chrome.runtime.sendMessage({
    type: 'SCAN_PAGE',
    data: { url: currentTab.url, pageContent: response }
  });
};
```

---

### **Phase 3: Content Extraction Process**

#### 3.1 Content Script Injection
```javascript
// content.js gets injected into the career page
console.log('Content script loaded on:', window.location.href);

// Message listener setup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'EXTRACT_CONTENT') {
    const content = extractPageContent();
    sendResponse(content);
  }
});
```

#### 3.2 Job Extraction Logic
```javascript
function extractJobListings() {
  const jobs = [];
  
  // Scan for job listing elements
  const jobSelectors = [
    '[data-testid*="job"]',
    '.job-item', '.job-listing', '.position',
    'a[href*="/job"]', 'a[href*="/position"]'
  ];
  
  jobSelectors.forEach(selector => {
    const elements = document.querySelectorAll(selector);
    elements.forEach(element => {
      const job = extractJobFromElement(element);
      if (job && job.title) jobs.push(job);
    });
  });
  
  return jobs;
}

function extractJobFromElement(element) {
  return {
    title: element.querySelector('h1, h2, h3, .job-title')?.textContent,
    company: element.querySelector('.company, .company-name')?.textContent,
    location: element.querySelector('.location, .job-location')?.textContent,
    url: element.querySelector('a')?.href || window.location.href,
    description: element.querySelector('.description, .summary')?.textContent
  };
}
```

---

### **Phase 4: Backend API Processing**

#### 4.1 Background Script API Call
```javascript
async function handleScanPage(data, sendResponse) {
  const { url, pageContent } = data;
  
  // Get user settings
  const settings = await chrome.storage.sync.get(['apiEndpoint', 'resumeText']);
  const apiEndpoint = settings.apiEndpoint || 'http://localhost:8000/api/v1';
  
  // Prepare request payload
  const requestData = {
    url: url,
    user_id: 'chrome-extension-user',
    page_content: pageContent,
    resume_text: settings.resumeText || null,
    match_threshold: 0.7
  };
  
  // HTTP POST Request
  const response = await fetch(`${apiEndpoint}/scan/page`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
  });
  
  const result = await response.json();
  sendResponse(result);
}
```

#### 4.2 FastAPI Endpoint Processing
```python
@app.post("/api/v1/scan/page")
async def scan_page_mock():
    """Mock scan endpoint that returns sample data"""
    return {
        "success": True,
        "message": "Found 2 matching jobs",
        "jobs_found": 5,
        "matches": [
            {
                "id": "1",
                "title": "Senior Software Engineer",
                "company": "Tech Corp",
                "location": "San Francisco, CA",
                "url": "https://example.com/job/1",
                "match_score": 92,
                "skills": ["React", "TypeScript", "Node.js"],
                "summary": "Excellent match for your React and TypeScript experience"
            }
        ],
        "processing_time_ms": 245
    }
```

---

### **Phase 5: Results Display & User Actions**

#### 5.1 Results Rendering
```javascript
// App.tsx receives results and renders
{matchedJobs.map((job) => (
  <div key={job.id} className="border rounded-lg p-3">
    <h3 className="font-medium">{job.title}</h3>
    <p className="text-gray-600">{job.company}</p>
    <span className={`px-2 py-1 rounded-full ${
      job.matchScore >= 90 ? 'bg-green-100 text-green-800' :
      job.matchScore >= 80 ? 'bg-blue-100 text-blue-800' :
      'bg-yellow-100 text-yellow-800'
    }`}>
      {job.matchScore}% match
    </span>
    <button onClick={() => openJob(job.url)}>
      View Job →
    </button>
  </div>
))}
```

#### 5.2 User Actions
```javascript
const openJob = (url) => {
  chrome.tabs.create({ url }); // Opens job in new tab
};

const openSettings = () => {
  chrome.runtime.openOptionsPage(); // Opens settings page
};
```

---

## 📡 **API Call Details**

### **Request Flow**
```
Chrome Extension → Background Script → HTTP POST → FastAPI Server
```

### **Request Payload**
```json
{
  "url": "https://careers.google.com/jobs",
  "user_id": "chrome-extension-user",
  "page_content": {
    "title": "Google Careers",
    "jobs": [
      {
        "title": "Software Engineer",
        "company": "Google",
        "location": "Mountain View, CA",
        "url": "https://careers.google.com/jobs/123",
        "description": "Build amazing products..."
      }
    ]
  },
  "resume_text": "Software engineer with React experience...",
  "match_threshold": 0.7
}
```

### **Response Payload**
```json
{
  "success": true,
  "message": "Found 2 matching jobs",
  "jobs_found": 5,
  "matches": [
    {
      "id": "1",
      "title": "Senior Software Engineer",
      "company": "Tech Corp",
      "location": "San Francisco, CA",
      "url": "https://example.com/job/1",
      "match_score": 92,
      "skills": ["React", "TypeScript", "Node.js"],
      "summary": "Excellent match for your React and TypeScript experience"
    }
  ],
  "processing_time_ms": 245
}
```

---

## 🔧 **Technical Implementation Details**

### **Frontend (Chrome Extension)**
- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS
- **Build**: Create React App with custom modifications
- **Chrome APIs**: tabs, storage, scripting, runtime
- **Communication**: Message passing between popup, background, content scripts

### **Backend (FastAPI)**
- **Framework**: FastAPI with async support
- **Server**: Uvicorn ASGI server
- **CORS**: Configured for Chrome extension origins
- **Endpoints**: RESTful API with automatic documentation
- **Response**: JSON with standardized structure

### **Communication Protocol**
- **Extension ↔ Background**: Chrome runtime messaging
- **Background ↔ API**: HTTP/HTTPS requests
- **Content ↔ Extension**: Chrome tabs messaging
- **Error Handling**: Graceful fallbacks with mock data

---

## 🚀 **Data Flow Diagram**

```
USER ACTION
    │
    ▼
┌─────────────────┐
│  Chrome Popup   │ ──┐
│  (React UI)     │   │
└─────────────────┘   │
                      │ chrome.runtime.sendMessage()
                      ▼
              ┌─────────────────┐
              │ Background      │
              │ Service Worker  │ ──┐
              └─────────────────┘   │
                      │             │ chrome.tabs.sendMessage()
                      │             ▼
               fetch() │     ┌─────────────────┐
                      │     │ Content Script  │
                      │     │ (Page Scanner)  │
                      │     └─────────────────┘
                      │             │
                      │             │ DOM Extraction
                      │             ▼
                      │     ┌─────────────────┐
                      │     │ Job Listings    │
                      │     │ {title, company}│
                      │     └─────────────────┘
                      │             │
                      │             │ Return data
                      ▼             ▼
              ┌─────────────────┐
              │ FastAPI Server  │
              │ localhost:8000  │
              └─────────────────┘
                      │
                      │ Process + Match
                      ▼
              ┌─────────────────┐
              │ JSON Response   │
              │ {matches: [...]}│
              └─────────────────┘
                      │
                      │ HTTP Response
                      ▼
              ┌─────────────────┐
              │ Background      │
              │ Receives Data   │
              └─────────────────┘
                      │
                      │ sendResponse()
                      ▼
              ┌─────────────────┐
              │ React UI        │
              │ Displays Jobs   │
              └─────────────────┘
```

---

## 🎯 **Current Status & What's Working**

### ✅ **Fully Functional Components**
1. **Chrome Extension Installation** - Loads in browser
2. **React Popup Interface** - Beautiful UI with Tailwind
3. **Background Service Worker** - Handles API communication  
4. **Content Script Injection** - Extracts page content
5. **FastAPI Backend Server** - Serves requests on port 8000
6. **API Communication** - HTTP requests between extension and server
7. **Mock Data Processing** - Returns sample job matches
8. **Error Handling** - Graceful fallbacks when API unavailable
9. **Settings Management** - User can configure API endpoint
10. **Cross-Origin Requests** - CORS properly configured

### 🔄 **Mock/Simulated Components**
1. **Job Extraction** - Returns sample jobs (not real scraping yet)
2. **Resume Matching** - Fixed match scores (no real AI yet)
3. **Skills Analysis** - Predefined skill lists
4. **Processing Time** - Simulated timing

### 📋 **Not Yet Implemented**
1. **Real Web Scraping** - Actual job extraction from diverse sites
2. **Resume Upload & Parsing** - PDF/DOCX file processing
3. **LLM Integration** - OpenAI API for intelligent matching
4. **Vector Database** - FAISS for semantic similarity
5. **PostgreSQL** - Persistent data storage
6. **User Authentication** - Individual user accounts
7. **Job History** - Tracking past searches
8. **Advanced Filtering** - Salary, location, experience filters

---

## 🚀 **How to Test Everything**

### 1. **Start Backend**
```bash
cd backend/
python main_simple.py
# ✅ Server running on http://localhost:8000
```

### 2. **Load Extension**
```
Chrome → chrome://extensions/ → Load unpacked → select extension/build/
# ✅ Extension loaded and pinned to toolbar
```

### 3. **Test API Directly**
```bash
curl -X POST "http://localhost:8000/api/v1/scan/page" \
  -H "Content-Type: application/json" \
  -d '{"url": "test", "user_id": "test"}'
# ✅ Returns mock job data
```

### 4. **Test Extension End-to-End**
```
1. Go to careers.google.com
2. Click extension icon
3. Click "Scan This Page"
4. ✅ See matched jobs with scores
```

### 5. **Debug & Monitor**
```
Extension Logs: chrome://extensions/ → Inspect views: service worker
API Logs: Terminal running python main_simple.py
Network: Chrome DevTools → Network tab
```

---

## 🔧 **Next Development Priorities**

### **Immediate (Phase 2)**
1. **Fix Full Backend** - Debug import issues in `main.py`
2. **Real Job Scraping** - Implement actual extraction
3. **Basic Resume Processing** - Text file upload

### **Short Term (Phase 3)**  
1. **LLM Integration** - OpenAI API for smart matching
2. **Database Setup** - PostgreSQL for persistence
3. **Advanced Parsing** - PDF/DOCX resume support

### **Long Term (Phase 4)**
1. **Production Deployment** - Docker + Cloud hosting
2. **User Management** - Authentication & profiles  
3. **Advanced Features** - Auto-apply, notifications, analytics

---

**🎉 The system is now fully documented and ready for development! Every API call, data flow, and process is mapped out above.** 