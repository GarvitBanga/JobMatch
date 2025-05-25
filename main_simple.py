#!/usr/bin/env python3
"""
Enhanced FastAPI server with resume processing and LLM integration
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import os
import logging
import requests
from bs4 import BeautifulSoup
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict
import traceback

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# 🚀 RATE LIMITING: Simple in-memory rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)  # {user_id: [timestamp1, timestamp2, ...]}
        self.openai_requests = defaultdict(list)  # Separate tracking for OpenAI calls
    
    def is_allowed(self, user_id: str, max_requests: int = 50, window_hours: int = 24) -> bool:
        """Check if user is within general rate limit"""
        now = datetime.now()
        cutoff = now - timedelta(hours=window_hours)
        
        # Clean old requests
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id] 
            if req_time > cutoff
        ]
        
        # Check if under limit
        if len(self.requests[user_id]) >= max_requests:
            return False
        
        # Record this request
        self.requests[user_id].append(now)
        return True
    
    def is_openai_allowed(self, user_id: str, max_openai_calls: int = 10, window_hours: int = 24) -> bool:
        """Check if user is within OpenAI API call limit"""
        now = datetime.now()
        cutoff = now - timedelta(hours=window_hours)
        
        # Clean old OpenAI requests
        self.openai_requests[user_id] = [
            req_time for req_time in self.openai_requests[user_id] 
            if req_time > cutoff
        ]
        
        # Check if under OpenAI limit
        if len(self.openai_requests[user_id]) >= max_openai_calls:
            return False
        
        # Record this OpenAI request
        self.openai_requests[user_id].append(now)
        return True
    
    def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get current usage statistics for a user"""
        now = datetime.now()
        cutoff_24h = now - timedelta(hours=24)
        cutoff_1h = now - timedelta(hours=1)
        
        # Count requests in last 24h and 1h
        requests_24h = len([r for r in self.requests[user_id] if r > cutoff_24h])
        requests_1h = len([r for r in self.requests[user_id] if r > cutoff_1h])
        
        openai_24h = len([r for r in self.openai_requests[user_id] if r > cutoff_24h])
        openai_1h = len([r for r in self.openai_requests[user_id] if r > cutoff_1h])
        
        return {
            "requests_last_24h": requests_24h,
            "requests_last_hour": requests_1h,
            "openai_calls_last_24h": openai_24h,
            "openai_calls_last_hour": openai_1h,
            "openai_limit_24h": 10,
            "general_limit_24h": 50
        }
    
    def record_openai_call(self, user_id: str) -> None:
        """Record an OpenAI call for rate limiting purposes"""
        now = datetime.now()
        self.openai_requests[user_id].append(now)
        logger.info(f"📊 Recorded OpenAI call for user {user_id}. Total today: {len(self.openai_requests[user_id])}")

# Global rate limiter instance
rate_limiter = RateLimiter()

# Import our resume processing services
try:
    from backend.app.services.resume_service import ResumeProcessor, JobMatcher
except ImportError:
    # Fallback if import fails
    ResumeProcessor = None
    JobMatcher = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Bulk-Scanner Résumé Matcher API",
    description="Backend API for Chrome extension that matches job descriptions against résumés",
    version="1.0.1",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
# Production CORS configuration for Chrome extensions
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "chrome-extension://*,http://localhost:3000")

# Handle Chrome extension origins properly
if "chrome-extension://*" in allowed_origins_env:
    # Allow all origins for Chrome extensions (they use unique extension IDs)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Chrome extensions need this
        allow_credentials=False,  # Must be False when allow_origins=["*"]
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
else:
    # Use specific origins for other deployments
    allowed_origins = allowed_origins_env.split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

# Pydantic models
class ScanPageRequest(BaseModel):
    url: str
    user_id: str
    page_content: Dict[str, Any]
    resume_text: Optional[str] = None
    resume_data: Optional[Dict[str, Any]] = None
    match_threshold: float = 0.4
    batch_processing: bool = True  # New field for batch processing

class BatchJobMatchRequest(BaseModel):
    jobs: List[Dict[str, Any]]
    resume_data: Dict[str, Any]
    user_id: str
    match_threshold: float = 0.4
    max_results: int = 10

class JobMatch(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    match_score: int
    matching_skills: List[str]
    missing_skills: List[str] = []
    summary: str
    confidence: str = "medium"
    ai_analysis: Optional[str] = None  # New field for detailed AI analysis
    rank: Optional[int] = None  # New field for ranking

class ScanPageResponse(BaseModel):
    success: bool
    message: str
    jobs_found: int
    matches: List[JobMatch]
    processing_time_ms: int
    processing_method: str = "mock"

# Global services (initialized with environment variables)
resume_processor = None
job_matcher = None

def get_resume_processor():
    """Get or create resume processor instance"""
    global resume_processor
    if resume_processor is None:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if ResumeProcessor:
            resume_processor = ResumeProcessor(openai_api_key=openai_api_key)
        else:
            logger.warning("ResumeProcessor not available - using mock processing")
    return resume_processor

def get_job_matcher():
    """Get or create job matcher instance"""
    global job_matcher
    if job_matcher is None:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if JobMatcher:
            job_matcher = JobMatcher(openai_api_key=openai_api_key)
        else:
            logger.warning("JobMatcher not available - using mock matching")
    return job_matcher

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Bulk-Scanner Résumé Matcher API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Enhanced health check that includes LLM service status"""
    try:
        # Check basic app status
        status = {
        "status": "healthy", 
            "timestamp": time.time(),
            "services": {}
        }
        
        # Check OpenAI availability
        if os.getenv("OPENAI_API_KEY"):
            status["services"]["openai"] = "available"
        else:
            status["services"]["openai"] = "not_configured"
            
        # Check Groq availability
        if os.getenv("GROQ_API_KEY"):
            status["services"]["groq"] = "available"
        else:
            status["services"]["groq"] = "not_configured"
            
        # Check Selenium WebDriver
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # Quick test - don't actually create driver
            status["services"]["selenium"] = "available"
        except Exception as e:
            status["services"]["selenium"] = f"error: {str(e)}"
        
        return status
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/usage/{user_id}")
async def get_user_usage(user_id: str, request: Request):
    """
    Check rate limiting status for a user
    """
    try:
        client_ip = request.client.host
        user_identifier = f"{user_id}_{client_ip}"
        
        usage_stats = rate_limiter.get_usage_stats(user_identifier)
        
        return {
            "success": True,
            "user_id": user_id,
            "ip": client_ip,
            "usage": usage_stats,
            "limits": {
                "general_requests_per_24h": 50,
                "openai_calls_per_24h": 10
            },
            "remaining": {
                "general_requests": max(0, 50 - usage_stats["requests_last_24h"]),
                "openai_calls": max(0, 10 - usage_stats["openai_calls_last_24h"])
            },
            "reset_time": "24 hours from first request"
        }
        
    except Exception as e:
        logger.error(f"Error getting usage stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting usage: {str(e)}")

@app.post("/api/v1/upload/resume")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = "default"
):
    """
    Upload and process a resume file (PDF, DOCX, TXT)
    Returns structured resume data
    """
    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.doc', '.docx', '.txt']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Read file content
        file_content = await file.read()
        
        # Process resume
        processor = get_resume_processor()
        if processor:
            result = await processor.process_resume_file(file_content, file.filename)
        else:
            # Fallback mock processing
            result = {
                "success": True,
                "raw_text": "Mock resume text processing",
                "structured_data": {
                    "personal_info": {"name": "John Doe", "email": "john@example.com"},
                    "skills": ["JavaScript", "React", "Node.js", "Python"],
                    "experience": [
                        {
                            "title": "Software Engineer",
                            "company": "Tech Corp",
                            "duration": "2021-2023",
                            "description": "Developed web applications",
                            "technologies": ["React", "Node.js"]
                        }
                    ],
                    "education": [],
                    "projects": [],
                    "certifications": []
                },
                "filename": file.filename,
                "processing_method": "mock"
            }
        
        return {
            "success": result.get("success", True),
            "user_id": user_id,
            "filename": file.filename,
            "file_size": len(file_content),
            "processing_method": result.get("processing_method", "mock"),
            "structured_data": result.get("structured_data", {}),
            "raw_text_preview": result.get("raw_text", "")[:200] + "..." if result.get("raw_text") else ""
        }
        
    except Exception as e:
        logger.error(f"Resume upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Resume processing failed: {str(e)}")

@app.post("/api/v1/scan/page", response_model=ScanPageResponse)
async def scan_page_with_resume(request: ScanPageRequest, http_request: Request):
    """
    Enhanced scan endpoint that supports both individual and batch processing
    """
    try:
        import time
        start_time = time.time()
        
        # 🚀 RATE LIMITING: Check if user is within limits
        client_ip = http_request.client.host
        user_identifier = f"{request.user_id}_{client_ip}"
        
        # Check general rate limit
        if not rate_limiter.is_allowed(user_identifier, max_requests=50, window_hours=24):
            usage_stats = rate_limiter.get_usage_stats(user_identifier)
            logger.warning(f"🚫 Rate limit exceeded for user {user_identifier}: {usage_stats}")
            raise HTTPException(
                status_code=429, 
                detail={
                    "error": "Rate limit exceeded",
                    "message": "You have exceeded the daily limit of 50 requests. Please try again tomorrow.",
                    "usage": usage_stats,
                    "retry_after": "24 hours"
                }
            )
        
        # Log rate limiting info
        usage_stats = rate_limiter.get_usage_stats(user_identifier)
        logger.info(f"🔒 Rate limit check passed for {user_identifier}: {usage_stats}")
        
        # Debug the request data
        logger.info(f"Request threshold: {request.match_threshold}")
        logger.info(f"Request has resume_data: {bool(request.resume_data)}")
        logger.info(f"Batch processing: {request.batch_processing}")
        
        # Extract jobs from page content
        jobs = extract_jobs_from_page_content(request.page_content, request.url)
        logger.info(f"Extracted {len(jobs)} jobs from page content")
        
        # 🔍 PRINT ALL JOB DESCRIPTIONS FOR DEBUGGING
        print("\n" + "="*80)
        print(f"📋 FETCHED JOB DESCRIPTIONS FROM {request.url}")
        print("="*80)
        
        for i, job in enumerate(jobs, 1):
            print(f"\n🔸 JOB #{i}")
            print(f"Title: {job.get('title', 'No Title')}")
            print(f"Company: {job.get('company', 'No Company')}")
            print(f"Location: {job.get('location', 'No Location')}")
            print(f"URL: {job.get('url', 'No URL')}")
            print(f"Description Length: {len(str(job.get('description', '')))}")
            print("Description:")
            print("-" * 60)
            description = job.get('description', 'No description available')
            # 🚀 SHOW MUCH MORE CONTENT - Print first 2000 characters instead of 500
            if len(description) > 2000:
                print(description[:2000])
                print("\n[Content continues... showing first 2000 characters]")
                print(f"[Total length: {len(description)} characters]")
            else:
                print(description)
            print("-" * 60)
        
        print("="*80)
        print(f"📊 TOTAL JOBS PROCESSED: {len(jobs)}")
        print("="*80 + "\n")
        
        # Check if we should use batch processing
        logger.info(f"🔍 ROUTE DEBUG: batch_processing={request.batch_processing}")
        logger.info(f"🔍 ROUTE DEBUG: resume_data available={bool(request.resume_data)}")
        logger.info(f"🔍 ROUTE DEBUG: jobs count={len(jobs)}")
        logger.info(f"🔍 ROUTE DEBUG: len(jobs) > 3 = {len(jobs) > 3}")
        
        # 🚀 ENHANCED: More flexible batch processing conditions
        should_use_batch = (
            request.batch_processing and 
            len(jobs) > 3 and
            (
                request.resume_data or  # Normal condition: has resume data
                ('amazon.jobs' in request.url.lower() and len(jobs) >= 5)  # Special case: Amazon with 5+ jobs
            )
        )
        
        if should_use_batch:
            logger.info(f"🚀 Using batch processing for {len(jobs)} jobs")
            logger.info(f"🔍 ROUTE DEBUG: CALLING BATCH_JOB_MATCHING")
            
            # Create resume data if missing (for Amazon Jobs fallback)
            resume_data_for_batch = request.resume_data or {
                "skills": ["JavaScript", "Python", "React", "AWS", "Node.js", "SQL", "Git", "Docker", "Kubernetes", "Java", "C++", "CSS"],
                "experience": [
                    {
                        "title": "Software Engineer",
                        "company": "Tech Company",
                        "duration": "2+ years",
                        "description": "Developed web applications using modern technologies",
                        "technologies": ["JavaScript", "Python", "React", "AWS", "Node.js"]
                    },
                    {
                        "title": "Junior Developer",
                        "company": "Previous Company",
                        "duration": "1 year",
                        "description": "Built responsive web interfaces and APIs",
                        "technologies": ["JavaScript", "React", "Node.js", "SQL"]
                    }
                ],
                "education": [
                    {
                        "degree": "Bachelor's",
                        "field": "Computer Science",
                        "institution": "University",
                        "year": "2020"
                    }
                ],
                "summary": "Software engineer with experience in web development and cloud technologies, skilled in modern JavaScript frameworks and backend development"
            }
            
            # Use the new batch matching endpoint internally
            batch_request = BatchJobMatchRequest(
                jobs=jobs,
                resume_data=resume_data_for_batch,
                user_id=request.user_id,
                match_threshold=request.match_threshold,
                max_results=15  # Return more results for better selection
            )
            
            # Call batch processing function directly
            return await batch_job_matching(batch_request)
        
        # Fallback to original processing for smaller job sets or when batch is disabled
        logger.info("🔍 ROUTE DEBUG: USING INDIVIDUAL PROCESSING (not batch)")
        logger.info("Using individual job processing")
        
        # Get job matcher
        matcher = get_job_matcher()
        
        # If we have resume data, use it for matching
        if request.resume_data and matcher:
            logger.info("Using real resume data for matching")
            matched_jobs = await matcher.match_jobs_with_resume(jobs, request.resume_data)
            processing_method = "llm" if os.getenv("OPENAI_API_KEY") else "similarity"
        
        elif request.resume_text and matcher:
            logger.info("Using resume text for basic matching")
            # Create basic resume data structure from text
            basic_resume_data = {
                "summary": request.resume_text[:200],
                "skills": extract_skills_from_text(request.resume_text),
                "experience": [],
                "education": []
            }
            matched_jobs = await matcher.match_jobs_with_resume(jobs, basic_resume_data)
            processing_method = "text_based"
        
        else:
            logger.info("No resume data - using mock matching")
            # Fallback to mock data
            matched_jobs = get_mock_job_matches(request.url)
            processing_method = "mock"
        
        # Filter by threshold
        threshold_score = request.match_threshold * 100
        filtered_jobs = [
            job for job in matched_jobs 
            if job.get('match_score', 0) >= threshold_score
        ]
        
        logger.info(f"Jobs after filtering: {len(filtered_jobs)}")
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return ScanPageResponse(
            success=True,
            message=f"Found {len(filtered_jobs)} matching jobs",
            jobs_found=len(jobs),
            matches=[
                JobMatch(
                    id=str(job.get('id', i)),
                    title=job.get('title', 'Unknown Title'),
                    company=job.get('company', 'Unknown Company'),
                    location=job.get('location', 'Unknown Location'),
                    url=job.get('url', request.url),
                    match_score=job.get('match_score', 50),
                    matching_skills=job.get('matching_skills', []),
                    missing_skills=job.get('missing_skills', []),
                    summary=job.get('summary', 'No analysis available'),
                    confidence=job.get('confidence', 'medium'),
                    ai_analysis=job.get('ai_analysis', ''),
                    rank=job.get('rank', i + 1)
                )
                for i, job in enumerate(filtered_jobs[:10])  # Limit to top 10
            ],
            processing_time_ms=processing_time,
            processing_method=processing_method
        )
        
    except Exception as e:
        logger.error(f"Scan page failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Page scanning failed: {str(e)}")

def extract_jobs_from_page_content(page_content: Dict[str, Any], url: str) -> List[Dict[str, Any]]:
    """Extract job listings from page content and fetch full descriptions from individual job pages"""
    
    # Debug logging
    logger.info(f"Page content received: {list(page_content.keys())}")
    logger.info(f"Page URL: {url}")
    
    # 🚀 ENHANCED DEBUG: Print what's actually in the page content
    logger.info(f"🔍 DEBUG: jobElements type: {type(page_content.get('jobElements'))}")
    logger.info(f"🔍 DEBUG: jobElements value: {page_content.get('jobElements')}")
    logger.info(f"🔍 DEBUG: jobLinks type: {type(page_content.get('jobLinks'))}")
    logger.info(f"🔍 DEBUG: jobLinks value: {page_content.get('jobLinks')}")
    
    # 🎯 NEW: Detect embedded job board platforms
    embedded_platform = detect_embedded_job_platform(url, page_content)
    if embedded_platform:
        logger.info(f"🔧 Detected embedded job platform: {embedded_platform}")
    
    # Check for enhanced content script data
    jobs_found = []
    
    # Try new enhanced format first - prioritize jobElements with structure
    job_elements = page_content.get('jobElements')
    if job_elements is not None and len(job_elements) > 0:
        logger.info(f"Found enhanced job data from content script: {len(job_elements)} elements")
        
        for i, element in enumerate(job_elements):
            # Enhanced job elements have structured data
            if isinstance(element, dict):
                job = {
                    "id": element.get('id', f"job-{i}"),
                    "title": element.get('title', 'Unknown Position'),
                    "company": element.get('company', 'Company'),
                    "location": element.get('location', 'Location TBD'),
                    "url": element.get('url', url),
                    "description": element.get('description', element.get('text', ''))[:1000]  # This is just the summary
                }
                
                # Only add jobs with meaningful titles and URLs
                if job["title"] and job["title"] not in ['Unknown Position', '', 'Amazon Position'] and job["url"]:
                    jobs_found.append(job)
                    logger.info(f"Added job: {job['title']} at {job['company']}")
                elif element.get('text') and len(element.get('text', '')) > 50:
                    # Try to extract title from text if structured data is missing
                    text = element.get('text', '')
                    lines = text.split('\n')
                    potential_title = lines[0].strip() if lines else 'Position Available'
                    
                    job["title"] = potential_title[:100]  # Limit title length
                    jobs_found.append(job)
                    logger.info(f"Added job from text: {job['title']}")
            else:
                # Fallback for old format
                logger.warning(f"Job element {i} is not a dict: {type(element)}")
    else:
        logger.warning(f"🔍 DEBUG: jobElements is None or empty: {job_elements}")
    
    # Fallback to jobLinks if no good jobElements
    job_links = page_content.get('jobLinks')
    if not jobs_found and job_links is not None and len(job_links) > 0:
        logger.info(f"Using jobLinks as fallback: {len(job_links)} links")
        
        for i, link in enumerate(job_links):
            if isinstance(link, dict) and link.get('text'):
                job = {
                    "id": link.get('id', f"link-{i}"),
                    "title": link.get('title', link.get('text', 'Position Available')),
                    "company": link.get('company', extract_company_from_url(url)),
                    "location": link.get('location', 'Various Locations'),
                    "url": link.get('url', url),
                    "description": link.get('text', '')
                }
                jobs_found.append(job)
    else:
        if not jobs_found:
            logger.warning(f"🔍 DEBUG: jobLinks is None or empty: {job_links}")
                
    # Final fallback to legacy format
    legacy_jobs = page_content.get('jobs')
    if not jobs_found and legacy_jobs is not None and len(legacy_jobs) > 0:
        jobs_found = legacy_jobs
        logger.info(f"Using legacy jobs format: {len(jobs_found)} jobs")
    else:
        if not jobs_found:
            logger.warning(f"🔍 DEBUG: legacy jobs is None or empty: {legacy_jobs}")
    
    # 🚀 If no jobs found at all, create a helpful debug response
    if not jobs_found:
        logger.error("🚨 NO JOBS FOUND IN PAGE CONTENT - Trying dynamic content extraction...")
        
        # 🎯 FIRST: Try to extract jobs from the Selenium-loaded content if available
        page_text = page_content.get('text', '')
        if page_text and len(page_text) > 1000:  # Substantial content loaded by Selenium
            logger.info(f"🔍 Found substantial page content ({len(page_text)} characters) - parsing for job links...")
            
            # 🔍 DEBUG: Log a sample of the page content to see what we're working with
            logger.info(f"🔍 DYNAMIC CONTENT SAMPLE (first 500 chars): {page_text[:500]}")
            logger.info(f"🔍 CHECKING FOR ASHBY PATTERNS: ashby_jid in content: {'ashby_jid' in page_text.lower()}")
            logger.info(f"🔍 CHECKING FOR JOB PATTERNS: 'job' in content: {'job' in page_text.lower()}")
            
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(page_text, 'html.parser')
                
                # 🔍 DEBUG: Check what links we can find
                all_links = soup.find_all('a', href=True)
                logger.info(f"🔍 TOTAL LINKS FOUND IN DYNAMIC CONTENT: {len(all_links)}")
                
                # Show first few links for debugging
                for i, link in enumerate(all_links[:5]):
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    logger.info(f"🔍 Link {i+1}: href='{href}' title='{title}'")
                
                # Use our enhanced generic selectors on the Selenium-loaded content
                logger.info("🔄 Applying enhanced job selectors to dynamic content...")
                
                # Enhanced generic job link selectors - same as in extract_generic_jobs_fallback
                job_selectors = [
                    # Traditional job URL patterns
                    'a[href*="job"]', 'a[href*="position"]', 'a[href*="career"]',
                    'a[href*="opening"]', 'a[href*="role"]', 'a[href*="opportunity"]',
                    
                    # Modern job board ID patterns (Ashby, Greenhouse, etc.)
                    'a[href*="jid="]', 'a[href*="ashby_jid="]', 'a[href*="gh_jid="]',
                    'a[href*="lever_id="]', 'a[href*="job_id="]', 'a[href*="posting_id="]',
                    
                    # CSS class patterns for job items
                    'a[class*="job"]', 'a[class*="position"]', 'a[class*="career"]',
                    'a[class*="posting"]', 'a[class*="opening"]', 'a[class*="role"]',
                    
                    # Ashby specific patterns (common class patterns)
                    'a[class*="undecorated"]', 'a[class*="jobPosting"]', '.ashby-job-posting-brief a',
                    'div[class*="jobPosting"] a', 'div[class*="job-posting"] a',
                ]
                
                dynamic_jobs = []
                for selector in job_selectors:
                    job_links = soup.select(selector)
                    if job_links:
                        logger.info(f"✅ Found {len(job_links)} job links in dynamic content using selector: {selector}")
                        
                        for i, link in enumerate(job_links[:10]):  # Limit to first 10
                            href = link.get('href', '')
                            title = link.get_text(strip=True)
                            
                            # Enhanced URL validation
                            if not href or not title or len(title) < 3:
                                continue
                            
                            # Skip invalid URLs
                            if (href.startswith('mailto:') or 
                                href.startswith('tel:') or 
                                href.startswith('#') or
                                href == '/' or
                                href == url):
                                continue
                            
                            # Skip navigation titles
                            title_lower = title.lower()
                            skip_titles = ['home', 'about', 'contact', 'privacy', 'terms', 'login', 'sign up', 'search', 'filter']
                            if any(skip_word in title_lower for skip_word in skip_titles) and len(title) < 30:
                                continue
                            
                            # Make absolute URL
                            if href.startswith('/'):
                                job_url = url.rstrip('/') + href
                            elif href.startswith('http'):
                                job_url = href
                            else:
                                job_url = url.rstrip('/') + '/' + href
                            
                            dynamic_job = {
                                "id": f"dynamic-{len(dynamic_jobs)+1}",
                                "title": title[:100],
                                "company": extract_company_from_url(url),
                                "location": "Location TBD",
                                "url": job_url,
                                "description": f"Job found in dynamic content: {title}",
                                "scraping_method": f"dynamic_content_{selector.replace('[', '').replace(']', '').replace('*', '')}",
                                "platform": embedded_platform or "unknown"
                            }
                            dynamic_jobs.append(dynamic_job)
                        
                        if dynamic_jobs:
                            break  # Stop at first successful selector
                
                if dynamic_jobs:
                    logger.info(f"🎉 Successfully extracted {len(dynamic_jobs)} jobs from dynamic content!")
                    jobs_found = dynamic_jobs
                else:
                    logger.warning("⚠️ No jobs found in dynamic content, falling back to direct scraping...")
                    
            except Exception as e:
                logger.error(f"❌ Error parsing dynamic content: {str(e)}")
        
        # 🎯 FALLBACK: If dynamic content extraction failed, try direct scraping
        if not jobs_found:
            logger.warning("⚠️ Dynamic content extraction failed - trying direct page scraping...")
            
            # 🎯 ENHANCED: Platform-specific extraction strategies
            if embedded_platform == 'ashby':
                logger.info("🔧 Using Ashby-specific extraction strategy")
                jobs_found = extract_ashby_jobs_fallback(url)
            elif embedded_platform == 'greenhouse':
                logger.info("🔧 Using Greenhouse-specific extraction strategy")
                jobs_found = extract_greenhouse_jobs_fallback(url)
            elif embedded_platform == 'lever':
                logger.info("🔧 Using Lever-specific extraction strategy")
                jobs_found = extract_lever_jobs_fallback(url)
            elif embedded_platform == 'workday':
                logger.info("🔧 Using Workday-specific extraction strategy")
                jobs_found = extract_workday_jobs_fallback(url)
            else:
                # Generic fallback
                jobs_found = extract_generic_jobs_fallback(url)
    
    # Final debug fallback if still no jobs
    if not jobs_found:
        logger.error("🚨 ALL EXTRACTION METHODS FAILED - Creating informational job")
        
        if embedded_platform:
            debug_job = {
                "id": "embedded-platform-1", 
                "title": f"{embedded_platform.title()} Jobs Available",
                "company": extract_company_from_url(url),
                "location": "Various Locations",
                "url": url,
                "description": f"This site uses {embedded_platform.title()} job board platform which loads jobs dynamically. Please visit the site directly to see available positions, or try using the Chrome extension after the page fully loads."
            }
        else:
            debug_job = {
                "id": "debug-1", 
                "title": "Debug: No Jobs Found",
                "company": "JobMatch Debug",
                "location": "Debug Mode",
                "url": url,
                "description": f"No jobs were extracted from the page content and direct scraping failed. Page content keys: {list(page_content.keys())}. This is a debug entry to help diagnose the issue."
            }
        jobs_found = [debug_job]
    
    # 🚀 SPECIAL CASE: Amazon Jobs requires Selenium for the search page itself
    if 'amazon.jobs' in url.lower() and jobs_found and len(jobs_found) == 1 and jobs_found[0].get('id') == 'debug-1':
        logger.info("🎯 Amazon Jobs detected with failed static extraction - trying Selenium for search page")
        
        try:
            # Use Selenium to extract jobs directly from the Amazon search page
            from selenium_job_extractor import fetch_job_selenium_implementation
            
            logger.info("🚀 Using Selenium for Amazon Jobs search page extraction")
            
            # Create a basic job object for the search page
            search_page_job = {
                "id": "amazon-search-page",
                "title": "Amazon Jobs Search",
                "company": "Amazon",
                "location": "Various Locations",
                "url": url,
                "description": "Amazon Jobs search page"
            }
            
            # Extract using Selenium
            selenium_result = fetch_job_selenium_implementation(url, search_page_job)
            
            if selenium_result and selenium_result.get('description') and len(selenium_result.get('description', '')) > 500:
                logger.info(f"✅ Selenium extraction successful for Amazon search: {len(selenium_result.get('description', ''))} characters")
                
                # If Selenium found job links, convert them to job objects
                if selenium_result.get('job_links_found'):
                    selenium_jobs = []
                    for job_link in selenium_result['job_links_found'][:10]:  # Limit to 10
                        selenium_job = {
                            "id": f"selenium-amazon-{len(selenium_jobs)+1}",
                            "title": job_link.get('title', 'Amazon Position'),
                            "company": "Amazon",
                            "location": "Location TBD",
                            "url": job_link.get('url', url),
                            "description": f"Amazon job: {job_link.get('title', 'Position')}. Individual job details available at job URL.",
                            "extraction_method": "selenium_amazon_search",
                            "full_details_fetched": False
                        }
                        selenium_jobs.append(selenium_job)
                    
                    if selenium_jobs:
                        logger.info(f"🎉 Selenium found {len(selenium_jobs)} Amazon jobs from search page!")
                        jobs_found = selenium_jobs
                    else:
                        # Use the search page result as a single job
                        jobs_found = [selenium_result]
                else:
                    # Use the search page result as a single job
                    jobs_found = [selenium_result]
            else:
                logger.warning("⚠️ Selenium extraction for Amazon search page returned minimal content")
                
        except ImportError:
            logger.warning("📦 Selenium not available for Amazon Jobs extraction")
        except Exception as e:
            logger.error(f"❌ Selenium extraction failed for Amazon search page: {str(e)}")
    
    # 🚀 NEW: FETCH FULL JOB DESCRIPTIONS FROM INDIVIDUAL JOB PAGES
    if jobs_found:
        logger.info(f"📡 Fetching full job descriptions from {len(jobs_found)} individual job pages...")
        
        enhanced_jobs = []
        for i, job in enumerate(jobs_found):
            job_url = job.get('url', '')
            
            # Skip if no valid URL or same as base URL
            if not job_url or job_url == url:
                logger.warning(f"Job {i+1}: No valid URL, using summary description")
                enhanced_jobs.append(job)
                continue
            
            try:
                logger.info(f"🔗 Fetching job {i+1}/{len(jobs_found)}: {job_url}")
                
                # 🚀 ENHANCED: Try multiple fetching strategies for different site types
                full_job_data = fetch_job_with_fallback_strategies(job_url, job)
                
                if full_job_data and full_job_data.get('description') and len(full_job_data.get('description', '')) > 100:
                    # Successfully extracted meaningful content
                    enhanced_job = {
                        **job,
                        "description": full_job_data.get('description', job.get('description', '')),
                        "requirements": full_job_data.get('requirements', []),
                        "qualifications": full_job_data.get('qualifications', []),
                        "benefits": full_job_data.get('benefits', []),
                        "salary": full_job_data.get('salary', ''),
                        "job_type": full_job_data.get('job_type', ''),
                        "posted_date": full_job_data.get('posted_date', ''),
                        "full_details_fetched": True,
                        "original_summary": job.get('description', ''),
                        "extraction_method": full_job_data.get('extraction_method', 'enhanced_fetch'),
                        "fetch_success": True
                    }
                    
                    enhanced_jobs.append(enhanced_job)
                    logger.info(f"✅ Job {i+1}: Successfully fetched {len(full_job_data.get('description', ''))} characters using {full_job_data.get('extraction_method', 'unknown')} method")
                else:
                    # Extraction failed, keep original data
                    logger.warning(f"⚠️ Job {i+1}: Extraction returned minimal content, keeping original summary")
                    job['full_details_fetched'] = False
                    job['fetch_success'] = False
                    job['extraction_method'] = 'failed_extraction'
                    enhanced_jobs.append(job)
                
                # Add delay to be respectful to servers
                import time
                time.sleep(0.5)  # 500ms delay between requests
                
            except Exception as e:
                logger.error(f"❌ Failed to fetch job {i+1} ({job_url}): {str(e)}")
                # Keep original job data if fetch fails
                job['full_details_fetched'] = False
                job['fetch_error'] = str(e)
                job['fetch_success'] = False
                enhanced_jobs.append(job)
        
        logger.info(f"✅ Enhanced {len(enhanced_jobs)} jobs with full descriptions")
        return enhanced_jobs
    
    # Fallback if no jobs found at all
    return jobs_found

def fetch_job_with_fallback_strategies(job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Try multiple strategies to fetch job content from different types of sites
    Handles both static HTML sites and JavaScript-heavy SPAs
    """
    
    # 🚀 GENERALIZED APPROACH: Try strategies in order for all sites
    logger.info(f"🔄 Using generalized extraction strategy for: {job_url}")
    
    strategies = [
        ("enhanced_static", fetch_job_static_enhanced),     # Try static first (fastest)
        ("selenium_fallback", fetch_job_selenium_fallback), # Try Selenium for dynamic content
        ("api_discovery", fetch_job_api_discovery)          # Try API discovery as last resort
    ]
    
    for strategy_name, strategy_func in strategies:
        try:
            logger.info(f"🔄 Trying {strategy_name} for {job_url}")
            result = strategy_func(job_url, basic_job)
            
            if result and result.get('description'):
                description = result.get('description', '')
                description_length = len(description)
                
                # Check if this is just a SPA detection message
                is_spa_warning = (
                    "JavaScript rendering" in description or
                    "Limited content available through static extraction" in description or
                    "Detected JavaScript SPA" in description
                )
                
                # 🚀 GENERALIZED THRESHOLD: Accept results based on content quality
                if strategy_name == "selenium_fallback" and description_length > 200:
                    # Accept Selenium results with lower threshold (dynamic content)
                    result['extraction_method'] = strategy_name
                    logger.info(f"✅ {strategy_name} succeeded: {description_length} characters")
                    return result
                elif strategy_name != "selenium_fallback" and description_length > 500:
                    # Higher threshold for static extraction
                    result['extraction_method'] = strategy_name
                    logger.info(f"✅ {strategy_name} succeeded: {description_length} characters")
                    return result
                elif is_spa_warning and strategy_name != "selenium_fallback":
                    # If SPA detected, continue to Selenium
                    logger.info(f"⚠️ {strategy_name} detected SPA, continuing to Selenium")
                    continue
                else:
                    logger.info(f"⚠️ {strategy_name} returned insufficient content ({description_length} chars), trying next strategy")
                    continue
            else:
                logger.info(f"⚠️ {strategy_name} returned no description, trying next strategy")
        
        except Exception as e:
            logger.warning(f"❌ {strategy_name} failed: {str(e)}")
            continue
    
    # All strategies failed, return basic job data
    logger.error(f"❌ All extraction strategies failed for {job_url}")
    return {
        **basic_job,
        "description": f"Unable to extract job details from {job_url}. This may be a JavaScript-heavy site.",
        "extraction_method": "all_strategies_failed"
    }

def fetch_job_static_enhanced(job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced static HTML fetching with better session handling and headers"""
    
    import requests
    from bs4 import BeautifulSoup
    
    # Create session with enhanced headers
    session = requests.Session()
    
    # Mimic a real browser more closely
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"'
    }
    
    session.headers.update(headers)
    
    # Make request with session
    response = session.get(job_url, timeout=15, allow_redirects=True)
    response.raise_for_status()
    
    # Parse response
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Initialize job data structure
    job_data = {
        "url": job_url,
        "title": basic_job.get('title', ''),
        "company": basic_job.get('company', ''),
        "location": basic_job.get('location', ''),
        "description": "",
        "requirements": [],
        "qualifications": [],
        "benefits": [],
        "salary": "",
        "job_type": "",
        "posted_date": "",
        "application_deadline": "",
        "extraction_method": "enhanced_static"
    }
    
    # Detect site type and use appropriate extraction
    job_url_lower = job_url.lower()
    
    if 'myworkdayjobs.com' in job_url_lower or 'workday' in job_url_lower:
        logger.info("🔧 Detected Workday site - using enhanced Workday extraction")
        job_data = extract_workday_job_enhanced(soup, job_data)
        
    elif 'greenhouse.io' in job_url_lower or 'grnh.se' in job_url_lower:
        logger.info("🔧 Detected Greenhouse site - using Greenhouse extraction")
        job_data = extract_greenhouse_job(soup, job_data)
        
    elif 'jobs.lever.co' in job_url_lower:
        logger.info("🔧 Detected Lever site - using Lever extraction")
        job_data = extract_lever_job(soup, job_data)
        
    elif 'bamboohr.com' in job_url_lower:
        logger.info("🔧 Detected BambooHR site - using BambooHR extraction")
        job_data = extract_bamboohr_job(soup, job_data)
        
    elif 'amazon.jobs' in job_url_lower:
        logger.info("🔧 Detected Amazon Jobs - using Amazon extraction")
        job_data = extract_amazon_job(soup, job_data)
        
    elif 'careers.db.com' in job_url_lower or 'deutsche-bank' in job_url_lower:
        logger.info("🔧 Detected Deutsche Bank careers site - using Deutsche Bank extraction")
        job_data = extract_deutsche_bank_job(soup, job_data, job_url)
        
        # Check if we got a short description (likely dynamic content not loaded)
        if len(job_data.get('description', '')) < 100:
            logger.warning(f"⚠️ Short description detected ({len(job_data.get('description', ''))} chars), retrying with Selenium")
            # Use Selenium for Deutsche Bank jobs
            from selenium_job_extractor import SeleniumJobExtractor
            extractor = SeleniumJobExtractor(headless=True)
            try:
                # Ensure we have a valid job URL
                if '#/professional/job/' in job_url:
                    job_id = job_url.split('/job/')[-1]
                    base_url = 'https://careers.db.com/professionals/search-roles/'
                    job_url = f"{base_url}#/professional/job/{job_id}"
                    logger.info(f"🔗 Using full Deutsche Bank URL: {job_url}")
                
                job_data = extractor.extract_deutsche_bank_job_selenium(job_url, basic_job)
                
                # Verify we got a substantial description
                if len(job_data.get('description', '')) < 100:
                    logger.warning("⚠️ Selenium extraction still got short description, retrying with longer wait")
                    # Retry with longer wait
                    extractor.driver.set_page_load_timeout(30)
                    job_data = extractor.extract_deutsche_bank_job_selenium(job_url, basic_job)
            finally:
                extractor.close()
    else:
        logger.info("🔧 Using generic extraction for unknown site")
        job_data = extract_generic_job_enhanced(soup, job_data)
    
    # Post-process and clean up the job data
    job_data = clean_job_data(job_data)
    
    return job_data

def fetch_job_api_discovery(job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
    """Try to discover and use internal APIs for job content"""
    
    import requests
    import json
    import re
    
    # For Workday sites, try to find the API endpoints
    if 'myworkdayjobs.com' in job_url.lower() or 'workday' in job_url.lower():
        try:
            # Extract job ID from URL
            job_id_match = re.search(r'_([^_]+)$', job_url)
            if job_id_match:
                job_id = job_id_match.group(1)
                
                # Try common Workday API patterns
                base_url = job_url.split('/job/')[0]
                api_endpoints = [
                    f"{base_url}/jobDetail/en-US/{job_id}",
                    f"{base_url}/api/v1/jobs/{job_id}",
                    f"{base_url}/job/{job_id}/details"
                ]
                
                headers = {
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                
                for api_url in api_endpoints:
                    try:
                        response = requests.get(api_url, headers=headers, timeout=10)
                        if response.status_code == 200 and 'application/json' in response.headers.get('content-type', ''):
                            data = response.json()
                            
                            # Extract job details from API response
                            job_data = extract_workday_api_data(data, basic_job, job_url)
                            if job_data.get('description') and len(job_data.get('description', '')) > 100:
                                logger.info(f"✅ Found Workday API data: {len(job_data.get('description', ''))} characters")
                                return job_data
                    except:
                        continue
        except Exception as e:
            logger.warning(f"Workday API discovery failed: {str(e)}")
    
    # Return empty result if API discovery fails
    return {}

def fetch_job_selenium_fallback(job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Selenium fallback for JavaScript-heavy sites
    """
    
    try:
        # Try to import and use the Selenium extractor
        from selenium_job_extractor import fetch_job_selenium_implementation
        
        logger.info("🚀 Using Selenium WebDriver for JavaScript content")
        result = fetch_job_selenium_implementation(job_url, basic_job)
        
        if result and result.get('description') and len(result.get('description', '')) > 100:
            logger.info(f"✅ Selenium extraction successful: {len(result.get('description', ''))} characters")
            return result
        else:
            logger.warning("⚠️ Selenium extraction returned minimal content")
            return {}
    
    except ImportError:
        logger.info("📦 Selenium not installed - skipping WebDriver extraction")
        logger.info("💡 Install with: pip install selenium")
        return {}
    
    except Exception as e:
        logger.error(f"❌ Selenium extraction failed: {str(e)}")
        return {}

def extract_workday_job_enhanced(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced Workday extraction that handles both static and dynamic content indicators"""
    
    try:
        logger.info(f"🔍 Enhanced Workday extraction for: {job.get('url', 'Unknown URL')}")
        
        # Check if this is a SPA (Single Page Application)
        page_text = soup.get_text()
        is_spa = (
            len(page_text.strip()) < 500 or  # Very little text content
            soup.find('div', {'id': 'root'}) or soup.find('div', {'id': 'app'}) or  # SPA indicators
            len(soup.find_all('script')) > 5  # Heavy JavaScript
        )
        
        if is_spa:
            logger.warning("⚠️ Detected JavaScript SPA - static extraction will have limited success")
            job["description"] = f"This Workday job posting uses JavaScript rendering. Limited content available through static extraction. Job URL: {job.get('url', '')}"
            job["extraction_method"] = "spa_limited"
            return job
        
        # Continue with standard Workday extraction for static content
        return extract_workday_job(soup, job)
        
    except Exception as e:
        logger.error(f"Enhanced Workday extraction failed: {str(e)}")
        job["description"] = f"Enhanced Workday extraction error: {str(e)}"
        return job

def extract_generic_job_enhanced(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced generic extraction with better content detection"""
    
    try:
        # Use the existing universal extraction but with enhanced error handling
        job = extract_universal_job_content(soup, job, "enhanced_generic")
        
        # If extraction failed, try alternative approaches
        if not job.get("description") or len(job.get("description", "")) < 100:
            logger.info("🔄 Primary extraction yielded minimal content, trying alternative methods")
            
            # Try to extract from meta tags
            meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                job["description"] = f"Job Summary: {meta_desc.get('content')}"
                logger.info("✅ Extracted content from meta description")
            
            # Try structured data (JSON-LD)
            json_ld_scripts = soup.find_all('script', {'type': 'application/ld+json'})
            for script in json_ld_scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if data.get('@type') == 'JobPosting':
                        description = data.get('description', '')
                        if description and len(description) > 100:
                            job["description"] = f"Job Posting: {description}"
                            logger.info("✅ Extracted content from JSON-LD structured data")
                            break
                except:
                    continue
        
        return job
        
    except Exception as e:
        logger.error(f"Enhanced generic extraction failed: {str(e)}")
        job["description"] = f"Enhanced generic extraction error: {str(e)}"
        return job

def extract_workday_api_data(api_data: Dict, basic_job: Dict[str, Any], job_url: str) -> Dict[str, Any]:
    """Extract job data from Workday API response"""
    
    try:
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "workday_api"
        }
        
        # Common Workday API field mappings
        if isinstance(api_data, dict):
            # Title
            title_fields = ['title', 'jobTitle', 'positionTitle', 'name']
            for field in title_fields:
                if api_data.get(field):
                    job_data["title"] = api_data[field]
                    break
            
            # Description
            desc_fields = ['description', 'jobDescription', 'summary', 'details']
            for field in desc_fields:
                if api_data.get(field):
                    job_data["description"] = api_data[field]
                    break
            
            # Location
            location_fields = ['location', 'jobLocation', 'address']
            for field in location_fields:
                if api_data.get(field):
                    if isinstance(api_data[field], dict):
                        # Handle nested location objects
                        city = api_data[field].get('city', '')
                        state = api_data[field].get('state', '')
                        country = api_data[field].get('country', '')
                        job_data["location"] = f"{city}, {state}, {country}".strip(', ')
                    else:
                        job_data["location"] = str(api_data[field])
                    break
            
            # Company
            company_fields = ['company', 'employer', 'organization']
            for field in company_fields:
                if api_data.get(field):
                    job_data["company"] = api_data[field]
                    break
        
        return job_data
        
    except Exception as e:
        logger.error(f"Error parsing Workday API data: {str(e)}")
        return basic_job

def extract_company_from_url(url: str) -> str:
    """Extract company name from URL"""
    if "google" in url.lower():
        return "Google"
    elif "microsoft" in url.lower():
        return "Microsoft"
    elif "apple" in url.lower():
        return "Apple"
    elif "amazon" in url.lower():
        return "Amazon"
    else:
        return "Tech Corp"

def extract_skills_from_text(text: str) -> List[str]:
    """Extract skills from resume text"""
    common_skills = [
        'Python', 'JavaScript', 'React', 'Node.js', 'Java', 'SQL',
        'AWS', 'Docker', 'Git', 'HTML', 'CSS', 'TypeScript', 'MongoDB'
    ]
    
    text_lower = text.lower()
    found_skills = [skill for skill in common_skills if skill.lower() in text_lower]
    return found_skills

def get_mock_job_matches(url: str) -> List[Dict[str, Any]]:
    """Fallback mock job matches"""
    return [
        {
            "id": "1",
            "title": "Senior Software Engineer",
            "company": extract_company_from_url(url),
            "location": "San Francisco, CA",
            "url": f"{url}/job/1",
            "match_score": 92,
            "matching_skills": ["React", "TypeScript", "Node.js"],
            "missing_skills": ["AWS", "Docker"],
            "summary": "Excellent match for your React and TypeScript experience",
            "confidence": "high"
        },
        {
            "id": "2",
            "title": "Full Stack Developer", 
            "company": extract_company_from_url(url),
            "location": "Remote",
            "url": f"{url}/job/2",
            "match_score": 87,
            "matching_skills": ["JavaScript", "Python"],
            "missing_skills": ["Kubernetes", "GraphQL"],
            "summary": "Good match for your full-stack development skills",
            "confidence": "medium"
        }
    ]

@app.post("/api/v1/fetch/job")
async def fetch_job_details(
    request: Dict[str, Any]
):
    """
    Enhanced job fetching for cross-origin sites (Workday, Greenhouse, Lever, etc.)
    """
    try:
        # Extract parameters from request
        job_url = request.get('job_url')
        user_id = request.get('user_id', 'default')
        include_full_content = request.get('include_full_content', True)
        extraction_method = request.get('extraction_method', 'enhanced')
        
        if not job_url:
            return {
                "success": False,
                "error": "job_url is required",
                "job_url": job_url
            }
        
        logger.info(f"Fetching job details for: {job_url}")
        
        # Enhanced headers to bypass most bot detection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Use session for better connection handling
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(job_url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Initialize job data structure
        job = {
            "url": job_url,
            "title": "",
            "company": "",
            "location": "",
            "description": "",
            "requirements": [],
            "qualifications": [],
            "benefits": [],
            "salary": "",
            "job_type": "",
            "posted_date": "",
            "application_deadline": "",
            "extraction_method": "server-side"
        }
        
        # Detect site type and use appropriate extraction
        job_url_lower = job_url.lower()
        
        if 'myworkdayjobs.com' in job_url_lower or 'workday' in job_url_lower:
            logger.info("Detected Workday site - using Workday extraction")
            job = extract_workday_job(soup, job)
            
        elif 'greenhouse.io' in job_url_lower or 'grnh.se' in job_url_lower:
            logger.info("Detected Greenhouse site - using Greenhouse extraction")
            job = extract_greenhouse_job(soup, job)
            
        elif 'jobs.lever.co' in job_url_lower:
            logger.info("Detected Lever site - using Lever extraction")
            job = extract_lever_job(soup, job)
            
        elif 'bamboohr.com' in job_url_lower:
            logger.info("Detected BambooHR site - using BambooHR extraction")
            job = extract_bamboohr_job(soup, job)
            
        elif 'amazon.jobs' in job_url_lower:
            logger.info("Detected Amazon Jobs - using Amazon extraction")
            job = extract_amazon_job(soup, job)
            
        elif 'careers.db.com' in job_url_lower or 'deutsche-bank' in job_url_lower:
            logger.info("Detected Deutsche Bank careers site - using Deutsche Bank extraction")
            job = extract_deutsche_bank_job(soup, job, job_url)
            
        else:
            logger.info("Using generic extraction for unknown site")
            job = extract_generic_job(soup, job)
        
        # Post-process and clean up the job data
        job = clean_job_data(job)
        
        logger.info(f"Successfully extracted job: {job['title']} at {job['company']}")
        
        return {
            "success": True,
            "job": job,
            "user_id": user_id,
            "processing_method": "enhanced_server_fetch",
            "extraction_site_type": detect_site_type(job_url),
            "content_length": len(job.get('description', '')),
            "processing_time_ms": 0  # Could add timing if needed
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching {job_url}: {str(e)}")
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "job_url": job_url,
            "error_type": "network"
        }
    except Exception as e:
        logger.error(f"Job fetch failed for {job_url}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "job_url": job_url,
            "error_type": "extraction"
        }

def extract_universal_job_content(soup: BeautifulSoup, job: Dict[str, Any], site_type: str = "generic") -> Dict[str, Any]:
    """
    Universal job content extraction that works across all job sites
    Uses intelligent text parsing similar to the successful Amazon approach
    """
    
    try:
        # 🚀 UNIVERSAL APPROACH: Extract everything from the main content area
        
        # Remove unwanted elements first
        for unwanted in soup.select('script, style, nav, footer, header, .navigation, .menu, .recommended-jobs, .similar-jobs, .related-jobs'):
            unwanted.decompose()
        
        # Get all text content and parse it intelligently
        full_text = soup.get_text()
        
        # Split into lines and clean up
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        # 🔍 ENHANCED: Print first 20 lines for debugging
        logger.info(f"🔍 First 20 lines from {site_type} site:")
        for i, line in enumerate(lines[:20]):
            logger.info(f"Line {i+1}: {line}")
        
        # Find major sections by their headers (works across all job sites)
        description_parts = []
        current_section = ""
        current_content = []
        
        # 🚀 EXPANDED: More section headers across all job sites
        section_headers = {
            # Job Description variations
            "DESCRIPTION": "Job Description",
            "JOB DESCRIPTION": "Job Description", 
            "OVERVIEW": "Job Overview",
            "JOB OVERVIEW": "Job Overview",
            "SUMMARY": "Job Summary",
            "JOB SUMMARY": "Job Summary",
            "ABOUT THIS ROLE": "About This Role",
            "ROLE DESCRIPTION": "Role Description",
            "WHAT YOU'LL DO": "What You'll Do",
            "RESPONSIBILITIES": "Responsibilities",
            "KEY RESPONSIBILITIES": "Key Responsibilities",
            "JOB RESPONSIBILITIES": "Job Responsibilities",
            "YOUR RESPONSIBILITIES": "Your Responsibilities",
            "ROLE RESPONSIBILITIES": "Role Responsibilities",
            "POSITION SUMMARY": "Position Summary",
            "JOB DUTIES": "Job Duties",
            "PRIMARY RESPONSIBILITIES": "Primary Responsibilities",
            
            # Qualifications variations
            "BASIC QUALIFICATIONS": "Basic Qualifications",
            "MINIMUM QUALIFICATIONS": "Minimum Qualifications", 
            "REQUIRED QUALIFICATIONS": "Required Qualifications",
            "REQUIREMENTS": "Requirements",
            "WHAT WE'RE LOOKING FOR": "What We're Looking For",
            "YOU HAVE": "Qualifications",
            "MUST HAVE": "Must Have Qualifications",
            "REQUIRED SKILLS": "Required Skills",
            "SKILLS AND EXPERIENCE": "Skills and Experience",
            "QUALIFICATIONS": "Qualifications",
            "MINIMUM REQUIREMENTS": "Minimum Requirements",
            "CRITICAL HIRING CRITERIA": "Critical Hiring Criteria",
            "PLEASE BRING TO THE TABLE": "Required Experience",
            "WHAT WE ARE LOOKING FOR": "What We Are Looking For",
            
            "PREFERRED QUALIFICATIONS": "Preferred Qualifications",
            "PREFERRED SKILLS": "Preferred Skills",
            "NICE TO HAVE": "Nice to Have",
            "ADDITIONAL QUALIFICATIONS": "Additional Qualifications",
            "BONUS POINTS": "Bonus Qualifications",
            "PLUS": "Additional Skills",
            "PREFERRED EXPERIENCE": "Preferred Experience",
            
            # Benefits and compensation
            "COMPENSATION": "Compensation",
            "SALARY": "Salary Information", 
            "PAY": "Pay Information",
            "BENEFITS": "Benefits",
            "WHAT WE OFFER": "What We Offer",
            "PERKS": "Perks & Benefits",
            "PACKAGE": "Compensation Package",
            "EMPLOYEE BENEFITS": "Employee Benefits",
            
            # Company info
            "ABOUT US": "About the Company",
            "ABOUT THE COMPANY": "About the Company",
            "COMPANY OVERVIEW": "Company Overview",
            "WHO WE ARE": "Who We Are",
            "ABOUT": "About the Company",
            
            # Location and details
            "LOCATION": "Location",
            "JOB DETAILS": "Job Details",
            "EMPLOYMENT TYPE": "Employment Type",
            "JOB TYPE": "Job Type"
        }
        
        # 🔍 ENHANCED: More comprehensive stop words
        stop_sections = {
            "RECOMMENDED JOBS", "SIMILAR JOBS", "RELATED JOBS", "OTHER OPENINGS",
            "SHARE THIS JOB", "APPLY NOW", "APPLICATION PROCESS", "HOW TO APPLY",
            "IMPORTANT FAQS", "EQUAL OPPORTUNITY", "PRIVACY POLICY", "TERMS",
            "CONTACT US", "FOOTER", "NAVIGATION", "MENU", "STAY CONNECTED",
            "EXPLORE THIS LOCATION", "WHERE WOULD YOU LIKE TO SHARE",
            "AWARDS WE'VE RECEIVED", "VIEW BENEFITS", "JOB ID", "FULL/PART TIME",
            "POSTING START DATE", "POSTING END DATE", "RECEIVE JOB ALERTS"
        }
        
        # 🎯 ENHANCED: Look for content before processing sections
        content_found = False
        main_content_lines = []
        
        # First pass: Find substantial content that looks like job descriptions
        for i, line in enumerate(lines):
            line_upper = line.upper().strip()
            
            # Skip obvious metadata/footer content
            if any(skip in line_upper for skip in stop_sections):
                continue
                
            # Look for lines that indicate job content
            job_indicators = [
                "SITE RELIABILITY", "ENGINEERING", "SOFTWARE", "DEVELOPER", "ANALYST",
                "YEARS OF EXPERIENCE", "BACHELOR", "MASTER", "DEGREE", "SKILLS",
                "RESPONSIBLE FOR", "WILL BE", "YOU WILL", "WE ARE LOOKING",
                "EXPERIENCE WITH", "KNOWLEDGE OF", "PROFICIENCY", "UNDERSTANDING"
            ]
            
            if (len(line) > 50 and  # Substantial content
                any(indicator in line_upper for indicator in job_indicators)):
                main_content_lines.append(line)
                content_found = True
        
        # If we found substantial content, use it
        if content_found and main_content_lines:
            logger.info(f"✅ Found {len(main_content_lines)} substantial content lines")
            description_parts.append(f"Job Information:\n{chr(10).join(main_content_lines)}")
        
        # Second pass: Normal section parsing
        i = 0
        while i < len(lines):
            line = lines[i].upper().strip()
            
            # Check if this line is a section header
            if line in section_headers:
                # Save previous section
                if current_section and current_content:
                    description_parts.append(f"{current_section}:\n{chr(10).join(current_content)}")
                
                current_section = section_headers[line]
                current_content = []
                i += 1
                
                # Collect content until next section or stop word
                while i < len(lines):
                    next_line = lines[i].upper().strip()
                    
                    # Stop if we hit another section header or stop section
                    if next_line in section_headers or next_line in stop_sections:
                        break
                    
                    # Add substantial content
                    if lines[i].strip() and len(lines[i]) > 10:
                        current_content.append(lines[i])
                    
                    i += 1
                i -= 1  # Step back one since the loop will increment
                
            # Check for stop sections
            elif line in stop_sections:
                break
                
            i += 1
        
        # Add the last section
        if current_section and current_content:
            description_parts.append(f"{current_section}:\n{chr(10).join(current_content)}")
        
        # 🔍 ENHANCED FALLBACK: If no structured sections found, use smart content extraction
        if not description_parts:
            logger.warning(f"No structured sections found for {site_type} site, using smart fallback extraction")
            
            # Join all lines into text for pattern matching
            text_content = " ".join(lines)
            
            # 🎯 ENHANCED: More aggressive pattern matching
            patterns_to_extract = [
                ("DESCRIPTION", "Job Description"),
                ("RESPONSIBILITIES", "Responsibilities"),
                ("QUALIFICATIONS", "Qualifications"), 
                ("REQUIREMENTS", "Requirements"),
                ("EXPERIENCE", "Experience Required"),
                ("SKILLS", "Skills Required"),
                ("EDUCATION", "Education Requirements"),
                ("WHAT YOU'LL DO", "What You'll Do"),
                ("AS A", "Role Description"),
                ("YOU WILL", "Responsibilities"),
                ("WE ARE LOOKING", "Requirements"),
                ("BRING TO THE TABLE", "Required Experience")
            ]
            
            for pattern, section_name in patterns_to_extract:
                if pattern in text_content.upper():
                    # Find content around this pattern
                    pattern_start = text_content.upper().find(pattern)
                    if pattern_start != -1:
                        # Extract content after the pattern
                        content_start = pattern_start + len(pattern)
                        content_end = min(content_start + 2000, len(text_content))  # Up to 2000 chars
                        
                        content = text_content[content_start:content_end].strip()
                        if len(content) > 100:  # Only substantial content
                            description_parts.append(f"{section_name}:\n{content}")
        
        # 🔧 ENHANCED: More aggressive element-based extraction
        if not description_parts:
            logger.warning(f"Pattern matching failed for {site_type} site, using enhanced element-based extraction")
            
            # Look for content in common job posting containers
            content_selectors = [
                '.job-description', '.job-content', '.posting-content', '.job-details',
                '.description', '.content', '.main-content', '.job-posting',
                '[data-test-id*="description"]', '[data-test-id*="content"]',
                '.posting-description', '.job-summary', '.role-description',
                'main', '.main', '#main', '.page-content', '.content-area',
                '.job-desc', '.position-content', '.role-content', '.opportunity-content',
                '[class*="description"]', '[class*="content"]', '[id*="description"]',
                '.inner-content', '.primary-content', '.job-info'
            ]
            
            extracted_content = []
            for selector in content_selectors:
                elements = soup.select(selector)
                for element in elements:
                    if element:
                        # Clean the element
                        for unwanted in element.select('script, style, nav, footer, .navigation'):
                            unwanted.decompose()
                        
                        element_text = element.get_text().strip()
                        if len(element_text) > 500:  # Only substantial content
                            # Filter out footer/navigation content
                            if not any(stop in element_text.upper() for stop in ["STAY CONNECTED", "RECEIVE JOB ALERTS", "EXPLORE THIS LOCATION"]):
                                extracted_content.append(element_text)
                                break
                
                if extracted_content:
                    break
            
            if extracted_content:
                description_parts.append(f"Job Information:\n{extracted_content[0]}")
        
        # 🎯 ENHANCED: More intelligent final fallback
        if not description_parts:
            logger.warning(f"All extraction methods failed for {site_type} site, using enhanced text content fallback")
            
            # Filter out navigation, footer, and other non-content text
            substantial_content = []
            skip_keywords = [
                'javascript', 'cookie', 'privacy', 'terms', 'navigation', 'menu', 
                'footer', 'header', 'login', 'sign in', 'register', 'stay connected',
                'receive job alerts', 'explore this location', 'where would you like',
                'job id', 'posting start date', 'posting end date', 'full/part time'
            ]
            
            for line in lines:
                if (len(line) > 40 and  # More substantial length
                    not any(keyword in line.lower() for keyword in skip_keywords) and
                    not line.startswith('http') and  # Skip URLs
                    not line.replace(' ', '').replace(':', '').replace('/', '').isdigit() and  # Skip dates/IDs
                    not line.startswith('Job ID')):  # Skip job metadata
                    substantial_content.append(line)
            
            if substantial_content:
                # Take first 30 substantial lines
                description_parts.append(f"Job Content:\n{chr(10).join(substantial_content[:30])}")
        
        # Combine all sections
        if description_parts:
            job["description"] = "\n\n".join(description_parts)
        else:
            job["description"] = "Job details not available from this page"
        
        # Limit total length but be generous
        if len(job["description"]) > 12000:  # Increased limit
            job["description"] = job["description"][:12000] + "\n\n[Content truncated for processing efficiency]"
        
        logger.info(f"📄 Universal extraction: {len(job['description'])} characters for {site_type} job: {job.get('title', 'Unknown')}")
        
    except Exception as e:
        logger.error(f"Error in universal job extraction for {site_type}: {str(e)}")
        job["description"] = f"Job details (universal extraction error: {str(e)})"
    
    return job

def extract_workday_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract job details from Workday sites with enhanced selectors and content extraction"""
    
    try:
        logger.info(f"🔍 Extracting Workday job from: {job.get('url', 'Unknown URL')}")
        
        # Enhanced title extraction for Workday
        title_selectors = [
            '[data-automation-id="jobPostingHeader"]',
            'h1[data-automation-id]',
            'h1.gwt-Label',
            '.css-12za9md',
            '.PXFDHSMLXB',  # Common Workday class
            'h1'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                logger.info(f"✅ Found title: {job['title']}")
                break
        
        # Enhanced company extraction for Workday
        company_selectors = [
            '[data-automation-id="breadcrumb"] span',
            '.css-1c6k6o1',
            '[data-automation-id="companyNameText"]',
            '.PXFDHSMLXB .PAFDHCMLXB',  # Nested Workday classes
            'title'
        ]
        
        for selector in company_selectors:
            company_el = soup.select_one(selector)
            if company_el and company_el.get_text().strip():
                company_text = company_el.get_text().strip()
                if 'careers' not in company_text.lower() and 'jobs' not in company_text.lower():
                    job["company"] = company_text.split('-')[0].split('|')[0].strip()
                    logger.info(f"✅ Found company: {job['company']}")
                    break
        
        # Enhanced location extraction for Workday
        location_selectors = [
            '[data-automation-id="locations"]',
            '[data-automation-id="jobPostingHeaderSubtitle"]',
            '.css-1t6zqoe',
            '.PAFDHGMLXB',  # Workday location class
            '.jobPostingHeaderSubtitle'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                logger.info(f"✅ Found location: {job['location']}")
                break
        
        # 🚀 ENHANCED: Workday-specific job description extraction
        description_parts = []
        
        # Primary Workday content selectors (ordered by priority)
        workday_content_selectors = [
            '[data-automation-id="jobPostingDescription"]',
            '[data-automation-id="jobPostingDescriptionText"]',
            '.css-1nqz5j',  # Common Workday description container
            '.PACDKGMLXB',  # Workday content class
            '.jobDescription',
            '.Job_Description',
            '.wd-text',
            '.gwt-RichTextArea',
            '.rich-text-content'
        ]
        
        logger.info("🔍 Searching for job description with Workday selectors...")
        
        for selector in workday_content_selectors:
            elements = soup.select(selector)
            logger.info(f"Selector '{selector}' found {len(elements)} elements")
            
            for element in elements:
                content = element.get_text(separator='\n', strip=True)
                if content and len(content) > 100:  # Substantial content
                    description_parts.append(f"Job Description:\n{content}")
                    logger.info(f"✅ Found substantial content: {len(content)} characters using selector '{selector}'")
                    break
            
            if description_parts:  # Stop at first substantial match
                break
        
        # 🔧 ENHANCED: Additional Workday content patterns
        if not description_parts:
            logger.info("🔍 Trying alternative Workday content extraction patterns...")
            
            # Look for sections with specific text patterns
            content_keywords = [
                'job responsibilities', 'what you\'ll do', 'role description',
                'key responsibilities', 'your role', 'about this job',
                'job summary', 'position summary', 'what we\'re looking for',
                'requirements', 'qualifications', 'skills needed'
            ]
            
            all_elements = soup.find_all(['div', 'section', 'p'], string=True)
            
            for element in all_elements:
                text = element.get_text().lower()
                if any(keyword in text for keyword in content_keywords):
                    # Found a section with job-related content
                    parent = element.find_parent(['div', 'section'])
                    if parent:
                        content = parent.get_text(separator='\n', strip=True)
                        if len(content) > 200:  # Substantial content
                            description_parts.append(f"Job Information:\n{content}")
                            logger.info(f"✅ Found job content via keyword matching: {len(content)} characters")
                            break
        
        # 🔧 FALLBACK: Extract from main content areas
        if not description_parts:
            logger.info("🔍 Using fallback content extraction for Workday...")
            
            # Look for main content containers
            main_selectors = [
                'main',
                '[role="main"]',
                '.main-content',
                '.content',
                '#content',
                '.job-content',
                '.posting-content'
            ]
            
            for selector in main_selectors:
                main_el = soup.select_one(selector)
                if main_el:
                    # Extract meaningful paragraphs and divs
                    content_elements = main_el.find_all(['p', 'div', 'li'], string=True)
                    meaningful_content = []
                    
                    for elem in content_elements:
                        text = elem.get_text(strip=True)
                        if (len(text) > 50 and 
                            not text.lower().startswith(('cookie', 'privacy', 'javascript', 'terms')) and
                            'apply' not in text.lower()[:20]):  # Skip apply buttons
                            meaningful_content.append(text)
                    
                    if meaningful_content:
                        combined_content = '\n\n'.join(meaningful_content)
                        if len(combined_content) > 200:
                            description_parts.append(f"Job Content:\n{combined_content}")
                            logger.info(f"✅ Found content via main container: {len(combined_content)} characters")
                            break
        
        # Combine all description parts
        if description_parts:
            job["description"] = "\n\n".join(description_parts)
        else:
            # Last resort: use universal extraction
            logger.warning("🚨 All Workday-specific extraction failed, falling back to universal extraction")
        job = extract_universal_job_content(soup, job, "workday")
        
        # Extract additional Workday-specific fields
        
        # Job type extraction
        job_type_selectors = [
            '[data-automation-id="jobClassification"]',
            '.job-type',
            '.employment-type'
        ]
        
        for selector in job_type_selectors:
            type_el = soup.select_one(selector)
            if type_el:
                job["job_type"] = type_el.get_text(strip=True)
                break
        
        # Posted date extraction
        date_selectors = [
            '[data-automation-id="postedOn"]',
            '.posted-date',
            '.date-posted'
        ]
        
        for selector in date_selectors:
            date_el = soup.select_one(selector)
            if date_el:
                job["posted_date"] = date_el.get_text(strip=True)
                break
        
        # Ensure we have a reasonable description
        if not job.get("description") or len(job["description"]) < 50:
            job["description"] = "Job details not available from this Workday page"
        
        # Limit description length for processing efficiency
        if len(job["description"]) > 8000:
            job["description"] = job["description"][:8000] + "\n\n[Content truncated for processing efficiency]"
        
        logger.info(f"📄 Workday extraction complete: {len(job['description'])} characters for '{job.get('title', 'Unknown')}'")
        
    except Exception as e:
        logger.error(f"Error extracting Workday job: {str(e)}")
        job["description"] = f"Workday job details (extraction error: {str(e)})"
    
    return job

def extract_greenhouse_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract job details from Greenhouse sites using universal extraction"""
    
    try:
        # Enhanced title extraction for Greenhouse
        title_selectors = [
            '.app-title',
            '.posting-headline h2',
            'h1',
            '.job-post-title'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Enhanced company extraction for Greenhouse
        title_tag = soup.find('title')
        if title_tag and title_tag.get_text():
            title_text = title_tag.get_text()
            if ' at ' in title_text:
                job["company"] = title_text.split(' at ')[-1].strip()
        
        # Enhanced location extraction for Greenhouse
        location_selectors = [
            '.location',
            '.posting-headline .location',
            '.app-info'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "greenhouse")
        
    except Exception as e:
        logger.error(f"Error extracting Greenhouse job: {str(e)}")
        job["description"] = f"Greenhouse job details (extraction error: {str(e)})"
    
    return job

def extract_lever_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract job details from Lever sites using universal extraction"""
    
    try:
        # Enhanced title extraction for Lever
        title_selectors = [
            '.posting-headline h2',
            'h2.posting-title',
            '.posting-title',
            'h1'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Enhanced company extraction for Lever
        if 'jobs.lever.co' in job.get("url", ""):
            url_parts = job["url"].split('/')
            if len(url_parts) > 3:
                job["company"] = url_parts[3].replace('-', ' ').title()
        
        # Enhanced location extraction for Lever
        location_selectors = [
            '.posting-categories .location',
            '.location',
            '.posting-headline .sort-by-time posting-category'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "lever")
        
    except Exception as e:
        logger.error(f"Error extracting Lever job: {str(e)}")
        job["description"] = f"Lever job details (extraction error: {str(e)})"
    
    return job

def extract_bamboohr_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract job details from BambooHR sites using universal extraction"""
    
    try:
        # Enhanced title extraction for BambooHR
        title_selectors = [
            '.BH-JobBoard-Job-Title',
            'h1.job-title',
            'h1'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Enhanced company extraction for BambooHR
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            if ' - ' in title_text:
                job["company"] = title_text.split(' - ')[-1].strip()
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "bamboohr")
        
    except Exception as e:
        logger.error(f"Error extracting BambooHR job: {str(e)}")
        job["description"] = f"BambooHR job details (extraction error: {str(e)})"
    
    return job

def extract_amazon_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract job details from Amazon Jobs using universal extraction (enhanced)"""
    
    try:
        # 🚀 ENHANCED: Extract title from URL first (more reliable for Amazon)
        job_url = job.get('url', '')
        if job_url and '/jobs/' in job_url:
            # Parse title from Amazon URL structure
            # URL format: https://www.amazon.jobs/en/jobs/ID/job-title-slug
            url_parts = job_url.split('/')
            if len(url_parts) >= 6:
                title_slug = url_parts[-1]  # Last part is usually the job title slug
                if title_slug and title_slug != job_url.split('/')[-2]:  # Not just the ID
                    # Convert slug to proper title
                    title_from_url = title_slug.replace('-', ' ').title()
                    if len(title_from_url) > 5 and not title_from_url.isdigit():
                        job["title"] = title_from_url
                        logger.info(f"📋 Extracted title from URL: {title_from_url}")
        
        # Enhanced title extraction for Amazon (fallback)
        if not job.get("title") or len(job.get("title", "")) < 5:
            title_selectors = [
                'h1.header-module_title__3cOil',
                'h1[data-test-id="header-title"]',
                '.job-title h1',
                '.posting-title',
                'h1',
                'h2'
            ]
            
            for selector in title_selectors:
                title_el = soup.select_one(selector)
                if title_el and title_el.get_text().strip():
                    title_text = title_el.get_text().strip()
                    # Avoid posting dates and navigation text
                    if (not title_text.lower().startswith('posted') and
                        'amazon.jobs' not in title_text.lower() and
                        len(title_text) > 10):
                        job["title"] = title_text
                        logger.info(f"📋 Extracted title from page: {title_text}")
                        break
        
        # Company is always Amazon
        job["company"] = "Amazon"
        
        # Enhanced location extraction for Amazon
        location_selectors = [
            '[data-test-id="header-location"]',
            '.header-module_location__2P5bY',
            '.location',
            '.job-location',
            '.posting-location'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                location_text = location_el.get_text().strip()
                # Clean up location text
                if 'location' not in location_text.lower():
                    job["location"] = location_text
                    logger.info(f"📍 Found location: {location_text}")
                    break
        
        # 🚀 ENHANCED: Try to extract location from job description if not found
        if not job.get("location") or job.get("location") == "Location":
            full_text = soup.get_text()
            # Look for location patterns in the text
            import re
            location_patterns = [
                r'Location[:\s]+([^.\n]+)',
                r'Based in ([^.\n]+)',
                r'([A-Z][a-z]+,\s*[A-Z]{2,})',  # City, State format
                r'([A-Z][a-z]+,\s*[A-Z][a-z]+)',  # City, Country format
            ]
            
            for pattern in location_patterns:
                matches = re.findall(pattern, full_text)
                if matches:
                    location = matches[0].strip()
                    if len(location) > 2 and len(location) < 50:
                        job["location"] = location
                        logger.info(f"📍 Extracted location from text: {location}")
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "amazon")
        
        # 🚀 FINAL CLEANUP: Ensure we have at least basic job information
        if not job.get("title") or job.get("title") in ["Job Position", "Unknown Title"]:
            # Last resort: try to extract from page title
            page_title = soup.find('title')
            if page_title and page_title.get_text():
                title_text = page_title.get_text().strip()
                # Clean up page title
                title_parts = title_text.split(' - ')
                if len(title_parts) > 1:
                    potential_title = title_parts[0].strip()
                    if (len(potential_title) > 10 and 
                        not potential_title.lower().startswith('posted') and
                        'amazon' not in potential_title.lower()):
                        job["title"] = potential_title
                        logger.info(f"📋 Extracted title from page title: {potential_title}")
        
        # Set default location if still empty
        if not job.get("location") or job.get("location") in ["Location", ""]:
            job["location"] = "Various Locations"
        
    except Exception as e:
        logger.error(f"Error extracting Amazon job: {str(e)}")
        job["description"] = f"Amazon job details (extraction error: {str(e)})"
    
    return job

def extract_generic_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Universal job extraction for any unknown site"""
    
    try:
        # Generic title extraction
        title_selectors = ['h1', 'h2', '.job-title', '.title', '.position-title', '.role-title']
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Generic company extraction
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            parts = title_text.split(' - ')
            if len(parts) > 1:
                job["company"] = parts[-1].strip()
        
        # Generic location extraction
        location_selectors = ['.location', '.job-location', '.city', '.address']
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "generic")
        
    except Exception as e:
        logger.error(f"Error in generic extraction: {str(e)}")
        job["description"] = f"Job details (generic extraction error: {str(e)})"
    
    return job

def clean_job_data(job: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and normalize job data"""
    
    # Clean up title
    if job.get("title"):
        job["title"] = " ".join(job["title"].split())  # Remove extra whitespace
        job["title"] = job["title"].replace('\n', ' ').replace('\t', ' ')
    
    # Clean up company
    if job.get("company"):
        job["company"] = job["company"].replace(' Careers', '').replace(' Jobs', '')
        job["company"] = " ".join(job["company"].split())
    
    # Clean up location
    if job.get("location"):
        job["location"] = job["location"].replace('\n', ', ').replace('\t', ' ')
        job["location"] = " ".join(job["location"].split())
    
    # Clean up description
    if job.get("description"):
        # Remove excessive whitespace and clean up formatting
        job["description"] = "\n".join(line.strip() for line in job["description"].split('\n') if line.strip())
        job["description"] = job["description"][:3000]  # Limit to 3000 chars
    
    # Ensure minimum data quality
    if not job.get("title"):
        job["title"] = "Job Position"
    if not job.get("company"):
        job["company"] = "Company"
    if not job.get("description"):
        job["description"] = "Job description not available"
    
    return job

def detect_site_type(url: str) -> str:
    """Detect the type of job site from URL"""
    url_lower = url.lower()
    
    if 'myworkdayjobs.com' in url_lower or 'workday' in url_lower:
        return 'workday'
    elif 'greenhouse.io' in url_lower or 'grnh.se' in url_lower:
        return 'greenhouse'
    elif 'jobs.lever.co' in url_lower:
        return 'lever'
    elif 'bamboohr.com' in url_lower:
        return 'bamboohr'
    elif 'amazon.jobs' in url_lower:
        return 'amazon'
    elif 'careers.db.com' in url_lower or 'deutsche-bank' in url_lower:
        return 'deutsche_bank'
    else:
        return 'generic'

@app.post("/api/v1/match/batch", response_model=ScanPageResponse)
async def batch_job_matching(request: BatchJobMatchRequest):
    """
    🎯 FIXED: Batch job matching endpoint that PRIORITIZES OpenAI scoring over similarity
    Ensures consistent, realistic match scores from OpenAI rather than inflated similarity scores
    """
    try:
        import time
        start_time = time.time()
        
        logger.info(f"🔄 Batch matching {len(request.jobs)} jobs for user {request.user_id}")
        
        # 🚀 RATE LIMITING: Check OpenAI-specific rate limit
        user_identifier = f"{request.user_id}_batch"
        
        # Check if we have OpenAI API key for intelligent matching
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # 🔍 DEBUG: Add extensive logging
        logger.info(f"🔍 BATCH DEBUG: OpenAI API key available: {bool(openai_api_key)}")
        logger.info(f"🔍 BATCH DEBUG: Number of jobs: {len(request.jobs)}")
        logger.info(f"🔍 BATCH DEBUG: User identifier: {user_identifier}")
        
        # 🎯 PRIORITY 1: Try OpenAI first if available and within rate limits
        if openai_api_key and len(request.jobs) > 0:
            logger.info(f"🔍 BATCH DEBUG: Checking OpenAI rate limits...")
            
            # Check OpenAI rate limit before proceeding
            rate_limit_result = rate_limiter.is_openai_allowed(user_identifier, max_openai_calls=10, window_hours=24)
            logger.info(f"🔍 BATCH DEBUG: Rate limit check result: {rate_limit_result}")
            
            if rate_limit_result:
                logger.info(f"🔒 OpenAI rate limit check passed for {user_identifier}")
                logger.info("🤖 Using OpenAI for realistic, accurate batch analysis")
                
                # 🚀 IMPORTANT: Record the OpenAI call BEFORE making the request
                rate_limiter.record_openai_call(user_identifier)
                
                try:
                    # 🎯 PRIMARY PATH: Use OpenAI for accurate scoring
                    matched_jobs = await batch_analyze_jobs_with_openai_enhanced(request.jobs, request.resume_data, openai_api_key, use_llama_extraction=True)
                    processing_method = "openai_realistic_primary"
                    
                    logger.info(f"✅ OpenAI analysis completed successfully with realistic scores")
                    
                except Exception as e:
                    logger.error(f"❌ OpenAI analysis failed: {str(e)}")
                    logger.info("📊 Falling back to conservative similarity matching")
                    matched_jobs = await batch_analyze_jobs_similarity(request.jobs, request.resume_data)
                    processing_method = "similarity_fallback_openai_error"
            else:
                # Rate limit exceeded, use similarity fallback
                usage_stats = rate_limiter.get_usage_stats(user_identifier)
                logger.warning(f"🚫 OpenAI rate limit exceeded for user {user_identifier}: {usage_stats}")
                logger.info("📊 Using conservative similarity matching due to rate limit")
                matched_jobs = await batch_analyze_jobs_similarity(request.jobs, request.resume_data)
                processing_method = "similarity_fallback_rate_limited"
                
                # Add rate limit info to response
                logger.info(f"⚠️ OpenAI calls exhausted ({usage_stats['openai_calls_last_24h']}/10 daily limit)")
        else:
            # No OpenAI API key or no jobs
            logger.info(f"🔍 BATCH DEBUG: Using similarity fallback - API key: {bool(openai_api_key)}, Jobs: {len(request.jobs)}")
            logger.info("📊 Using conservative similarity matching (no OpenAI key)")
            matched_jobs = await batch_analyze_jobs_similarity(request.jobs, request.resume_data)
            processing_method = "similarity_conservative_no_openai"
        
        # Filter by threshold and limit results
        threshold_score = request.match_threshold * 100
        filtered_jobs = [
            job for job in matched_jobs 
            if job.get('match_score', 0) >= threshold_score
        ]
        
        # Sort by match score and limit results
        filtered_jobs.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        top_jobs = filtered_jobs[:request.max_results]
        
        # Add ranking
        for i, job in enumerate(top_jobs):
            job['rank'] = i + 1
        
        processing_time = int((time.time() - start_time) * 1000)
        
        logger.info(f"✅ Batch analysis complete: {len(top_jobs)}/{len(request.jobs)} jobs passed threshold")
        
        # 🚀 DEBUG: Log the exact response being sent to frontend
        logger.info("=" * 80)
        logger.info("🔍 FRONTEND RESPONSE DEBUG")
        logger.info("=" * 80)
        logger.info(f"📊 Response Summary:")
        logger.info(f"   • Success: True")
        logger.info(f"   • Jobs found: {len(request.jobs)}")
        logger.info(f"   • Matches returned: {len(top_jobs)}")
        logger.info(f"   • Processing method: {processing_method}")
        logger.info(f"   • Processing time: {processing_time}ms")
        
        logger.info(f"\n📋 Individual Job Results:")
        for i, job in enumerate(top_jobs, 1):
            score_source = job.get('score_source', 'unknown')
            logger.info(f"   Job {i}:")
            logger.info(f"     • Title: {job.get('title', 'Unknown')}")
            logger.info(f"     • Company: {job.get('company', 'Unknown')}")
            logger.info(f"     • Match Score: {job.get('match_score', 0)}% ({score_source})")
            logger.info(f"     • Matching Skills: {job.get('matching_skills', [])}")
            logger.info(f"     • Summary: {job.get('summary', 'No summary')[:100]}...")
            logger.info(f"     • Confidence: {job.get('confidence', 'unknown')}")
        
        # Create the response object
        response_data = ScanPageResponse(
            success=True,
            message=f"Batch analyzed {len(request.jobs)} jobs, found {len(top_jobs)} matches using {processing_method}",
            jobs_found=len(request.jobs),
            matches=[
                JobMatch(
                    id=str(job.get('id', i)),
                    title=job.get('title', 'Unknown Title'),
                    company=job.get('company', 'Unknown Company'),
                    location=job.get('location', 'Unknown Location'),
                    url=job.get('url', ''),
                    match_score=job.get('match_score', 50),
                    matching_skills=job.get('matching_skills', []),
                    missing_skills=job.get('missing_skills', []),
                    summary=job.get('summary', 'No analysis available'),
                    confidence=job.get('confidence', 'medium'),
                    ai_analysis=job.get('ai_analysis', ''),
                    rank=job.get('rank', i + 1)
                )
                for i, job in enumerate(top_jobs)
            ],
            processing_time_ms=processing_time,
            processing_method=processing_method
        )
        
        # 🚀 DEBUG: Log the exact JSON being sent
        logger.info(f"\n📤 FINAL SCORES SUMMARY:")
        logger.info("=" * 80)
        for i, job in enumerate(top_jobs, 1):
            logger.info(f"Job {i}: {job.get('title', 'Unknown')} = {job.get('match_score')}% via {job.get('score_source', 'unknown')}")
        
        logger.info("=" * 80)
        logger.info("🔍 END FRONTEND RESPONSE DEBUG")
        logger.info("=" * 80)
        
        return response_data
        
    except Exception as e:
        logger.error(f"Batch job matching failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch matching failed: {str(e)}")

def create_concise_job_summary(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a concise job summary for OpenAI processing by extracting only essential information
    Reduces 11,000+ character descriptions to ~1,500 character summaries
    """
    
    try:
        full_description = job.get('description', '')
        title = job.get('title', '')
        company = job.get('company', '')
        
        # If description is already short, return as-is
        if len(full_description) <= 2000:
            return job
        
        # Split description into sections
        sections = full_description.split('\n\n')
        
        # Prioritize essential sections for OpenAI analysis
        essential_sections = []
        company_fluff_sections = []
        
        for section in sections:
            section_upper = section.upper()
            section_clean = section.strip()
            
            # Essential sections that matter for job matching
            if any(keyword in section_upper for keyword in [
                'QUALIFICATIONS', 'REQUIREMENTS', 'SKILLS', 'EXPERIENCE',
                'MUST HAVE', 'YOU WILL', 'RESPONSIBILITIES', 'WHAT YOU\'LL DO',
                'LOOKING FOR', 'BRING TO THE TABLE', 'CRITICAL HIRING',
                'PREFERRED', 'MINIMUM', 'REQUIRED', 'YEARS OF'
            ]):
                essential_sections.append(section_clean)
            
            # Company fluff that's less important for matching
            elif any(keyword in section_upper for keyword in [
                'ABOUT US', 'COMPANY OVERVIEW', 'OUR MISSION', 'OUR VISION',
                'WHO WE ARE', 'BENEFITS', 'WHAT WE OFFER', 'PERKS',
                'EQUAL OPPORTUNITY', 'DIVERSITY', 'AWARDS'
            ]):
                company_fluff_sections.append(section_clean)
        
        # Build concise summary
        summary_parts = []
        
        # Always include job title and company
        summary_parts.append(f"Position: {title} at {company}")
        
        # Add essential sections (most important)
        if essential_sections:
            essential_content = '\n\n'.join(essential_sections)
            # Limit essential content to 1200 characters
            if len(essential_content) > 1200:
                essential_content = essential_content[:1200] + '...'
            summary_parts.append(essential_content)
        
        # Add brief company info if space allows
        if company_fluff_sections and len('\n\n'.join(summary_parts)) < 1000:
            company_info = company_fluff_sections[0]
            # Limit company info to 300 characters
            if len(company_info) > 300:
                company_info = company_info[:300] + '...'
            summary_parts.append(company_info)
        
        # Create final summary
        concise_description = '\n\n'.join(summary_parts)
        
        # Final length check - keep under 1500 characters for OpenAI efficiency
        if len(concise_description) > 1500:
            concise_description = concise_description[:1500] + '...'
        
        # Return job with concise description
        job_summary = job.copy()
        job_summary['description'] = concise_description
        job_summary['original_description_length'] = len(full_description)
        job_summary['summary_description_length'] = len(job_summary['description'])
        job_summary['compression_ratio'] = f"{len(concise_description)/len(full_description)*100:.1f}%"
        
        logger.info(f"📝 Compressed job '{title}': {len(full_description)} → {len(concise_description)} chars ({job_summary['compression_ratio']})")
        
        return job_summary
        
    except Exception as e:
        logger.error(f"Error creating job summary: {str(e)}")
        return job

async def batch_analyze_jobs_with_openai(jobs: List[Dict], resume_data: Dict, api_key: str) -> List[Dict]:
    """
    🎯 FIXED: Analyze all jobs in a single OpenAI API call for consistent, accurate scoring
    Now prioritizes OpenAI's match scores over inflated similarity matching
    """
    try:
        import openai
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # 🚀 Create concise summaries for OpenAI processing (to reduce token costs)
        logger.info("📝 Creating concise job summaries for OpenAI analysis...")
        job_summaries = []
        
        for i, job in enumerate(jobs):
            # Create concise summary to save tokens
            job_summary = create_concise_job_summary(job)
            
            summary = {
                "id": i + 1,
                "title": job_summary.get('title', 'Unknown'),
                "company": job_summary.get('company', 'Unknown'),
                "location": job_summary.get('location', 'Unknown'),
                "description": job_summary.get('description', ''),  # This is now concise
                "original_length": job_summary.get('original_description_length', 0),
                "summary_length": job_summary.get('summary_description_length', 0)
            }
            job_summaries.append(summary)
        
        # Calculate total token savings
        total_original = sum(s.get('original_length', 0) for s in job_summaries)
        total_summary = sum(s.get('summary_length', 0) for s in job_summaries)
        savings = f"{total_summary/total_original*100:.1f}%" if total_original > 0 else "0%"
        
        logger.info(f"💰 Token usage reduction: {total_original} → {total_summary} chars ({savings} of original)")
        
        # Prepare resume summary (also keep concise)
        resume_summary = {
            "skills": resume_data.get('skills', [])[:10],  # Limit to top 10 skills
            "experience": [
                {
                    "title": exp.get('title', ''),
                    "company": exp.get('company', ''),
                    "technologies": exp.get('technologies', [])[:5]  # Limit technologies
                }
                for exp in resume_data.get('experience', [])[:3]  # Limit to last 3 jobs
            ],
            "education": [edu.get('degree', '') for edu in resume_data.get('education', [])][:2],  # Limit education
            "summary": resume_data.get('summary', '')[:300] if resume_data.get('summary') else ''  # Limit summary
        }
        
        # 🎯 ENHANCED: Create focused prompt that asks OpenAI to be realistic about scoring
        prompt = f"""
Analyze {len(job_summaries)} software engineering jobs against this candidate's profile. 

⚠️ IMPORTANT: Be REALISTIC with match scores. A 100% match should be extremely rare - only for perfect fits where the candidate has ALL required skills and experience. Most good matches should be 60-85%.

CANDIDATE PROFILE:
Skills: {', '.join(resume_summary.get('skills', []))}
Experience: {len(resume_summary.get('experience', []))} positions in software engineering
Education: {', '.join(resume_summary.get('education', []))}
Background: {resume_summary.get('summary', 'Not provided')}

JOBS TO ANALYZE:
{chr(10).join([f"{i+1}. {job['title']} at {job['company']}{chr(10)}{str(job['description'])[:300]}..." for i, job in enumerate(job_summaries)])}

🎯 SCORING GUIDELINES:
- 90-100%: Perfect match (has ALL required skills + experience level)
- 75-89%: Excellent match (has most required skills + right experience)
- 60-74%: Good match (has core skills, some gaps in experience/tools)
- 45-59%: Fair match (has some relevant skills, significant gaps)
- 30-44%: Poor match (few relevant skills, wrong experience level)
- Below 30%: Not suitable

For each job, provide:
1. Realistic match score (30-100) based on actual fit
2. Top 3 matching skills from candidate's profile
3. Top 2 missing/weak skills that would strengthen candidacy
4. Brief reasoning for the score (1 sentence)
5. Confidence level (high/medium/low)

Format as JSON array:
[
  {{
    "id": 1,
    "match_score": 68,
    "matching_skills": ["Python", "AWS", "React"],
    "missing_skills": ["Kubernetes", "GraphQL"],
    "analysis": "Good Python/AWS fit but lacks senior experience and specific tools mentioned",
    "confidence": "medium"
  }}
]

Focus on realistic assessment. Don't inflate scores - be honest about gaps.
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Using 3.5-turbo for cost efficiency
            messages=[
                {"role": "system", "content": "You are a brutally honest technical recruiter. Give realistic match scores - most jobs should score 60-80% for good candidates. Only perfect fits get 90%+."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,  # Reduced tokens since we need less output
            temperature=0.2  # Lower temperature for more consistent realistic scoring
        )
        
        # Parse OpenAI response
        ai_response = response.choices[0].message.content
        logger.info(f"🤖 OpenAI response length: {len(ai_response)} characters")
        
        # Try to parse JSON response
        import json
        try:
            ai_analysis = json.loads(ai_response)
            logger.info(f"✅ Successfully parsed OpenAI analysis for {len(ai_analysis)} jobs")
        except json.JSONDecodeError:
            logger.warning("❌ OpenAI response not valid JSON, using fallback similarity matching")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # 🎯 PRIORITY FIX: Use OpenAI scores directly, not similarity scores
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            ai_result = ai_analysis[i] if i < len(ai_analysis) else {}
            
            # 🚀 KEY FIX: Use OpenAI's realistic score as the PRIMARY score
            openai_score = ai_result.get('match_score', 50)
            
            analyzed_job = {
                **job,  # Keep original full job data
                "match_score": openai_score,  # 🎯 Use OpenAI score directly
                "matching_skills": ai_result.get('matching_skills', []),
                "missing_skills": ai_result.get('missing_skills', []),
                "summary": ai_result.get('analysis', 'AI analysis not available'),
                "confidence": ai_result.get('confidence', 'medium'),
                "ai_analysis": ai_result.get('analysis', ''),
                "processing_method": "openai_realistic_scoring",
                "score_source": "openai_primary"  # Track that this came from OpenAI
            }
            analyzed_jobs.append(analyzed_job)
            
            # 🔍 Log the realistic scoring
            logger.info(f"🎯 Job {i+1}: {job.get('title', 'Unknown')} - OpenAI Score: {openai_score}%")
        
        logger.info(f"✅ OpenAI realistic batch analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"❌ OpenAI batch analysis failed: {str(e)}")
        # Fallback to similarity matching
        return await batch_analyze_jobs_similarity(jobs, resume_data)

async def batch_analyze_jobs_similarity(jobs: List[Dict], resume_data: Dict) -> List[Dict]:
    """
    🎯 FIXED: More realistic similarity-based matching when OpenAI is not available
    Reduced inflated scoring and made it more honest about limitations
    """
    try:
        logger.info(f"📊 Using similarity matching as fallback for {len(jobs)} jobs")
        
        # Common words to exclude from matching
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'as', 'are', 'was', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'is', 'am', 'we', 'you', 'they', 'them', 'their', 'this', 'that', 'these', 'those', 'if', 'when', 'where', 'how', 'why', 'what', 'who', 'which'}
        
        # Prepare resume text
        resume_skills = resume_data.get('skills', [])
        resume_text = ' '.join(str(skill) for skill in resume_skills) + ' ' + str(resume_data.get('summary', ''))
        
        # Analyze each job with REALISTIC scoring
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            try:
                job_text_lower = str(job.get('description', '')).lower()
                
                # 🎯 MORE REALISTIC: Start with lower base scores
                skill_matches = []
                skill_match_count = 0
                
                # Count actual skill matches (be strict)
                for skill in resume_skills:
                    if str(skill).lower() in job_text_lower:
                        skill_matches.append(skill)
                        skill_match_count += 1
                
                # 🎯 REALISTIC SCORING: Much more conservative
                if skill_match_count >= 6:  # Has most skills
                    base_score = 75  # Reduced from inflated scores
                elif skill_match_count >= 4:  # Has good skills
                    base_score = 65
                elif skill_match_count >= 2:  # Has some skills
                    base_score = 55
                elif skill_match_count >= 1:  # Has few skills
                    base_score = 45
                else:  # No clear skill matches
                    base_score = 35
                
                # 🎯 CONSERVATIVE BONUSES: Much smaller bonuses
                tech_bonus = 0
                tech_terms = ['api', 'database', 'cloud', 'agile']  # Reduced list
                tech_matches = [term for term in tech_terms if term in job_text_lower]
                if tech_matches:
                    tech_bonus = min(len(tech_matches) * 2, 8)  # Max 8 points from tech terms
                
                # 🎯 REALISTIC FINAL SCORE: Cap at reasonable level for similarity matching
                final_score = min(base_score + tech_bonus, 78)  # Cap at 78% for similarity matching
                final_score = max(final_score, 30)  # Minimum 30%
                
                # 🎯 HONEST SUMMARY: Acknowledge limitations of similarity matching
                summary = f"Similarity match: {final_score}% (found {skill_match_count} matching skills). Note: This is basic keyword matching - OpenAI analysis would be more accurate."
                
                analyzed_job = {
                    **job,
                    "match_score": final_score,
                    "matching_skills": skill_matches[:5],  # Show top 5 matches
                    "missing_skills": [],  # Can't reliably determine missing skills with similarity
                    "summary": summary,
                    "confidence": "medium" if final_score > 60 else "low",  # Lower confidence for similarity
                    "processing_method": "similarity_conservative",
                    "score_source": "similarity_fallback",  # Track that this is fallback
                    "skill_match_count": skill_match_count,
                    "base_score": base_score,
                    "tech_bonus": tech_bonus
                }
                analyzed_jobs.append(analyzed_job)
                
                logger.info(f"📊 Job {i+1}: {job.get('title', 'Unknown')} - Similarity Score: {final_score}% ({skill_match_count} skills)")
                
            except Exception as e:
                logger.error(f"Error processing job {i+1}: {str(e)}")
                # Ultra-basic fallback
                analyzed_job = {
                    **job,
                    "match_score": 40,  # Conservative default
                    "matching_skills": [],
                    "missing_skills": [],
                    "summary": "Basic similarity matching failed - limited analysis available",
                    "confidence": "low",
                    "processing_method": "similarity_error_fallback"
                }
                analyzed_jobs.append(analyzed_job)
        
        logger.info(f"✅ Conservative similarity analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"Similarity analysis failed: {str(e)}")
        # Return minimal scoring if everything fails
        return [
            {
                **job,
                "match_score": 40,  # Conservative default
                "matching_skills": [],
                "missing_skills": [],
                "summary": "Limited analysis available - recommend using OpenAI for accurate scoring",
                "confidence": "low",
                "processing_method": "minimal_fallback"
            }
            for job in jobs
        ]

async def create_ai_job_summary(job: Dict[str, Any], use_free_llm: bool = False) -> Dict[str, Any]:
    """
    Create AI-powered job summary using free LLM APIs
    Alternative to smart extraction for higher quality summaries
    """
    
    if not use_free_llm:
        # Use smart extraction by default
        return create_concise_job_summary(job)
    
    try:
        full_description = job.get('description', '')
        title = job.get('title', '')
        company = job.get('company', '')
        
        # If description is already short, return as-is
        if len(full_description) <= 2000:
            return job
        
        # Prepare prompt for free LLM summarization
        summarization_prompt = f"""
Summarize this job posting for {title} at {company}. Focus on:
1. Key technical requirements and qualifications
2. Main responsibilities 
3. Required skills and experience
4. Must-have vs nice-to-have qualifications

Keep the summary under 1000 characters and focus only on information relevant for job matching.

Job Description:
{full_description[:8000]}  # Limit input to avoid token limits

Summary:"""

        # Option 1: Hugging Face Inference API (Free)
        try:
            import requests
            
            hf_api_url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
            headers = {"Authorization": f"Bearer {os.getenv('HUGGINGFACE_API_KEY', '')}"}
            
            if os.getenv('HUGGINGFACE_API_KEY'):
                payload = {
                    "inputs": summarization_prompt,
                    "parameters": {
                        "max_length": 500,
                        "min_length": 100,
                        "do_sample": False
                    }
                }
                
                response = requests.post(hf_api_url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        ai_summary = result[0].get('summary_text', '')
                        
                        if ai_summary and len(ai_summary) > 50:
                            job_summary = job.copy()
                            job_summary['description'] = f"Position: {title} at {company}\n\n{ai_summary}"
                            job_summary['original_description_length'] = len(full_description)
                            job_summary['summary_description_length'] = len(job_summary['description'])
                            job_summary['summarization_method'] = 'huggingface_ai'
                            
                            logger.info(f"🤖 AI summarized '{title}': {len(full_description)} → {len(job_summary['description'])} chars")
                            return job_summary
        
        except Exception as e:
            logger.warning(f"Hugging Face summarization failed: {str(e)}")
        
        # Option 2: Ollama Local LLM (Free, requires local setup)
        try:
            if os.getenv('OLLAMA_AVAILABLE'):
                ollama_url = "http://localhost:11434/api/generate"
                payload = {
                    "model": "llama2",  # or "mistral", "codellama"
                    "prompt": summarization_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "max_tokens": 500
                    }
                }
                
                response = requests.post(ollama_url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    ai_summary = result.get('response', '')
                    
                    if ai_summary and len(ai_summary) > 50:
                        job_summary = job.copy()
                        job_summary['description'] = f"Position: {title} at {company}\n\n{ai_summary}"
                        job_summary['original_description_length'] = len(full_description)
                        job_summary['summary_description_length'] = len(job_summary['description'])
                        job_summary['summarization_method'] = 'ollama_local'
                        
                        logger.info(f"🏠 Local AI summarized '{title}': {len(full_description)} → {len(job_summary['description'])} chars")
                        return job_summary
        
        except Exception as e:
            logger.warning(f"Ollama summarization failed: {str(e)}")
        
        # Fallback to smart extraction
        logger.info(f"AI summarization unavailable, using smart extraction for '{title}'")
        return create_concise_job_summary(job)
        
    except Exception as e:
        logger.error(f"Error in AI job summarization: {str(e)}")
        return create_concise_job_summary(job)

async def create_llama_context_extraction(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Groq (free Llama API) for intelligent, context-aware job content extraction
    Preserves nuance and relationships while reducing length for OpenAI
    """
    
    try:
        full_description = job.get('description', '')
        title = job.get('title', '')
        company = job.get('company', '')
        
        # If description is already short, return as-is
        if len(full_description) <= 2000:
            return job
        
        # 🔍 DEBUG: Print original job description details
        print(f"\n🚀 GROQ EXTRACTION DEMO for: {title} at {company}")
        print("=" * 60)
        print(f"📄 Original Description Length: {len(full_description)} characters")
        print("📄 Original Description Preview:")
        print("-" * 40)
        print(full_description[:800] + "..." if len(full_description) > 800 else full_description)
        print("-" * 40)
        
        # 🎯 SMART: Reduce input size to avoid rate limits
        # Limit to 6000 characters to stay within token limits
        smart_description = full_description[:6000]
        if len(full_description) > 6000:
            print(f"📝 Smart input limiting: {len(full_description)} → {len(smart_description)} chars to avoid rate limits")
        
        # Create intelligent extraction prompt for Llama
        extraction_prompt = f"""Extract the most important information from this job posting for accurate candidate matching. Focus on technical requirements, experience levels, and key responsibilities while preserving context.

Job Title: {title}
Company: {company}

Original Job Description:
{smart_description}

Extract and summarize in under 800 characters:

1. Core technical requirements (languages, frameworks, tools)
2. Experience level needed (years, specific domains)
3. Key responsibilities and what the person will actually do
4. Must-have vs nice-to-have qualifications
5. Any important context about team, company, or project scope

Focus only on information that helps determine if a candidate is a good fit. Be concise but preserve important technical nuance.

Extracted Summary:"""

        # 🚀 Priority 1: Groq (Very fast, free Llama API - 6,000 requests/day)
        if os.getenv('GROQ_API_KEY'):
            try:
                import requests
                import time
                
                groq_api_key = os.getenv('GROQ_API_KEY')
                logger.info(f"🔑 Groq API key found: {groq_api_key[:8]}...{groq_api_key[-4:] if len(groq_api_key) > 12 else ''}")
                
                logger.info("🔄 Calling Groq API for intelligent extraction...")
                
                groq_url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json"
                }
                
                # Calculate safe batch size based on job description length
                safe_batch_size = 5  # Default safe size
                if len(full_description) > 5000:  # Very long descriptions
                    safe_batch_size = 3
                elif len(full_description) > 2000:  # Long descriptions
                    safe_batch_size = 4
                
                logger.info(f"📊 Job description length: {len(full_description)} chars")
                logger.info(f"🎯 Safe batch size for this job: {safe_batch_size}")
                
                payload = {
                    "model": "llama3-70b-8192",  # Fast and very capable model
                    "messages": [
                        {"role": "system", "content": "You are an expert technical recruiter. Extract key job information while preserving context for accurate candidate matching."},
                        {"role": "user", "content": extraction_prompt}
                    ],
                    "max_tokens": 600,  # Reduced from 800 to use fewer tokens
                    "temperature": 0.1,  # Lower temperature for more consistent extraction
                    "top_p": 0.9
                }
                
                # Add delay between jobs to avoid rate limits
                if hasattr(create_llama_context_extraction, '_last_groq_call'):
                    time_since_last = time.time() - create_llama_context_extraction._last_groq_call
                    if time_since_last < 2.5:  # Minimum 2.5 seconds between calls
                        wait_time = 2.5 - time_since_last
                        logger.info(f"⏳ Waiting {wait_time:.1f}s between Groq calls to avoid rate limits...")
                        time.sleep(wait_time)
                
                # 🔄 SMART RATE LIMITING: Retry with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        logger.info(f"🔄 Groq API attempt {attempt + 1}/{max_retries} for job: {title}")
                        response = requests.post(groq_url, headers=headers, json=payload, timeout=15)
                        
                        # Record successful API call time
                        create_llama_context_extraction._last_groq_call = time.time()
                        
                        if response.status_code == 200:
                            result = response.json()
                            llama_summary = result['choices'][0]['message']['content'].strip()
                            
                            if llama_summary and len(llama_summary) > 100:
                                # Clean up and format the summary
                                if len(llama_summary) > 1000:  # Reduced from 1200
                                    llama_summary = llama_summary[:1000] + "..."
                                
                                # Create final description with structure
                                final_description = f"Position: {title} at {company}\n\n{llama_summary}"
                                
                                # 🔍 ENHANCED LOGGING: Show actual Groq content for debugging
                                logger.info("✅ Groq extraction successful!")
                                logger.info(f"📊 Compression: {len(full_description)} → {len(final_description)} chars ({len(final_description)/len(full_description)*100:.1f}%)")
                                logger.info("🧠 GROQ EXTRACTED SUMMARY:")
                                logger.info("-" * 60)
                                logger.info(f"Job: {title} at {company}")
                                logger.info("-" * 60)
                                logger.info(llama_summary)
                                logger.info("-" * 60)
                                logger.info(f"📝 Summary length: {len(llama_summary)} chars")
                                logger.info(f"🎯 Final description length: {len(final_description)} chars")
                                logger.info("=" * 80)
                                
                                job_summary = job.copy()
                                job_summary['description'] = final_description
                                job_summary['original_description_length'] = len(full_description)
                                job_summary['summary_description_length'] = len(final_description)
                                job_summary['extraction_method'] = 'groq_llama_extraction'
                                job_summary['compression_ratio'] = f"{len(final_description)/len(full_description)*100:.1f}%"
                                
                                logger.info(f"🚀 Groq extracted '{title}': {len(full_description)} → {len(final_description)} chars ({job_summary['compression_ratio']})")
                                return job_summary
                            else:
                                logger.error(f"❌ Groq returned empty or too short summary: {len(llama_summary) if llama_summary else 0} chars")
                        
                        elif response.status_code == 429:  # Rate limit
                            error_data = response.json()
                            wait_time = 10  # Default wait time
                            
                            # Try to extract wait time from error message
                            error_message = error_data.get('error', {}).get('message', '')
                            if 'try again in' in error_message:
                                try:
                                    # Extract seconds from "try again in X.XXXs"
                                    import re
                                    match = re.search(r'try again in (\d+\.?\d*)s', error_message)
                                    if match:
                                        wait_time = float(match.group(1)) + 1  # Add 1 second buffer
                                except:
                                    pass
                            
                            logger.warning(f"⚠️  Rate limit hit (attempt {attempt + 1}/{max_retries})")
                            logger.warning(f"⏳ Waiting {wait_time:.1f} seconds before retry...")
                            logger.warning(f"🚨 GROQ RATE LIMIT: {response.status_code} - {error_message}")
                            
                            if attempt < max_retries - 1:  # Don't wait on last attempt
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"❌ Max Groq retries reached. Using fallback extraction.")
                                logger.error("💡 Tip: Process fewer jobs at once or upgrade Groq tier")
                                logger.error(f"🔢 Current batch size: {safe_batch_size} jobs")
                                break
                        else:
                            error_message = response.text
                            try:
                                error_json = response.json()
                                error_message = error_json.get('error', {}).get('message', error_message)
                            except:
                                pass
                            logger.error(f"❌ Groq API error: {response.status_code} - {error_message}")
                            logger.error(f"🔍 Request details: URL={groq_url}, Headers={headers.keys()}, Payload size={len(str(payload))} chars")
                            break
                    
                    except requests.exceptions.Timeout:
                        logger.warning(f"⏰ Groq API timeout (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            break
                    
                    except Exception as e:
                        logger.error(f"❌ Groq request failed: {str(e)}")
                        logger.error(f"🔍 Error type: {type(e).__name__}")
                        import traceback
                        logger.error(f"📚 Stack trace:\n{traceback.format_exc()}")
                        break
                
                # If we get here, Groq failed - mark it as failed and continue to fallbacks
                logger.error("❌ Groq extraction completely failed - trying fallback methods")
            
            except Exception as e:
                logger.error(f"❌ Groq extraction failed: {str(e)}")
                logger.warning(f"Groq extraction failed: {str(e)}")
        else:
            logger.warning("❌ GROQ_API_KEY not found - skipping Groq extraction")
        
        # 🏠 Priority 2: Ollama Local (Free, requires local setup)
        if os.getenv('OLLAMA_AVAILABLE', '').lower() == 'true':
            try:
                import requests
                
                ollama_url = "http://localhost:11434/api/generate"
                payload = {
                    "model": "llama3",  # or "llama2", "mistral"
                    "prompt": extraction_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 600
                    }
                }
                
                response = requests.post(ollama_url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    llama_summary = result.get('response', '').strip()
                    
                    if llama_summary and len(llama_summary) > 100:
                        if len(llama_summary) > 1200:
                            llama_summary = llama_summary[:1200] + "..."
                        
                        final_description = f"Position: {title} at {company}\n\n{llama_summary}"
                        
                        job_summary = job.copy()
                        job_summary['description'] = final_description
                        job_summary['original_description_length'] = len(full_description)
                        job_summary['summary_description_length'] = len(final_description)
                        job_summary['extraction_method'] = 'ollama_local_extraction'
                        job_summary['compression_ratio'] = f"{len(final_description)/len(full_description)*100:.1f}%"
                        
                        logger.info(f"🏠 Ollama extracted '{title}': {len(full_description)} → {len(final_description)} chars")
                        return job_summary
            
            except Exception as e:
                logger.warning(f"Ollama extraction failed: {str(e)}")
        
        # 🤗 Priority 3: Hugging Face (Free tier, slower)
        if os.getenv('HUGGINGFACE_API_KEY'):
            try:
                import requests
                
                hf_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-large"
                headers = {"Authorization": f"Bearer {os.getenv('HUGGINGFACE_API_KEY')}"}
                
                payload = {
                    "inputs": extraction_prompt,
                    "parameters": {
                        "max_new_tokens": 600,
                        "temperature": 0.1,
                        "return_full_text": False
                    }
                }
                
                response = requests.post(hf_url, headers=headers, json=payload, timeout=25)
                
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        llama_summary = result[0].get('generated_text', '').strip()
                        
                        if llama_summary and len(llama_summary) > 100:
                            if len(llama_summary) > 1200:
                                llama_summary = llama_summary[:1200] + "..."
                            
                            final_description = f"Position: {title} at {company}\n\n{llama_summary}"
                            
                            job_summary = job.copy()
                            job_summary['description'] = final_description
                            job_summary['original_description_length'] = len(full_description)
                            job_summary['summary_description_length'] = len(final_description)
                            job_summary['extraction_method'] = 'huggingface_extraction'
                            job_summary['compression_ratio'] = f"{len(final_description)/len(full_description)*100:.1f}%"
                            
                            logger.info(f"🤗 HuggingFace extracted '{title}': {len(full_description)} → {len(final_description)} chars")
                            return job_summary
            
            except Exception as e:
                logger.warning(f"HuggingFace extraction failed: {str(e)}")
        
        # Fallback to smart extraction if all LLM options unavailable
        logger.info(f"🔄 All LLM options unavailable, using smart keyword extraction for '{title}'")
        return create_concise_job_summary(job)
        
    except Exception as e:
        logger.error(f"❌ Error in LLM context extraction: {str(e)}")
        return create_concise_job_summary(job)

# Update the batch analysis to use Llama extraction
async def batch_analyze_jobs_with_openai_enhanced(jobs: List[Dict], resume_data: Dict, api_key: str, use_llama_extraction: bool = True) -> List[Dict]:
    """
    Enhanced batch job analysis with Llama-powered context extraction
    Two-stage process: Llama for extraction, OpenAI for matching
    """
    try:
        import openai
        from openai import OpenAI
        import time
        
        # 🚀 Add start_time for logging
        start_time = time.time()
        
        # 🔍 DEBUG: Add extensive logging
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: FUNCTION ENTRY")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Starting with {len(jobs)} jobs")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: API key length: {len(api_key) if api_key else 0}")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: use_llama_extraction: {use_llama_extraction}")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Resume data available: {bool(resume_data)}")
        
        # 🚀 NEW DEBUG: Log actual resume_data structure
        logger.info(f"🔍 RESUME DEBUG: Resume data type: {type(resume_data)}")
        logger.info(f"🔍 RESUME DEBUG: Resume data keys: {list(resume_data.keys()) if isinstance(resume_data, dict) else 'Not a dict'}")
        if isinstance(resume_data, dict):
            logger.info(f"🔍 RESUME DEBUG: Skills count: {len(resume_data.get('skills', []))}")
            logger.info(f"🔍 RESUME DEBUG: Experience count: {len(resume_data.get('experience', []))}")
            logger.info(f"🔍 RESUME DEBUG: Education count: {len(resume_data.get('education', []))}")
            logger.info(f"🔍 RESUME DEBUG: Summary length: {len(str(resume_data.get('summary', '')))}")
            
            # Log first experience item structure if available
            experience_list = resume_data.get('experience', [])
            if experience_list and len(experience_list) > 0:
                first_exp = experience_list[0]
                logger.info(f"🔍 RESUME DEBUG: First experience type: {type(first_exp)}")
                if isinstance(first_exp, dict):
                    logger.info(f"🔍 RESUME DEBUG: First experience keys: {list(first_exp.keys())}")
                    logger.info(f"🔍 RESUME DEBUG: Has technologies field: {'technologies' in first_exp}")
        
        client = OpenAI(api_key=api_key)
        
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: OpenAI client created successfully")
        
        # 🚀 Validate input data
        if not isinstance(jobs, list):
            logger.error(f"Jobs parameter must be a list, got {type(jobs)}")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # Filter and validate job objects
        valid_jobs = []
        for i, job in enumerate(jobs):
            if isinstance(job, dict):
                # Ensure job has all required fields with defaults
                processed_job = {
                    'title': job.get('title', 'Unknown Position'),
                    'company': job.get('company', 'Unknown Company'),
                    'description': job.get('description', ''),
                    'extraction_method': job.get('extraction_method', 'original'),
                    'url': job.get('url', ''),
                    'location': job.get('location', ''),
                    **job  # Keep all other fields
                }
                valid_jobs.append(processed_job)
            else:
                logger.warning(f"Job {i} is not a dict: {type(job)}, skipping")
        
        if not valid_jobs:
            logger.error("No valid job dictionaries found")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # 🚀 GROQ RATE LIMIT PROTECTION: Limit batch size to prevent 429 errors
        if use_llama_extraction and os.getenv('GROQ_API_KEY'):
            # Groq free tier: 6k tokens/minute limit
            # With ~600 tokens per job, max 5-6 jobs per minute
            max_groq_batch_size = 5
            if len(valid_jobs) > max_groq_batch_size:
                logger.warning(f"🚨 GROQ PROTECTION: Batch size {len(valid_jobs)} exceeds safe limit of {max_groq_batch_size}")
                logger.warning(f"💡 Processing first {max_groq_batch_size} jobs to avoid rate limits")
                logger.warning(f"🔧 Consider splitting large batches or upgrading Groq tier")
                valid_jobs = valid_jobs[:max_groq_batch_size]
        
        logger.info(f"🔍 Processing {len(valid_jobs)} valid jobs out of {len(jobs)} total")
        
        # 🚀 Stage 1: Use smart extraction for job summaries
        if use_llama_extraction:
            logger.info("🧠 Using Groq + smart extraction for enhanced job summaries...")
            job_summaries = []
            
            for i, job in enumerate(valid_jobs):
                try:
                    # 🎯 PRIORITY 1: Try Groq extraction for intelligent summarization
                    if os.getenv('GROQ_API_KEY'):
                        logger.info(f"🔄 Job {i+1}/{len(jobs)}: Trying Groq extraction for '{job.get('title', 'Unknown')}'")
                        groq_enhanced_job = await create_llama_context_extraction(job)
                        # logger.info("groq_enhanced_job",groq_enhanced_job)
                        
                        # Check if Groq extraction was successful by looking for Groq-specific formatting
                        if (groq_enhanced_job and 
                            groq_enhanced_job.get('description') and 
                            len(groq_enhanced_job.get('description', '')) > 200 and
                            ('Position:' in groq_enhanced_job.get('description', '') or 
                             groq_enhanced_job.get('extraction_method') == 'groq_llama_extraction')):
                            
                            # Use Groq-enhanced summary
                            job_summary = groq_enhanced_job
                            logger.info(f"✅ Job {i+1}: Groq success - {groq_enhanced_job.get('compression_ratio', 'N/A')} compression")
                        else:
                            # Groq failed, use smart extraction fallback
                            logger.info(f"⚠️ Job {i+1}: Groq failed, using smart extraction fallback")
                            job_summary = create_concise_job_summary(job)
                    else:
                        # No Groq API key, use smart extraction
                        logger.info(f"📝 Job {i+1}/{len(jobs)}: Using smart extraction (no Groq key)")
                        job_summary = create_concise_job_summary(job)
                    
                    # Create summary object for OpenAI
                    summary = {
                        "id": i + 1,
                        "title": job_summary.get('title', 'Unknown'),
                        "company": job_summary.get('company', 'Unknown'),
                        "location": job_summary.get('location', 'Unknown'),
                        "description": job_summary.get('description', ''),
                        "original_length": job_summary.get('original_description_length', len(str(job.get('description', '')))),
                        "summary_length": job_summary.get('summary_description_length', len(str(job_summary.get('description', '')))),
                        "extraction_method": job_summary.get('extraction_method', 'smart_extraction'),
                        "compression_ratio": job_summary.get('compression_ratio', 'N/A')
                    }
                    job_summaries.append(summary)
                    
                    # Add small delay between Groq requests to respect rate limits
                    if os.getenv('GROQ_API_KEY') and i < len(jobs) - 1:
                        await asyncio.sleep(2.5)  # 2.5 second delay between Groq requests for rate limiting
                    
                except Exception as e:
                    logger.error(f"❌ Job {i+1}: Error in summarization: {str(e)}")
                    # Ultra-basic fallback
                    job_summary = create_concise_job_summary(job)
                    summary = {
                        "id": i + 1,
                        "title": job.get('title', 'Unknown'),
                        "company": job.get('company', 'Unknown'),
                        "location": job.get('location', 'Unknown'),
                        "description": job_summary.get('description', job.get('description', '')),
                        "original_length": len(str(job.get('description', ''))),
                        "summary_length": len(str(job_summary.get('description', ''))),
                        "extraction_method": 'fallback_smart_extraction'
                    }
                    job_summaries.append(summary)
        
        if not job_summaries:
            logger.error("No job summaries created, falling back to similarity matching")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # 🚀 DEBUG: Log summaries status
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Created {len(job_summaries)} job summaries")
        
        # Calculate processing statistics
        total_original = sum(s.get('original_length', 0) for s in job_summaries)
        total_summary = sum(s.get('summary_length', 0) for s in job_summaries)
        savings = f"{total_summary/total_original*100:.1f}%" if total_original > 0 else "0%"
        
        logger.info(f"💰 Context extraction: {total_original} → {total_summary} chars ({savings} of original)")
        
        # 🎯 Stage 2: Use OpenAI for intelligent job-resume matching
        logger.info("🔍 OPENAI ENHANCED DEBUG: STARTING OPENAI STAGE...")
        logger.info("🤖 Using OpenAI for intelligent job-resume matching...")
        
        # Prepare focused resume summary
        resume_summary = {
            "skills": resume_data.get('skills', [])[:12] if isinstance(resume_data.get('skills'), list) else [],
            "experience": [
                {
                    "title": exp.get('title', '') if isinstance(exp, dict) else '',
                    "company": exp.get('company', '') if isinstance(exp, dict) else '',
                    "technologies": exp.get('technologies', [])[:6] if isinstance(exp, dict) and isinstance(exp.get('technologies'), list) else [],
                    "duration": exp.get('duration', '') if isinstance(exp, dict) else ''
                }
                for exp in (resume_data.get('experience', []) if isinstance(resume_data.get('experience'), list) else [])[:3]
            ],
            "education": [edu.get('degree', '') if isinstance(edu, dict) else str(edu) for edu in (resume_data.get('education', []) if isinstance(resume_data.get('education'), list) else [])][:2],
            "summary": str(resume_data.get('summary', ''))[:400] if resume_data.get('summary') else ''
        }
        
        # 🚀 DEBUG: Log resume summary
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Resume skills: {len(resume_summary.get('skills', []))}")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Resume experience: {len(resume_summary.get('experience', []))}")
        
        # Create enhanced matching prompt
        newline = chr(10)
        matching_prompt = f"""
Analyze {len(job_summaries)} software engineering positions against this candidate's profile. The job descriptions have been intelligently extracted to preserve context and technical nuance.

CANDIDATE PROFILE:
Technical Skills: {', '.join(resume_summary.get('skills', []))}
Experience: {len(resume_summary.get('experience', []))} positions
Background: {resume_summary.get('summary', 'Not provided')}

CONTEXT-RICH JOB SUMMARIES:
{chr(10).join([f"{i+1}. {job['title']} at {job['company']}{newline}{str(job['description'])[:300]}...{newline}" for i, job in enumerate(job_summaries)])}

For each position, analyze:
1. **Technical Alignment** (0-100): How well do the candidate's skills match the technical requirements?
2. **Experience Match** (0-100): Does their experience level and domain background fit?
3. **Growth Potential** (0-100): Is this a good career progression opportunity?
4. **Overall Match Score** (0-100): Weighted average considering all factors

Provide concise analysis in JSON format:
[
  {{
    "id": 1,
    "technical_alignment": 85,
    "experience_match": 90,
    "growth_potential": 80,
    "match_score": 87,
    "matching_skills": ["Python", "AWS", "React"],
    "missing_skills": ["Kubernetes", "GraphQL"],
    "analysis": "Strong technical fit with excellent cloud experience. Good growth opportunity in fintech domain.",
    "confidence": "high"
  }}
]

Focus on accurate assessment based on the contextual job information provided.
"""

        # 🚀 DEBUG: Log prompt details
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Prompt length: {len(matching_prompt)} characters")
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: About to call OpenAI API...")

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter specializing in software engineering roles. Provide accurate, nuanced job-candidate matching analysis."},
                {"role": "user", "content": matching_prompt}
            ],
            max_tokens=2500,  # Increased from 1800 to ensure all jobs get analyzed
            temperature=0.3
        )
        
        # 🚀 DEBUG: Log OpenAI response
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: OpenAI API call successful!")
        
        # Parse and process results
        ai_response = response.choices[0].message.content
        logger.info(f"🤖 OpenAI enhanced matching response: {len(ai_response)} characters")
        
        # 🔍 DEBUG: Log the actual response to understand the format
        logger.info(f"🔍 OPENAI RESPONSE DEBUG: First 500 chars: {ai_response[:500]}")
        
        # Check if response is empty or None
        if not ai_response or ai_response.strip() == "":
            logger.warning("❌ OpenAI returned empty response, using fallback")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # Try to parse JSON response
        import json
        try:
            # Try to parse as JSON directly
            ai_analysis = json.loads(ai_response)
            logger.info(f"✅ Successfully parsed JSON response with {len(ai_analysis)} items")
        except json.JSONDecodeError as e:
            logger.warning(f"❌ JSON parsing failed: {str(e)}")
            logger.info(f"🔍 Attempting to extract JSON from response...")
            
            # Try to extract JSON from markdown code blocks or other formats
            import re
            
            # Look for JSON in code blocks
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', ai_response, re.DOTALL)
            if json_match:
                try:
                    ai_analysis = json.loads(json_match.group(1))
                    logger.info(f"✅ Extracted JSON from code block with {len(ai_analysis)} items")
                except json.JSONDecodeError:
                    logger.warning("❌ Failed to parse JSON from code block")
                    logger.warning("OpenAI response not valid JSON, using fallback")
                    return await batch_analyze_jobs_similarity(jobs, resume_data)
            else:
                # Look for JSON array pattern anywhere in the response
                json_match = re.search(r'(\[.*?\])', ai_response, re.DOTALL)
                if json_match:
                    try:
                        ai_analysis = json.loads(json_match.group(1))
                        logger.info(f"✅ Extracted JSON array with {len(ai_analysis)} items")
                    except json.JSONDecodeError:
                        logger.warning("❌ Failed to parse extracted JSON array")
                        logger.warning("OpenAI response not valid JSON, using fallback")
                        return await batch_analyze_jobs_similarity(jobs, resume_data)
                else:
                    logger.warning("❌ No JSON found in OpenAI response")
                    logger.warning("OpenAI response not valid JSON, using fallback")
                    return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # Merge AI analysis with original job data
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            ai_result = ai_analysis[i] if i < len(ai_analysis) else {}
            
            analyzed_job = {
                **job,  # Keep original full job data
                "match_score": ai_result.get('match_score', 50),
                "technical_alignment": ai_result.get('technical_alignment', 50),
                "experience_match": ai_result.get('experience_match', 50),
                "growth_potential": ai_result.get('growth_potential', 50),
                "matching_skills": ai_result.get('matching_skills', []) if isinstance(ai_result.get('matching_skills'), list) else [],
                "missing_skills": ai_result.get('missing_skills', []) if isinstance(ai_result.get('missing_skills'), list) else [],
                "summary": ai_result.get('analysis', 'Enhanced analysis not available'),
                "confidence": ai_result.get('confidence', 'medium'),
                "ai_analysis": ai_result.get('analysis', ''),
                "processing_method": "openai_realistic_primary",  # Fixed to show correct method
                "score_source": "openai_primary"  # Track that this came from OpenAI
            }
            analyzed_jobs.append(analyzed_job)
        
        logger.info(f"🔍 OPENAI ENHANCED DEBUG: Completed successfully with {len(analyzed_jobs)} analyzed jobs")
        logger.info(f"✅ Enhanced two-stage analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"Enhanced batch analysis failed: {str(e)}")
        logger.error(f"🔍 OPENAI ENHANCED DEBUG: Exception in main try block")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return await batch_analyze_jobs_similarity(jobs, resume_data)

def detect_embedded_job_platform(url: str, page_content: Dict[str, Any]) -> str:
    """
    Detect embedded job board platforms from URL and page content
    Returns platform name if detected, empty string otherwise
    """
    
    url_lower = url.lower()
    page_text = str(page_content.get('text', '')).lower()
    
    # Check URL patterns first
    if 'ashby' in url_lower or 'ashby_jid=' in url_lower:
        return 'ashby'
    elif 'greenhouse.io' in url_lower or 'grnh.se' in url_lower:
        return 'greenhouse'
    elif 'lever.co' in url_lower or 'jobs.lever.co' in url_lower:
        return 'lever'
    elif 'myworkdayjobs.com' in url_lower or 'workday' in url_lower:
        return 'workday'
    elif 'bamboohr.com' in url_lower:
        return 'bamboohr'
    elif 'smartrecruiters.com' in url_lower:
        return 'smartrecruiters'
    elif 'jobvite.com' in url_lower:
        return 'jobvite'
    
    # 🎯 ENHANCED: Check page content for embedded indicators (more comprehensive)
    if ('ashby' in page_text and 
        ('ashby_embed' in page_text or 'ashby-job-posting' in page_text or 'ashby_jid' in page_text)):
        return 'ashby'
    elif 'greenhouse' in page_text and ('gh_jid' in page_text or 'greenhouse-job' in page_text):
        return 'greenhouse'
    elif 'lever' in page_text and ('lever-job' in page_text or 'postings.lever.co' in page_text):
        return 'lever'
    elif 'workday' in page_text and ('workday-job' in page_text or 'myworkdayjobs' in page_text):
        return 'workday'
    elif 'bamboohr' in page_text and 'bamboo-job' in page_text:
        return 'bamboohr'
    
    # 🚀 NEW: Additional detection for common patterns
    # Check for specific div IDs and classes that indicate job board embeds
    if ('id="ashby_embed"' in page_text or 'id=\'ashby_embed\'' in page_text or
        'class="ashby-embed"' in page_text or 'ashby embed' in page_text):
        logger.info("🎯 Detected Ashby embed div - jobs load dynamically")
        return 'ashby'
    
    # Check for other job board indicators
    if 'greenhouse.io/embed' in page_text or 'greenhouse_iframe' in page_text:
        return 'greenhouse'
    elif 'lever.co/embed' in page_text or 'lever_iframe' in page_text:
        return 'lever'
    elif 'workday-iframe' in page_text or 'workday/embed' in page_text:
        return 'workday'
    
    return ''

def extract_ashby_jobs_fallback(url: str) -> List[Dict[str, Any]]:
    """
    Fallback extraction specifically for Ashby job boards
    Handles dynamic loading and Ashby-specific selectors
    """
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        logger.info(f"🔧 Ashby fallback extraction for: {url}")
        
        # Enhanced headers for Ashby
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scraped_jobs = []
        
        # 🎯 PRIORITY 1: Check for Ashby embed div first
        ashby_embed = soup.find('div', id='ashby_embed') or soup.find(class_='ashby-embed')
        if ashby_embed:
            logger.info("🎯 Found Ashby embed div - jobs are loaded dynamically via JavaScript")
            
            # Create an informative job entry for dynamic loading
            company_name = extract_company_from_url(url)
            return [{
                "id": "ashby-dynamic-loading",
                "title": f"💼 Current Openings at {company_name}",
                "company": company_name,
                "location": "Multiple Locations",
                "url": url,
                "description": f"""🚀 {company_name} uses Ashby job board platform with dynamic loading.

📝 **How to see available positions:**
1. **Visit the careers page directly**: {url}
2. **Wait 3-5 seconds** for jobs to load via JavaScript
3. **Refresh the Chrome extension** after jobs appear on the page
4. **Alternative**: Check back later as new positions are posted regularly

💡 **Why this happens:**
Modern job boards like Ashby load content after the initial page render to improve performance. Our system detected the Ashby embed but jobs haven't loaded yet during the scan.

🔍 **Company Info:**
Based on their careers page, {company_name} appears to be actively hiring and mentions sending resumes to careers@{url.split('//')[1].split('/')[0]} for general inquiries.""",
                "platform": "ashby",
                "scraping_method": "ashby_dynamic_loading_detected",
                "is_dynamic_loading": True,
                "user_guidance": "Visit page directly and wait for jobs to load"
            }]
        
        # 🎯 PRIORITY 2: Look for already-loaded Ashby jobs
        ashby_selectors = [
            'a[href*="ashby_jid="]',  # Direct Ashby job ID links
            '.ashby-job-posting-brief',  # Ashby job posting containers
            'a._undecorated_1aam4_1[href*="careers"]',  # Specific Ashby link classes
            '._jobPosting_12ylk_379',  # Ashby job posting divs
            '.ashby-embed a',  # Links within Ashby embed
            '[data-ashby-job-id]',  # Data attributes for Ashby jobs
            'a[href*="careers/?ashby_jid="]',  # Career page with Ashby job ID
            'div[class*="ashby"] a',  # Any div with ashby class containing links
            '.ashby-job a'  # Ashby job links
        ]
        
        for selector in ashby_selectors:
            elements = soup.select(selector)
            logger.info(f"Ashby selector '{selector}' found {len(elements)} elements")
            
            for i, element in enumerate(elements):
                try:
                    # Extract job data from Ashby elements
                    if element.name == 'a':
                        link = element
                        job_container = element
                    else:
                        link = element.find_parent('a') or element.find('a')
                        job_container = element
                    
                    if not link:
                        continue
                    
                    href = link.get('href', '')
                    
                    # Skip email links and invalid URLs
                    if ('mailto:' in href or 
                        href == url or 
                        not href or
                        href.startswith('#')):
                        continue
                    
                    # Make absolute URL
                    if href.startswith('/?'):
                        job_url = url.rstrip('/') + href
                    elif href.startswith('/'):
                        job_url = url.rstrip('/') + href
                    elif href.startswith('http'):
                        job_url = href
                    else:
                        job_url = f"{url}?{href}" if '=' in href else url
                    
                    # Extract title from Ashby structure
                    title = ""
                    title_selectors = [
                        '._title_12ylk_383',  # Ashby title class
                        '.ashby-job-posting-brief-title',
                        'h3',
                        '.job-title'
                    ]
                    
                    for title_sel in title_selectors:
                        title_el = job_container.select_one(title_sel)
                        if title_el and title_el.get_text(strip=True):
                            title = title_el.get_text(strip=True)
                            break
                    
                    if not title:
                        title = link.get_text(strip=True)
                    
                    # Extract details (location, department, type)
                    details = ""
                    details_selectors = [
                        '._details_12ylk_389',  # Ashby details class
                        '.ashby-job-posting-brief-details',
                        '.job-details',
                        '.job-meta'
                    ]
                    
                    for details_sel in details_selectors:
                        details_el = job_container.select_one(details_sel)
                        if details_el and details_el.get_text(strip=True):
                            details = details_el.get_text(strip=True)
                            break
                    
                    # Parse location from details (format: "Department • Location • Type • Schedule")
                    location = "Location TBD"
                    if details and '•' in details:
                        parts = [part.strip() for part in details.split('•')]
                        if len(parts) >= 2:
                            location = parts[1]  # Second part is usually location
                    
                    # Validate job data - stricter validation
                    if (title and len(title) > 3 and 
                        title.lower() not in ['careers', 'jobs', 'apply', 'search', 'home', 'contact'] and
                        not title.startswith('@') and  # Skip email addresses
                        job_url and job_url != url and 'mailto:' not in job_url):
                        
                        scraped_job = {
                            "id": f"ashby-job-{len(scraped_jobs)+1}",
                            "title": title[:100],
                            "company": extract_company_from_url(url),
                            "location": location,
                            "url": job_url,
                            "description": f"Ashby job posting: {title}. Department: {details if details else 'Not specified'}. Full details available at job URL.",
                            "scraping_method": f"ashby_fallback_{selector}",
                            "job_details": details,
                            "platform": "ashby"
                        }
                        scraped_jobs.append(scraped_job)
                        logger.info(f"✅ Extracted Ashby job: {title} - {location}")
                        
                        # Limit to prevent overwhelming results
                        if len(scraped_jobs) >= 20:
                            break
                    else:
                        logger.debug(f"Skipped invalid job: title='{title}', url='{job_url}'")
                    
                except Exception as e:
                    logger.warning(f"Error processing Ashby element {i}: {str(e)}")
                    continue
            
            if scraped_jobs:
                break  # Stop at first successful selector
        
        # If no jobs found but we know it's Ashby, provide helpful guidance
        if not scraped_jobs:
            logger.info("No loaded jobs found - likely dynamic loading scenario")
            company_name = extract_company_from_url(url)
            return [{
                "id": "ashby-loading-guidance",
                "title": f"🕒 Jobs Loading at {company_name}",
                "company": company_name,
                "location": "Various Locations",
                "url": url,
                "description": f"""⏰ **Dynamic Job Loading Detected**

{company_name} uses Ashby job board platform. If you're not seeing job listings:

🔄 **Try these steps:**
1. **Wait**: Jobs may take 3-10 seconds to load
2. **Refresh**: Refresh your browser and wait for content
3. **Check directly**: Visit {url} in a new tab
4. **Retry extension**: Use the Chrome extension after jobs appear

💼 **Alternative contact**: 
If jobs don't appear, you can send your resume directly to their careers email.

🔍 **Technical note**: This site loads job postings via JavaScript after the initial page render.""",
                "platform": "ashby",
                "scraping_method": "ashby_loading_guidance",
                "is_dynamic_loading": True
            }]
        
        logger.info(f"Ashby extraction completed: {len(scraped_jobs)} jobs found")
        return scraped_jobs
        
    except Exception as e:
        logger.error(f"Ashby fallback extraction failed: {str(e)}")
        return []

def extract_greenhouse_jobs_fallback(url: str) -> List[Dict[str, Any]]:
    """Fallback extraction for Greenhouse job boards"""
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scraped_jobs = []
        
        # Greenhouse-specific selectors
        greenhouse_selectors = [
            'a[href*="gh_jid="]',
            '.opening',
            '.job-post',
            'a[href*="greenhouse.io"]'
        ]
        
        for selector in greenhouse_selectors:
            elements = soup.select(selector)
            if elements:
                for i, element in enumerate(elements[:10]):
                    title = element.get_text(strip=True)
                    href = element.get('href', '')
                    
                    if title and href:
                        scraped_job = {
                            "id": f"greenhouse-{i+1}",
                            "title": title[:100],
                            "company": extract_company_from_url(url),
                            "location": "Location TBD",
                            "url": href if href.startswith('http') else url + href,
                            "description": f"Greenhouse job: {title}",
                            "platform": "greenhouse"
                        }
                        scraped_jobs.append(scraped_job)
                
                if scraped_jobs:
                    break
        
        return scraped_jobs
        
    except Exception as e:
        logger.error(f"Greenhouse fallback failed: {str(e)}")
        return []

def extract_lever_jobs_fallback(url: str) -> List[Dict[str, Any]]:
    """Fallback extraction for Lever job boards"""
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scraped_jobs = []
        
        # Lever-specific selectors
        lever_selectors = [
            '.posting',
            '.job',
            'a[href*="lever.co"]'
        ]
        
        for selector in lever_selectors:
            elements = soup.select(selector)
            if elements:
                for i, element in enumerate(elements[:10]):
                    title_el = element.find(['h3', 'h2', 'h4']) or element
                    title = title_el.get_text(strip=True)
                    
                    link = element if element.name == 'a' else element.find('a')
                    href = link.get('href', '') if link else ''
                    
                    if title and href:
                        scraped_job = {
                            "id": f"lever-{i+1}",
                            "title": title[:100],
                            "company": extract_company_from_url(url),
                            "location": "Location TBD",
                            "url": href if href.startswith('http') else url + href,
                            "description": f"Lever job: {title}",
                            "platform": "lever"
                        }
                        scraped_jobs.append(scraped_job)
                
                if scraped_jobs:
                    break
        
        return scraped_jobs
        
    except Exception as e:
        logger.error(f"Lever fallback failed: {str(e)}")
        return []

def extract_workday_jobs_fallback(url: str) -> List[Dict[str, Any]]:
    """Fallback extraction for Workday job boards"""
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scraped_jobs = []
        
        # Workday-specific selectors
        workday_selectors = [
            'a[href*="job/"]',
            '[data-automation-id*="job"]',
            '.jobPosting'
        ]
        
        for selector in workday_selectors:
            elements = soup.select(selector)
            if elements:
                for i, element in enumerate(elements[:10]):
                    title = element.get_text(strip=True)
                    href = element.get('href', '') if element.name == 'a' else element.find('a', href=True)
                    href = href.get('href', '') if hasattr(href, 'get') else str(href) if href else ''
                    
                    if title and href:
                        scraped_job = {
                            "id": f"workday-{i+1}",
                            "title": title[:100],
                            "company": extract_company_from_url(url),
                            "location": "Location TBD",
                            "url": href if href.startswith('http') else url + href,
                            "description": f"Workday job: {title}",
                            "platform": "workday"
                        }
                        scraped_jobs.append(scraped_job)
                
                if scraped_jobs:
                    break
        
        return scraped_jobs
        
    except Exception as e:
        logger.error(f"Workday fallback failed: {str(e)}")
        return []

def extract_generic_jobs_fallback(url: str) -> List[Dict[str, Any]]:
    """Generic fallback extraction for unknown job sites"""
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        logger.info(f"🔍 Attempting generic job scraping from: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        scraped_jobs = []
        
        # Generic job link selectors
        job_selectors = [
            # Traditional job URL patterns
            'a[href*="job"]', 'a[href*="position"]', 'a[href*="career"]',
            'a[href*="opening"]', 'a[href*="role"]', 'a[href*="opportunity"]',
            
            # Modern job board ID patterns (Ashby, Greenhouse, etc.)
            'a[href*="jid="]', 'a[href*="ashby_jid="]', 'a[href*="gh_jid="]',
            'a[href*="lever_id="]', 'a[href*="job_id="]', 'a[href*="posting_id="]',
            
            # Job board specific URL patterns
            'a[href*="greenhouse.io"]', 'a[href*="lever.co"]', 'a[href*="workday"]',
            'a[href*="bamboohr"]', 'a[href*="smartrecruiters"]', 'a[href*="jobvite"]',
            
            # CSS class patterns for job items
            '.job-link', '.position-link', '.career-link', '.opening-link',
            '.job-item a', '.position-item a', '.career-item a', '.opening-item a',
            
            # Modern job board CSS class patterns
            'a[class*="job"]', 'a[class*="position"]', 'a[class*="career"]',
            'a[class*="posting"]', 'a[class*="opening"]', 'a[class*="role"]',
            
            # Ashby specific patterns (common class patterns)
            'a[class*="undecorated"]', 'a[class*="jobPosting"]', '.ashby-job-posting-brief a',
            'div[class*="jobPosting"] a', 'div[class*="job-posting"] a',
            
            # Data attribute patterns
            '[data-test*="job"] a', '[data-test*="position"] a', '[data-testid*="job"] a',
            '[data-job-id] a', '[data-posting-id] a', '[data-role-id] a',
            
            # Title-based selectors
            '.jobTitle a', '.job-title a', '.position-title a', '.role-title a',
            
            # Generic container patterns that might contain job links
            'article a', '.listing a', '.post a', '[role="listitem"] a'
        ]
        
        for selector in job_selectors:
            job_links = soup.select(selector)
            if job_links:
                logger.info(f"✅ Found {len(job_links)} job links using selector: {selector}")
                
                for i, link in enumerate(job_links[:10]):  # Limit to first 10
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # Enhanced URL validation
                    if not href or not title or len(title) < 3:
                        continue
                    
                    # Skip invalid URLs
                    if (href.startswith('mailto:') or 
                        href.startswith('tel:') or 
                        href.startswith('#') or
                        href == '/' or
                        href == url):
                        continue
                    
                    # Check if it's a valid job-related link
                    href_lower = href.lower()
                    title_lower = title.lower()
                    
                    # Skip if title suggests it's not a job (common false positives)
                    skip_titles = ['home', 'about', 'contact', 'privacy', 'terms', 'login', 'sign up', 'search', 'filter']
                    if any(skip_word in title_lower for skip_word in skip_titles) and len(title) < 30:
                        continue
                    
                    # Make absolute URL
                    if href.startswith('/'):
                        job_url = url.rstrip('/') + href
                    elif href.startswith('http'):
                        job_url = href
                    else:
                        job_url = url.rstrip('/') + '/' + href
                    
                    scraped_job = {
                        "id": f"generic-{len(scraped_jobs)+1}",
                        "title": title[:100],  # Limit title length
                        "company": extract_company_from_url(url),
                        "location": "Location TBD",
                        "url": job_url,
                        "description": f"Job found via generic scraping: {title}",
                        "scraping_method": f"generic_{selector.replace('[', '').replace(']', '').replace('*', '')}",
                        "platform": "unknown"
                    }
                    scraped_jobs.append(scraped_job)
                
                if scraped_jobs:
                    break  # Stop at first successful selector
        
        logger.info(f"Generic extraction completed: {len(scraped_jobs)} jobs found")
        return scraped_jobs
        
    except Exception as e:
        logger.error(f"❌ Generic fallback extraction failed: {str(e)}")
        return []

def extract_deutsche_bank_job(soup: BeautifulSoup, job: Dict[str, Any], job_url: str) -> Dict[str, Any]:
    """
    Deutsche Bank careers site extraction with dynamic content handling
    Deutsche Bank uses a SPA (Single Page Application) where job details are loaded via JavaScript
    """
    
    try:
        logger.info(f"🏦 Extracting Deutsche Bank job from: {job_url}")
        
        # Deutsche Bank specific selectors
        # The site structure is: careers.db.com/professionals/search-roles/#/professional/job/{job_id}
        
        # Extract job ID from URL for potential API calls
        job_id = None
        if '/job/' in job_url:
            job_id = job_url.split('/job/')[-1]
            logger.info(f"🆔 Extracted job ID: {job_id}")
        
        # Try to extract basic info from the initial HTML
        # Deutsche Bank often has some metadata in the initial page
        
        # Title extraction - try multiple approaches
        title_found = False
        
        # Method 1: Look for job title in meta tags
        meta_title = soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            potential_title = meta_title.get('content').strip()
            if potential_title and len(potential_title) > 5 and 'Deutsche Bank' not in potential_title:
                job["title"] = potential_title
                title_found = True
                logger.info(f"📋 Found title in meta tag: {potential_title}")
        
        # Method 2: Look for title in page title
        if not title_found:
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text().strip()
                # Clean up the title
                if ' - ' in title_text:
                    potential_title = title_text.split(' - ')[0].strip()
                    if potential_title and len(potential_title) > 5:
                        job["title"] = potential_title
                        title_found = True
                        logger.info(f"📋 Found title in page title: {potential_title}")
        
        # Method 3: Look for structured data
        if not title_found:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('title'):
                        job["title"] = data['title']
                        title_found = True
                        logger.info(f"📋 Found title in structured data: {data['title']}")
                        break
                except:
                    continue
        
        # Set company
        job["company"] = "Deutsche Bank"
        
        # Try to extract location from various sources
        location_selectors = [
            '[data-testid*="location"]',
            '.location',
            '.job-location',
            '.city'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                logger.info(f"📍 Found location: {job['location']}")
                break
        
        # For Deutsche Bank, the main content is loaded dynamically
        # We need to provide a meaningful description that indicates this
        
        # Try to extract any available content from the initial page
        content_areas = []
        
        # Look for any job-related content in the initial HTML
        content_selectors = [
            '.job-description',
            '.job-content',
            '.description',
            '.content',
            'main',
            '.main-content',
            '#content'
        ]
        
        for selector in content_selectors:
            content_el = soup.select_one(selector)
            if content_el:
                text_content = content_el.get_text().strip()
                if text_content and len(text_content) > 50:
                    content_areas.append(text_content[:500])  # Limit to 500 chars
        
        # Build description
        if content_areas:
            # Use the longest content area found
            best_content = max(content_areas, key=len)
            job["description"] = f"Position: {job.get('title', 'Software Engineer')} at Deutsche Bank\n\n{best_content}"
        else:
            # Fallback description for Deutsche Bank jobs
            job["description"] = f"""Position: {job.get('title', 'Software Engineer')} at Deutsche Bank

Deutsche Bank is a leading global investment bank with a strong and profitable private clients franchise. We are seeking talented professionals to join our technology teams.

Key areas of focus:
• Software development and engineering
• Financial technology solutions
• Digital transformation initiatives
• Risk management systems
• Trading platforms and analytics

This role offers the opportunity to work with cutting-edge technology in the financial services industry, contributing to Deutsche Bank's digital transformation and innovation initiatives.

Location: {job.get('location', 'Various locations globally')}

Note: This is a dynamic job posting. For complete details, please visit the original job posting at Deutsche Bank careers."""
        
        # Set default location if not found
        if not job.get("location"):
            job["location"] = "Various Locations"
        
        # Set default title if not found
        if not job.get("title"):
            job["title"] = "Software Engineer"
        
        # Add Deutsche Bank specific metadata
        job["extraction_method"] = "deutsche_bank_enhanced"
        job["requires_dynamic_loading"] = True
        job["job_id"] = job_id
        
        logger.info(f"✅ Deutsche Bank extraction completed: {job['title']} at {job['company']}")
        logger.info(f"📄 Description length: {len(job.get('description', ''))}")
        
    except Exception as e:
        logger.error(f"❌ Error extracting Deutsche Bank job: {str(e)}")
        # Provide fallback data
        job["title"] = job.get("title") or "Software Engineer"
        job["company"] = "Deutsche Bank"
        job["location"] = job.get("location") or "Various Locations"
        job["description"] = f"Deutsche Bank {job['title']} position. Please visit the original job posting for complete details."
        job["extraction_method"] = "deutsche_bank_fallback"
    
    return job

def extract_generic_job(soup: BeautifulSoup, job: Dict[str, Any]) -> Dict[str, Any]:
    """Universal job extraction for any unknown site"""
    
    try:
        # Generic title extraction
        title_selectors = ['h1', 'h2', '.job-title', '.title', '.position-title', '.role-title']
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Generic company extraction
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            parts = title_text.split(' - ')
            if len(parts) > 1:
                job["company"] = parts[-1].strip()
        
        # Generic location extraction
        location_selectors = ['.location', '.job-location', '.city', '.address']
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "generic")
        
    except Exception as e:
        logger.error(f"Error in generic extraction: {str(e)}")
        job["description"] = f"Job details (generic extraction error: {str(e)})"
    
    return job

if __name__ == "__main__":
    print("Starting Enhanced Bulk-Scanner API server...")
    print(f"OpenAI API Key available: {bool(os.getenv('OPENAI_API_KEY'))}")
    print(f"Resume processing available: {ResumeProcessor is not None}")
    
    # Show extraction methods status
    print("\n🔧 Job Extraction Methods:")
    if os.getenv('GROQ_API_KEY'):
        print("✅ Groq (Llama 3-70B) - FREE, 6,000 requests/day")
    else:
        print("❌ Groq - Get free key: https://console.groq.com/")
    
    if os.getenv('OLLAMA_AVAILABLE', '').lower() == 'true':
        print("✅ Ollama (Local) - FREE, unlimited")
    else:
        print("❌ Ollama - Install locally for unlimited free extraction")
    
    if os.getenv('HUGGINGFACE_API_KEY'):
        print("✅ HuggingFace - FREE tier available")
    else:
        print("❌ HuggingFace - Optional free tier")
    
    print("✅ Smart Keyword Extraction - Always available")
    
    print(f"\n💰 Cost per 50 jobs: $0.02 (96% savings vs old system)")
    print(f"🚀 Quality ranking: Groq > Ollama > HuggingFace > Smart Extraction")
    
    # Production-ready server configuration
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("DEBUG", "false").lower() == "true"
    
    uvicorn.run(
        "main_simple:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    ) 