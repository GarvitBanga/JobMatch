"""
Main API router that includes all endpoint routes
"""

from fastapi import APIRouter
from .endpoints import scan, jobs, resumes, matches

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(scan.router, prefix="/scan", tags=["scan"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(matches.router, prefix="/matches", tags=["matches"]) 