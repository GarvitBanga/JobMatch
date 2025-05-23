"""
Enhanced Resume Processing Service with LLM Career Intelligence
Handles PDF parsing, text extraction, resume structuring, and career insights generation
"""
import logging
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import base64

# PDF processing
import PyPDF2
import pdfplumber
from docx import Document

# Text processing (optional)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    TfidfVectorizer = None

# OpenAI for LLM processing
import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

class ResumeProcessor:
    """Enhanced processor with LLM-powered career intelligence"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None
        
    async def process_resume_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Enhanced resume processing with career intelligence
        
        Args:
            file_content: Raw file bytes
            filename: Original filename with extension
            
        Returns:
            Enhanced resume data with career insights
        """
        try:
            # Extract text based on file type
            text = await self._extract_text_from_file(file_content, filename)
            
            # Process and structure the resume data
            structured_data = await self._structure_resume_data(text)
            
            # Generate career insights using LLM
            career_insights = await self._generate_career_insights(structured_data, text)
            
            # Combine structured data with career insights
            enhanced_data = {
                **structured_data,
                "career_insights": career_insights
            }
            
            return {
                "success": True,
                "raw_text": text,
                "structured_data": enhanced_data,
                "filename": filename,
                "processing_method": "llm_enhanced" if self.openai_client else "rule_based",
                "insights_generated": bool(career_insights)
            }
            
        except Exception as e:
            logger.error(f"Error processing resume: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "filename": filename
            }
    
    async def _extract_text_from_file(self, file_content: bytes, filename: str) -> str:
        """Extract text from different file formats"""
        file_ext = Path(filename).suffix.lower()
        
        if file_ext == '.pdf':
            return self._extract_from_pdf(file_content)
        elif file_ext in ['.doc', '.docx']:
            return self._extract_from_docx(file_content)
        elif file_ext == '.txt':
            return file_content.decode('utf-8')
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
    
    def _extract_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF using multiple methods"""
        text = ""
        
        try:
            # Method 1: pdfplumber (better for complex layouts)
            import io
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
            
            # Method 2: PyPDF2 (fallback)
            try:
                import io
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            except Exception as e2:
                logger.error(f"PyPDF2 also failed: {e2}")
                raise ValueError("Could not extract text from PDF")
        
        return text.strip()
    
    def _extract_from_docx(self, docx_bytes: bytes) -> str:
        """Extract text from DOCX file"""
        try:
            import io
            doc = Document(io.BytesIO(docx_bytes))
            text = []
            
            for paragraph in doc.paragraphs:
                text.append(paragraph.text)
            
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting from DOCX: {e}")
            raise ValueError("Could not extract text from DOCX")
    
    async def _structure_resume_data(self, text: str) -> Dict[str, Any]:
        """Structure resume text into organized data"""
        
        if self.openai_client:
            return await self._structure_with_llm(text)
        else:
            return self._structure_with_rules(text)
    
    async def _structure_with_llm(self, text: str) -> Dict[str, Any]:
        """Use OpenAI to structure resume data"""
        try:
            prompt = f"""
            Parse this resume text and extract structured information in JSON format:

            RESUME TEXT:
            {text}

            Extract the following information and return as valid JSON:
            {{
                "personal_info": {{
                    "name": "Full Name",
                    "email": "email@example.com",
                    "phone": "phone number",
                    "location": "city, state/country"
                }},
                "summary": "Professional summary or objective",
                "skills": ["skill1", "skill2", "skill3"],
                "experience": [
                    {{
                        "title": "Job Title",
                        "company": "Company Name",
                        "duration": "Start - End dates",
                        "description": "Job description",
                        "technologies": ["tech1", "tech2"]
                    }}
                ],
                "education": [
                    {{
                        "degree": "Degree Type",
                        "institution": "School Name", 
                        "year": "Graduation Year",
                        "field": "Field of Study"
                    }}
                ],
                "projects": [
                    {{
                        "name": "Project Name",
                        "description": "Project Description",
                        "technologies": ["tech1", "tech2"]
                    }}
                ],
                "certifications": ["Certification 1", "Certification 2"]
            }}

            Return only valid JSON, no explanations.
            """
            
            response = await self.openai_client.chat.completions.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a resume parsing expert. Extract structured data from resumes and return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            json_str = response.choices[0].message.content
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"LLM structuring failed: {e}")
            # Fallback to rule-based parsing
            return self._structure_with_rules(text)
    
    async def _generate_career_insights(self, structured_data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        """
        Generate intelligent career insights using LLM
        """
        if not self.openai_client:
            return self._generate_basic_insights(structured_data)
        
        try:
            # Prepare resume summary for analysis
            resume_summary = self._prepare_resume_summary(structured_data, raw_text)
            
            prompt = f"""
            Analyze this resume and provide intelligent career insights and recommendations.
            
            RESUME DATA:
            {resume_summary}
            
            Based on this resume, provide detailed career analysis in this JSON format:
            {{
                "career_level": {{
                    "current_level": "Junior/Mid/Senior/Executive",
                    "years_experience": "estimated years",
                    "confidence": "high/medium/low"
                }},
                "recommended_job_profiles": [
                    {{
                        "title": "Specific Job Title",
                        "match_percentage": 95,
                        "reasoning": "Why this role fits well",
                        "growth_potential": "high/medium/low"
                    }}
                ],
                "skill_analysis": {{
                    "strong_skills": ["skill1", "skill2"],
                    "emerging_skills": ["skill3", "skill4"],
                    "recommended_skills": [
                        {{
                            "skill": "Skill Name",
                            "priority": "high/medium/low",
                            "reasoning": "Why learn this skill"
                        }}
                    ]
                }},
                "industry_recommendations": [
                    {{
                        "industry": "Industry Name",
                        "fit_score": 90,
                        "growth_trend": "growing/stable/declining",
                        "reasoning": "Why this industry fits"
                    }}
                ],
                "salary_insights": {{
                    "estimated_range": "$X - $Y",
                    "location_factor": "location impact on salary",
                    "growth_potential": "salary growth prospects"
                }},
                "career_path_suggestions": [
                    {{
                        "path": "Career Path Name",
                        "next_role": "Next Role Title",
                        "timeline": "6-12 months",
                        "key_requirements": ["requirement1", "requirement2"]
                    }}
                ],
                "improvement_areas": [
                    {{
                        "area": "Area to improve",
                        "impact": "high/medium/low",
                        "suggestions": "Specific improvement suggestions"
                    }}
                ],
                "market_demand": {{
                    "overall_demand": "high/medium/low",
                    "trending_skills": ["trending1", "trending2"],
                    "market_insights": "Current market analysis"
                }}
            }}
            
            Provide realistic, actionable insights based on current job market trends.
            Return only valid JSON.
            """
            
            response = await self.openai_client.chat.completions.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a career counselor and industry expert. Analyze resumes and provide detailed, actionable career insights based on current market trends."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            insights = json.loads(response.choices[0].message.content)
            
            # Add metadata
            insights["generated_at"] = json.dumps({"timestamp": "now"}),
            insights["analysis_version"] = "1.0"
            
            return insights
            
        except Exception as e:
            logger.error(f"Career insights generation failed: {e}")
            return self._generate_basic_insights(structured_data)
    
    def _prepare_resume_summary(self, structured_data: Dict[str, Any], raw_text: str) -> str:
        """Prepare resume data for LLM analysis"""
        summary_parts = []
        
        # Personal info
        if structured_data.get("personal_info"):
            summary_parts.append(f"Name: {structured_data['personal_info'].get('name', 'N/A')}")
            summary_parts.append(f"Location: {structured_data['personal_info'].get('location', 'N/A')}")
        
        # Summary
        if structured_data.get("summary"):
            summary_parts.append(f"Summary: {structured_data['summary']}")
        
        # Skills
        if structured_data.get("skills"):
            summary_parts.append(f"Skills: {', '.join(structured_data['skills'][:10])}")
        
        # Experience
        if structured_data.get("experience"):
            summary_parts.append("Experience:")
            for i, exp in enumerate(structured_data["experience"][:3]):  # Top 3 experiences
                summary_parts.append(f"- {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')} ({exp.get('duration', 'N/A')})")
        
        # Education
        if structured_data.get("education"):
            summary_parts.append("Education:")
            for edu in structured_data["education"][:2]:  # Top 2 education entries
                summary_parts.append(f"- {edu.get('degree', 'N/A')} in {edu.get('field', 'N/A')}")
        
        return "\n".join(summary_parts)
    
    def _generate_basic_insights(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic insights when LLM is not available"""
        skills = structured_data.get("skills", [])
        experience = structured_data.get("experience", [])
        
        # Basic analysis without LLM
        return {
            "career_level": {
                "current_level": "Mid" if len(experience) > 2 else "Junior",
                "years_experience": f"{len(experience) * 2}-{len(experience) * 3}",
                "confidence": "low"
            },
            "recommended_job_profiles": [
                {
                    "title": "Software Developer",
                    "match_percentage": 80,
                    "reasoning": "Based on technical skills",
                    "growth_potential": "high"
                }
            ],
            "skill_analysis": {
                "strong_skills": skills[:5],
                "emerging_skills": [],
                "recommended_skills": [
                    {
                        "skill": "React",
                        "priority": "high", 
                        "reasoning": "High market demand"
                    }
                ]
            },
            "market_demand": {
                "overall_demand": "medium",
                "trending_skills": ["Python", "React", "AWS"],
                "market_insights": "Basic analysis without LLM"
            }
        }
    
    def _structure_with_rules(self, text: str) -> Dict[str, Any]:
        """Rule-based resume parsing (fallback when no LLM)"""
        
        structured = {
            "personal_info": {},
            "summary": "",
            "skills": [],
            "experience": [],
            "education": [],
            "projects": [],
            "certifications": []
        }
        
        # Extract email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if email_match:
            structured["personal_info"]["email"] = email_match.group()
        
        # Extract phone number
        phone_match = re.search(r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        if phone_match:
            structured["personal_info"]["phone"] = phone_match.group()
        
        # Extract skills (look for common skill keywords)
        skill_keywords = [
            'python', 'javascript', 'react', 'node.js', 'java', 'c++', 'sql',
            'aws', 'docker', 'kubernetes', 'git', 'html', 'css', 'typescript',
            'mongodb', 'postgresql', 'redis', 'machine learning', 'ai',
            'fastapi', 'django', 'flask', 'angular', 'vue.js', 'swift',
            'kotlin', 'go', 'rust', 'scala', 'tensorflow', 'pytorch'
        ]
        
        text_lower = text.lower()
        found_skills = []
        for skill in skill_keywords:
            if skill in text_lower:
                found_skills.append(skill.title())
        
        structured["skills"] = found_skills
        
        return structured
    
    def extract_skills_for_matching(self, resume_data: Dict[str, Any]) -> List[str]:
        """Extract all skills from structured resume for job matching"""
        skills = []
        
        # Add explicit skills
        if 'skills' in resume_data:
            skills.extend(resume_data['skills'])
        
        # Add recommended skills from career insights
        if 'career_insights' in resume_data:
            insights = resume_data['career_insights']
            if 'skill_analysis' in insights and 'recommended_skills' in insights['skill_analysis']:
                for rec_skill in insights['skill_analysis']['recommended_skills']:
                    if isinstance(rec_skill, dict) and 'skill' in rec_skill:
                        skills.append(rec_skill['skill'])
        
        # Extract skills from experience descriptions
        if 'experience' in resume_data:
            for exp in resume_data['experience']:
                if 'technologies' in exp:
                    skills.extend(exp['technologies'])
        
        # Extract from projects
        if 'projects' in resume_data:
            for project in resume_data['projects']:
                if 'technologies' in project:
                    skills.extend(project['technologies'])
        
        # Remove duplicates and return
        return list(set(skills))

class JobMatcher:
    """Enhanced job matcher with career insights integration"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None
        if SKLEARN_AVAILABLE:
            self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
        else:
            self.vectorizer = None
            logger.info("scikit-learn not available. Using basic text matching.")
    
    async def match_jobs_with_resume(
        self, 
        jobs: List[Dict[str, Any]], 
        resume_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Enhanced job matching using career insights
        """
        matched_jobs = []
        
        # Get career insights if available
        career_insights = resume_data.get('career_insights', {})
        recommended_profiles = career_insights.get('recommended_job_profiles', [])
        
        for job in jobs:
            match_result = await self._score_job_match(job, resume_data, career_insights)
            
            # Check if job matches recommended profiles
            profile_boost = self._calculate_profile_boost(job, recommended_profiles)
            match_result['match_score'] = min(100, match_result.get('match_score', 50) + profile_boost)
            
            matched_jobs.append({
                **job,
                **match_result
            })
        
        # Sort by match score (descending)
        matched_jobs.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        
        return matched_jobs
    
    def _calculate_profile_boost(self, job: Dict[str, Any], recommended_profiles: List[Dict[str, Any]]) -> int:
        """Calculate score boost based on recommended career profiles"""
        job_title = job.get('title', '').lower()
        
        for profile in recommended_profiles:
            profile_title = profile.get('title', '').lower()
            if any(word in job_title for word in profile_title.split()):
                return int(profile.get('match_percentage', 0) * 0.15)  # 15% boost
        
        return 0
    
    async def _score_job_match(self, job: Dict[str, Any], resume_data: Dict[str, Any], career_insights: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced job scoring with career insights"""
        
        if self.openai_client:
            return await self._score_with_enhanced_llm(job, resume_data, career_insights)
        else:
            return self._score_with_similarity(job, resume_data)
    
    async def _score_with_enhanced_llm(self, job: Dict[str, Any], resume_data: Dict[str, Any], career_insights: Dict[str, Any]) -> Dict[str, Any]:
        """Use OpenAI with career insights for enhanced scoring"""
        try:
            # Prepare enhanced context
            job_summary = f"""
            Job Title: {job.get('title', 'N/A')}
            Company: {job.get('company', 'N/A')}
            Location: {job.get('location', 'N/A')}
            Description: {job.get('description', 'N/A')[:500]}
            """
            
            # Include career insights in analysis
            insights_summary = ""
            if career_insights:
                recommended_profiles = career_insights.get('recommended_job_profiles', [])
                strong_skills = career_insights.get('skill_analysis', {}).get('strong_skills', [])
                career_level = career_insights.get('career_level', {}).get('current_level', 'Unknown')
                
                insights_summary = f"""
                Career Level: {career_level}
                Strong Skills: {', '.join(strong_skills)}
                Recommended Profiles: {', '.join([p.get('title', '') for p in recommended_profiles[:3]])}
                """
            
            resume_summary = f"""
            Skills: {', '.join(resume_data.get('skills', []))}
            Experience: {len(resume_data.get('experience', []))} positions
            {insights_summary}
            """
            
            prompt = f"""
            Rate how well this resume matches this job posting, considering career insights.
            
            JOB POSTING:
            {job_summary}
            
            RESUME & CAREER ANALYSIS:
            {resume_summary}
            
            Provide enhanced analysis in this JSON format:
            {{
                "match_score": 85,
                "matching_skills": ["skill1", "skill2", "skill3"],
                "missing_skills": ["skill4", "skill5"],
                "summary": "Detailed explanation including career fit",
                "confidence": "high/medium/low",
                "career_progression": "excellent/good/fair/poor",
                "skill_gap_analysis": "Assessment of missing skills impact"
            }}
            
            Return only valid JSON.
            """
            
            response = await self.openai_client.chat.completions.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert job-resume matcher with deep understanding of career progression and skill requirements."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=600
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Enhanced LLM matching failed: {e}")
            return self._score_with_similarity(job, resume_data)
    
    def _score_with_similarity(self, job: Dict[str, Any], resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback similarity-based matching"""
        
        # Extract text from job
        job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('company', '')}"
        
        # Extract text from resume
        resume_text = f"{resume_data.get('summary', '')} {' '.join(resume_data.get('skills', []))}"
        for exp in resume_data.get('experience', []):
            resume_text += f" {exp.get('title', '')} {exp.get('description', '')}"
        
        # Calculate similarity
        score = 50  # Default score
        if SKLEARN_AVAILABLE and self.vectorizer:
            try:
                corpus = [job_text, resume_text]
                tfidf_matrix = self.vectorizer.fit_transform(corpus)
                similarity = (tfidf_matrix[0] * tfidf_matrix[1].T).toarray()[0][0]
                score = int(similarity * 100)
            except Exception as e:
                logger.warning(f"TF-IDF similarity calculation failed: {e}")
                score = self._calculate_basic_similarity(job_text, resume_text)
        else:
            score = self._calculate_basic_similarity(job_text, resume_text)
        
        # Find matching skills
        job_skills = self._extract_skills_from_text(job_text)
        resume_skills = resume_data.get('skills', [])
        matching_skills = list(set(job_skills) & set([s.lower() for s in resume_skills]))
        
        return {
            "match_score": score,
            "matching_skills": matching_skills[:5],  # Top 5
            "missing_skills": list(set(job_skills) - set([s.lower() for s in resume_skills]))[:3],
            "summary": f"Match based on {len(matching_skills)} shared skills and text analysis",
            "confidence": "medium"
        }
    
    def _calculate_basic_similarity(self, job_text: str, resume_text: str) -> int:
        """Basic text similarity without sklearn"""
        job_words = set(job_text.lower().split())
        resume_words = set(resume_text.lower().split())
        
        if not job_words or not resume_words:
            return 30
        
        intersection = job_words.intersection(resume_words)
        union = job_words.union(resume_words)
        
        # Jaccard similarity
        similarity = len(intersection) / len(union) if union else 0
        return max(30, min(90, int(similarity * 100)))
    
    def _extract_skills_from_text(self, text: str) -> List[str]:
        """Extract potential skills from job text"""
        common_skills = [
            'python', 'javascript', 'react', 'node.js', 'java', 'sql',
            'aws', 'docker', 'git', 'html', 'css', 'typescript', 'mongodb'
        ]
        
        text_lower = text.lower()
        found_skills = [skill for skill in common_skills if skill in text_lower]
        return found_skills 