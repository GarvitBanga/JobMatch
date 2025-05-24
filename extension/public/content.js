// Enhanced Content Script with Real Cross-Origin Job Fetching
// This version actually fetches job descriptions from cross-origin URLs

class JobExtractor {
  constructor() {
      this.apiEndpoint = 'http://localhost:8000/api/v1';
      this.maxJobsToFetch = 5;
      this.fetchTimeout = 10000; // 10 seconds
  }

  // Main function to extract job listings with enhanced cross-origin fetching
  async extractJobListings() {
      const jobs = [];
      
      console.log('🔍 Starting enhanced job extraction...');
      
      // Step 1: Find job links on the page
      const jobLinks = await this.findJobLinks();
      
      if (jobLinks.length > 0) {
          console.log(`📋 Found ${jobLinks.length} job links, fetching detailed descriptions...`);
          
          // Limit to prevent overwhelming the system
          const limitedLinks = jobLinks.slice(0, this.maxJobsToFetch);
          
          // Step 2: Fetch detailed job info (with cross-origin support)
          for (const link of limitedLinks) {
              try {
                  const fullJob = await this.fetchJobDetailsEnhanced(link);
                  if (fullJob && fullJob.title) {
                      jobs.push(fullJob);
                      console.log(`✅ Successfully fetched: ${fullJob.title}`);
                  }
              } catch (error) {
                  console.error('❌ Error fetching job details:', error);
                  
                  // Fallback to basic extraction
                  const basicJob = this.extractJobFromLink(link);
                  if (basicJob && basicJob.title) {
                      jobs.push(basicJob);
                      console.log(`⚡ Fallback extraction: ${basicJob.title}`);
                  }
              }
          }
      }
      
      // Step 3: Fallback to basic page scraping if no links found
      if (jobs.length === 0) {
          console.log('🔄 No job links found, using basic page extraction...');
          return this.extractJobListingsBasic();
      }
      
      console.log(`🎯 Final result: ${jobs.length} jobs extracted`);
      return jobs;
  }

  // Enhanced job details fetching with cross-origin support
  async fetchJobDetailsEnhanced(jobLink) {
      try {
          // Check if we can fetch directly (same-origin)
          if (jobLink.url.startsWith(window.location.origin)) {
              console.log(`🟢 Same-origin fetch: ${jobLink.url}`);
              return await this.fetchDirectly(jobLink);
          } 
          // Cross-origin - use backend API
          else {
              console.log(`🟡 Cross-origin fetch via backend: ${jobLink.url}`);
              return await this.fetchViaBackend(jobLink);
          }
      } catch (error) {
          console.error('Error in fetchJobDetailsEnhanced:', error);
          return jobLink; // Return basic info if all fails
      }
  }

  // Direct fetch for same-origin URLs
  async fetchDirectly(jobLink) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.fetchTimeout);
      
      try {
          const response = await fetch(jobLink.url, {
              signal: controller.signal,
              headers: {
                  'User-Agent': 'Mozilla/5.0 (compatible; JobScanner/1.0)'
              }
          });
          
          if (!response.ok) {
              throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }
          
          const html = await response.text();
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, 'text/html');
          
          return this.extractFullJobFromPage(doc, jobLink);
          
      } finally {
          clearTimeout(timeoutId);
      }
  }

  // Fetch via backend API for cross-origin URLs
  async fetchViaBackend(jobLink) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.fetchTimeout);
      
      try {
          console.log(`📡 Requesting backend fetch for: ${jobLink.url}`);
          
          const response = await fetch(`${this.apiEndpoint}/fetch/job`, {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                  job_url: jobLink.url,
                  user_id: 'chrome-extension-user',
                  include_full_content: true,
                  extraction_method: 'enhanced'
              }),
              signal: controller.signal
          });
          
          if (!response.ok) {
              throw new Error(`Backend API error: ${response.status}`);
          }
          
          const result = await response.json();
          
          if (result.success && result.job) {
              console.log(`✅ Backend fetch successful for: ${jobLink.url}`);
              
              // Merge backend data with original link data
              return {
                  ...jobLink,
                  title: result.job.title || jobLink.title,
                  company: result.job.company || jobLink.company,
                  location: result.job.location || jobLink.location,
                  description: result.job.description || 'Description fetched via backend',
                  requirements: result.job.requirements || [],
                  qualifications: result.job.qualifications || [],
                  benefits: result.job.benefits || [],
                  salary: result.job.salary || '',
                  jobType: result.job.job_type || '',
                  extractionMethod: 'backend-api',
                  fetchedAt: new Date().toISOString()
              };
          } else {
              throw new Error(result.error || 'Backend extraction failed');
          }
          
      } catch (error) {
          console.error('❌ Backend fetch failed:', error);
          
          // Return basic job info with indication of fetch failure
          return {
              ...jobLink,
              description: `Job details could not be fetched (${error.message})`,
              requirements: [],
              extractionMethod: 'fallback',
              fetchError: error.message
          };
          
      } finally {
          clearTimeout(timeoutId);
      }
  }

  // Find job links on the current page
  async findJobLinks() {
      const jobLinks = [];
      
      // Comprehensive selectors for different career sites
      const siteSpecificSelectors = {
          // Workday sites
          workday: [
              'a[href*="myworkdayjobs.com"]',
              'a[data-automation-id*="jobTitle"]',
              '.css-1qx8o17 a', // Common Workday class
              '[data-automation-id="jobTitle"] a'
          ],
          
          // Greenhouse sites  
          greenhouse: [
              'a[href*="greenhouse.io"]',
              'a[href*="grnh.se"]',
              '.opening a',
              '.job-post a'
          ],
          
          // Lever sites
          lever: [
              'a[href*="jobs.lever.co"]',
              '.posting a',
              '.posting-title a'
          ],
          
          // BambooHR sites
          bamboohr: [
              'a[href*="bamboohr.com"]',
              '.BH-JobBoard-Item a'
          ],
          
          // Generic job site selectors
          generic: [
              'a[href*="/job/"]',
              'a[href*="/jobs/"]',
              'a[href*="/position/"]',
              'a[href*="/career/"]',
              'a[href*="/opening/"]',
              '.job-item a',
              '.job-listing a',
              '.position a',
              '.career-item a'
          ]
      };
      
      // Detect site type and use appropriate selectors
      const currentDomain = window.location.hostname.toLowerCase();
      let selectorsToUse = siteSpecificSelectors.generic;
      
      if (currentDomain.includes('workday')) {
          selectorsToUse = [...siteSpecificSelectors.workday, ...siteSpecificSelectors.generic];
      } else if (currentDomain.includes('greenhouse')) {
          selectorsToUse = [...siteSpecificSelectors.greenhouse, ...siteSpecificSelectors.generic];
      } else if (currentDomain.includes('lever')) {
          selectorsToUse = [...siteSpecificSelectors.lever, ...siteSpecificSelectors.generic];
      } else if (currentDomain.includes('bamboo')) {
          selectorsToUse = [...siteSpecificSelectors.bamboohr, ...siteSpecificSelectors.generic];
      }
      
      console.log(`🎯 Using selectors for site type: ${currentDomain}`);
      
      // Extract job links using selected selectors
      selectorsToUse.forEach(selector => {
          try {
              const elements = document.querySelectorAll(selector);
              console.log(`🔍 Selector "${selector}" found ${elements.length} elements`);
              
              elements.forEach(element => {
                  const href = element.href;
                  if (href && !jobLinks.find(link => link.url === href)) {
                      // Extract basic info visible on listing page
                      const jobInfo = this.extractJobFromLink(element);
                      if (jobInfo.title) {
                          jobLinks.push({
                              url: href,
                              title: jobInfo.title,
                              company: jobInfo.company,
                              location: jobInfo.location,
                              element: element,
                              selector: selector
                          });
                      }
                  }
              });
          } catch (error) {
              console.warn(`Error with selector "${selector}":`, error);
          }
      });
      
      console.log(`📋 Total unique job links found: ${jobLinks.length}`);
      return jobLinks;
  }

  // Extract basic job info from a job link element
  extractJobFromLink(linkElement) {
      const job = {
          title: '',
          company: '',
          location: '',
          url: linkElement.href || linkElement.url
      };
      
      // Find the job card/container
      const jobCard = linkElement.closest('.job-tile') || 
                     linkElement.closest('.job-item') || 
                     linkElement.closest('.job-listing') ||
                     linkElement.closest('[data-automation-id*="job"]') ||
                     linkElement.closest('.opening') ||
                     linkElement.closest('.posting') ||
                     linkElement.closest('.BH-JobBoard-Item') ||
                     linkElement.parentElement;
      
      if (jobCard) {
          // Extract title with multiple strategies
          const titleSelectors = [
              'h1', 'h2', 'h3', 'h4',
              '.title', '.job-title', '.position-title',
              '[data-automation-id*="title"]',
              '.posting-title',
              '.opening-title'
          ];
          
          for (const selector of titleSelectors) {
              const titleEl = jobCard.querySelector(selector) || linkElement.querySelector(selector);
              if (titleEl && titleEl.textContent.trim()) {
                  job.title = titleEl.textContent.trim();
                  break;
              }
          }
          
          // If no title found in card, use link text
          if (!job.title) {
              job.title = linkElement.textContent.trim() || linkElement.title || 'Job Position';
          }
          
          // Extract company
          const companySelectors = [
              '.company', '.company-name', '.employer',
              '[data-automation-id*="company"]',
              '.posting-company'
          ];
          
          for (const selector of companySelectors) {
              const companyEl = jobCard.querySelector(selector);
              if (companyEl && companyEl.textContent.trim()) {
                  job.company = companyEl.textContent.trim();
                  break;
              }
          }
          
          // Fallback company extraction from domain or page title
          if (!job.company) {
              job.company = document.title.split(' - ')[0] || 
                           window.location.hostname.replace('www.', '').split('.')[0] ||
                           'Company';
          }
          
          // Extract location
          const locationSelectors = [
              '.location', '.job-location', '.city',
              '[data-automation-id*="location"]',
              '.posting-location'
          ];
          
          for (const selector of locationSelectors) {
              const locationEl = jobCard.querySelector(selector);
              if (locationEl && locationEl.textContent.trim()) {
                  job.location = locationEl.textContent.trim();
                  break;
              }
          }
      }
      
      return job;
  }

  // Extract full job details from a job page DOM
  extractFullJobFromPage(doc, basicJob) {
      const job = { ...basicJob };
      
      try {
          // Enhanced extraction based on common ATS patterns
          
          // Workday-specific extraction
          if (job.url.includes('myworkdayjobs.com') || job.url.includes('workday')) {
              job.description = this.extractWorkdayJob(doc);
          }
          // Greenhouse-specific extraction
          else if (job.url.includes('greenhouse.io') || job.url.includes('grnh.se')) {
              job.description = this.extractGreenhouseJob(doc);
          }
          // Lever-specific extraction
          else if (job.url.includes('jobs.lever.co')) {
              job.description = this.extractLeverJob(doc);
          }
          // BambooHR-specific extraction
          else if (job.url.includes('bamboohr.com')) {
              job.description = this.extractBambooHRJob(doc);
          }
          // Generic extraction for other sites
          else {
              job.description = this.extractGenericJob(doc);
          }
          
      } catch (error) {
          console.error('Error extracting job details:', error);
          job.description = 'Error extracting job description';
      }
      
      return job;
  }

  // Workday-specific extraction
  extractWorkdayJob(doc) {
      const contentSelectors = [
          '[data-automation-id="jobPostingDescription"]',
          '.jobDescription',
          '.Job_Description',
          '.wd-text'
      ];
      
      for (const selector of contentSelectors) {
          const element = doc.querySelector(selector);
          if (element) {
              return element.textContent.trim().substring(0, 2000);
          }
      }
      
      return 'Workday job description (detailed extraction in progress)';
  }

  // Greenhouse-specific extraction
  extractGreenhouseJob(doc) {
      const contentSelectors = [
          '.job-post-content',
          '.content',
          '.job-description'
      ];
      
      for (const selector of contentSelectors) {
          const element = doc.querySelector(selector);
          if (element) {
              return element.textContent.trim().substring(0, 2000);
          }
      }
      
      return 'Greenhouse job description (detailed extraction in progress)';
  }

  // Lever-specific extraction
  extractLeverJob(doc) {
      const contentSelectors = [
          '.posting-content',
          '.section-wrapper',
          '.posting-description'
      ];
      
      for (const selector of contentSelectors) {
          const element = doc.querySelector(selector);
          if (element) {
              return element.textContent.trim().substring(0, 2000);
          }
      }
      
      return 'Lever job description (detailed extraction in progress)';
  }

  // BambooHR-specific extraction
  extractBambooHRJob(doc) {
      const contentSelectors = [
          '.BH-Job-Description',
          '.job-description',
          '.content'
      ];
      
      for (const selector of contentSelectors) {
          const element = doc.querySelector(selector);
          if (element) {
              return element.textContent.trim().substring(0, 2000);
          }
      }
      
      return 'BambooHR job description (detailed extraction in progress)';
  }

  // Generic job extraction
  extractGenericJob(doc) {
      const contentSelectors = [
          '.job-description',
          '.description',
          '.content',
          '.job-content',
          'main',
          '.main-content',
          '#content'
      ];
      
      for (const selector of contentSelectors) {
          const element = doc.querySelector(selector);
          if (element) {
              // Remove scripts and unwanted elements
              const scripts = element.querySelectorAll('script, style, nav, footer');
              scripts.forEach(el => el.remove());
              
              return element.textContent.trim().substring(0, 2000);
          }
      }
      
      return 'Job description available (extraction in progress)';
  }

  // Fallback basic extraction method
  extractJobListingsBasic() {
      const jobs = [];
      
      const jobSelectors = [
          '[data-testid*="job"]',
          '.job-item',
          '.job-listing', 
          '.position',
          '.opening',
          '.career-opportunity'
      ];
      
      jobSelectors.forEach(selector => {
          const elements = document.querySelectorAll(selector);
          elements.forEach(element => {
              const job = this.extractJobFromElement(element);
              if (job && job.title) {
                  jobs.push(job);
              }
          });
      });
      
      return jobs.filter((job, index, self) => 
          index === self.findIndex(j => j.title === job.title && j.company === job.company)
      );
  }

  extractJobFromElement(element) {
      try {
          const job = {
              title: '',
              company: '',
              location: '',
              url: '',
              description: '',
              requirements: []
          };
          
          // Extract title
          const titleSelectors = [
              'h1', 'h2', 'h3', 'h4',
              '.job-title', '.position-title', '.title',
              '[data-testid*="title"]'
          ];
          
          for (const selector of titleSelectors) {
              const titleEl = element.querySelector(selector) || element.closest('a')?.querySelector(selector);
              if (titleEl && titleEl.textContent.trim()) {
                  job.title = titleEl.textContent.trim();
                  break;
              }
          }
          
          // Extract company
          const companySelectors = [
              '.company', '.company-name', '.employer',
              '[data-testid*="company"]'
          ];
          
          for (const selector of companySelectors) {
              const companyEl = element.querySelector(selector);
              if (companyEl && companyEl.textContent.trim()) {
                  job.company = companyEl.textContent.trim();
                  break;
              }
          }
          
          if (!job.company) {
              job.company = document.title.split(' - ')[0] || window.location.hostname;
          }
          
          // Extract location
          const locationSelectors = [
              '.location', '.job-location', '.city',
              '[data-testid*="location"]'
          ];
          
          for (const selector of locationSelectors) {
              const locationEl = element.querySelector(selector);
              if (locationEl && locationEl.textContent.trim()) {
                  job.location = locationEl.textContent.trim();
                  break;
              }
          }
          
          // Extract URL
          const linkEl = element.closest('a') || element.querySelector('a');
          if (linkEl && linkEl.href) {
              job.url = linkEl.href;
          } else {
              job.url = window.location.href;
          }
          
          // Extract description (basic)
          const descEl = element.querySelector('.description, .summary, .excerpt');
          if (descEl) {
              job.description = descEl.textContent.trim().substring(0, 200);
          }
          
          return job;
      } catch (error) {
          console.error('Error extracting job from element:', error);
          return null;
      }
  }
}

// Enhanced content extraction function
async function extractPageContent() {
  console.log('🚀 Starting enhanced content extraction from:', window.location.href);
  
  const extractor = new JobExtractor();
  
  const content = {
      title: document.title,
      url: window.location.href,
      text: '',
      jobElements: [],
      jobLinks: [],
      enhancedJobs: [] // New field for enhanced job data
  };
  
  try {
      // Get enhanced job listings with cross-origin support
      const enhancedJobs = await extractor.extractJobListings();
      content.enhancedJobs = enhancedJobs;
      
      console.log(`✅ Enhanced extraction complete: ${enhancedJobs.length} jobs with detailed info`);
      
      // Also populate legacy fields for compatibility
      content.jobElements = enhancedJobs.map((job, index) => ({
          id: `enhanced-${index}`,
          title: job.title,
          company: job.company,
          location: job.location,
          description: job.description,
          text: `${job.title} at ${job.company}`,
          html: `<div>${job.title}</div>`,
          selector: 'enhanced-extraction',
          url: job.url
      }));
      
  } catch (error) {
      console.error('❌ Enhanced extraction failed, falling back to basic:', error);
      
      // Fallback to basic extraction
      const basicJobs = extractor.extractJobListingsBasic();
      content.jobElements = basicJobs.map((job, index) => ({
          id: `basic-${index}`,
          title: job.title,
          company: job.company,
          location: job.location,
          description: job.description || 'Basic job extraction',
          text: `${job.title} at ${job.company}`,
          html: `<div>${job.title}</div>`,
          selector: 'basic-extraction',
          url: job.url
      }));
  }
  
  // Extract main text content
  const mainContent = document.querySelector('main') || 
                     document.querySelector('.main') ||
                     document.querySelector('#main') ||
                     document.body;
  
  if (mainContent) {
      const scripts = mainContent.querySelectorAll('script, style, nav, footer, .nav, .footer');
      scripts.forEach(el => el.remove());
      content.text = mainContent.textContent.trim().substring(0, 5000);
  }
  
  console.log(`📊 Final extraction summary:`, {
      enhancedJobs: content.enhancedJobs?.length || 0,
      jobElements: content.jobElements?.length || 0,
      textLength: content.text?.length || 0
  });
  
  return content;
}

// Listen for messages from background script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📨 Enhanced content script received message:', message);
  
  switch (message.type) {
      case 'EXTRACT_CONTENT':
          extractPageContent().then(content => {
              sendResponse(content);
          }).catch(error => {
              console.error('Error in EXTRACT_CONTENT:', error);
              sendResponse({ error: error.message });
          });
          return true; // Keep message channel open for async response
          
      case 'EXTRACT_JOBS':
          const extractor = new JobExtractor();
          extractor.extractJobListings().then(jobs => {
              sendResponse({ jobs });
          }).catch(error => {
              console.error('Error in EXTRACT_JOBS:', error);
              sendResponse({ jobs: [], error: error.message });
          });
          return true;
          
      case 'PING':
          sendResponse({ status: 'ready', enhanced: true });
          break;
          
      default:
          console.log('❓ Unknown message type:', message.type);
  }
});

// Auto-extract content when script loads (for auto-scan feature)
if (window.location.href.includes('career') || 
  window.location.href.includes('job') ||
  window.location.href.includes('employment')) {
  
  setTimeout(async () => {
      try {
          console.log('🤖 Auto-extracting content...');
          const content = await extractPageContent();
          
          // Send to background script for processing
          chrome.runtime.sendMessage({
              type: 'PAGE_CONTENT_EXTRACTED',
              data: content
          });
          
          console.log('📤 Auto-extracted content sent to background script');
      } catch (error) {
          console.error('❌ Error in auto-extraction:', error);
      }
  }, 3000); // Wait for page to fully load
}

console.log('✅ Enhanced content script initialization complete'); 