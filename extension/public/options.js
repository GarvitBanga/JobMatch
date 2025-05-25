// Enhanced Options page with Career Insights for Bulk-Scanner Chrome Extension

document.addEventListener('DOMContentLoaded', function() {
    loadSettings();
    setupEventListeners();
});
    
function setupEventListeners() {
    // Settings form submission
    document.getElementById('settingsForm').addEventListener('submit', saveSettings);
    
    // Reset button
    document.getElementById('resetBtn').addEventListener('click', resetSettings);
    
    // Test connection button
    document.getElementById('testConnectionBtn').addEventListener('click', testConnection);
    
    // Resume file upload
    document.getElementById('resumeFile').addEventListener('change', handleResumeUpload);
}

async function loadSettings() {
    try {
        const settings = await chrome.storage.sync.get([
            'apiEndpoint',
            'matchThreshold', 
            'autoScan', 
            'resumeData',
            'resumeFileName',
            'resumeUploadDate',
            'resumeProcessingMethod'
        ]);
        
        // Populate form fields
        document.getElementById('apiEndpoint').value = settings.apiEndpoint || 'https://jobmatch-production.up.railway.app/api/v1';
        document.getElementById('matchThreshold').value = settings.matchThreshold || 70;
        document.getElementById('autoScan').checked = settings.autoScan || false;
        
        // Show resume info and insights if available
        if (settings.resumeData) {
            showResumeInfo(settings.resumeFileName, settings.resumeUploadDate, settings.resumeProcessingMethod);
            
            // Show career insights if available
            if (settings.resumeData.career_insights) {
                showCareerInsights(settings.resumeData.career_insights);
            }
        }
        
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
            matchThreshold: parseInt(document.getElementById('matchThreshold').value),
            autoScan: document.getElementById('autoScan').checked
        };
        
        await chrome.storage.sync.set(settings);
        showStatus('Settings saved successfully!', 'success');
        
    } catch (error) {
        console.error('Error saving settings:', error);
        showStatus('Error saving settings', 'error');
    }
}

async function resetSettings() {
    try {
        await chrome.storage.sync.clear();
        
        // Reset form to defaults
        document.getElementById('apiEndpoint').value = 'https://jobmatch-production.up.railway.app/api/v1';
        document.getElementById('matchThreshold').value = 70;
        document.getElementById('autoScan').checked = false;
        document.getElementById('resumeFile').value = '';
        
        // Hide resume info and insights
        hideResumeInfo();
        hideCareerInsights();
        
        showStatus('Settings reset to defaults', 'success');
        
    } catch (error) {
        console.error('Error resetting settings:', error);
        showStatus('Error resetting settings', 'error');
    }
}

async function testConnection() {
    try {
        const settings = await chrome.storage.sync.get(['apiEndpoint']);
        const apiEndpoint = settings.apiEndpoint || 'https://jobmatch-production.up.railway.app/api/v1';
        
        showStatus('Testing connection...', 'info');
        
        // Remove /api/v1 from endpoint for health check
        const baseUrl = apiEndpoint.replace('/api/v1', '');
        const response = await fetch(`${baseUrl}/health`);
        
        if (response.ok) {
            const data = await response.json();
            showStatus(
                `✅ Connection successful! Features: Resume Processing: ${data.features.resume_processing}, LLM Matching: ${data.features.llm_matching}`, 
                'success'
            );
        } else {
            showStatus(`❌ Connection failed: ${response.status}`, 'error');
        }
        
    } catch (error) {
        console.error('Connection test failed:', error);
        showStatus(`❌ Connection failed: ${error.message}`, 'error');
    }
}

async function handleResumeUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    try {
        showStatus('Processing resume with AI insights...', 'info');
        
        // Validate file type
        const allowedTypes = ['.pdf', '.doc', '.docx', '.txt'];
        const fileExt = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!allowedTypes.includes(fileExt)) {
            throw new Error(`Unsupported file type. Allowed: ${allowedTypes.join(', ')}`);
        }
        
        // Get API endpoint
        const settings = await chrome.storage.sync.get(['apiEndpoint']);
        const apiEndpoint = settings.apiEndpoint || 'https://jobmatch-production.up.railway.app/api/v1';
        
        // Create FormData for file upload
        const formData = new FormData();
        formData.append('file', file);
        formData.append('user_id', 'chrome-extension-user');
        
        // Upload to backend for processing
        const response = await fetch(`${apiEndpoint}/upload/resume`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            // Store enhanced resume data in Chrome storage
            await chrome.storage.sync.set({
                resumeData: result.structured_data,
                resumeFileName: file.name,
                resumeUploadDate: new Date().toISOString(),
                resumeProcessingMethod: result.processing_method
            });
            
            showResumeInfo(file.name, new Date().toISOString(), result.processing_method);
            
            const insightsMessage = result.insights_generated ? 
                'with AI career insights' : 'without insights (no OpenAI key)';
            
            showStatus(
                `✅ Resume processed successfully using ${result.processing_method} method ${insightsMessage}!`, 
                'success'
            );
            
            // Show structured data preview
            showResumePreview(result.structured_data);
            
            // Show career insights if generated
            if (result.structured_data.career_insights) {
                showCareerInsights(result.structured_data.career_insights);
            }
            
        } else {
            throw new Error(result.error || 'Resume processing failed');
        }
        
    } catch (error) {
        console.error('Resume upload failed:', error);
        showStatus(`❌ Resume upload failed: ${error.message}`, 'error');
    }
}

function showResumeInfo(fileName, uploadDate, processingMethod) {
    const container = document.querySelector('.form-group:has(#resumeFile)');
    
    // Remove existing info if present
    const existingInfo = container.querySelector('.resume-info');
    if (existingInfo) {
        existingInfo.remove();
    }
    
    // Create resume info display
    const resumeInfo = document.createElement('div');
    resumeInfo.className = 'resume-info';
    resumeInfo.style.cssText = `
        margin-top: 10px;
        padding: 10px;
        background-color: #f0f9ff;
        border: 1px solid #bae6fd;
        border-radius: 6px;
        font-size: 14px;
    `;
    
    const uploadDateFormatted = new Date(uploadDate).toLocaleDateString();
    const methodBadge = processingMethod === 'llm_enhanced' ? 
        '<span style="background: #10b981; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">AI Enhanced</span>' :
        '<span style="background: #6b7280; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Basic</span>';
    
    resumeInfo.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong>📄 Current Resume:</strong> ${fileName} ${methodBadge}<br>
                <small style="color: #6b7280;">Uploaded: ${uploadDateFormatted}</small>
            </div>
            <button type="button" id="removeResumeBtn" style="
                background: #ef4444; 
                color: white; 
                border: none; 
                padding: 4px 8px; 
                border-radius: 4px; 
                font-size: 12px;
                cursor: pointer;
                margin-left: 10px;
            ">Remove</button>
        </div>
    `;
    
    container.appendChild(resumeInfo);
    
    // Add remove functionality
    document.getElementById('removeResumeBtn').addEventListener('click', removeResume);
}

function showCareerInsights(insights) {
    // Remove existing insights
    hideCareerInsights();
    
    const container = document.querySelector('.container');
    
    const insightsContainer = document.createElement('div');
    insightsContainer.id = 'careerInsights';
    insightsContainer.style.cssText = `
        margin-top: 30px;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 12px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    `;
    
    // Career Level
    const careerLevel = insights.career_level || {};
    const currentLevel = careerLevel.current_level || 'Unknown';
    const experience = careerLevel.years_experience || 'Unknown';
    
    // Recommended Profiles
    const profiles = insights.recommended_job_profiles || [];
    const profilesHTML = profiles.slice(0, 3).map(profile => `
        <div style="background: rgba(255,255,255,0.15); padding: 12px; border-radius: 8px; margin: 8px 0;">
            <strong>${profile.title}</strong> 
            <span style="background: rgba(16,185,129,0.8); padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 8px;">
                ${profile.match_percentage}% match
            </span>
            <br>
            <small style="opacity: 0.9;">${profile.reasoning}</small>
        </div>
    `).join('');
    
    // Skill Analysis
    const skillAnalysis = insights.skill_analysis || {};
    const strongSkills = skillAnalysis.strong_skills || [];
    const recommendedSkills = skillAnalysis.recommended_skills || [];
    
    const recommendedSkillsHTML = recommendedSkills.slice(0, 4).map(skill => `
        <div style="background: rgba(255,255,255,0.15); padding: 8px 12px; border-radius: 6px; margin: 4px; display: inline-block;">
            <strong>${skill.skill || skill}</strong>
            ${skill.priority ? `<span style="font-size: 11px; opacity: 0.8;"> (${skill.priority} priority)</span>` : ''}
        </div>
    `).join('');
    
    // Industry Recommendations
    const industries = insights.industry_recommendations || [];
    const industryHTML = industries.slice(0, 2).map(industry => `
        <span style="background: rgba(255,255,255,0.2); padding: 4px 8px; border-radius: 4px; margin: 4px; display: inline-block; font-size: 13px;">
            ${industry.industry} (${industry.fit_score}% fit)
        </span>
    `).join('');
    
    // Salary Insights
    const salaryInsights = insights.salary_insights || {};
    const estimatedRange = salaryInsights.estimated_range || 'Not available';
    
    insightsContainer.innerHTML = `
        <h2 style="margin-top: 0; display: flex; align-items: center; gap: 10px;">
            🧠 AI Career Insights
            <button type="button" id="hideInsightsBtn" style="
                background: rgba(255,255,255,0.2);
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                cursor: pointer;
                margin-left: auto;
            ">Hide</button>
        </h2>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            <div>
                <h3 style="margin: 0 0 10px 0; color: #fbbf24;">📊 Career Profile</h3>
                <p><strong>Level:</strong> ${currentLevel}</p>
                <p><strong>Experience:</strong> ${experience} years</p>
                <p><strong>Salary Range:</strong> ${estimatedRange}</p>
            </div>
            
            <div>
                <h3 style="margin: 0 0 10px 0; color: #34d399;">💪 Your Strengths</h3>
                <p>${strongSkills.slice(0, 5).join(', ') || 'Analysis in progress'}</p>
                
                <h3 style="margin: 15px 0 10px 0; color: #fbbf24;">🏭 Top Industries</h3>
                <div>${industryHTML || 'Analyzing market fit...'}</div>
            </div>
        </div>
        
        <div style="margin-top: 20px;">
            <h3 style="margin: 0 0 10px 0; color: #60a5fa;">🎯 Recommended Job Profiles</h3>
            ${profilesHTML || '<p>Generating personalized job recommendations...</p>'}
        </div>
        
        <div style="margin-top: 20px;">
            <h3 style="margin: 0 0 10px 0; color: #f87171;">📈 Skills to Learn</h3>
            <div style="margin-top: 10px;">
                ${recommendedSkillsHTML || '<p>Analyzing skill gaps...</p>'}
            </div>
        </div>
        
        <div style="margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 13px;">
            💡 <strong>Pro Tip:</strong> These insights are generated by AI analysis of your resume and current market trends. 
            Use them to optimize your job search and identify growth opportunities!
        </div>
    `;
    
    container.appendChild(insightsContainer);
    
    // Add hide functionality
    document.getElementById('hideInsightsBtn').addEventListener('click', hideCareerInsights);
}

function hideCareerInsights() {
    const insights = document.getElementById('careerInsights');
    if (insights) {
        insights.remove();
    }
}

function hideResumeInfo() {
    const resumeInfo = document.querySelector('.resume-info');
    if (resumeInfo) {
        resumeInfo.remove();
    }
    hideCareerInsights();
}

async function removeResume() {
    try {
        await chrome.storage.sync.remove([
            'resumeData', 
            'resumeFileName', 
            'resumeUploadDate',
            'resumeProcessingMethod'
        ]);
        
        hideResumeInfo();
        document.getElementById('resumeFile').value = '';
        showStatus('Resume and career insights removed successfully', 'success');
        
    } catch (error) {
        console.error('Error removing resume:', error);
        showStatus('Error removing resume', 'error');
    }
}

function showResumePreview(resumeData) {
    // Create a modal or expandable section to show parsed resume data
    const container = document.querySelector('.container');
    
    // Remove existing preview
    const existingPreview = document.getElementById('resumePreview');
    if (existingPreview) {
        existingPreview.remove();
    }
    
    const preview = document.createElement('div');
    preview.id = 'resumePreview';
    preview.style.cssText = `
        margin-top: 20px;
        padding: 20px;
        background-color: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        max-height: 300px;
        overflow-y: auto;
    `;
    
    const skillsText = resumeData.skills ? resumeData.skills.join(', ') : 'None detected';
    const experienceCount = resumeData.experience ? resumeData.experience.length : 0;
    const educationCount = resumeData.education ? resumeData.education.length : 0;
    
    // Check if career insights are available
    const hasInsights = resumeData.career_insights && Object.keys(resumeData.career_insights).length > 0;
    const insightsIndicator = hasInsights ? 
        '<span style="background: #10b981; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 10px;">AI Enhanced</span>' :
        '<span style="background: #6b7280; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 10px;">Basic Parse</span>';
    
    preview.innerHTML = `
        <h3 style="margin-top: 0; color: #374151;">
            📊 Resume Analysis Preview ${insightsIndicator}
        </h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; font-size: 14px;">
            <div>
                <strong>Personal Info:</strong><br>
                Name: ${resumeData.personal_info?.name || 'Not detected'}<br>
                Email: ${resumeData.personal_info?.email || 'Not detected'}<br>
                Phone: ${resumeData.personal_info?.phone || 'Not detected'}
            </div>
            <div>
                <strong>Summary:</strong><br>
                ${resumeData.summary || 'No summary detected'}
            </div>
            <div>
                <strong>Skills (${resumeData.skills?.length || 0}):</strong><br>
                ${skillsText}
            </div>
            <div>
                <strong>Experience:</strong><br>
                ${experienceCount} positions found<br>
                <strong>Education:</strong><br>
                ${educationCount} degrees found
            </div>
        </div>
        
        ${hasInsights ? `
            <div style="margin-top: 15px; padding: 10px; background: #ecfdf5; border: 1px solid #d1fae5; border-radius: 6px;">
                <strong style="color: #065f46;">🎯 AI Insights Available:</strong>
                <ul style="margin: 5px 0; padding-left: 20px; color: #047857;">
                    <li>${resumeData.career_insights.recommended_job_profiles?.length || 0} recommended job profiles</li>
                    <li>${resumeData.career_insights.skill_analysis?.recommended_skills?.length || 0} skill recommendations</li>
                    <li>${resumeData.career_insights.industry_recommendations?.length || 0} industry suggestions</li>
                </ul>
            </div>
        ` : `
            <div style="margin-top: 15px; padding: 10px; background: #fef3c7; border: 1px solid #fbbf24; border-radius: 6px;">
                <strong style="color: #92400e;">💡 Tip:</strong> Set up OpenAI API key in your backend to get AI-powered career insights!
            </div>
        `}
        
        <button type="button" id="closePreviewBtn" style="
            margin-top: 15px;
            background: #6b7280;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
        ">Close Preview</button>
    `;
    
    container.appendChild(preview);
    
    document.getElementById('closePreviewBtn').addEventListener('click', () => {
        preview.remove();
    });
}

function showStatus(message, type) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = `status ${type}`;
    status.style.display = 'block';
    
    // Add info type styling
    if (type === 'info') {
        status.style.backgroundColor = '#dbeafe';
        status.style.color = '#1e40af';
        status.style.border = '1px solid #93c5fd';
    }
    
    // Auto-hide after 5 seconds
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

console.log('Enhanced Options page with Career Insights loaded'); 