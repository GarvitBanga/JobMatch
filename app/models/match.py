"""
Database models for job-resume matches
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship


class JobMatchBase(SQLModel):
    """Base job match model with shared fields"""
    job_id: int = Field(foreign_key="jobs.id", index=True)
    resume_id: int = Field(foreign_key="resumes.id", index=True)
    
    # Match results
    match_score: float = Field(ge=0.0, le=1.0)  # Score between 0 and 1
    confidence: float = Field(ge=0.0, le=1.0)  # Confidence in the match
    
    # Detailed analysis
    explanation: Optional[str] = Field(default=None)  # Human-readable explanation
    matched_skills: Optional[str] = Field(default=None)  # JSON array of matched skills
    missing_skills: Optional[str] = Field(default=None)  # JSON array of missing skills
    skill_match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    experience_match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
    # Embedding similarity
    embedding_similarity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
    # Metadata
    algorithm_version: str = Field(max_length=50, default="v1.0")
    processing_time_ms: Optional[int] = Field(default=None)


class JobMatch(JobMatchBase, table=True):
    """Job match table model"""
    __tablename__ = "job_matches"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    job: "Job" = Relationship(back_populates="matches")
    resume: "Resume" = Relationship(back_populates="matches")


class JobMatchCreate(JobMatchBase):
    """Model for creating new job matches"""
    pass


class JobMatchRead(JobMatchBase):
    """Model for reading job matches"""
    id: int
    created_at: datetime


class JobMatchWithDetails(JobMatchRead):
    """Job match with related job and resume details"""
    job: "JobRead"
    resume: "ResumeRead"


# Import models to avoid circular imports
from .job import Job, JobRead
from .resume import Resume, ResumeRead

# Update forward references
JobMatch.model_rebuild()
JobMatchWithDetails.model_rebuild() 