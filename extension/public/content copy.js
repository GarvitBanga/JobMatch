// Content script for Bulk-Scanner Résumé Matcher Chrome Extension

console.log('Bulk-Scanner content script loaded on:', window.location.href);

// Function to extract job listings from the current page
async function extractJobListings() {
  const jobs = [];
  
  // First, try to find job links on the page
  const jobLinks = await findJobLinks();
  
  if (jobLinks.length > 0) {
    console.log(`Found ${jobLinks.length} job links, fetching full descriptions...`);
    
    // Limit to first 5 jobs to avoid overwhelming the system
    const limitedLinks = jobLinks.slice(0, 5);
    
    for (const link of limitedLinks) {
      try {
        const fullJob = await fetchJobDetails(link);
        if (fullJob && fullJob.title) {
          jobs.push(fullJob);
        }
      } catch (error) {
        console.error('Error fetching job details:', error);
        // Fallback to basic extraction
        const basicJob = extractJobFromLink(link);
        if (basicJob && basicJob.title) {
          jobs.push(basicJob);
        }
      }
    }
  }
  
  // If no job links found, fall back to original method
  if (jobs.length === 0) {
    console.log('No job links found, using basic extraction...');
    return extractJobListingsBasic();
  }
  
  return jobs;
}

// Find job links on the current page
async function findJobLinks() {
  const jobLinks = [];
  
  // Amazon Jobs specific selectors
  const amazonSelectors = [
    'a[href*="/jobs/"]',
    'a.read-more',
    '.job-tile a',
    '[data-test-id*="job"] a'
  ];
  
  // General job link selectors
  const generalSelectors = [
    'a[href*="/job/"]',
    'a[href*="/position/"]',
    'a[href*="/career/"]',
    'a[href*="/opening/"]',
    '.job-item a',
    '.job-listing a',
    '.position a'
  ];
  
  const allSelectors = [...amazonSelectors, ...generalSelectors];
  
  allSelectors.forEach(selector => {
    const elements = document.querySelectorAll(selector);
    elements.forEach(element => {
      const href = element.href;
      if (href && !jobLinks.includes(href)) {
        // Extract basic info visible on listing page
        const jobInfo = extractJobFromLink(element);
        if (jobInfo.title) {
          jobLinks.push({
            url: href,
            title: jobInfo.title,
            company: jobInfo.company,
            location: jobInfo.location,
            element: element
          });
        }
      }
    });
  });
  
  return jobLinks;
}

// Extract basic job info from a job link element
function extractJobFromLink(linkElement) {
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
                 linkElement.closest('[data-test-id*="job"]') ||
                 linkElement.parentElement;
  
  if (jobCard) {
    // Extract title
    const titleEl = jobCard.querySelector('h1, h2, h3, h4, .title, .job-title') || linkElement;
    if (titleEl) {
      job.title = titleEl.textContent.trim();
    }
    
    // Extract company
    const companyEl = jobCard.querySelector('.company, .company-name, .employer');
    if (companyEl) {
      job.company = companyEl.textContent.trim();
    } else {
      job.company = document.title.split(' - ')[0] || window.location.hostname;
    }
    
    // Extract location
    const locationEl = jobCard.querySelector('.location, .job-location, .city');
    if (locationEl) {
      job.location = locationEl.textContent.trim();
    }
  }
  
  return job;
}

// Fetch full job details from individual job page
async function fetchJobDetails(jobLink) {
  try {
    // For same-origin requests, we can fetch directly
    if (jobLink.url.startsWith(window.location.origin)) {
      const response = await fetch(jobLink.url);
      const html = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      
      return extractFullJobFromPage(doc, jobLink);
    } else {
      // For cross-origin, we'll have the backend fetch it
      console.log('Cross-origin job page, will fetch server-side:', jobLink.url);
      return {
        ...jobLink,
        description: 'Full description will be fetched server-side',
        requirements: [],
        fullContentUrl: jobLink.url
      };
    }
  } catch (error) {
    console.error('Error fetching job page:', error);
    return jobLink; // Return basic info if fetch fails
  }
}

// Extract full job details from a job page DOM
function extractFullJobFromPage(doc, basicJob) {
  const job = { ...basicJob };
  
  // Amazon-specific extraction
  if (job.url.includes('amazon.jobs')) {
    // Description
    const descEl = doc.querySelector('#job-detail-body .section:first-child p, .description');
    if (descEl) {
      job.description = descEl.textContent.trim();
    }
    
    // Basic qualifications
    const basicQualEl = doc.querySelector('h2:contains("BASIC QUALIFICATIONS") + ul, h3:contains("BASIC QUALIFICATIONS") + ul');
    if (basicQualEl) {
      job.basicQualifications = Array.from(basicQualEl.querySelectorAll('li')).map(li => li.textContent.trim());
    }
    
    // Preferred qualifications  
    const prefQualEl = doc.querySelector('h2:contains("PREFERRED QUALIFICATIONS") + ul, h3:contains("PREFERRED QUALIFICATIONS") + ul');
    if (prefQualEl) {
      job.preferredQualifications = Array.from(prefQualEl.querySelectorAll('li')).map(li => li.textContent.trim());
    }
    
    // Combine all text for description
    const allText = doc.body.textContent;
    job.description = allText.substring(0, 1000); // First 1000 chars
  }
  
  // Generic extraction for other sites
  else {
    const contentSelectors = [
      '.job-description',
      '.description', 
      '.content',
      '.job-content',
      'main',
      '.main-content'
    ];
    
    for (const selector of contentSelectors) {
      const contentEl = doc.querySelector(selector);
      if (contentEl) {
        job.description = contentEl.textContent.trim().substring(0, 1000);
        break;
      }
    }
  }
  
  return job;
}

// Original basic extraction method (fallback)
function extractJobListingsBasic() {
  const jobs = [];
  
  // Common selectors for job listings on various career sites
  const jobSelectors = [
    '[data-testid*="job"]',
    '.job-item',
    '.job-listing',
    '.position',
    '.opening',
    '.career-opportunity',
    'a[href*="/job"]',
    'a[href*="/position"]',
    'a[href*="/career"]'
  ];
  
  jobSelectors.forEach(selector => {
    const elements = document.querySelectorAll(selector);
    elements.forEach(element => {
      const job = extractJobFromElement(element);
      if (job && job.title) {
        jobs.push(job);
      }
    });
  });
  
  // Remove duplicates based on title and company
  const uniqueJobs = jobs.filter((job, index, self) => 
    index === self.findIndex(j => j.title === job.title && j.company === job.company)
  );
  
  return uniqueJobs;
}

function extractJobFromElement(element) {
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
    
    // If no company found, try to get from page title or domain
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

// Function to extract general page content with enhanced job detection
async function extractPageContent() {
  console.log('Extracting content from:', window.location.href);
  
  const content = {
    title: document.title,
    url: window.location.href,
    text: '',
    jobElements: [],
    jobLinks: []
  };
  
  // Amazon Jobs specific extraction
  if (window.location.href.includes('amazon.jobs')) {
    console.log('Amazon jobs page detected');
    
    // Amazon job cards - multiple selector attempts
    const amazonJobSelectors = [
      '[data-test="job-alert-card"]',
      '.job-tile',
      '.job-item',
      '[data-automation-id*="job"]',
      '.search-result',
      '.result-card',
      '[data-test*="job"]',
      'article',
      '.css-u9r0o6', // Sometimes Amazon uses CSS module classes
      '.css-rq1yv7'  // Another common Amazon class
    ];
    
    amazonJobSelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      console.log(`Found ${elements.length} elements with selector: ${selector}`);
      
      elements.forEach((el, index) => {
        if (el.innerText.trim().length > 10) { // Only elements with substantial text
          
          // Try to extract structured data
          const jobData = extractAmazonJobData(el);
          
          content.jobElements.push({
            id: `amazon-job-${index}`,
            title: jobData.title || 'Amazon Position',
            company: jobData.company || 'Amazon',
            location: jobData.location || '',
            description: jobData.description || el.innerText.trim().substring(0, 500),
            text: el.innerText.trim(),
            html: el.outerHTML.slice(0, 1000),
            selector: selector,
            url: jobData.url || window.location.href
          });
        }
      });
    });
    
    // Also extract job links specifically for Amazon
    const jobLinks = document.querySelectorAll('a[href*="/jobs/"], a[href*="job-id"]');
    jobLinks.forEach((link, index) => {
      if (link.innerText.trim()) {
        content.jobLinks.push({
          id: `link-${index}`,
          title: link.innerText.trim(),
          company: 'Amazon',
          location: '',
          description: '',
          url: link.href,
          text: link.innerText.trim()
        });
      }
    });
  }
  
  // Generic job extraction for other sites
  else {
    const jobSelectors = [
      '[data-job-id]',
      '.job-result',
      '.job-listing',
      '.job-item',
      '.job-card',
      '.career-job',
      '.position',
      '.opportunity',
      'article[data-job]',
      '.search-result',
      '.job',
      '[class*="job"]',
      '[data-testid*="job"]'
    ];
    
    jobSelectors.forEach(selector => {
      const elements = document.querySelectorAll(selector);
      elements.forEach((el, index) => {
        if (el.innerText.trim().length > 20) {
          const jobData = extractGenericJobData(el);
          
          content.jobElements.push({
            id: `job-${index}`,
            title: jobData.title || '',
            company: jobData.company || '',
            location: jobData.location || '',
            description: jobData.description || el.innerText.trim().substring(0, 300),
            text: el.innerText.trim(),
            html: el.outerHTML.slice(0, 800),
            selector: selector,
            url: jobData.url || window.location.href
          });
        }
      });
    });
    
    // Extract job links for generic sites
    const links = document.querySelectorAll('a[href*="job"], a[href*="career"], a[href*="position"], a[href*="opening"]');
    content.jobLinks = Array.from(links).slice(0, 20).map((link, index) => ({
      id: `link-${index}`,
      title: link.innerText.trim() || link.title || '',
      company: '',
      location: '',
      description: '',
      url: link.href,
      text: link.innerText.trim()
    }));
  }
  
  // Extract main text content, excluding navigation and footer
  const mainContent = document.querySelector('main') || 
                     document.querySelector('.main') ||
                     document.querySelector('#main') ||
                     document.body;
  
  if (mainContent) {
    // Remove script and style elements
    const scripts = mainContent.querySelectorAll('script, style, nav, footer, .nav, .footer');
    scripts.forEach(el => el.remove());
    
    content.text = mainContent.textContent.trim().substring(0, 5000); // Limit text length
  }
  
  console.log(`Extracted ${content.jobElements.length} job elements and ${content.jobLinks.length} job links`);
  
  return content;
}

// Helper function to extract structured data from Amazon job elements
function extractAmazonJobData(element) {
  const jobData = {
    title: '',
    company: 'Amazon',
    location: '',
    description: '',
    url: window.location.href
  };
  
  // Try to extract title
  const titleSelectors = [
    'h3', 'h2', 'h1',
    '.job-title',
    '[data-test*="title"]',
    'a[data-test="job-title"]',
    '.css-1l5zw42', // Common Amazon title class
    'span[data-automation-id="job-title"]'
  ];
  
  for (const selector of titleSelectors) {
    const titleEl = element.querySelector(selector);
    if (titleEl && titleEl.innerText.trim()) {
      jobData.title = titleEl.innerText.trim();
      break;
    }
  }
  
  // Try to extract location
  const locationSelectors = [
    '[data-test*="location"]',
    '.location',
    '.job-location',
    'span[data-automation-id="job-location"]',
    '.css-1p77iir' // Common Amazon location class
  ];
  
  for (const selector of locationSelectors) {
    const locationEl = element.querySelector(selector);
    if (locationEl && locationEl.innerText.trim()) {
      jobData.location = locationEl.innerText.trim();
      break;
    }
  }
  
  // Try to extract job URL
  const linkEl = element.querySelector('a[href*="/jobs/"]') || element.querySelector('a');
  if (linkEl && linkEl.href) {
    jobData.url = linkEl.href;
  }
  
  // Get description from element text (fallback)
  if (element.innerText) {
    jobData.description = element.innerText.trim().substring(0, 500);
  }
  
  return jobData;
}

// Helper function to extract structured data from generic job elements
function extractGenericJobData(element) {
  const jobData = {
    title: '',
    company: '',
    location: '',
    description: '',
    url: window.location.href
  };
  
  // Extract title
  const titleSelectors = ['h1', 'h2', 'h3', 'h4', '.job-title', '.title', '.position-title'];
  for (const selector of titleSelectors) {
    const titleEl = element.querySelector(selector);
    if (titleEl && titleEl.innerText.trim()) {
      jobData.title = titleEl.innerText.trim();
      break;
    }
  }
  
  // Extract company
  const companySelectors = ['.company', '.company-name', '.employer'];
  for (const selector of companySelectors) {
    const companyEl = element.querySelector(selector);
    if (companyEl && companyEl.innerText.trim()) {
      jobData.company = companyEl.innerText.trim();
      break;
    }
  }
  
  // Extract location
  const locationSelectors = ['.location', '.job-location', '.city'];
  for (const selector of locationSelectors) {
    const locationEl = element.querySelector(selector);
    if (locationEl && locationEl.innerText.trim()) {
      jobData.location = locationEl.innerText.trim();
      break;
    }
  }
  
  // Extract URL
  const linkEl = element.querySelector('a');
  if (linkEl && linkEl.href) {
    jobData.url = linkEl.href;
  }
  
  // Get description
  if (element.innerText) {
    jobData.description = element.innerText.trim().substring(0, 300);
  }
  
  return jobData;
}

// Listen for messages from background script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Content script received message:', message);
  
  switch (message.type) {
    case 'EXTRACT_CONTENT':
      // Handle async response
      extractPageContent().then(content => {
        sendResponse(content);
      }).catch(error => {
        console.error('Error extracting content:', error);
        sendResponse({ error: error.message });
      });
      return true; // Indicates async response
      
    case 'EXTRACT_JOBS':
      // Handle async response
      extractJobListings().then(jobs => {
        sendResponse({ jobs });
      }).catch(error => {
        console.error('Error extracting jobs:', error);
        sendResponse({ jobs: [], error: error.message });
      });
      return true; // Indicates async response
      
    case 'PING':
      sendResponse({ status: 'ready' });
      break;
      
    default:
      console.log('Unknown message type:', message.type);
  }
});

// Auto-extract content when script loads (for auto-scan feature)
if (window.location.href.includes('career') || 
    window.location.href.includes('job') ||
    window.location.href.includes('employment')) {
  
  setTimeout(async () => {
    try {
      const content = await extractPageContent();
      console.log('Auto-extracted content:', content);
      
      // Send to background script for processing
      chrome.runtime.sendMessage({
        type: 'PAGE_CONTENT_EXTRACTED',
        data: content
      });
    } catch (error) {
      console.error('Error in auto-extraction:', error);
    }
  }, 3000); // Wait longer for dynamic content to load
}

console.log('Content script initialization complete'); 