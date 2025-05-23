"""
Database models for resumes
"""

from datetime import datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship


class ResumeBase(SQLModel):
    """Base resume model with shared fields"""
    user_id: str = Field(max_length=100, index=True)  # Chrome extension user ID
    filename: Optional[str] = Field(default=None, max_length=200)
    content_text: str  # Extracted text content
    
    # Parsed fields
    name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=100)
    
    # Professional info
    title: Optional[str] = Field(default=None, max_length=200)
    summary: Optional[str] = Field(default=None)
    skills: Optional[str] = Field(default=None)  # JSON string of skills array
    experience: Optional[str] = Field(default=None)  # JSON string of experience array
    education: Optional[str] = Field(default=None)  # JSON string of education array
    
    # Vector embeddings (stored as JSON)
    embedding: Optional[str] = Field(default=None)  # JSON string of vector


class Resume(ResumeBase, table=True):
    """Resume table model"""
    __tablename__ = "resumes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    matches: List["JobMatch"] = Relationship(back_populates="resume")


class ResumeCreate(ResumeBase):
    """Model for creating new resumes"""
    pass


class ResumeRead(ResumeBase):
    """Model for reading resumes"""
    id: int
    created_at: datetime
    updated_at: datetime


class ResumeUpdate(SQLModel):
    """Model for updating resumes"""
    filename: Optional[str] = None
    content_text: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    embedding: Optional[str] = None 