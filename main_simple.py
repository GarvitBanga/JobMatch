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
    allow_origins=[
        "chrome-extension://*",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
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
    match_threshold: float = 0.7

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
            "job_matching": JobMatcher is not None
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
    Enhanced scan endpoint that uses real resume data for job matching
    """
    try:
        import time
        start_time = time.time()
        
        # Extract jobs from page content (this would be enhanced in real implementation)
        jobs = extract_jobs_from_page_content(request.page_content, request.url)
        
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
        filtered_jobs = [
            job for job in matched_jobs 
            if job.get('match_score', 0) >= (request.match_threshold * 100)
        ]
        
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
                    confidence=job.get('confidence', 'medium')
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
    """Extract job listings from page content"""
    
    # Try to get jobs from content script extraction
    if 'jobs' in page_content and page_content['jobs']:
        logger.info(f"Found {len(page_content['jobs'])} jobs from content script")
        return page_content['jobs']
    
    # Generate mock jobs based on URL for demo purposes
    company_name = extract_company_from_url(url)
    
    mock_jobs = [
        {
            "id": "1",
            "title": "Senior Software Engineer",
            "company": company_name,
            "location": "San Francisco, CA",
            "url": f"{url}/job/1",
            "description": "We are looking for a skilled software engineer with experience in React, Node.js, and cloud technologies. You will work on building scalable web applications and APIs."
        },
        {
            "id": "2", 
            "title": "Full Stack Developer",
            "company": company_name,
            "location": "Remote",
            "url": f"{url}/job/2",
            "description": "Join our team to build modern web applications using JavaScript, Python, and AWS. Experience with databases and DevOps is a plus."
        },
        {
            "id": "3",
            "title": "Frontend Developer",
            "company": company_name,
            "location": "New York, NY",
            "url": f"{url}/job/3",
            "description": "Looking for a frontend developer skilled in React, TypeScript, and modern CSS frameworks. You'll create beautiful user interfaces."
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

if __name__ == "__main__":
    print("Starting Enhanced Bulk-Scanner API server...")
    print(f"OpenAI API Key available: {bool(os.getenv('OPENAI_API_KEY'))}")
    print(f"Resume processing available: {ResumeProcessor is not None}")
    
    uvicorn.run(
        "main_simple:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 