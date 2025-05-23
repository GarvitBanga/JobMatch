"""
API endpoints for scanning and processing job pages
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, HttpUrl
import time
import json

from ...services.scraper import ScrapingService
from ...services.matcher import MatchingService
from ...core.config import settings

router = APIRouter()

class ScanRequest(BaseModel):
    """Request model for page scanning"""
    url: str
    page_content: Optional[Dict[str, Any]] = None
    user_id: str
    resume_text: Optional[str] = None
    match_threshold: Optional[float] = None

class JobResult(BaseModel):
    """Job result model"""
    id: str
    title: str
    company: str
    location: str
    url: str
    match_score: float
    skills: List[str] = []
    summary: Optional[str] = None

class ScanResponse(BaseModel):
    """Response model for scan results"""
    success: bool
    message: str
    jobs_found: int
    matches: List[JobResult] = []
    processing_time_ms: int
    error: Optional[str] = None

@router.post("/page", response_model=ScanResponse)
async def scan_page(
    request: ScanRequest,
    background_tasks: BackgroundTasks
):
    """
    Scan a career page and return matching jobs
    
    This endpoint:
    1. Extracts job listings from the provided page content
    2. Matches jobs against the user's resume
    3. Returns top matching jobs with scores
    """
    start_time = time.time()
    
    try:
        # Validate inputs
        if not request.url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        if not request.user_id:
            raise HTTPException(status_code=400, detail="User ID is required")
        
        # Set default threshold
        threshold = request.match_threshold or settings.default_match_threshold
        
        # Initialize services
        scraper = ScrapingService()
        matcher = MatchingService()
        
        # Extract jobs from page content
        extracted_jobs = []
        if request.page_content and request.page_content.get('jobs'):
            # Use jobs from content script
            extracted_jobs = request.page_content['jobs']
        else:
            # Fallback to scraping the URL directly
            extracted_jobs = await scraper.extract_jobs_from_url(request.url)
        
        if not extracted_jobs:
            return ScanResponse(
                success=True,
                message="No jobs found on this page",
                jobs_found=0,
                matches=[],
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
        
        # Filter and limit jobs
        jobs_to_process = extracted_jobs[:settings.max_jobs_per_scan]
        
        # Match jobs against resume
        matched_jobs = []
        if request.resume_text:
            matches = await matcher.match_jobs_to_resume(
                jobs=jobs_to_process,
                resume_text=request.resume_text,
                threshold=threshold
            )
            
            # Convert to response format
            for match in matches:
                if match['score'] >= threshold:
                    matched_jobs.append(JobResult(
                        id=str(match['job'].get('id', hash(match['job']['title']))),
                        title=match['job']['title'],
                        company=match['job']['company'],
                        location=match['job'].get('location', 'Not specified'),
                        url=match['job'].get('url', request.url),
                        match_score=int(match['score'] * 100),  # Convert to percentage
                        skills=match.get('matched_skills', []),
                        summary=match.get('explanation')
                    ))
        else:
            # No resume provided, return jobs without matching
            for job in jobs_to_process:
                matched_jobs.append(JobResult(
                    id=str(hash(job['title'])),
                    title=job['title'],
                    company=job['company'],
                    location=job.get('location', 'Not specified'),
                    url=job.get('url', request.url),
                    match_score=75,  # Default score when no resume
                    skills=[],
                    summary="No resume provided for matching"
                ))
        
        # Sort by match score
        matched_jobs.sort(key=lambda x: x.match_score, reverse=True)
        
        # Store results in background
        background_tasks.add_task(
            store_scan_results,
            request.user_id,
            request.url,
            extracted_jobs,
            matched_jobs
        )
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return ScanResponse(
            success=True,
            message=f"Found {len(matched_jobs)} matching jobs",
            jobs_found=len(extracted_jobs),
            matches=matched_jobs[:10],  # Return top 10
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        processing_time = int((time.time() - start_time) * 1000)
        return ScanResponse(
            success=False,
            message="Failed to process page",
            jobs_found=0,
            matches=[],
            processing_time_ms=processing_time,
            error=str(e)
        )

async def store_scan_results(
    user_id: str,
    url: str,
    jobs: List[Dict],
    matches: List[JobResult]
):
    """
    Store scan results in the database (background task)
    """
    try:
        # TODO: Implement database storage
        # - Store jobs in jobs table
        # - Store matches in job_matches table
        # - Update user scan history
        pass
    except Exception as e:
        # Log error but don't fail the main request
        print(f"Error storing scan results: {e}")

@router.get("/history/{user_id}")
async def get_scan_history(user_id: str, limit: int = 20):
    """
    Get scan history for a user
    """
    # TODO: Implement scan history retrieval
    return {"message": "Scan history endpoint - TODO implement"}

@router.get("/stats")
async def get_scan_stats():
    """
    Get overall scanning statistics
    """
    # TODO: Implement scan statistics
    return {
        "total_scans": 0,
        "total_jobs_found": 0,
        "average_match_score": 0.0,
        "most_active_domains": []
    } 