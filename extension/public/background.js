console.log('Background service worker loaded');

// Handle extension installation
chrome.runtime.onInstalled.addListener((details) => {
  console.log('Extension installed:', details);
  
  if (details.reason === 'install') {
    // Set default settings
    chrome.storage.sync.set({
      apiEndpoint: 'https://jobmatch-production.up.railway.app/api/v1',
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
      chrome.storage.sync.get(['matchThreshold', 'resumeData'], sendResponse);
      return true;
      
    case 'SAVE_SETTINGS':
      chrome.storage.sync.set(message.data, () => {
        sendResponse({ success: true });
      });
      return true;
      
    case 'GET_LAST_RESULTS':
      // Get the last scan results from storage
      chrome.storage.local.get(['lastScanResults', 'lastScanStatus'], (data) => {
        sendResponse(data);
      });
      return true;
      
    case 'CLEAR_RESULTS':
      // Clear stored results
      chrome.storage.local.remove(['lastScanResults', 'lastScanStatus'], () => {
        sendResponse({ success: true });
      });
      return true;
      
    case 'HEALTH_CHECK':
      // Check if backend is available
      checkBackendHealth(sendResponse);
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
      'resumeData', 
      'resumeFileName',
      'matchThreshold'
    ]);
    
    // Use fixed production API endpoint with security
    const apiEndpoint = 'https://jobmatch-production.up.railway.app/api/v1';
    const apiKey = 'ext_jobmatch_secure_key_2024';  // Must match server config
    
    console.log('API endpoint:', apiEndpoint);
    console.log('Scanning page:', url);
    console.log('Using API:', apiEndpoint);
    console.log('Resume data available:', !!settings.resumeData);
    console.log('Page content:', pageContent.jobElements?.length || 0, 'job elements');
    
    // Send immediate acknowledgment to prevent timeout
    sendResponse({
      success: true,
      status: 'processing',
      message: `Processing ${pageContent.jobElements?.length || 0} jobs... This may take several minutes.`,
      progress: 0
    });
    
    const requestData = {
      url: url,
      user_id: 'chrome-extension-user',
      page_content: pageContent,
      match_threshold: (settings.matchThreshold || 70) / 100,
      batch_processing: true,
      resume_data: settings.resumeData || null,
      resume_text: settings.resumeData ? 
        generateResumeText(settings.resumeData) : null
    };
    
    console.log('Sending request for', requestData.page_content.jobElements?.length || 0, 'jobs');
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      console.log('Request timeout - continuing in background');
      controller.abort();
    }, 600000);
    
    try {
      console.log('Starting API request...');
      console.log('API Endpoint:', apiEndpoint);
      console.log('Full URL:', `${apiEndpoint}/scan/page`);
      console.log('Request payload size:', JSON.stringify(requestData).length, 'characters');
      console.log('Request headers:', {
        'Content-Type': 'application/json',
      });
      
      try {
        const healthResponse = await fetch(`${apiEndpoint.replace('/api/v1', '')}/health`, {
          method: 'GET',
          mode: 'cors'
        });
        console.log('Health check status:', healthResponse.status);
      } catch (healthError) {
        console.error('Health check failed:', healthError);
      }
      
      const response = await fetch(`${apiEndpoint}/scan/page`, {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-JobMatch-API-Key': apiKey,
          'X-Extension-ID': chrome.runtime.id
        },
        body: JSON.stringify(requestData),
        signal: controller.signal
      });
      
      console.log('Response status:', response.status);
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      console.log('API response:', result.success ? 'success' : 'failed', result.matches?.length || 0, 'matches');
      
      await chrome.storage.local.set({
        lastScanResults: {
          url: url,
          timestamp: Date.now(),
          results: result,
          settings: settings
        }
      });
      
      try {
        
        const messageData = {
          type: 'SCAN_COMPLETE',
          data: {
            success: result.success,
            matches: result.matches || [],
            message: result.message,
            jobs_found: result.jobs_found,
            processing_time: result.processing_time_ms,
            processing_method: result.processing_method,
            resume_used: result.resume_used
          }
        };
        
        await chrome.storage.local.set({ 
          pendingResults: messageData.data,
          resultsTimestamp: Date.now()
        });
        
        try {
          await chrome.runtime.sendMessage(messageData);
        } catch (messageError) {
          console.log('Popup not available, results stored for retrieval');
        }
        
        const tabs = await chrome.tabs.query({});
        for (const tab of tabs) {
          try {
            await chrome.tabs.sendMessage(tab.id, messageData);
          } catch (tabError) {
          }
        }
        
      } catch (error) {
        console.error('Error sending completion notification:', error);
      }
      
      console.log('Scan completed successfully');
      
    } catch (apiError) {
      clearTimeout(timeoutId);
      
      console.error('API request failed:', apiError);
      
      if (apiError.name === 'TypeError' && apiError.message.includes('Failed to fetch')) {
        console.error('Network error - check connection and API availability');
      }
      
      if (apiError.name === 'AbortError') {
        console.log('Request timeout - processing may still be running');
        
        await chrome.storage.local.set({
          lastScanStatus: {
            url: url,
            status: 'timeout',
            message: 'Processing took longer than expected.',
            timestamp: Date.now()
          }
        });
        
        try {
          await chrome.runtime.sendMessage({
            type: 'SCAN_TIMEOUT',
            data: {
              url: url,
              message: 'Processing is taking longer than expected.',
              canRetry: true
            }
          });
        } catch (notifyError) {
          console.log('Popup not available for timeout notification');
        }
        
        return;
      }
      
      console.error('API request failed:', apiError);
      
      console.log('Using fallback data');
      const mockResponse = {
        success: true,
        matches: generateMockData(url, settings.resumeData, pageContent),
        message: settings.resumeData ? 
          'Found job matches using local resume data (API unavailable)' : 
          'Found job matches (API unavailable)',
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
      
      await chrome.storage.local.set({
        lastScanResults: {
          url: url,
          timestamp: Date.now(),
          results: mockResponse,
          settings: settings
        }
      });
      
      try {
        await chrome.runtime.sendMessage({
          type: 'SCAN_COMPLETE',
          data: mockResponse
        });
      } catch (notifyError) {
        console.log('Popup not available for results');
      }
    }
    
  } catch (error) {
    console.error('Error scanning page:', error);
    
    const errorResponse = {
      success: false,
      error: error.message,
      matches: [],
      message: 'Failed to scan page',
      processing_method: 'error'
    };
    
    await chrome.storage.local.set({
      lastScanResults: {
        url: data.url,
        timestamp: Date.now(),
        results: errorResponse,
        error: error.message
      }
    });
    
    try {
      await chrome.runtime.sendMessage({
        type: 'SCAN_ERROR',
        data: errorResponse
      });
    } catch (notifyError) {
      console.log('Popup not available for error notification');
    }
  }
}

function generateResumeText(resumeData) {
  if (!resumeData) return null;
  
  let text = '';
  
  if (resumeData.personal_info) {
    if (resumeData.personal_info.name) text += `Name: ${resumeData.personal_info.name}\n`;
    if (resumeData.personal_info.email) text += `Email: ${resumeData.personal_info.email}\n`;
    if (resumeData.personal_info.phone) text += `Phone: ${resumeData.personal_info.phone}\n`;
  }
  
  if (resumeData.summary) {
    text += `\nSummary: ${resumeData.summary}\n`;
  }
  
  if (resumeData.skills && resumeData.skills.length > 0) {
    text += `\nSkills: ${resumeData.skills.join(', ')}\n`;
  }
  
  if (resumeData.experience && resumeData.experience.length > 0) {
    text += '\nExperience:\n';
    resumeData.experience.forEach(exp => {
      text += `- ${exp.title} at ${exp.company} (${exp.duration})\n`;
      if (exp.description) text += `  ${exp.description}\n`;
      if (exp.technologies) text += `  Technologies: ${exp.technologies.join(', ')}\n`;
    });
  }
  
  if (resumeData.education && resumeData.education.length > 0) {
    text += '\nEducation:\n';
    resumeData.education.forEach(edu => {
      text += `- ${edu.degree} in ${edu.field} from ${edu.institution} (${edu.year})\n`;
    });
  }
  
  return text;
}

function generateMockData(url, resumeData, pageContent) {
  
  const baseJobs = [];
  
  if (pageContent && pageContent.jobElements && pageContent.jobElements.length > 0) {
    pageContent.jobElements.slice(0, 8).forEach((jobElement, index) => {
      const job = {
        id: jobElement.id || `real-${index}`,
        title: jobElement.title || jobElement.text?.split('\n')[0]?.trim() || 'Software Position',
        company: jobElement.company || extractCompanyFromUrl(url),
        location: jobElement.location || 'Various Locations',
        url: jobElement.url || url,
        summary: 'Job from page'
      };
      
      baseJobs.push(job);
    });
  }
  
  else if (pageContent && pageContent.jobLinks && pageContent.jobLinks.length > 0) {
    pageContent.jobLinks.slice(0, 6).forEach((jobLink, index) => {
      const job = {
        id: jobLink.id || `link-${index}`,
        title: jobLink.title || jobLink.text || 'Position Available',
        company: jobLink.company || extractCompanyFromUrl(url),
        location: jobLink.location || 'Location TBD',
        url: jobLink.url || url,
        summary: 'Job link from page'
      };
      
      baseJobs.push(job);
    });
  }
  
  if (baseJobs.length === 0) {
    
    baseJobs.push(
      {
        id: 1,
        title: 'Senior Software Engineer',
        company: extractCompanyFromUrl(url),
        location: 'San Francisco, CA',
        url: url,
        summary: 'Good match for your background'
      },
      {
        id: 2,
        title: 'Full Stack Developer',
        company: extractCompanyFromUrl(url),
        location: 'Remote',
        url: url,
        summary: 'Matches your skills'
      },
      {
        id: 3,
        title: 'Software Engineer',
        company: extractCompanyFromUrl(url),
        location: 'New York, NY',
        url: url,
        summary: 'Growing team opportunity'
      }
    );
  }
  
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
    
    baseJobs.forEach((job, index) => {
      let baseScore = 70 + (index * -5);
      
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
        'Strong match for React experience' :
        hasPythonExperience && job.title.toLowerCase().includes('python') ?
        'Good fit for Python skills' :
        'Potential match for your background';
    });
  } else {
    baseJobs.forEach((job, index) => {
      job.match_score = 75 - (index * 3);
      job.matching_skills = ['JavaScript', 'HTML', 'CSS'].slice(0, 2);
      job.missing_skills = ['React', 'TypeScript'];
      job.summary = 'Upload resume for better matching';
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

// Auto-scanning feature removed - extension only works when manually clicked

// Check backend health
async function checkBackendHealth(sendResponse) {
  try {
    const apiEndpoint = 'https://jobmatch-production.up.railway.app/api/v1';
    
    const response = await fetch(`${apiEndpoint.replace('/api/v1', '')}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });
    
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    
    const result = await response.json();
    sendResponse({
      success: true,
      health: result,
      endpoint: apiEndpoint
    });
    
  } catch (error) {
    sendResponse({
      success: false,
      error: error.message,
      endpoint: 'https://jobmatch-production.up.railway.app/api/v1'
    });
  }
} 