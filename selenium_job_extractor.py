#!/usr/bin/env python3
"""
Selenium-based job extractor for JavaScript-heavy sites
Handles Workday, Greenhouse, Lever, and other SPA job sites
"""

import logging
import time
import os
from typing import Dict, List, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)

class SeleniumJobExtractor:
    """Enhanced job extractor using Selenium for JavaScript-rendered content"""
    
    def __init__(self, headless: bool = True, timeout: int = 15):
        self.timeout = timeout
        self.driver = None
        self.setup_driver(headless)
    
    def setup_driver(self, headless: bool):
        """Setup Chrome WebDriver with optimized settings"""
        
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless=new")  # Use new headless mode
        
        # Performance and stability optimizations
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        
        # Memory optimizations
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        
        # Mimic real browser
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        try:
            # Use Service class for better error handling
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(self.timeout)
            logger.info("✅ Selenium WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize WebDriver: {str(e)}")
            self.driver = None
    
    def extract_job_details(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detailed job information from a URL using Selenium"""
        
        if not self.driver:
            logger.error("❌ WebDriver not available")
            return basic_job
        
        try:
            logger.info(f"🚀 Selenium: Fetching {job_url}")
            
            # Navigate to job page
            self.driver.get(job_url)
            
            # 🚀 GENERALIZED WAITING: Wait for dynamic content to load (5-10 seconds)
            logger.info("⏳ Waiting for dynamic content to load...")
            
            # Wait for initial page load
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for dynamic content (5-10 seconds as requested)
            time.sleep(7)  # 7 second wait for dynamic content to load
            
            # Try to detect if more content is still loading
            initial_text_length = len(self.driver.find_element(By.TAG_NAME, "body").text)
            time.sleep(3)  # Wait another 3 seconds
            final_text_length = len(self.driver.find_element(By.TAG_NAME, "body").text)
            
            # If content is still loading, wait a bit more
            if final_text_length > initial_text_length * 1.1:  # 10% more content loaded
                logger.info("📈 Content still loading, waiting additional 3 seconds...")
                time.sleep(3)
            
            logger.info(f"✅ Page loaded with {final_text_length} characters of content")
            
            # Detect site type and use appropriate extraction strategy
            if 'amazon.jobs' in job_url.lower():
                return self.extract_amazon_jobs_selenium(job_url, basic_job)
            elif 'myworkdayjobs.com' in job_url.lower() or 'workday' in job_url.lower():
                return self.extract_workday_job_selenium(job_url, basic_job)
            elif 'greenhouse.io' in job_url.lower() or 'grnh.se' in job_url.lower():
                return self.extract_greenhouse_job_selenium(job_url, basic_job)
            elif 'jobs.lever.co' in job_url.lower():
                return self.extract_lever_job_selenium(job_url, basic_job)
            elif 'deutschebank.com' in job_url.lower() or 'careers.db.com' in job_url.lower():
                return self.extract_deutsche_bank_job_selenium(job_url, basic_job)
            else:
                return self.extract_generic_job_selenium(job_url, basic_job)
        
        except Exception as e:
            logger.error(f"❌ Selenium extraction failed for {job_url}: {str(e)}")
            return {
                **basic_job,
                "description": f"Selenium extraction failed: {str(e)}",
                "extraction_method": "selenium_failed"
            }
    
    def extract_workday_job_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Workday job using Selenium with enhanced waiting"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_workday"
        }
        
        try:
            # Wait for Workday to load (they are notoriously slow)
            logger.info("⏳ Waiting for Workday content to load...")
            
            # Multiple strategies to wait for content
            content_loaded = False
            
            # Strategy 1: Wait for specific Workday elements
            workday_selectors = [
                (By.CSS_SELECTOR, '[data-automation-id="jobPostingDescription"]'),
                (By.CSS_SELECTOR, '[data-automation-id="jobPostingDescriptionText"]'),
                (By.CSS_SELECTOR, '.gwt-RichTextArea'),
                (By.CSS_SELECTOR, '.PACDKGMLXB')
            ]
            
            for by, selector in workday_selectors:
                try:
                    element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if element and element.text.strip():
                        content_loaded = True
                        logger.info(f"✅ Workday content loaded using selector: {selector}")
                        break
                except TimeoutException:
                    continue
            
            # Strategy 2: Wait for any substantial text content
            if not content_loaded:
                try:
                    WebDriverWait(self.driver, 8).until(
                        lambda driver: len(driver.find_element(By.TAG_NAME, "body").text) > 1000
                    )
                    content_loaded = True
                    logger.info("✅ Workday content loaded (substantial text detected)")
                except TimeoutException:
                    logger.warning("⚠️ Workday content still loading, proceeding with partial content")
            
            # Extract title
            title_selectors = [
                '[data-automation-id="jobPostingHeader"]',
                'h1[data-automation-id]',
                'h1.gwt-Label',
                '.PXFDHSMLXB h1',
                'h1'
            ]
            
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if title_element and title_element.text.strip():
                        job_data["title"] = title_element.text.strip()
                        logger.info(f"📋 Found title: {job_data['title']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract location
            location_selectors = [
                '[data-automation-id="locations"]',
                '[data-automation-id="jobPostingHeaderSubtitle"]',
                '.PAFDHGMLXB',
                '.jobPostingHeaderSubtitle'
            ]
            
            for selector in location_selectors:
                try:
                    location_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if location_element and location_element.text.strip():
                        job_data["location"] = location_element.text.strip()
                        logger.info(f"📍 Found location: {job_data['location']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract detailed job description
            description_parts = []
            
            description_selectors = [
                '[data-automation-id="jobPostingDescription"]',
                '[data-automation-id="jobPostingDescriptionText"]',
                '.PACDKGMLXB',
                '.gwt-RichTextArea',
                '.wd-text',
                '[class*="description"]'
            ]
            
            for selector in description_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 100:
                            description_parts.append(text)
                            logger.info(f"📄 Found description part: {len(text)} characters")
                except NoSuchElementException:
                    continue
            
            # Combine description parts
            if description_parts:
                job_data["description"] = "\n\n".join(description_parts)
                logger.info(f"✅ Total description: {len(job_data['description'])} characters")
            else:
                # Fallback: get all text from body
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if len(body_text) > 500:
                    job_data["description"] = f"Workday Job Content:\n{body_text[:2000]}..."
                    logger.info("📄 Used fallback body text extraction")
                else:
                    job_data["description"] = "Workday job content could not be extracted (JavaScript rendering issue)"
            
            # Extract additional fields if available
            try:
                # Job type
                job_type_element = self.driver.find_element(By.CSS_SELECTOR, '[data-automation-id="jobClassification"]')
                if job_type_element:
                    job_data["job_type"] = job_type_element.text.strip()
            except NoSuchElementException:
                pass
            
            return job_data
        
        except Exception as e:
            logger.error(f"❌ Workday Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Workday extraction error: {str(e)}"
            return job_data
    
    def extract_greenhouse_job_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Greenhouse job using Selenium"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_greenhouse"
        }
        
        try:
            # Wait for Greenhouse content
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".app-title, .posting-headline"))
            )
            
            # Extract title
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, ".app-title, .posting-headline h2, h1")
                job_data["title"] = title_element.text.strip()
            except NoSuchElementException:
                pass
            
            # Extract description
            try:
                desc_element = self.driver.find_element(By.CSS_SELECTOR, "#content, .posting-content, .app-content")
                job_data["description"] = desc_element.text.strip()
            except NoSuchElementException:
                job_data["description"] = self.driver.find_element(By.TAG_NAME, "body").text[:2000]
            
            return job_data
        
        except Exception as e:
            logger.error(f"❌ Greenhouse Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Greenhouse extraction error: {str(e)}"
            return job_data
    
    def extract_lever_job_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Lever job using Selenium"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_lever"
        }
        
        try:
            # Wait for Lever content
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".posting-headline, .posting-content"))
            )
            
            # Extract title
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, ".posting-headline h2, .posting-title")
                job_data["title"] = title_element.text.strip()
            except NoSuchElementException:
                pass
            
            # Extract description
            try:
                desc_element = self.driver.find_element(By.CSS_SELECTOR, ".posting-content, .content")
                job_data["description"] = desc_element.text.strip()
            except NoSuchElementException:
                job_data["description"] = self.driver.find_element(By.TAG_NAME, "body").text[:2000]
            
            return job_data
        
        except Exception as e:
            logger.error(f"❌ Lever Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Lever extraction error: {str(e)}"
            return job_data
    
    def extract_deutsche_bank_job_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Deutsche Bank job using Selenium with enhanced waiting"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_deutsche_bank"
        }
        
        try:
            # Extract job ID from URL
            job_id = None
            if '/job/' in job_url:
                job_id = job_url.split('/job/')[-1]
                logger.info(f"🆔 Extracted job ID: {job_id}")
            
            # Construct the full URL if it's a fragment URL
            if '#/professional/job/' in job_url:
                base_url = 'https://careers.db.com/professionals/search-roles/'
                job_url = f"{base_url}#/professional/job/{job_id}"
                logger.info(f"🔗 Constructed full URL: {job_url}")
            
            # Navigate to the job page
            logger.info(f"🌐 Navigating to: {job_url}")
            self.driver.get(job_url)
            
            # Wait for initial page load
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for dynamic content
            logger.info("⏳ Waiting for Deutsche Bank dynamic content to load...")
            time.sleep(5)  # Initial wait for SPA initialization
            
            # Try to find and click any "View Job" or similar buttons
            try:
                view_job_buttons = self.driver.find_elements(By.XPATH, 
                    "//button[contains(., 'View Job') or contains(., 'View Details') or contains(., 'Show More')]")
                if view_job_buttons:
                    view_job_buttons[0].click()
                    logger.info("✅ Clicked 'View Job' button")
                    time.sleep(2)  # Wait for content to load after click
            except Exception as e:
                logger.warning(f"⚠️ Could not find/click view job button: {str(e)}")
            
            # Wait for job content to load
            content_selectors = [
                '.job-details',
                '.job-description',
                '.content',
                '.description',
                '[data-test*="description"]',
                'main',
                '.job-content',
                '.posting-content',
                '.job-detail-content',
                '.job-detail-description'
            ]
            
            content_loaded = False
            for selector in content_selectors:
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element and len(element.text.strip()) > 100:
                        content_loaded = True
                        logger.info(f"✅ Content loaded using selector: {selector}")
                        break
                except (TimeoutException, NoSuchElementException):
                    continue
            
            if not content_loaded:
                logger.warning("⚠️ Primary content selectors not found, trying alternative approach")
                # Try to find any substantial content
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda driver: len(driver.find_element(By.TAG_NAME, "body").text) > 500
                    )
                    content_loaded = True
                    logger.info("✅ Content loaded (substantial text detected)")
                except TimeoutException:
                    logger.warning("⚠️ Content still loading, proceeding with available content")
            
            # Extract title
            title_selectors = [
                'h1',
                '.job-title',
                '.position-title',
                '[data-test*="title"]',
                '.title',
                '.posting-headline',
                '.job-detail-title'
            ]
            
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if title_element and title_element.text.strip():
                        job_data["title"] = title_element.text.strip()
                        logger.info(f"📋 Found title: {job_data['title']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract location
            location_selectors = [
                '.location',
                '.job-location',
                '[data-test*="location"]',
                '.city',
                '.posting-location',
                '.job-detail-location'
            ]
            
            for selector in location_selectors:
                try:
                    location_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if location_element and location_element.text.strip():
                        job_data["location"] = location_element.text.strip()
                        logger.info(f"📍 Found location: {job_data['location']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract job description
            description_parts = []
            
            # Try multiple approaches to get the description
            description_selectors = [
                '.job-description',
                '.job-details',
                '.content',
                '.description',
                '[data-test*="description"]',
                'main',
                '.job-content',
                '.posting-content',
                '.job-detail-content',
                '.job-detail-description',
                '.job-detail-body'
            ]
            
            for selector in description_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 100:
                            description_parts.append(text)
                            logger.info(f"📄 Found description part: {len(text)} characters")
                except NoSuchElementException:
                    continue
            
            # If no substantial content found, try to extract from the entire page
            if not description_parts:
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if len(body_text) > 500:
                        # Filter out navigation and footer content
                        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
                        content_lines = []
                        for line in lines:
                            if len(line) > 50 and not any(skip in line.lower() for skip in [
                                'cookie', 'privacy', 'terms', 'copyright', 'navigation',
                                'menu', 'search', 'login', 'sign in', 'register'
                            ]):
                                content_lines.append(line)
                        
                        if content_lines:
                            description_parts.append("\n".join(content_lines))
                            logger.info("📄 Extracted content from page body")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to extract from body: {str(e)}")
            
            # Combine description parts
            if description_parts:
                job_data["description"] = "\n\n".join(description_parts)
                logger.info(f"✅ Total description: {len(job_data['description'])} characters")
            else:
                # Try one last time with a different approach
                try:
                    # Look for any div with substantial content
                    divs = self.driver.find_elements(By.TAG_NAME, "div")
                    for div in divs:
                        text = div.text.strip()
                        if len(text) > 500 and not any(skip in text.lower() for skip in [
                            'cookie', 'privacy', 'terms', 'copyright', 'navigation',
                            'menu', 'search', 'login', 'sign in', 'register'
                        ]):
                            job_data["description"] = text
                            logger.info(f"📄 Found substantial content in div: {len(text)} characters")
                            break
                except Exception as e:
                    logger.warning(f"⚠️ Final extraction attempt failed: {str(e)}")
                
                if not job_data.get("description"):
                    job_data["description"] = "Deutsche Bank job content could not be extracted (JavaScript rendering issue)"
                    logger.warning("⚠️ No substantial content found")
            
            # Set company
            job_data["company"] = "Deutsche Bank"
            
            return job_data
        
        except Exception as e:
            logger.error(f"❌ Deutsche Bank Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Deutsche Bank extraction error: {str(e)}"
            return job_data
    
    def extract_generic_job_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Generic job extraction using Selenium with enhanced waiting for dynamic content"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_generic"
        }
        
        try:
            # Wait for page to load completely
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for dynamic content
            logger.info("⏳ Generic extraction: Waiting for dynamic content...")
            import time
            time.sleep(5)  # 5 second wait for dynamic content
            
            # Try to wait for substantial content to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda driver: len(driver.find_element(By.TAG_NAME, "body").text) > 500
                )
                logger.info("✅ Substantial content detected")
            except TimeoutException:
                logger.warning("⚠️ Limited content detected, proceeding with extraction")
            
            # Extract title from common locations
            title_selectors = ["h1", "h2", ".job-title", ".position-title", "title", ".posting-headline", ".job-detail-title"]
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if title_element and title_element.text.strip():
                        job_data["title"] = title_element.text.strip()
                        logger.info(f"📋 Found title: {job_data['title']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract main content from multiple possible locations
            content_selectors = [
                "main", ".content", ".job-description", ".job-details", 
                ".description", "#content", ".main-content", ".posting-content",
                ".job-content", ".job-detail-content", ".job-detail-description"
            ]
            
            description_parts = []
            for selector in content_selectors:
                try:
                    content_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in content_elements:
                        text = element.text.strip()
                        if text and len(text) > 100:
                            description_parts.append(text)
                            logger.info(f"📄 Found content part: {len(text)} characters")
                except NoSuchElementException:
                    continue
            
            # Combine description parts
            if description_parts:
                job_data["description"] = "\n\n".join(description_parts)
                logger.info(f"✅ Total description: {len(job_data['description'])} characters")
            else:
                # Fallback to body text
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if len(body_text) > 200:
                    # Filter out navigation and footer content
                    lines = [line.strip() for line in body_text.split('\n') if line.strip()]
                    content_lines = []
                    for line in lines:
                        if len(line) > 30 and not any(skip in line.lower() for skip in [
                            'cookie', 'privacy', 'terms', 'copyright', 'navigation',
                            'menu', 'search', 'login', 'sign in', 'register', 'footer'
                        ]):
                            content_lines.append(line)
                    
                    if content_lines:
                        job_data["description"] = "\n".join(content_lines[:50])  # Limit to first 50 relevant lines
                        logger.info(f"📄 Used filtered body content: {len(job_data['description'])} characters")
                    else:
                        job_data["description"] = body_text[:2000] if len(body_text) > 2000 else body_text
                        logger.info("📄 Used raw body text as fallback")
                else:
                    job_data["description"] = "Content could not be extracted - page may require user interaction"
                    logger.warning("⚠️ Minimal content found")
            
            return job_data
        
        except Exception as e:
            logger.error(f"❌ Generic Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Generic extraction error: {str(e)}"
            return job_data
    
    def extract_amazon_jobs_selenium(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Amazon Jobs using Selenium - specialized for Amazon's SPA architecture"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "extraction_method": "selenium_amazon"
        }
        
        try:
            logger.info("🎯 Amazon Jobs extraction with Selenium...")
            
            # Amazon Jobs is a complex SPA, need to wait for content to load
            time.sleep(3)  # Initial wait for SPA initialization
            
            # Check if this is a job search page or individual job page
            is_search_page = '/search' in job_url
            
            if is_search_page:
                logger.info("📋 Detected Amazon Jobs search page - extracting job listings")
                return self.extract_amazon_search_results(job_url, basic_job)
            else:
                logger.info("📄 Detected individual Amazon job page - extracting job details")
                return self.extract_amazon_individual_job(job_url, basic_job)
                
        except Exception as e:
            logger.error(f"❌ Amazon Jobs Selenium extraction failed: {str(e)}")
            job_data["description"] = f"Amazon Jobs extraction failed: {str(e)}"
        
        return job_data
    
    def extract_amazon_search_results(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract multiple job listings from Amazon Jobs search page"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "company": "Amazon",
            "extraction_method": "selenium_amazon_search"
        }
        
        try:
            # Wait for search results to load
            logger.info("⏳ Waiting for Amazon search results to load...")
            
            # Try multiple strategies to detect loaded content
            content_selectors = [
                '.job-tile',
                '.JobTile', 
                '.result-item',
                '.search-result',
                '[data-test*="job"]',
                '.job-listing',
                '[data-testid*="job"]'
            ]
            
            jobs_found = False
            for selector in content_selectors:
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"✅ Found {len(elements)} job elements using: {selector}")
                        jobs_found = True
                        break
                except TimeoutException:
                    continue
            
            # If no specific job elements found, check for general content
            if not jobs_found:
                try:
                    WebDriverWait(self.driver, 8).until(
                        lambda driver: len(driver.find_element(By.TAG_NAME, "body").text) > 2000
                    )
                    logger.info("✅ Amazon page content loaded (text-based detection)")
                    jobs_found = True
                except TimeoutException:
                    logger.warning("⚠️ Amazon content still loading, proceeding with available content")
            
            # Extract job listings
            job_links = []
            
            # Try different link selectors for Amazon
            amazon_link_selectors = [
                'a.read-more[href*="/en/jobs/"]',  # Specific Amazon "Read more" links
                'a[href*="/en/jobs/"]',
                'a[href*="/jobs/"]', 
                '.job-tile a',
                '.JobTile a',
                '.result-item a',
                '[data-test="job-title"] a',
                '.job-result a',
                '.search-result a[href*="job"]',
                'a[href*="Job-"]',
                'a[data-test*="job"]'
            ]
            
            for selector in amazon_link_selectors:
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if links:
                        logger.info(f"🔗 Found {len(links)} job links using: {selector}")
                        
                        for link in links[:10]:  # Limit to 10 jobs
                            href = link.get_attribute('href')
                            title = link.text.strip()
                            
                            # Validate this is a real job link
                            if (href and title and 
                                len(title) > 10 and
                                not any(skip in title.lower() for skip in [
                                    'categories', 'teams', 'locations', 'benefits', 
                                    'tips', 'faq', 'help', 'careers', 'security'
                                ]) and
                                not any(skip in href.lower() for skip in [
                                    'job_categories', 'landing_pages', 'check_application'
                                ])):
                                
                                job_links.append({
                                    'url': href,
                                    'title': title,
                                    'company': 'Amazon'
                                })
                        
                        if job_links:
                            break
                
                except Exception as e:
                    logger.warning(f"Link extraction failed for {selector}: {str(e)}")
                    continue
            
            # If we found job links, create a summary
            if job_links:
                descriptions = []
                descriptions.append(f"Amazon Jobs Search Results from {job_url}")
                descriptions.append(f"Found {len(job_links)} job opportunities:")
                
                for i, job in enumerate(job_links, 1):
                    descriptions.append(f"{i}. {job['title']}")
                    descriptions.append(f"   URL: {job['url']}")
                
                descriptions.append("\nNote: Use individual job URLs for detailed descriptions")
                
                job_data.update({
                    "title": f"Amazon Jobs Search - {len(job_links)} Results",
                    "description": "\n".join(descriptions),
                    "job_links_found": job_links,
                    "jobs_count": len(job_links)
                })
                
                logger.info(f"✅ Amazon search extraction: {len(job_links)} jobs found")
            else:
                # Fallback: extract any meaningful content from the page
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if len(body_text) > 500:
                    job_data["description"] = f"Amazon Jobs Page Content:\n{body_text[:1500]}..."
                else:
                    job_data["description"] = "Amazon Jobs search page loaded but no job listings were found. The page may require user interaction or specific search parameters."
                
                logger.warning("⚠️ No job links found on Amazon search page")
        
        except Exception as e:
            logger.error(f"❌ Amazon search extraction failed: {str(e)}")
            job_data["description"] = f"Amazon search extraction error: {str(e)}"
        
        return job_data
    
    def extract_amazon_individual_job(self, job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
        """Extract details from an individual Amazon job page"""
        
        job_data = {
            **basic_job,
            "url": job_url,
            "company": "Amazon",
            "extraction_method": "selenium_amazon_individual"
        }
        
        try:
            # Wait for job page to load
            logger.info("⏳ Waiting for Amazon job page to load...")
            
            # Wait for job content elements
            job_content_selectors = [
                '.job-detail',
                '.job-description',
                '.posting-content',
                '.job-content',
                '[data-test*="job-description"]',
                '.description'
            ]
            
            content_loaded = False
            for selector in job_content_selectors:
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    content_loaded = True
                    logger.info(f"✅ Job content loaded using: {selector}")
                    break
                except TimeoutException:
                    continue
            
            # Extract job title
            title_selectors = [
                'h1',
                '.job-title',
                '.posting-title',
                '[data-test*="job-title"]',
                '.title'
            ]
            
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if title_element and title_element.text.strip():
                        job_data["title"] = title_element.text.strip()
                        logger.info(f"📋 Found title: {job_data['title']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract job location
            location_selectors = [
                '.location',
                '.job-location', 
                '[data-test*="location"]',
                '.posting-location'
            ]
            
            for selector in location_selectors:
                try:
                    location_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if location_element and location_element.text.strip():
                        job_data["location"] = location_element.text.strip()
                        logger.info(f"📍 Found location: {job_data['location']}")
                        break
                except NoSuchElementException:
                    continue
            
            # Extract job description
            description_parts = []
            
            description_selectors = [
                '.job-description',
                '.job-detail',
                '.posting-content',
                '.description',
                '.job-content',
                '[data-test*="description"]'
            ]
            
            for selector in description_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 100:
                            description_parts.append(text)
                except NoSuchElementException:
                    continue
            
            if description_parts:
                job_data["description"] = "\n\n".join(description_parts)
                logger.info(f"✅ Job description: {len(job_data['description'])} characters")
            else:
                # Fallback: extract from entire page
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if len(body_text) > 500:
                    job_data["description"] = f"Amazon Job Details:\n{body_text[:2000]}..."
                else:
                    job_data["description"] = "Amazon job page loaded but detailed description not found."
        
        except Exception as e:
            logger.error(f"❌ Amazon individual job extraction failed: {str(e)}")
            job_data["description"] = f"Amazon individual job extraction error: {str(e)}"
        
        return job_data
    
    def close(self):
        """Clean up WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("🔴 WebDriver closed")

# Integration with existing system
def fetch_job_selenium_implementation(job_url: str, basic_job: Dict[str, Any]) -> Dict[str, Any]:
    """Implementation of Selenium job fetching for the main system"""
    
    extractor = SeleniumJobExtractor(headless=True)
    
    try:
        result = extractor.extract_job_details(job_url, basic_job)
        return result
    finally:
        extractor.close()

# Example usage
if __name__ == "__main__":
    # Test with a Workday URL
    test_job = {
        "title": "Test Job",
        "company": "Test Company",
        "location": "Test Location"
    }
    
    test_url = "https://workday.wd5.myworkdayjobs.com/en-US/Workday/job/INDChennai/Sr-Software-Engineer---Public-Cloud-Engineering_JR-0096550?q=software%20engineer&source=Careers_Website"
    
    result = fetch_job_selenium_implementation(test_url, test_job)
    print(f"✅ Extracted: {len(result.get('description', ''))} characters")
    print(f"📋 Title: {result.get('title', 'N/A')}")
    print(f"📄 Description preview: {result.get('description', '')[:200]}...") 