#!/bin/bash

echo "🧹 Starting repository cleanup for Chrome Extension deployment..."

# Remove test files
echo "Removing test files..."
rm -f test_*.py
rm -f debug_*.py
rm -f simple_test.py

# Remove duplicate/backup files
echo "Removing duplicate files..."
rm -f main_simple_previous.py
rm -f "main_simple copy.py"
rm -f enhanced_content_script.js
rm -f "extension/public/content copy.js"
rm -f extension/public/content-enhanced.js

# Remove test data files
echo "Removing test data files..."
rm -f test_extension_results.js
rm -f test_batch_request_debug.json
rm -f test_batch_request.json
rm -f test-batch-processing.html
rm -f test-amazon-career-page.html
rm -f test-job-page.html

# Remove excessive documentation (keep essential ones)
echo "Removing excessive documentation..."
rm -f ENHANCED_JOB_EXTRACTION.md
rm -f GROQ_SETUP.md
rm -f BATCH_PROCESSING_ENHANCEMENT.md
rm -f DEPLOYMENT_COMPLETE.md
rm -f DEPLOYMENT_AND_TESTING_GUIDE.md
rm -f CROSS_ORIGIN_ENHANCEMENT.md
rm -f CAREER_SITES_COMPATIBILITY.md
rm -f EXTENSION_FLOW_DETAILED.md
rm -f DEPLOYMENT_STRATEGY.md
rm -f ENHANCED_SYSTEM_SUMMARY.md
rm -f LLM_ENHANCED_WORKFLOW.md
rm -f DEMO_SCRIPT.md
rm -f COMPLETION_CHECKLIST.md
rm -f COMPLETE_WORKFLOW.md

# Remove system files
echo "Removing system files..."
rm -f .DS_Store
rm -f extension/.DS_Store
rm -rf __pycache__/
rm -rf extension/__pycache__/

# Remove unnecessary extension files
echo "Cleaning extension directory..."
cd extension/public
rm -f robots.txt
cd ../..

# Remove node_modules if present (will be rebuilt)
echo "Removing node_modules..."
rm -rf extension/node_modules/

# Remove build directories (will be rebuilt)
echo "Removing build directories..."
rm -rf extension/build/
rm -rf build/

# Clean up other unnecessary directories
echo "Removing unnecessary directories..."
rm -rf public/
rm -rf src/
rm -rf app/
rm -rf matcher/
rm -rf parser/
rm -rf scraper/
rm -rf infra/

# Remove unnecessary config files
echo "Removing unnecessary config files..."
rm -f tailwind.config.js
rm -f package-lock.json
rm -f package.json

echo "✅ Repository cleanup complete!"
echo ""
echo "📁 Remaining essential files:"
echo "├── backend/ (complete backend application)"
echo "├── extension/public/ (Chrome extension files)"
echo "├── main_simple.py (main backend server)"
echo "├── selenium_job_extractor.py (job extraction logic)"
echo "├── requirements.txt (Python dependencies)"
echo "├── docker-compose.yml (Docker setup)"
echo "├── Dockerfile (Docker build)"
echo "├── .gitignore (Git ignore rules)"
echo "├── README.md (Project documentation)"
echo "└── REPOSITORY_CLEANUP_PLAN.md (this cleanup plan)"
echo ""
echo "⚠️  NEXT STEPS REQUIRED:"
echo "1. Implement rate limiting and authentication"
echo "2. Add API key management system"
echo "3. Create privacy policy and terms of service"
echo "4. Test extension with production backend"
echo "5. Prepare Chrome Web Store submission"
echo ""
echo "🔒 SECURITY WARNING:"
echo "Current system has NO rate limiting - implement before public release!" 