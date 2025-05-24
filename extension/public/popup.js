// Popup script for Bulk-Scanner Resume Matcher Chrome Extension

console.log('Popup script loaded');

document.addEventListener('DOMContentLoaded', function() {
    const scanButton = document.getElementById('scanButton');
    const settingsButton = document.getElementById('settingsButton');
    const helpButton = document.getElementById('helpButton');
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    
    // Initialize popup
    initializePopup();
    
    // Event listeners
    scanButton.addEventListener('click', handleScanPage);
    settingsButton.addEventListener('click', openSettings);
    helpButton.addEventListener('click', showHelp);
    
    async function initializePopup() {
        try {
            // Get current tab info
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Check if we're on a valid page
            if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
                showStatus('Cannot scan Chrome internal pages', 'error');
                scanButton.disabled = true;
                return;
            }
            
            // Check settings
            const settings = await chrome.storage.sync.get(['apiEndpoint', 'resumeData']);
            
            // Update UI based on available data
            if (settings.resumeData) {
                showStatus('Resume loaded - Enhanced matching available', 'success');
            } else {
                showStatus('No resume uploaded - Basic matching only', 'loading');
            }
            
        } catch (error) {
            console.error('Error initializing popup:', error);
            showStatus('Initialization error', 'error');
        }
    }
    
    async function handleScanPage() {
        try {
            scanButton.disabled = true;
            showStatus('Scanning page for jobs...', 'loading');
            results.classList.add('hidden');
            
            // Get current tab
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            // Check if content script is loaded by sending a ping
            let contentScriptReady = false;
            try {
                const pingResponse = await chrome.tabs.sendMessage(tab.id, { type: 'PING' });
                contentScriptReady = pingResponse && pingResponse.status === 'ready';
            } catch (error) {
                console.log('Content script not ready, injecting...');
            }
            
            // If content script not ready, inject it
            if (!contentScriptReady) {
                try {
                    await chrome.scripting.executeScript({
                        target: { tabId: tab.id },
                        files: ['content.js']
                    });
                    
                    // Wait a moment for the script to initialize
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (error) {
                    console.error('Failed to inject content script:', error);
                    throw new Error('Could not inject content script');
                }
            }
            
            // Send message to content script to extract page content
            const pageContent = await new Promise((resolve, reject) => {
                chrome.tabs.sendMessage(tab.id, { type: 'EXTRACT_CONTENT' }, (response) => {
                    if (chrome.runtime.lastError) {
                        reject(new Error(chrome.runtime.lastError.message));
                    } else if (response && response.error) {
                        reject(new Error(response.error));
                    } else if (response) {
                        resolve(response);
                    } else {
                        reject(new Error('No response from content script'));
                    }
                });
            });
            
            console.log('Page content extracted:', pageContent);
            
            // Send scan request to background script
            const response = await new Promise((resolve, reject) => {
                chrome.runtime.sendMessage({
                    type: 'SCAN_PAGE',
                    data: {
                        url: tab.url,
                        pageContent: pageContent
                    }
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        reject(new Error(chrome.runtime.lastError.message));
                    } else {
                        resolve(response);
                    }
                });
            });
            
            console.log('Scan response:', response);
            
            if (response.success) {
                displayResults(response);
            } else {
                throw new Error(response.error || 'Scan failed');
            }
            
        } catch (error) {
            console.error('Scan error:', error);
            showStatus(`Scan failed: ${error.message}`, 'error');
        } finally {
            scanButton.disabled = false;
        }
    }
    
    function displayResults(response) {
        const { matches, jobs_found, processing_method, resume_used, api_features } = response;
        
        // Update status
        let statusText = `Found ${jobs_found} jobs`;
        if (resume_used) {
            statusText += ' (Enhanced with your resume)';
        }
        if (api_features?.llm_matching) {
            statusText += ' - AI Powered';
        }
        
        showStatus(statusText, 'success');
        
        // Display job matches
        if (matches && matches.length > 0) {
            results.innerHTML = '';
            
            matches.forEach(job => {
                const jobElement = createJobElement(job);
                results.appendChild(jobElement);
            });
            
            results.classList.remove('hidden');
        } else {
            results.innerHTML = '<div class="job-item">No matching jobs found on this page</div>';
            results.classList.remove('hidden');
        }
    }
    
    function createJobElement(job) {
        const jobDiv = document.createElement('div');
        jobDiv.className = 'job-item';
        
        const matchScore = job.match_score || 0;
        const matchColor = matchScore >= 80 ? '#10b981' : matchScore >= 60 ? '#f59e0b' : '#ef4444';
        
        jobDiv.innerHTML = `
            <div class="job-title">${job.title || 'Job Title'}</div>
            <div class="job-company">${job.company || 'Company'} • ${job.location || 'Location'}</div>
            <div style="margin-top: 8px;">
                <span class="match-score" style="background-color: ${matchColor}">
                    ${matchScore}% match
                </span>
            </div>
            ${job.matching_skills && job.matching_skills.length > 0 ? `
                <div style="margin-top: 8px; font-size: 11px; opacity: 0.8;">
                    Skills: ${job.matching_skills.slice(0, 3).join(', ')}
                </div>
            ` : ''}
            ${job.summary ? `
                <div style="margin-top: 6px; font-size: 11px; opacity: 0.9;">
                    ${job.summary}
                </div>
            ` : ''}
        `;
        
        // Add click handler to open job URL
        if (job.url) {
            jobDiv.style.cursor = 'pointer';
            jobDiv.addEventListener('click', () => {
                chrome.tabs.create({ url: job.url });
            });
        }
        
        return jobDiv;
    }
    
    function showStatus(message, type = 'loading') {
        status.textContent = message;
        status.className = `status ${type}`;
        status.classList.remove('hidden');
    }
    
    function openSettings() {
        chrome.runtime.openOptionsPage();
    }
    
    function showHelp() {
        const helpText = `
📖 How to use Resume Matcher:

1️⃣ Upload Resume (Optional):
   • Click Settings → Upload resume file
   • Get enhanced AI-powered matching

2️⃣ Scan Job Pages:
   • Visit any career page
   • Click "Scan Current Page"
   • View matched jobs with scores

3️⃣ Best Results:
   • Use on company career pages
   • Works with LinkedIn, Indeed, etc.
   • Higher scores = better matches

💡 Tips:
   • Upload resume for better matching
   • Check Settings for API connection
   • Scan multiple pages for more jobs
        `;
        
        alert(helpText);
    }
});

// No longer needed - using content script messaging instead of function injection 