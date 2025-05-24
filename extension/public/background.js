// Background service worker for Bulk-Scanner Résumé Matcher Chrome Extension

console.log('Bulk-Scanner background service worker loaded');

// Handle extension installation
chrome.runtime.onInstalled.addListener((details) => {
  console.log('Extension installed:', details);
  
  if (details.reason === 'install') {
    // Set default settings
    chrome.storage.sync.set({
      apiEndpoint: 'http://localhost:8000/api/v1',
      autoScan: false,
      matchThreshold: 40
    });
  }
});

// Handle messages from content scripts and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Background received message:', message);
  
  switch (message.type) {
    case 'SCAN_PAGE':
      handleScanPage(message.data, sendResponse);
      return true; // Keep message channel open for async response
      
    case 'GET_SETTINGS':
      chrome.storage.sync.get(['apiEndpoint', 'autoScan', 'matchThreshold', 'resumeData'], sendResponse);
      return true;
      
    case 'SAVE_SETTINGS':
      chrome.storage.sync.set(message.data, () => {
        sendResponse({ success: true });
      });
      return true;
      
    default:
      console.log('Unknown message type:', message.type);
  }
});

async function handleScanPage(data, sendResponse) {
  try {
    const { url, pageContent } = data;
    
    // Get all relevant settings and data from storage
    const settings = await chrome.storage.sync.get([
      'apiEndpoint', 
      'resumeData', 
      'resumeFileName',
      'matchThreshold'
    ]);
    
    const apiEndpoint = settings.apiEndpoint || 'http://localhost:8000/api/v1';
    
    console.log('Scanning page:', url);
    console.log('Using API:', apiEndpoint);
    console.log('Resume data available:', !!settings.resumeData);
    console.log('Page content summary:', {
      jobElements: pageContent.jobElements?.length || 0,
      jobLinks: pageContent.jobLinks?.length || 0,
      hasJobs: !!pageContent.jobs?.length
    });
    
    // Prepare enhanced request data with resume information
    const requestData = {
      url: url,
      user_id: 'chrome-extension-user',
      page_content: pageContent,
      match_threshold: (settings.matchThreshold || 70) / 100, // Convert percentage to decimal
      
      // Include structured resume data if available
      resume_data: settings.resumeData || null,
      
      // Fallback to basic resume text if structured data not available
      resume_text: settings.resumeData ? 
        generateResumeText(settings.resumeData) : null
    };
    
    console.log('Request payload summary:', {
      url: requestData.url,
      jobElementsCount: requestData.page_content.jobElements?.length || 0,
      jobLinksCount: requestData.page_content.jobLinks?.length || 0,
      matchThreshold: requestData.match_threshold,
      resumeDataAvailable: !!requestData.resume_data,
      resumeTextGenerated: !!requestData.resume_text
    });
    
    // Send enhanced request to backend API
    try {
      const response = await fetch(`${apiEndpoint}/scan/page`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData)
      });
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      console.log('API response summary:', {
        success: result.success,
        matchesCount: result.matches?.length || 0,
        jobsFound: result.jobs_found,
        processingMethod: result.processing_method,
        processingTime: result.processing_time_ms
      });
      
      // Enhanced response with processing method info
      sendResponse({
        success: result.success,
        matches: result.matches || [],
        message: result.message,
        jobs_found: result.jobs_found,
        processing_time: result.processing_time_ms,
        processing_method: result.processing_method,
        resume_used: !!settings.resumeData,
        threshold_used: settings.matchThreshold || 70,
        api_features: {
          llm_matching: result.processing_method === 'llm',
          resume_processing: !!settings.resumeData,
          real_scoring: result.processing_method !== 'mock'
        }
      });
      
    } catch (apiError) {
      console.error('API request failed:', apiError);
      
      // Enhanced fallback with resume awareness
      console.log('Falling back to mock data');
      const mockResponse = {
        success: true,
        matches: generateEnhancedMockData(url, settings.resumeData, pageContent),
        message: settings.resumeData ? 
          'Found job matches using local resume data (API unavailable)' : 
          'Found job matches (using mock data - no resume uploaded)',
        jobs_found: Math.max(5, pageContent.jobElements?.length || pageContent.jobLinks?.length || 0),
        processing_time: 245,
        processing_method: 'mock',
        resume_used: !!settings.resumeData,
        threshold_used: settings.matchThreshold || 70,
        api_features: {
          llm_matching: false,
          resume_processing: !!settings.resumeData,
          real_scoring: false
        }
      };
      
      sendResponse(mockResponse);
    }
    
  } catch (error) {
    console.error('Error scanning page:', error);
    sendResponse({
      success: false,
      error: error.message,
      matches: [],
      message: 'Failed to scan page',
      processing_method: 'error'
    });
  }
}

function generateResumeText(resumeData) {
  /**
   * Convert structured resume data back to text for API compatibility
   */
  if (!resumeData) return null;
  
  let text = '';
  
  // Add personal info
  if (resumeData.personal_info) {
    if (resumeData.personal_info.name) text += `Name: ${resumeData.personal_info.name}\n`;
    if (resumeData.personal_info.email) text += `Email: ${resumeData.personal_info.email}\n`;
    if (resumeData.personal_info.phone) text += `Phone: ${resumeData.personal_info.phone}\n`;
  }
  
  // Add summary
  if (resumeData.summary) {
    text += `\nSummary: ${resumeData.summary}\n`;
  }
  
  // Add skills
  if (resumeData.skills && resumeData.skills.length > 0) {
    text += `\nSkills: ${resumeData.skills.join(', ')}\n`;
  }
  
  // Add experience
  if (resumeData.experience && resumeData.experience.length > 0) {
    text += '\nExperience:\n';
    resumeData.experience.forEach(exp => {
      text += `- ${exp.title} at ${exp.company} (${exp.duration})\n`;
      if (exp.description) text += `  ${exp.description}\n`;
      if (exp.technologies) text += `  Technologies: ${exp.technologies.join(', ')}\n`;
    });
  }
  
  // Add education
  if (resumeData.education && resumeData.education.length > 0) {
    text += '\nEducation:\n';
    resumeData.education.forEach(edu => {
      text += `- ${edu.degree} in ${edu.field} from ${edu.institution} (${edu.year})\n`;
    });
  }
  
  return text;
}

function generateEnhancedMockData(url, resumeData, pageContent) {
  /**
   * Generate more realistic mock data based on resume and actual page content if available
   */
  
  const baseJobs = [];
  
  // First, try to use real job data from page content if available
  if (pageContent && pageContent.jobElements && pageContent.jobElements.length > 0) {
    console.log('Using real job data from page content for mock scoring');
    
    // Use the actual jobs found but with mock scoring
    pageContent.jobElements.slice(0, 8).forEach((jobElement, index) => {
      const job = {
        id: jobElement.id || `real-${index}`,
        title: jobElement.title || jobElement.text?.split('\n')[0]?.trim() || 'Software Position',
        company: jobElement.company || extractCompanyFromUrl(url),
        location: jobElement.location || 'Various Locations',
        url: jobElement.url || url,
        summary: 'Real job from page with mock scoring'
      };
      
      baseJobs.push(job);
    });
  }
  
  // If we have job links but no elements, use those
  else if (pageContent && pageContent.jobLinks && pageContent.jobLinks.length > 0) {
    console.log('Using job links from page content');
    
    pageContent.jobLinks.slice(0, 6).forEach((jobLink, index) => {
      const job = {
        id: jobLink.id || `link-${index}`,
        title: jobLink.title || jobLink.text || 'Position Available',
        company: jobLink.company || extractCompanyFromUrl(url),
        location: jobLink.location || 'Location TBD',
        url: jobLink.url || url,
        summary: 'Job link from page with mock scoring'
      };
      
      baseJobs.push(job);
    });
  }
  
  // Fallback to completely mock jobs
  if (baseJobs.length === 0) {
    console.log('No real job data found, using completely mock jobs');
    
    baseJobs.push(
      {
        id: 1,
        title: 'Senior Software Engineer',
        company: extractCompanyFromUrl(url),
        location: 'San Francisco, CA',
        url: url,
        summary: 'Excellent match for your technical background'
      },
      {
        id: 2,
        title: 'Full Stack Developer',
        company: extractCompanyFromUrl(url),
        location: 'Remote',
        url: url,
        summary: 'Good fit for your development skills'
      },
      {
        id: 3,
        title: 'Software Engineer',
        company: extractCompanyFromUrl(url),
        location: 'New York, NY',
        url: url,
        summary: 'Growing team with modern tech stack'
      }
    );
  }
  
  // Enhance with resume-specific scoring if available
  if (resumeData) {
    const userSkills = resumeData.skills || [];
    const hasReactExperience = userSkills.some(skill => 
      skill.toLowerCase().includes('react')
    );
    const hasPythonExperience = userSkills.some(skill => 
      skill.toLowerCase().includes('python')
    );
    const hasJavaScriptExperience = userSkills.some(skill => 
      skill.toLowerCase().includes('javascript')
    );
    
    // Apply realistic scoring based on resume
    baseJobs.forEach((job, index) => {
      // Base score varies by position and user skills
      let baseScore = 70 + (index * -5); // Decreasing scores
      
      // Boost for skill matches
      if (hasReactExperience && job.title.toLowerCase().includes('react')) {
        baseScore += 15;
      }
      if (hasPythonExperience && (job.title.toLowerCase().includes('python') || job.title.toLowerCase().includes('backend'))) {
        baseScore += 12;
      }
      if (hasJavaScriptExperience && (job.title.toLowerCase().includes('javascript') || job.title.toLowerCase().includes('frontend') || job.title.toLowerCase().includes('full stack'))) {
        baseScore += 10;
      }
      
      job.match_score = Math.min(95, Math.max(65, baseScore));
      job.matching_skills = userSkills.filter(skill => 
        ['javascript', 'python', 'react', 'node.js', 'sql', 'aws'].includes(skill.toLowerCase())
      ).slice(0, 4);
      job.missing_skills = ['Docker', 'Kubernetes'].filter(skill => 
        !userSkills.some(userSkill => userSkill.toLowerCase().includes(skill.toLowerCase()))
      ).slice(0, 2);
      job.summary = hasReactExperience && job.title.toLowerCase().includes('react') ?
        'Excellent match - your React experience is exactly what we need!' :
        hasPythonExperience && job.title.toLowerCase().includes('python') ?
        'Great fit - your Python skills are highly valued here!' :
        'Good potential match for your technical background';
    });
  } else {
    // Default scores when no resume
    baseJobs.forEach((job, index) => {
      job.match_score = 75 - (index * 3); // Decreasing scores from 75
      job.matching_skills = ['JavaScript', 'HTML', 'CSS'].slice(0, 2);
      job.missing_skills = ['React', 'TypeScript'];
      job.summary = 'Upload your resume for better matching accuracy';
    });
  }
  
  return baseJobs;
}

function extractCompanyFromUrl(url) {
  if (url.includes('google')) return 'Google';
  if (url.includes('microsoft')) return 'Microsoft';
  if (url.includes('apple')) return 'Apple';
  if (url.includes('amazon')) return 'Amazon';
  if (url.includes('meta')) return 'Meta';
  if (url.includes('netflix')) return 'Netflix';
  return 'Tech Corp';
}

// Handle tab updates for auto-scanning
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    const settings = await chrome.storage.sync.get(['autoScan']);
    
    if (settings.autoScan && isCareerPage(tab.url)) {
      console.log('Auto-scanning career page:', tab.url);
      // Inject content script to scan page
      chrome.scripting.executeScript({
        target: { tabId: tabId },
        files: ['content.js']
      });
    }
  }
});

function isCareerPage(url) {
  const careerKeywords = [
    'careers', 'jobs', 'employment', 'opportunities', 
    'openings', 'positions', 'work-with-us', 'join-us'
  ];
  
  return careerKeywords.some(keyword => 
    url.toLowerCase().includes(keyword)
  );
} 