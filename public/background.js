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
      matchThreshold: 70
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
      chrome.storage.sync.get(['apiEndpoint', 'autoScan', 'matchThreshold'], sendResponse);
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
    
    // Get API endpoint from storage
    const settings = await chrome.storage.sync.get(['apiEndpoint']);
    const apiEndpoint = settings.apiEndpoint || 'http://localhost:8000/api/v1';
    
    console.log('Scanning page:', url);
    
    // TODO: Send request to backend API
    // For now, simulate API response
    setTimeout(() => {
      const mockResponse = {
        success: true,
        matches: [
          {
            id: 1,
            title: 'Senior Software Engineer',
            company: 'Tech Corp',
            matchScore: 92,
            location: 'San Francisco, CA',
            url: url,
            skills: ['React', 'TypeScript', 'Node.js'],
            summary: 'Excellent match for your React and TypeScript experience'
          },
          {
            id: 2,
            title: 'Full Stack Developer',
            company: 'Startup Inc',
            matchScore: 87,
            location: 'Remote',
            url: url,
            skills: ['JavaScript', 'Python', 'AWS'],
            summary: 'Good match for your full-stack development skills'
          }
        ]
      };
      
      sendResponse(mockResponse);
    }, 1000);
    
  } catch (error) {
    console.error('Error scanning page:', error);
    sendResponse({
      success: false,
      error: error.message
    });
  }
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