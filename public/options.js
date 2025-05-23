// Options page JavaScript for Bulk-Scanner Chrome Extension

document.addEventListener('DOMContentLoaded', function() {
    loadSettings();
    
    // Form submission
    document.getElementById('settingsForm').addEventListener('submit', saveSettings);
    
    // Reset button
    document.getElementById('resetBtn').addEventListener('click', resetSettings);
    
    // Test connection button
    document.getElementById('testConnectionBtn').addEventListener('click', testConnection);
    
    // Resume file upload
    document.getElementById('resumeFile').addEventListener('change', handleResumeUpload);
});

async function loadSettings() {
    try {
        const settings = await chrome.storage.sync.get([
            'apiEndpoint',
            'autoScan', 
            'matchThreshold',
            'resumeText'
        ]);
        
        document.getElementById('apiEndpoint').value = settings.apiEndpoint || 'http://localhost:8000/api/v1';
        document.getElementById('autoScan').checked = settings.autoScan || false;
        document.getElementById('matchThreshold').value = settings.matchThreshold || 70;
        
        console.log('Settings loaded:', settings);
    } catch (error) {
        console.error('Error loading settings:', error);
        showStatus('Error loading settings', 'error');
    }
}

async function saveSettings(event) {
    event.preventDefault();
    
    try {
        const settings = {
            apiEndpoint: document.getElementById('apiEndpoint').value,
            autoScan: document.getElementById('autoScan').checked,
            matchThreshold: parseInt(document.getElementById('matchThreshold').value)
        };
        
        await chrome.storage.sync.set(settings);
        
        console.log('Settings saved:', settings);
        showStatus('Settings saved successfully!', 'success');
        
        // Notify background script about settings change
        chrome.runtime.sendMessage({
            type: 'SETTINGS_UPDATED',
            data: settings
        });
        
    } catch (error) {
        console.error('Error saving settings:', error);
        showStatus('Error saving settings', 'error');
    }
}

async function resetSettings() {
    try {
        const defaultSettings = {
            apiEndpoint: 'http://localhost:8000/api/v1',
            autoScan: false,
            matchThreshold: 70
        };
        
        await chrome.storage.sync.set(defaultSettings);
        
        // Update form fields
        document.getElementById('apiEndpoint').value = defaultSettings.apiEndpoint;
        document.getElementById('autoScan').checked = defaultSettings.autoScan;
        document.getElementById('matchThreshold').value = defaultSettings.matchThreshold;
        document.getElementById('resumeFile').value = '';
        
        showStatus('Settings reset to defaults', 'success');
        
    } catch (error) {
        console.error('Error resetting settings:', error);
        showStatus('Error resetting settings', 'error');
    }
}

async function testConnection() {
    const apiEndpoint = document.getElementById('apiEndpoint').value;
    const testBtn = document.getElementById('testConnectionBtn');
    
    testBtn.textContent = 'Testing...';
    testBtn.disabled = true;
    
    try {
        const response = await fetch(`${apiEndpoint}/health`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            showStatus('✅ API connection successful!', 'success');
        } else {
            showStatus(`❌ API connection failed: ${response.status}`, 'error');
        }
    } catch (error) {
        console.error('Connection test failed:', error);
        showStatus(`❌ Connection failed: ${error.message}`, 'error');
    } finally {
        testBtn.textContent = 'Test API Connection';
        testBtn.disabled = false;
    }
}

async function handleResumeUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    try {
        const text = await extractTextFromFile(file);
        
        // Store resume text in extension storage
        await chrome.storage.sync.set({
            resumeText: text,
            resumeFileName: file.name,
            resumeUploadDate: new Date().toISOString()
        });
        
        showStatus(`Resume "${file.name}" uploaded successfully!`, 'success');
        
    } catch (error) {
        console.error('Error uploading resume:', error);
        showStatus('Error uploading resume', 'error');
    }
}

function extractTextFromFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            const content = e.target.result;
            
            if (file.type === 'text/plain') {
                resolve(content);
            } else if (file.type === 'application/pdf') {
                // For PDF files, we'd need a PDF parser library
                // For now, just show a message
                showStatus('PDF parsing not yet implemented. Please use a .txt file.', 'error');
                reject(new Error('PDF parsing not implemented'));
            } else if (file.type.includes('word')) {
                // For Word documents, we'd need a Word parser library
                showStatus('Word document parsing not yet implemented. Please use a .txt file.', 'error');
                reject(new Error('Word document parsing not implemented'));
            } else {
                reject(new Error('Unsupported file type'));
            }
        };
        
        reader.onerror = function() {
            reject(new Error('Error reading file'));
        };
        
        reader.readAsText(file);
    });
}

function showStatus(message, type) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = `status ${type}`;
    status.style.display = 'block';
    
    // Hide after 5 seconds
    setTimeout(() => {
        status.style.display = 'none';
    }, 5000);
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Options page received message:', message);
    
    switch (message.type) {
        case 'SETTINGS_REQUEST':
            loadSettings();
            break;
            
        default:
            console.log('Unknown message type:', message.type);
    }
});

console.log('Options page JavaScript loaded'); 