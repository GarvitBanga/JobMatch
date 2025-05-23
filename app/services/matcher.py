"""
Job-Resume matching service using text similarity and LLM analysis
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher
import json

from ..core.config import settings


class MatchingService:
    """Service for matching job descriptions against resumes"""
    
    def __init__(self):
        self.common_skills = self._load_common_skills()
        self.stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    
    def _load_common_skills(self) -> List[str]:
        """Load common technical skills for matching"""
        return [
            # Programming Languages
            'python', 'javascript', 'java', 'c++', 'c#', 'go', 'rust', 'swift', 'kotlin',
            'typescript', 'php', 'ruby', 'scala', 'r', 'matlab', 'sql',
            
            # Web Technologies
            'react', 'vue', 'angular', 'nodejs', 'express', 'django', 'flask',
            'html', 'css', 'sass', 'bootstrap', 'tailwind',
            
            # Databases
            'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
            'sqlite', 'oracle', 'cassandra',
            
            # Cloud & DevOps
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab',
            'terraform', 'ansible', 'chef', 'puppet',
            
            # Data & ML
            'pandas', 'numpy', 'scikit-learn', 'tensorflow', 'pytorch',
            'spark', 'hadoop', 'kafka', 'airflow',
            
            # Tools & Methodologies
            'git', 'jira', 'agile', 'scrum', 'kanban', 'ci/cd', 'tdd', 'api',
            'rest', 'graphql', 'microservices', 'testing', 'debugging'
        ]
    
    async def match_jobs_to_resume(
        self,
        jobs: List[Dict[str, Any]],
        resume_text: str,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Match a list of jobs against a resume
        
        Args:
            jobs: List of job dictionaries
            resume_text: Resume text content
            threshold: Minimum match score threshold
            
        Returns:
            List of matches with scores and explanations
        """
        matches = []
        resume_skills = self._extract_skills(resume_text)
        resume_keywords = self._extract_keywords(resume_text)
        
        for job in jobs:
            try:
                match_result = await self._match_single_job(
                    job, resume_text, resume_skills, resume_keywords
                )
                
                if match_result['score'] >= threshold:
                    matches.append(match_result)
                    
            except Exception as e:
                print(f"Error matching job {job.get('title', 'Unknown')}: {e}")
                continue
        
        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches
    
    async def _match_single_job(
        self,
        job: Dict[str, Any],
        resume_text: str,
        resume_skills: List[str],
        resume_keywords: List[str]
    ) -> Dict[str, Any]:
        """
        Match a single job against resume
        
        Returns:
            Dictionary with job, score, matched_skills, and explanation
        """
        # Extract job information
        job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
        job_skills = self._extract_skills(job_text)
        job_keywords = self._extract_keywords(job_text)
        
        # Calculate different types of matches
        skill_score, matched_skills = self._calculate_skill_match(resume_skills, job_skills)
        keyword_score = self._calculate_keyword_match(resume_keywords, job_keywords)
        title_score = self._calculate_title_match(job.get('title', ''), resume_text)
        
        # Weighted final score
        final_score = (
            skill_score * 0.5 +      # Skills are most important
            keyword_score * 0.3 +    # General keywords
            title_score * 0.2        # Job title relevance
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            matched_skills, skill_score, keyword_score, title_score
        )
        
        return {
            'job': job,
            'score': final_score,
            'matched_skills': matched_skills,
            'missing_skills': [skill for skill in job_skills if skill not in matched_skills],
            'explanation': explanation,
            'skill_score': skill_score,
            'keyword_score': keyword_score,
            'title_score': title_score
        }
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract technical skills from text"""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.common_skills:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(skill.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)
        
        return found_skills
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text"""
        # Clean and tokenize text
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Filter out stop words and short words
        keywords = [
            word for word in words 
            if len(word) > 2 and word not in self.stop_words
        ]
        
        # Get unique keywords with frequency
        keyword_freq = {}
        for word in keywords:
            keyword_freq[word] = keyword_freq.get(word, 0) + 1
        
        # Return top keywords by frequency
        sorted_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_keywords[:50]]
    
    def _calculate_skill_match(self, resume_skills: List[str], job_skills: List[str]) -> Tuple[float, List[str]]:
        """Calculate skill match score and return matched skills"""
        if not job_skills:
            return 0.0, []
        
        matched_skills = [skill for skill in job_skills if skill in resume_skills]
        score = len(matched_skills) / len(job_skills) if job_skills else 0.0
        
        return min(score, 1.0), matched_skills
    
    def _calculate_keyword_match(self, resume_keywords: List[str], job_keywords: List[str]) -> float:
        """Calculate general keyword match score"""
        if not job_keywords or not resume_keywords:
            return 0.0
        
        # Calculate Jaccard similarity
        resume_set = set(resume_keywords)
        job_set = set(job_keywords)
        
        intersection = len(resume_set.intersection(job_set))
        union = len(resume_set.union(job_set))
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_title_match(self, job_title: str, resume_text: str) -> float:
        """Calculate how well the job title matches resume content"""
        if not job_title:
            return 0.0
        
        # Extract potential job titles from resume
        title_patterns = [
            r'(software engineer|developer|programmer|architect)',
            r'(data scientist|analyst|engineer)',
            r'(product manager|project manager)',
            r'(designer|ui/ux)',
            r'(devops|sre|infrastructure)',
            r'(qa|test|quality assurance)',
            r'(consultant|specialist)'
        ]
        
        job_title_lower = job_title.lower()
        resume_lower = resume_text.lower()
        
        # Check for direct title matches
        for pattern in title_patterns:
            if re.search(pattern, job_title_lower) and re.search(pattern, resume_lower):
                return 0.8
        
        # Calculate general text similarity
        return SequenceMatcher(None, job_title_lower, resume_lower[:200]).ratio()
    
    def _generate_explanation(
        self,
        matched_skills: List[str],
        skill_score: float,
        keyword_score: float,
        title_score: float
    ) -> str:
        """Generate human-readable explanation for the match"""
        explanations = []
        
        if skill_score > 0.7:
            explanations.append(f"Excellent skill match with {len(matched_skills)} relevant technologies")
        elif skill_score > 0.4:
            explanations.append(f"Good skill match with {len(matched_skills)} relevant technologies")
        elif matched_skills:
            explanations.append(f"Some relevant skills: {', '.join(matched_skills[:3])}")
        
        if keyword_score > 0.3:
            explanations.append("Strong keyword alignment with job requirements")
        
        if title_score > 0.5:
            explanations.append("Job title aligns well with your background")
        
        if not explanations:
            explanations.append("Limited match based on available information")
        
        return ". ".join(explanations) + "."
    
    async def get_improvement_suggestions(
        self,
        resume_text: str,
        target_jobs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze resume against target jobs and suggest improvements
        """
        # Extract all skills from target jobs
        all_job_skills = set()
        for job in target_jobs:
            job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
            job_skills = self._extract_skills(job_text)
            all_job_skills.update(job_skills)
        
        resume_skills = set(self._extract_skills(resume_text))
        missing_skills = all_job_skills - resume_skills
        
        return {
            'current_skills': list(resume_skills),
            'missing_skills': list(missing_skills)[:10],  # Top 10 missing skills
            'skill_coverage': len(resume_skills) / len(all_job_skills) if all_job_skills else 0,
            'suggestions': [
                "Consider adding more specific technical skills to your resume",
                "Include quantifiable achievements and project outcomes",
                "Use industry-standard terminology that matches job descriptions"
            ]
        } 