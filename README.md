# Bulk-Scanner Résumé Matcher

A Chrome Extension + cloud backend that scans multiple company career sites, parses job descriptions, matches them against a user's résumé, and surfaces the top roles with relevance scores.

## Project Structure

- `extension/` — Chrome extension (React + Tailwind) ✅ **COMPLETED**
- `backend/`   — FastAPI API Gateway, Celery, SQLModel 🚧 **IN PROGRESS**
- `scraper/`   — Playwright scraping service 📋 **TODO**
- `parser/`    — JD and résumé parsing 📋 **TODO**
- `matcher/`   — Embedding, FAISS, LLM logic 📋 **TODO**
- `infra/`     — Docker Compose, Terraform, CI/CD 📋 **TODO**

## Progress Status

### ✅ Chrome Extension (COMPLETED)
- ✅ React + TypeScript + Tailwind CSS setup
- ✅ Chrome Manifest V3 configuration
- ✅ Popup UI with job scanning interface
- ✅ Background service worker for handling requests
- ✅ Content script for extracting page content
- ✅ Options page for settings management
- ✅ Chrome APIs integration (tabs, storage, scripting)

**Ready to test:** Load `extension/build/` as unpacked extension in Chrome

### 🚧 Backend API (IN PROGRESS)
- Scaffolding FastAPI application
- Setting up Celery for background jobs
- Database models with SQLModel
- API endpoints for job scanning

### 📋 TODO Components
- Playwright scraping service
- Job description parsing
- Résumé parsing integration
- LLM-powered matching logic
- Vector embeddings with FAISS
- PostgreSQL + Redis setup
- Docker containerization
- CI/CD pipeline

## Quick Start

### Chrome Extension
```bash
cd extension
npm install
npm run build
# Load extension/build/ in Chrome (chrome://extensions → Load unpacked)
```

### Testing the Extension
1. Navigate to a company career page (e.g., Google Careers, Microsoft Jobs)
2. Click the extension icon
3. Click "Scan This Page"
4. View matched jobs (currently shows mock data)

## Development Plan

**Next Steps:**
1. ✅ ~~Chrome Extension scaffold~~
2. 🚧 **FastAPI backend setup (Current)**
3. 📋 Playwright scraping service
4. 📋 Job description parsing
5. 📋 LLM integration for matching
6. 📋 Database setup
7. 📋 Docker containerization 