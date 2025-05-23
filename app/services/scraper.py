"""
Web scraping service for extracting job listings
"""

import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup

from ..core.config import settings


class ScrapingService:
    """Service for scraping job listings from web pages"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=settings.scrape_timeout)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session
    
    async def extract_jobs_from_url(self, url: str) -> List[Dict[str, Any]]:
        """
        Extract job listings from a given URL
        
        Args:
            url: The URL to scrape
            
        Returns:
            List of job dictionaries with extracted information
        """
        try:
            session = await self.get_session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return []
                
                html = await response.text()
                return self._parse_jobs_from_html(html, url)
                
        except Exception as e:
            print(f"Error scraping URL {url}: {e}")
            return []
    
    def _parse_jobs_from_html(self, html: str, base_url: str) -> List[Dict[str, Any]]:
        """
        Parse job listings from HTML content
        
        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links
            
        Returns:
            List of extracted job dictionaries
        """
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        
        # Common job listing selectors (generic patterns)
        job_selectors = [
            'div[class*="job"]',
            'li[class*="job"]',
            'article[class*="job"]',
            'div[class*="position"]',
            'li[class*="position"]',
            'div[class*="opening"]',
            'div[class*="career"]',
            'a[href*="/job"]',
            'a[href*="/position"]',
            'a[href*="/career"]'
        ]
        
        for selector in job_selectors:
            elements = soup.select(selector)
            
            for element in elements:
                job = self._extract_job_from_element(element, base_url)
                if job and job.get('title') and job.get('company'):
                    jobs.append(job)
        
        # Remove duplicates based on title + company
        seen = set()
        unique_jobs = []
        
        for job in jobs:
            key = (job.get('title', '').strip().lower(), 
                   job.get('company', '').strip().lower())
            if key not in seen and key[0] and key[1]:
                seen.add(key)
                unique_jobs.append(job)
        
        return unique_jobs[:settings.max_jobs_per_scan]
    
    def _extract_job_from_element(self, element, base_url: str) -> Dict[str, Any]:
        """
        Extract job information from a single HTML element
        
        Args:
            element: BeautifulSoup element
            base_url: Base URL for resolving relative links
            
        Returns:
            Dictionary with job information
        """
        job = {
            'title': '',
            'company': '',
            'location': '',
            'url': base_url,
            'description': '',
            'requirements': ''
        }
        
        try:
            # Extract title
            title_selectors = [
                'h1', 'h2', 'h3', 'h4',
                '.title', '.job-title', '.position-title',
                '[class*="title"]', '[class*="job-title"]'
            ]
            
            for selector in title_selectors:
                title_elem = element.select_one(selector)
                if title_elem and title_elem.get_text(strip=True):
                    job['title'] = title_elem.get_text(strip=True)
                    break
            
            # Extract company
            company_selectors = [
                '.company', '.company-name', '.employer',
                '[class*="company"]', '[class*="employer"]'
            ]
            
            for selector in company_selectors:
                company_elem = element.select_one(selector)
                if company_elem and company_elem.get_text(strip=True):
                    job['company'] = company_elem.get_text(strip=True)
                    break
            
            # If no company found, try to extract from page title or domain
            if not job['company']:
                page_title = element.find_parent().find('title')
                if page_title:
                    job['company'] = page_title.get_text().split(' - ')[0].strip()
                else:
                    job['company'] = urlparse(base_url).netloc.replace('www.', '').split('.')[0].title()
            
            # Extract location
            location_selectors = [
                '.location', '.job-location', '.city',
                '[class*="location"]', '[class*="city"]'
            ]
            
            for selector in location_selectors:
                location_elem = element.select_one(selector)
                if location_elem and location_elem.get_text(strip=True):
                    job['location'] = location_elem.get_text(strip=True)
                    break
            
            # Extract URL
            link_elem = element.find('a', href=True)
            if link_elem:
                href = link_elem['href']
                if href.startswith('http'):
                    job['url'] = href
                else:
                    job['url'] = urljoin(base_url, href)
            
            # Extract description (limited)
            desc_selectors = [
                '.description', '.summary', '.excerpt',
                '[class*="description"]', '[class*="summary"]'
            ]
            
            for selector in desc_selectors:
                desc_elem = element.select_one(selector)
                if desc_elem:
                    job['description'] = desc_elem.get_text(strip=True)[:500]
                    break
            
            # Clean up job data
            job = {k: self._clean_text(v) if isinstance(v, str) else v 
                   for k, v in job.items()}
            
            return job
            
        except Exception as e:
            print(f"Error extracting job from element: {e}")
            return job
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common unwanted characters
        text = re.sub(r'[^\w\s\-\.,;:()&/]', '', text)
        
        return text
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close() 