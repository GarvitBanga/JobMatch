// Content script for Bulk-Scanner Résumé Matcher Chrome Extension

console.log('Bulk-Scanner content script loaded on:', window.location.href);

// Function to extract job listings from the current page
function extractJobListings() {
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

// Function to extract general page content
function extractPageContent() {
  const content = {
    title: document.title,
    url: window.location.href,
    text: '',
    jobs: extractJobListings()
  };
  
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
  
  return content;
}

// Listen for messages from background script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Content script received message:', message);
  
  switch (message.type) {
    case 'EXTRACT_CONTENT':
      const content = extractPageContent();
      sendResponse(content);
      break;
      
    case 'EXTRACT_JOBS':
      const jobs = extractJobListings();
      sendResponse({ jobs });
      break;
      
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
  
  setTimeout(() => {
    const content = extractPageContent();
    console.log('Auto-extracted content:', content);
    
    // Send to background script for processing
    chrome.runtime.sendMessage({
      type: 'PAGE_CONTENT_EXTRACTED',
      data: content
    });
  }, 2000); // Wait for page to fully load
}

console.log('Content script initialization complete'); 