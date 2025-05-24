#!/usr/bin/env python3
"""
Enhanced FastAPI server with resume processing and LLM integration
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import os
import logging
import requests
from bs4 import BeautifulSoup
import asyncio

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

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
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
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
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "bulk-scanner-api",
        "features": {
            "resume_processing": ResumeProcessor is not None,
            "llm_matching": bool(os.getenv("OPENAI_API_KEY")),
            "job_matching": JobMatcher is not None,
            "extraction_methods": {
                "groq_llama": bool(os.getenv("GROQ_API_KEY")),
                "ollama_local": os.getenv("OLLAMA_AVAILABLE", "").lower() == "true",
                "huggingface": bool(os.getenv("HUGGINGFACE_API_KEY")),
                "smart_keyword": True  # Always available
            }
        },
        "recommended_setup": {
            "groq_api_key": "Get free key at https://console.groq.com/ (6,000 requests/day)",
            "cost_per_50_jobs": "$0.02",
            "extraction_quality": "groq > ollama > huggingface > smart_keyword"
        }
    }

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
async def scan_page_with_resume(request: ScanPageRequest):
    """
    Enhanced scan endpoint that supports both individual and batch processing
    """
    try:
        import time
        start_time = time.time()
        
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
        if request.batch_processing and request.resume_data and len(jobs) > 3:
            logger.info(f"🚀 Using batch processing for {len(jobs)} jobs")
            
            # Use the new batch matching endpoint internally
            batch_request = BatchJobMatchRequest(
                jobs=jobs,
                resume_data=request.resume_data,
                user_id=request.user_id,
                match_threshold=request.match_threshold,
                max_results=15  # Return more results for better selection
            )
            
            # Call batch processing function directly
            return await batch_job_matching(batch_request)
        
        # Fallback to original processing for smaller job sets or when batch is disabled
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
    
    # Check for enhanced content script data
    jobs_found = []
    
    # Try new enhanced format first - prioritize jobElements with structure
    if 'jobElements' in page_content and page_content['jobElements']:
        logger.info("Found enhanced job data from content script")
        job_elements = page_content['jobElements']
        logger.info(f"Processing {len(job_elements)} job elements")
        
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
    
    # Fallback to jobLinks if no good jobElements
    elif 'jobLinks' in page_content and page_content['jobLinks']:
        logger.info("Using jobLinks as fallback")
        job_links = page_content['jobLinks']
        
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
                
    # Final fallback to legacy format
    elif 'jobs' in page_content and page_content['jobs']:
        jobs_found = page_content['jobs']
        logger.info(f"Using legacy jobs format: {len(jobs_found)} jobs")
    
    # 🚀 NEW: FETCH FULL JOB DESCRIPTIONS FROM INDIVIDUAL JOB PAGES
    if jobs_found:
        logger.info(f"📡 Fetching full job descriptions from {len(jobs_found)} individual job pages...")
        
        enhanced_jobs = []
        for i, job in enumerate(jobs_found):
            job_url = job.get('url', '')
            
            # Skip if no valid URL
            if not job_url or job_url == url:
                logger.warning(f"Job {i+1}: No valid URL, using summary description")
                enhanced_jobs.append(job)
                continue
            
            try:
                logger.info(f"🔗 Fetching job {i+1}/{len(jobs_found)}: {job_url}")
                
                # Enhanced headers to bypass bot detection
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
                
                # Fetch the individual job page
                import requests
                from bs4 import BeautifulSoup
                
                response = requests.get(job_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse the job page
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract full job details using the existing Amazon extraction logic
                full_job_data = {
                    "url": job_url,
                    "title": job.get('title', ''),
                    "company": job.get('company', 'Amazon'),
                    "location": job.get('location', ''),
                    "description": "",
                    "extraction_method": "individual_page_fetch"
                }
                
                # Use the existing Amazon job extraction function
                full_job_data = extract_universal_job_content(soup, full_job_data)
                
                # Update the original job with full description
                enhanced_job = {
                    **job,
                    "description": full_job_data.get('description', job.get('description', '')),
                    "full_details_fetched": True,
                    "original_summary": job.get('description', ''),  # Keep original summary for reference
                }
                
                enhanced_jobs.append(enhanced_job)
                logger.info(f"✅ Job {i+1}: Fetched {len(full_job_data.get('description', ''))} characters")
                
            except Exception as e:
                logger.error(f"❌ Failed to fetch job {i+1} ({job_url}): {str(e)}")
                # Keep original job data if fetch fails
                job['full_details_fetched'] = False
                job['fetch_error'] = str(e)
                enhanced_jobs.append(job)
        
        logger.info(f"✅ Enhanced {len(enhanced_jobs)} jobs with full descriptions")
        return enhanced_jobs
    
    # Generate mock jobs if no real jobs found
    logger.info("No jobs found in any format, generating mock jobs for demo")
    company_name = extract_company_from_url(url)
    
    mock_jobs = [
        {
            "id": "mock-1",
            "title": "Senior Software Engineer",
            "company": company_name,
            "location": "San Francisco, CA",
            "url": f"{url}#job-1",
            "description": f"We are looking for a skilled software engineer to join {company_name}. You will work with modern technologies including React, Node.js, Python, and cloud platforms. This role offers opportunities to build scalable systems and work with a dynamic team on challenging technical problems."
        },
        {
            "id": "mock-2", 
            "title": "Full Stack Developer",
            "company": company_name,
            "location": "Remote",
            "url": f"{url}#job-2",
            "description": f"Join our engineering team at {company_name} to build modern web applications. We use JavaScript, Python, TypeScript, AWS, and Docker. Experience with databases, API design, and DevOps practices is highly valued. Great opportunity for growth and learning."
        },
        {
            "id": "mock-3",
            "title": "Frontend Developer",
            "company": company_name,
            "location": "New York, NY",
            "url": f"{url}#job-3",
            "description": f"Looking for a frontend developer skilled in React, TypeScript, and modern CSS frameworks. At {company_name}, you'll create beautiful user interfaces and work closely with design and backend teams to deliver exceptional user experiences."
        }
    ]
    
    return mock_jobs

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
    """Extract job details from Workday sites using universal extraction"""
    
    try:
        # Enhanced title extraction for Workday
        title_selectors = [
            '[data-automation-id="jobPostingHeader"]',
            'h1[data-automation-id]',
            'h1.gwt-Label',
            '.css-12za9md',
            'h1'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Enhanced company extraction for Workday
        company_selectors = [
            '[data-automation-id="breadcrumb"] span',
            '.css-1c6k6o1',
            'title'
        ]
        
        for selector in company_selectors:
            company_el = soup.select_one(selector)
            if company_el and company_el.get_text().strip():
                company_text = company_el.get_text().strip()
                if 'careers' not in company_text.lower():
                    job["company"] = company_text.split('-')[0].strip()
                    break
        
        # Enhanced location extraction for Workday
        location_selectors = [
            '[data-automation-id="locations"]',
            '.css-1t6zqoe',
            '[data-automation-id="jobPostingHeaderSubtitle"]'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "workday")
        
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
        # Enhanced title extraction for Amazon
        title_selectors = [
            'h1.header-module_title__3cOil',
            'h1[data-test-id="header-title"]',
            'h1',
            'h2'
        ]
        
        for selector in title_selectors:
            title_el = soup.select_one(selector)
            if title_el and title_el.get_text().strip():
                job["title"] = title_el.get_text().strip()
                break
        
        # Company
        job["company"] = "Amazon"
        
        # Enhanced location extraction for Amazon
        location_selectors = [
            '[data-test-id="header-location"]',
            '.header-module_location__2P5bY',
            '.location'
        ]
        
        for selector in location_selectors:
            location_el = soup.select_one(selector)
            if location_el and location_el.get_text().strip():
                job["location"] = location_el.get_text().strip()
                break
        
        # Use universal content extraction
        job = extract_universal_job_content(soup, job, "amazon")
        
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
    else:
        return 'generic'

@app.post("/api/v1/match/batch", response_model=ScanPageResponse)
async def batch_job_matching(request: BatchJobMatchRequest):
    """
    Batch job matching endpoint - sends all jobs to OpenAI in a single API call
    This is much more cost-effective than individual job analysis
    """
    try:
        import time
        start_time = time.time()
        
        logger.info(f"🔄 Batch matching {len(request.jobs)} jobs for user {request.user_id}")
        
        # Check if we have OpenAI API key for intelligent matching
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if openai_api_key and len(request.jobs) > 0:
            logger.info("🤖 Using enhanced OpenAI batch analysis with context extraction")
            
            # Check if Llama/free LLM is available for context extraction
            use_llama = (
                os.getenv('GROQ_API_KEY') or 
                os.getenv('OLLAMA_AVAILABLE', '').lower() == 'true' or 
                os.getenv('HUGGINGFACE_API_KEY')
            )
            
            if use_llama:
                logger.info("🧠 Llama available for context-aware extraction")
                matched_jobs = await batch_analyze_jobs_with_openai_enhanced(request.jobs, request.resume_data, openai_api_key, use_llama_extraction=True)
                processing_method = "llama_openai_enhanced"
            else:
                logger.info("📝 Using smart extraction with OpenAI matching")
                matched_jobs = await batch_analyze_jobs_with_openai(request.jobs, request.resume_data, openai_api_key)
                processing_method = "smart_openai_optimized"
        else:
            logger.info("📊 Using fallback similarity matching")
            matched_jobs = await batch_analyze_jobs_similarity(request.jobs, request.resume_data)
            processing_method = "similarity_batch"
        
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
        
        return ScanPageResponse(
            success=True,
            message=f"Batch analyzed {len(request.jobs)} jobs, found {len(top_jobs)} matches",
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
    Analyze all jobs in a single OpenAI API call for cost efficiency
    Now uses concise job summaries to reduce token usage
    """
    try:
        import openai
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # 🚀 NEW: Create concise summaries for OpenAI processing
        logger.info("📝 Creating concise job summaries for OpenAI analysis...")
        job_summaries = []
        
        for i, job in enumerate(jobs):
            # Create concise summary
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
        
        # Create focused prompt for batch analysis
        prompt = f"""
Analyze {len(job_summaries)} software engineering jobs against this candidate's profile. Focus on technical skill alignment and experience relevance.

CANDIDATE PROFILE:
Skills: {', '.join(resume_summary.get('skills', []))}
Experience: {len(resume_summary.get('experience', []))} positions
Education: {', '.join(resume_summary.get('education', []))}

JOBS TO ANALYZE:
{chr(10).join([f"{i+1}. {job['title']} at {job['company']} - {job['description'][:200]}..." for i, job in enumerate(job_summaries)])}

For each job, provide:
1. Match score (0-100) based on skills and experience alignment
2. Top 3 matching skills from candidate profile
3. Top 2 missing skills that would strengthen candidacy
4. Brief match reasoning (1 sentence)
5. Confidence level (high/medium/low)

Format as JSON array:
[
  {{
    "id": 1,
    "match_score": 85,
    "matching_skills": ["Python", "AWS", "React"],
    "missing_skills": ["Kubernetes", "GraphQL"],
    "analysis": "Strong technical match with required Python and cloud experience.",
    "confidence": "high"
  }}
]

Focus on technical requirements and career progression fit. Be concise and accurate.
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Using 3.5-turbo for cost efficiency
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter. Provide accurate, concise job-candidate matching analysis."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,  # Reduced tokens since we need less output
            temperature=0.3
        )
        
        # Parse OpenAI response
        ai_response = response.choices[0].message.content
        logger.info(f"🤖 OpenAI response length: {len(ai_response)} characters")
        
        # Try to parse JSON response
        import json
        try:
            ai_analysis = json.loads(ai_response)
        except json.JSONDecodeError:
            logger.warning("OpenAI response not valid JSON, using fallback")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # Merge AI analysis with original job data
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            ai_result = ai_analysis[i] if i < len(ai_analysis) else {}
            
            analyzed_job = {
                **job,  # Keep original full job data
                "match_score": ai_result.get('match_score', 50),
                "matching_skills": ai_result.get('matching_skills', []),
                "missing_skills": ai_result.get('missing_skills', []),
                "summary": ai_result.get('analysis', 'AI analysis not available'),
                "confidence": ai_result.get('confidence', 'medium'),
                "ai_analysis": ai_result.get('analysis', ''),
                "processing_method": "openai_batch_optimized"
            }
            analyzed_jobs.append(analyzed_job)
        
        logger.info(f"✅ Optimized OpenAI batch analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"OpenAI batch analysis failed: {str(e)}")
        # Fallback to similarity matching
        return await batch_analyze_jobs_similarity(jobs, resume_data)

async def batch_analyze_jobs_similarity(jobs: List[Dict], resume_data: Dict) -> List[Dict]:
    """
    Fallback similarity-based matching when OpenAI is not available
    """
    try:
        # 🔍 PRINT JOB DESCRIPTIONS BEING ANALYZED IN BATCH MODE
        print("\n" + "="*80)
        print(f"🔄 BATCH ANALYZING {len(jobs)} JOBS WITH SIMILARITY MATCHING")
        print("="*80)
        
        # 🚀 DEMO: Test Groq extraction on first 3 jobs to show quality
        if os.getenv('GROQ_API_KEY') and len(jobs) >= 3:
            print("\n🧪 GROQ EXTRACTION DEMO (First 3 Jobs)")
            print("="*80)
            
            for i in range(min(3, len(jobs))):
                job = jobs[i]
                print(f"\n📋 DEMO JOB #{i+1}")
                print(f"Title: {job.get('title', 'No Title')}")
                print(f"Company: {job.get('company', 'No Company')}")
                print(f"Original Length: {len(str(job.get('description', '')))} characters")
                
                # Test Groq extraction
                if len(str(job.get('description', ''))) > 2000:
                    enhanced_job = await create_llama_context_extraction(job)
                    
                    # Show comparison
                    if enhanced_job.get('extraction_method') == 'groq_llama_extraction':
                        original_len = enhanced_job.get('original_description_length', 0)
                        summary_len = enhanced_job.get('summary_description_length', 0)
                        print(f"🎯 GROQ SUCCESS: {original_len} → {summary_len} chars ({enhanced_job.get('compression_ratio', 'N/A')})")
                    else:
                        print("🔄 Groq extraction not used (description too short or API issue)")
                else:
                    print("⏭️  Job description too short for Groq extraction demo")
                
                # 🕐 SMART: Add delay between requests to avoid rate limits
                if i < 2:  # Don't delay after last job
                    print("⏳ Pausing 3 seconds to respect rate limits...")
                    await asyncio.sleep(3)
            
            print("\n" + "="*80)
            print("📊 GROQ DEMO COMPLETE - Now proceeding with similarity matching...")
            print("="*80)
        
        for i, job in enumerate(jobs, 1):
            print(f"\n📋 ANALYZING JOB #{i}")
            print(f"Title: {job.get('title', 'No Title')}")
            print(f"Company: {job.get('company', 'No Company')}")
            print(f"Location: {job.get('location', 'No Location')}")
            description = job.get('description', 'No description available')
            print(f"Description Length: {len(str(description))}")
            print("Description Preview:")
            print("-" * 40)
            # 🚀 SHOW MORE CONTENT - Print first 1500 characters instead of 300
            if len(description) > 1500:
                print(description[:1500])
                print("\n[Description continues... showing first 1500 characters]")
                print(f"[Total length: {len(description)} characters]")
            else:
                print(description)
            print("-" * 40)
        
        print("="*80 + "\n")
        
        # Common words to exclude from matching
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'as', 'are', 'was', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'is', 'am', 'we', 'you', 'they', 'them', 'their', 'this', 'that', 'these', 'those', 'if', 'when', 'where', 'how', 'why', 'what', 'who', 'which'}
        
        # Prepare resume text
        resume_skills = resume_data.get('skills', [])
        resume_text = ' '.join(resume_skills) + ' ' + resume_data.get('summary', '')
        
        # Analyze each job
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            job_text_lower = job.get('description', '').lower()
            
            # Debug logging for first few jobs
            if i < 3:
                logger.info(f"DEBUG Job {i+1}: Title='{job.get('title', 'None')}', Description preview='{job.get('description', 'None')[:100]}...'")
                logger.info(f"DEBUG Job {i+1}: Job words sample: {list(job_text_lower.split())[:10]}")
            
            # Calculate match score based on keyword overlap
            matching_keywords = set(job_text_lower.split()) - common_words
            
            # Calculate match percentage
            match_percentage = min(int((len(matching_keywords) / len(job_text_lower.split())) * 100), 100)
            
            # Start with base score
            match_score = 30  # Base score
            
            # Boost score if key skills are found
            skill_matches = []
            for skill in resume_skills:
                if skill.lower() in job_text_lower:
                    skill_matches.append(skill)
                    match_score += 10  # Bonus for each skill match
            
            # Special handling for Amazon jobs - boost common tech terms
            amazon_tech_terms = ['aws', 'cloud', 'java', 'python', 'javascript', 'react', 'node', 'docker', 'kubernetes', 'sql']
            amazon_matches = [term for term in amazon_tech_terms if term in job_text_lower]
            if amazon_matches:
                match_score += len(amazon_matches) * 5  # Bonus for Amazon tech terms
                skill_matches.extend(amazon_matches)
            
            # Cap the score at 100
            match_score = min(match_score, 100)
            
            # Ensure minimum score for real jobs
            match_score = max(match_score, 25)  # Minimum score
            
            analyzed_job = {
                **job,
                "match_score": match_score,
                "matching_skills": skill_matches[:5],
                "missing_skills": [],
                "summary": f"Similarity-based match: {match_percentage}% alignment with your profile",
                "confidence": "medium" if match_score > 60 else "low",
                "processing_method": "similarity_batch"
            }
            analyzed_jobs.append(analyzed_job)
            
            # Print analysis result
            print(f"✅ Job #{i+1} Analysis: Score={match_score}%, Skills matched: {skill_matches}")
        
        logger.info(f"✅ Similarity batch analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"Similarity analysis failed: {str(e)}")
        # Return basic job data with minimal scoring
        return [
            {
                **job,
                "match_score": 50,
                "matching_skills": [],
                "missing_skills": [],
                "summary": "Basic job information available",
                "confidence": "low"
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
                
                print("🔄 Calling Groq API for intelligent extraction...")
                
                groq_url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                    "Content-Type": "application/json"
                }
                
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
                
                # 🔄 SMART RATE LIMITING: Retry with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = requests.post(groq_url, headers=headers, json=payload, timeout=15)
                        
                        if response.status_code == 200:
                            result = response.json()
                            llama_summary = result['choices'][0]['message']['content'].strip()
                            
                            if llama_summary and len(llama_summary) > 100:
                                # Clean up and format the summary
                                if len(llama_summary) > 1000:  # Reduced from 1200
                                    llama_summary = llama_summary[:1000] + "..."
                                
                                # Create final description with structure
                                final_description = f"Position: {title} at {company}\n\n{llama_summary}"
                                
                                # 🔍 DEBUG: Print extraction results
                                print("✅ Groq extraction successful!")
                                print(f"📊 Compression: {len(full_description)} → {len(final_description)} chars ({len(final_description)/len(full_description)*100:.1f}%)")
                                print("🧠 Groq Extracted Summary:")
                                print("-" * 40)
                                print(llama_summary)
                                print("-" * 40)
                                print("=" * 60 + "\n")
                                
                                job_summary = job.copy()
                                job_summary['description'] = final_description
                                job_summary['original_description_length'] = len(full_description)
                                job_summary['summary_description_length'] = len(final_description)
                                job_summary['extraction_method'] = 'groq_llama_extraction'
                                job_summary['compression_ratio'] = f"{len(final_description)/len(full_description)*100:.1f}%"
                                
                                logger.info(f"🚀 Groq extracted '{title}': {len(full_description)} → {len(final_description)} chars ({job_summary['compression_ratio']})")
                                return job_summary
                        
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
                            
                            print(f"⚠️  Rate limit hit (attempt {attempt + 1}/{max_retries})")
                            print(f"⏳ Waiting {wait_time:.1f} seconds before retry...")
                            
                            if attempt < max_retries - 1:  # Don't wait on last attempt
                                time.sleep(wait_time)
                                continue
                            else:
                                print(f"❌ Max retries reached. Using fallback extraction.")
                                print("💡 Tip: Process fewer jobs at once or upgrade Groq tier")
                                print("=" * 60 + "\n")
                                break
                        else:
                            print(f"❌ Groq API error: {response.status_code} - {response.text}")
                            print("=" * 60 + "\n")
                            break
                    
                    except requests.exceptions.Timeout:
                        print(f"⏰ Groq API timeout (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            break
                    
                    except Exception as e:
                        print(f"❌ Groq request failed: {str(e)}")
                        break
            
            except Exception as e:
                print(f"❌ Groq extraction failed: {str(e)}")
                print("=" * 60 + "\n")
                logger.warning(f"Groq extraction failed: {str(e)}")
        else:
            print("❌ GROQ_API_KEY not found - skipping Groq extraction")
            print("=" * 60 + "\n")
        
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
        print(f"🔄 All LLM options unavailable, using smart keyword extraction for '{title}'")
        print("=" * 60 + "\n")
        logger.info(f"🔄 All LLM options unavailable, using smart keyword extraction for '{title}'")
        return create_concise_job_summary(job)
        
    except Exception as e:
        print(f"❌ Error in LLM context extraction: {str(e)}")
        print("=" * 60 + "\n")
        logger.error(f"Error in LLM context extraction: {str(e)}")
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
        
        client = OpenAI(api_key=api_key)
        
        # 🚀 Stage 1: Use Llama for intelligent context extraction
        if use_llama_extraction:
            logger.info("🧠 Using Llama for context-aware job extraction...")
            job_summaries = []
            
            for i, job in enumerate(jobs):
                # Use Llama for intelligent extraction
                job_summary = await create_llama_context_extraction(job)
                
                summary = {
                    "id": i + 1,
                    "title": job_summary.get('title', 'Unknown'),
                    "company": job_summary.get('company', 'Unknown'),
                    "location": job_summary.get('location', 'Unknown'),
                    "description": job_summary.get('description', ''),
                    "extraction_method": job_summary.get('extraction_method', 'smart'),
                    "original_length": job_summary.get('original_description_length', 0),
                    "summary_length": job_summary.get('summary_description_length', 0)
                }
                job_summaries.append(summary)
        else:
            # Fallback to smart extraction
            logger.info("📝 Using smart keyword extraction...")
            job_summaries = []
            for i, job in enumerate(jobs):
                job_summary = create_concise_job_summary(job)
                summary = {
                    "id": i + 1,
                    "title": job_summary.get('title', 'Unknown'),
                    "company": job_summary.get('company', 'Unknown'),
                    "location": job_summary.get('location', 'Unknown'),
                    "description": job_summary.get('description', ''),
                    "original_length": job_summary.get('original_description_length', 0),
                    "summary_length": job_summary.get('summary_description_length', 0)
                }
                job_summaries.append(summary)
        
        # Calculate processing statistics
        total_original = sum(s.get('original_length', 0) for s in job_summaries)
        total_summary = sum(s.get('summary_length', 0) for s in job_summaries)
        savings = f"{total_summary/total_original*100:.1f}%" if total_original > 0 else "0%"
        
        logger.info(f"💰 Context extraction: {total_original} → {total_summary} chars ({savings} of original)")
        
        # 🎯 Stage 2: Use OpenAI for intelligent job-resume matching
        logger.info("🤖 Using OpenAI for intelligent job-resume matching...")
        
        # Prepare focused resume summary
        resume_summary = {
            "skills": resume_data.get('skills', [])[:12],
            "experience": [
                {
                    "title": exp.get('title', ''),
                    "company": exp.get('company', ''),
                    "technologies": exp.get('technologies', [])[:6],
                    "duration": exp.get('duration', '')
                }
                for exp in resume_data.get('experience', [])[:3]
            ],
            "education": [edu.get('degree', '') for edu in resume_data.get('education', [])][:2],
            "summary": resume_data.get('summary', '')[:400] if resume_data.get('summary') else ''
        }
        
        # Create enhanced matching prompt
        newline = chr(10)
        matching_prompt = f"""
Analyze {len(job_summaries)} software engineering positions against this candidate's profile. The job descriptions have been intelligently extracted to preserve context and technical nuance.

CANDIDATE PROFILE:
Technical Skills: {', '.join(resume_summary.get('skills', []))}
Experience: {len(resume_summary.get('experience', []))} positions
Background: {resume_summary.get('summary', 'Not provided')}

CONTEXT-RICH JOB SUMMARIES:
{chr(10).join([f"{i+1}. {job['title']} at {job['company']}{newline}{job['description'][:300]}...{newline}" for i, job in enumerate(job_summaries)])}

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

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert technical recruiter specializing in software engineering roles. Provide accurate, nuanced job-candidate matching analysis."},
                {"role": "user", "content": matching_prompt}
            ],
            max_tokens=1800,
            temperature=0.3
        )
        
        # Parse and process results
        ai_response = response.choices[0].message.content
        logger.info(f"🤖 OpenAI enhanced matching response: {len(ai_response)} characters")
        
        import json
        try:
            ai_analysis = json.loads(ai_response)
        except json.JSONDecodeError:
            logger.warning("OpenAI response not valid JSON, using fallback")
            return await batch_analyze_jobs_similarity(jobs, resume_data)
        
        # Merge enhanced analysis with original job data
        analyzed_jobs = []
        for i, job in enumerate(jobs):
            ai_result = ai_analysis[i] if i < len(ai_analysis) else {}
            
            analyzed_job = {
                **job,  # Keep original full job data
                "match_score": ai_result.get('match_score', 50),
                "technical_alignment": ai_result.get('technical_alignment', 50),
                "experience_match": ai_result.get('experience_match', 50),
                "growth_potential": ai_result.get('growth_potential', 50),
                "matching_skills": ai_result.get('matching_skills', []),
                "missing_skills": ai_result.get('missing_skills', []),
                "summary": ai_result.get('analysis', 'Enhanced analysis not available'),
                "confidence": ai_result.get('confidence', 'medium'),
                "ai_analysis": ai_result.get('analysis', ''),
                "processing_method": "llama_openai_enhanced" if use_llama_extraction else "smart_openai_enhanced"
            }
            analyzed_jobs.append(analyzed_job)
        
        logger.info(f"✅ Enhanced two-stage analysis complete for {len(analyzed_jobs)} jobs")
        return analyzed_jobs
        
    except Exception as e:
        logger.error(f"Enhanced batch analysis failed: {str(e)}")
        return await batch_analyze_jobs_similarity(jobs, resume_data)

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
    
    uvicorn.run(
        "main_simple:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 