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
            
            // 🚀 ENHANCED: Check for stored results from previous scans more aggressively
            const storedResults = await chrome.storage.local.get(['lastScanResults', 'lastScanStatus']);
            
            // Check for completed results (even if not exactly same URL)
            if (storedResults.lastScanResults && 
                storedResults.lastScanResults.url === tab.url && 
                Date.now() - storedResults.lastScanResults.timestamp < 600000) { // 10 minutes
                
                console.log('Found recent scan results for this page:', storedResults.lastScanResults);
                
                // Display the stored results
                const results = storedResults.lastScanResults.results;
                if (results.success && results.matches) {
                    displayResults(results);
                    const timeAgo = Math.round((Date.now() - storedResults.lastScanResults.timestamp) / 1000);
                    showStatus(`✅ Scan completed ${timeAgo}s ago - ${results.matches.length} matches found!`, 'success');
                    return;
                }
            }
            
            // 🚀 NEW: Also check for very recent results (within 2 minutes) even with different URLs
            if (storedResults.lastScanResults && 
                Date.now() - storedResults.lastScanResults.timestamp < 120000) { // 2 minutes
                
                const results = storedResults.lastScanResults.results;
                if (results.success && results.matches && results.matches.length > 0) {
                    console.log('Found very recent scan results (different URL):', storedResults.lastScanResults);
                    
                    displayResults(results);
                    const timeAgo = Math.round((Date.now() - storedResults.lastScanResults.timestamp) / 1000);
                    showStatus(`✅ Recent scan completed ${timeAgo}s ago - ${results.matches.length} matches found! (Different page)`, 'success');
                    
                    // Add a button to start fresh scan
                    const freshScanButton = document.createElement('button');
                    freshScanButton.textContent = 'Scan Current Page Instead';
                    freshScanButton.className = 'secondary-button';
                    freshScanButton.onclick = () => {
                        chrome.storage.local.remove(['lastScanResults', 'lastScanStatus']);
                        location.reload();
                    };
                    status.parentNode.insertBefore(freshScanButton, status.nextSibling);
                    
                    return;
                }
            }
            
            // Check if there's a timeout status for this page
            if (storedResults.lastScanStatus && 
                storedResults.lastScanStatus.url === tab.url && 
                storedResults.lastScanStatus.status === 'timeout' &&
                Date.now() - storedResults.lastScanStatus.timestamp < 300000) { // 5 minutes
                
                showStatus('Previous scan timed out. Backend may still be processing. Try again or check backend logs.', 'loading');
                
                // Add button to check for results
                const checkButton = document.createElement('button');
                checkButton.textContent = 'Check for Results';
                checkButton.onclick = () => checkForStoredResults();
                status.parentNode.insertBefore(checkButton, status.nextSibling);
                
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
                        files: ['content.js']  // Use the enhanced content script with Amazon SPA support
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
            
            // 🚀 ENHANCED: Set up listener for background messages
            const messageListener = (message, sender, sendResponse) => {
                console.log('🔍 DEBUG: Popup received message:', message);
                
                if (message.type === 'SCAN_COMPLETE') {
                    console.log('✅ Received scan complete notification:', message.data);
                    displayResults(message.data);
                    scanButton.disabled = false;
                    chrome.runtime.onMessage.removeListener(messageListener);
                } else if (message.type === 'SCAN_TIMEOUT') {
                    console.log('⏰ Received scan timeout notification:', message.data);
                    showStatus('Processing is taking longer than expected. Check backend logs for progress...', 'loading');
                    
                    // Show timeout UI with option to check results
                    setTimeout(() => {
                        showTimeoutUI(message.data);
                    }, 2000);
                    
                } else if (message.type === 'SCAN_ERROR') {
                    console.log('❌ Received scan error notification:', message.data);
                    showStatus(`Scan failed: ${message.data.message}`, 'error');
                    scanButton.disabled = false;
                    chrome.runtime.onMessage.removeListener(messageListener);
                } else {
                    console.log('🔍 DEBUG: Unknown message type:', message.type);
                }
            };
            
            chrome.runtime.onMessage.addListener(messageListener);
            
            // 🚀 ENHANCED: Check for pending results with better error handling
            const checkPendingResults = async (attempt = 1, maxAttempts = 30) => {
                console.log(`🔍 DEBUG: Checking for pending results (attempt ${attempt}/${maxAttempts})`);
                
                try {
                    const { pendingResults, resultsTimestamp } = await chrome.storage.local.get(['pendingResults', 'resultsTimestamp']);
                    
                    if (pendingResults && resultsTimestamp) {
                        const resultAge = Date.now() - resultsTimestamp;
                        console.log(`✅ Found pending results (${Math.round(resultAge/1000)}s old):`, pendingResults);
                        
                        // Display results and stop polling
                        displayResults(pendingResults);
                        scanButton.disabled = false;
                        
                        // Clear the stored results
                        await chrome.storage.local.remove(['pendingResults', 'resultsTimestamp']);
                        return;
                    }
                    
                    if (attempt < maxAttempts) {
                        // Continue polling with longer intervals
                        const delay = Math.min(1000 + (attempt * 100), 3000); // Progressive delay up to 3s
                        setTimeout(() => checkPendingResults(attempt + 1, maxAttempts), delay);
                    } else {
                        console.log('⏰ Polling timed out, no results found');
                        showStatus('Processing is taking longer than expected. Please try refreshing or contact support.', 'error');
                        scanButton.disabled = false;
                    }
                } catch (error) {
                    console.error('❌ Error checking pending results:', error);
                    if (attempt < maxAttempts) {
                        setTimeout(() => checkPendingResults(attempt + 1, maxAttempts), 2000);
                    }
                }
            };
            
            // Clean up result checker when page is unloaded
            window.addEventListener('beforeunload', () => {
                clearInterval(resultChecker);
            });
            
            // 🚀 ENHANCED: Send scan request with immediate response handling
            const initialResponse = await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('Extension communication timeout'));
                }, 10000); // 10 second timeout for initial response
                
                chrome.runtime.sendMessage({
                    type: 'SCAN_PAGE',
                    data: {
                        url: tab.url,
                        pageContent: pageContent
                    }
                }, (response) => {
                    clearTimeout(timeout);
                    if (chrome.runtime.lastError) {
                        reject(new Error(chrome.runtime.lastError.message));
                    } else {
                        resolve(response);
                    }
                });
            });
            
            console.log('Initial scan response:', initialResponse);
            
            // Handle initial acknowledgment
            if (initialResponse && initialResponse.status === 'processing') {
                showStatus(initialResponse.message, 'loading');
                
                // Show progress info
                const jobCount = pageContent.jobElements?.length || pageContent.jobLinks?.length || 0;
                if (jobCount > 10) {
                    showProgressInfo(jobCount);
                }
                
                // 🚀 NEW: Add immediate result check for fast completions
                setTimeout(async () => {
                    console.log('🔍 DEBUG: Quick check for immediate results...');
                    try {
                        const { pendingResults } = await chrome.storage.local.get(['pendingResults']);
                        
                        if (pendingResults && pendingResults.timestamp > Date.now() - (5 * 60 * 1000)) { // Within last 5 minutes
                            console.log('✅ Found immediate results!');
                            displayResults(pendingResults.data);
                            scanButton.disabled = false;
                            chrome.runtime.onMessage.removeListener(messageListener);
                            
                            // Clear the pending results
                            chrome.storage.local.remove(['pendingResults']);
                            return;
                        }
                    } catch (error) {
                        console.error('Error in immediate result check:', error);
                    }
                }, 5000); // Check after 5 seconds
                
                // Don't re-enable button yet - wait for completion message
                return;
            }
            
            // Handle immediate completion (for small job sets)
            if (initialResponse && initialResponse.success && initialResponse.matches) {
                displayResults(initialResponse);
                chrome.runtime.onMessage.removeListener(messageListener);
            } else if (initialResponse && !initialResponse.success) {
                throw new Error(initialResponse.error || 'Scan failed');
            }
            
        } catch (error) {
            console.error('Scan error:', error);
            showStatus(`Scan failed: ${error.message}`, 'error');
        } finally {
            // Only re-enable if not waiting for background processing
            if (!status.textContent.includes('Processing') && !status.textContent.includes('longer than expected')) {
                scanButton.disabled = false;
            }
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
    
    // 🚀 NEW: Show progress information for large job batches
    function showProgressInfo(jobCount) {
        const progressDiv = document.createElement('div');
        progressDiv.id = 'progress-info';
        progressDiv.style.cssText = `
            margin-top: 10px;
            padding: 8px;
            background-color: #f3f4f6;
            border-radius: 4px;
            font-size: 12px;
            color: #6b7280;
        `;
        
        progressDiv.innerHTML = `
            <div style="margin-bottom: 4px;">📊 Processing ${jobCount} jobs with enhanced AI analysis</div>
            <div style="margin-bottom: 4px;">⏱️ This may take 1-2 minutes for full content extraction</div>
            <div style="font-size: 11px; opacity: 0.8;">💡 Backend is fetching full job descriptions from individual pages</div>
        `;
        
        // Insert after status
        status.parentNode.insertBefore(progressDiv, status.nextSibling);
        
        // Auto-remove after 30 seconds
        setTimeout(() => {
            if (progressDiv.parentNode) {
                progressDiv.remove();
            }
        }, 30000);
    }
    
    // 🚀 NEW: Show timeout UI with options
    function showTimeoutUI(timeoutData) {
        const timeoutDiv = document.createElement('div');
        timeoutDiv.style.cssText = `
            margin-top: 10px;
            padding: 10px;
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            font-size: 12px;
        `;
        
        timeoutDiv.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 6px;">⏰ Processing Timeout</div>
            <div style="margin-bottom: 8px;">${timeoutData.message}</div>
            <div style="display: flex; gap: 8px;">
                <button id="check-results-btn" style="font-size: 11px; padding: 4px 8px;">Check for Results</button>
                <button id="retry-scan-btn" style="font-size: 11px; padding: 4px 8px;">Retry Scan</button>
            </div>
        `;
        
        // Clear previous content and show timeout UI
        results.innerHTML = '';
        results.appendChild(timeoutDiv);
        results.classList.remove('hidden');
        
        // Add event listeners
        timeoutDiv.querySelector('#check-results-btn').addEventListener('click', checkForStoredResults);
        timeoutDiv.querySelector('#retry-scan-btn').addEventListener('click', () => {
            timeoutDiv.remove();
            handleScanPage();
        });
        
        scanButton.disabled = false;
    }
    
    // 🚀 NEW: Check for stored results from background processing
    async function checkForStoredResults() {
        try {
            showStatus('Checking for completed results...', 'loading');
            
            const storedResults = await chrome.storage.local.get(['lastScanResults', 'lastScanStatus']);
            
            if (storedResults.lastScanResults) {
                const results = storedResults.lastScanResults.results;
                const timeAgo = Math.round((Date.now() - storedResults.lastScanResults.timestamp) / 1000);
                
                // 🚀 ENHANCED: Even show mock results if they exist, but indicate they are fallback
                if (results.success && results.matches) {
                    console.log('✅ Found completed results!', results);
                    
                    // Check if these are mock results and warn user
                    if (results.processing_method === 'mock') {
                        console.warn('⚠️ These are mock/fallback results. Backend processing may have failed.');
                        displayResults(results);
                        showStatus(`⚠️ Found fallback results (${timeAgo}s ago) - Backend may have timed out. Try scanning again.`, 'loading');
                        
                        // Add button to try again
                        const retryButton = document.createElement('button');
                        retryButton.textContent = 'Scan Again with Backend';
                        retryButton.style.cssText = 'margin-top: 8px; padding: 6px 12px; font-size: 12px;';
                        retryButton.onclick = () => {
                            // Clear mock results and rescan
                            chrome.storage.local.remove(['lastScanResults', 'lastScanStatus']);
                            handleScanPage();
                        };
                        status.parentNode.insertBefore(retryButton, status.nextSibling);
                        
                    } else {
                        // Real backend results
                        displayResults(results);
                        showStatus(`✅ Found completed scan results (${timeAgo}s ago) - ${results.matches.length} matches!`, 'success');
                    }
                    
                    scanButton.disabled = false;
                    return;
                }
            }
            
            showStatus('No completed results found. The backend may still be processing.', 'loading');
            
        } catch (error) {
            console.error('Error checking stored results:', error);
            showStatus('Error checking for results', 'error');
        }
    }
});

// No longer needed - using content script messaging instead of function injection 