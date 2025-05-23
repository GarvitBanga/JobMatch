"""
Database models for job listings
"""

from datetime import datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship
from pydantic import HttpUrl


class JobBase(SQLModel):
    """Base job model with shared fields"""
    title: str = Field(max_length=200, index=True)
    company: str = Field(max_length=100, index=True)
    location: Optional[str] = Field(default=None, max_length=100)
    url: str = Field(max_length=500)
    description: Optional[str] = Field(default=None)
    requirements: Optional[str] = Field(default=None)
    salary_min: Optional[int] = Field(default=None)
    salary_max: Optional[int] = Field(default=None)
    job_type: Optional[str] = Field(default=None, max_length=50)  # full-time, part-time, contract
    remote_option: Optional[bool] = Field(default=None)
    
    # Extracted data
    skills: Optional[str] = Field(default=None)  # JSON string of skills array
    benefits: Optional[str] = Field(default=None)
    
    # Metadata
    scraped_from: str = Field(max_length=200)  # URL domain where scraped
    content_hash: Optional[str] = Field(default=None, max_length=64)  # For deduplication


class Job(JobBase, table=True):
    """Job table model"""
    __tablename__ = "jobs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    matches: List["JobMatch"] = Relationship(back_populates="job")


class JobCreate(JobBase):
    """Model for creating new jobs"""
    pass


class JobRead(JobBase):
    """Model for reading jobs"""
    id: int
    created_at: datetime
    updated_at: datetime


class JobUpdate(SQLModel):
    """Model for updating jobs"""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_type: Optional[str] = None
    remote_option: Optional[bool] = None
    skills: Optional[str] = None
    benefits: Optional[str] = None 