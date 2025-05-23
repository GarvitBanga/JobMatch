import React, { useState, useEffect } from 'react';
import './App.css';

interface Job {
  id: number;
  title: string;
  company: string;
  matchScore: number;
  location: string;
  url: string;
  skills?: string[];
  summary?: string;
}

function App() {
  const [isScanning, setIsScanning] = useState(false);
  const [matchedJobs, setMatchedJobs] = useState<Job[]>([]);
  const [currentUrl, setCurrentUrl] = useState<string>('');
  const [error, setError] = useState<string>('');

  useEffect(() => {
    // Get current tab URL when popup opens
    getCurrentTab();
  }, []);

  const getCurrentTab = async () => {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tabs[0]?.url) {
        setCurrentUrl(tabs[0].url);
      }
    } catch (error) {
      console.error('Error getting current tab:', error);
      setError('Unable to access current tab');
    }
  };

  const handleScanPage = async () => {
    setIsScanning(true);
    setError('');
    
    try {
      // Get current tab
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const currentTab = tabs[0];
      
      if (!currentTab?.url) {
        throw new Error('No active tab found');
      }

      // Inject content script if needed
      await chrome.scripting.executeScript({
        target: { tabId: currentTab.id! },
        files: ['content.js']
      });

      // Wait a moment for content script to load
      await new Promise(resolve => setTimeout(resolve, 500));

      // Send message to content script to extract page content
      const response = await chrome.tabs.sendMessage(currentTab.id!, {
        type: 'EXTRACT_CONTENT'
      });

      console.log('Extracted content:', response);

      // Send to background script for processing
      const matchResult = await chrome.runtime.sendMessage({
        type: 'SCAN_PAGE',
        data: {
          url: currentTab.url,
          pageContent: response
        }
      });

      if (matchResult.success) {
        setMatchedJobs(matchResult.matches || []);
      } else {
        throw new Error(matchResult.error || 'Failed to process page');
      }

    } catch (error) {
      console.error('Error scanning page:', error);
      setError(error instanceof Error ? error.message : 'Failed to scan page');
    } finally {
      setIsScanning(false);
    }
  };

  const openSettings = () => {
    chrome.runtime.openOptionsPage();
  };

  const openJob = (url: string) => {
    chrome.tabs.create({ url });
  };

  const isCareerPage = (url: string) => {
    const careerKeywords = ['career', 'job', 'employment', 'opening', 'position'];
    return careerKeywords.some(keyword => 
      url.toLowerCase().includes(keyword)
    );
  };

  return (
    <div className="w-96 h-96 bg-white relative overflow-hidden">
      {/* Header */}
      <div className="bg-blue-600 text-white p-4">
        <h1 className="text-lg font-bold">Résumé Matcher</h1>
        <p className="text-sm opacity-90">Find matching jobs instantly</p>
      </div>

      {/* Content */}
      <div className="p-4 pb-16 h-full overflow-y-auto">
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-3 py-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        {!isCareerPage(currentUrl) && matchedJobs.length === 0 && (
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-3 py-2 rounded mb-4 text-sm">
            <strong>Tip:</strong> Navigate to a company's career page for better results
          </div>
        )}

        {matchedJobs.length === 0 ? (
          <div className="text-center">
            <div className="mb-4">
              <svg className="w-16 h-16 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold mb-2">Scan Current Page</h2>
            <p className="text-gray-600 mb-4 text-sm">
              {currentUrl ? (
                <>Analyze <span className="text-blue-600 font-medium">{new URL(currentUrl).hostname}</span> for job matches</>
              ) : (
                'Click scan to find matching jobs on this page'
              )}
            </p>
            <button
              onClick={handleScanPage}
              disabled={isScanning}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isScanning ? (
                <div className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Scanning...
                </div>
              ) : (
                'Scan This Page'
              )}
            </button>
          </div>
        ) : (
          <div>
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-lg font-semibold">Matched Jobs ({matchedJobs.length})</h2>
              <button
                onClick={() => setMatchedJobs([])}
                className="text-gray-500 hover:text-gray-700 text-sm"
              >
                Clear
              </button>
            </div>
            
            <div className="space-y-3 max-h-48 overflow-y-auto">
              {matchedJobs.map((job) => (
                <div key={job.id} className="border rounded-lg p-3 hover:bg-gray-50 transition-colors">
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-medium text-sm leading-tight">{job.title}</h3>
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      job.matchScore >= 90 ? 'bg-green-100 text-green-800' :
                      job.matchScore >= 80 ? 'bg-blue-100 text-blue-800' :
                      job.matchScore >= 70 ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {job.matchScore}% match
                    </span>
                  </div>
                  
                  <p className="text-gray-600 text-xs mb-1">{job.company}</p>
                  <p className="text-gray-500 text-xs mb-2">{job.location}</p>
                  
                  {job.skills && job.skills.length > 0 && (
                    <div className="mb-2">
                      <div className="flex flex-wrap gap-1">
                        {job.skills.slice(0, 3).map((skill, index) => (
                          <span key={index} className="bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded">
                            {skill}
                          </span>
                        ))}
                        {job.skills.length > 3 && (
                          <span className="text-xs text-gray-500">+{job.skills.length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {job.summary && (
                    <p className="text-xs text-gray-600 mb-2 italic">{job.summary}</p>
                  )}
                  
                  <button
                    onClick={() => openJob(job.url)}
                    className="text-blue-600 text-xs hover:underline"
                  >
                    View Job →
                  </button>
                </div>
              ))}
            </div>
            
            <button
              onClick={handleScanPage}
              disabled={isScanning}
              className="mt-3 w-full bg-gray-100 text-gray-700 py-2 rounded-lg hover:bg-gray-200 text-sm transition-colors"
            >
              Scan Again
            </button>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="absolute bottom-0 w-full bg-gray-50 p-3 border-t">
        <div className="flex justify-between items-center">
          <button 
            onClick={openSettings}
            className="text-blue-600 text-sm hover:underline"
          >
            Settings
          </button>
          <div className="text-xs text-gray-500">
            v1.0.0
          </div>
        </div>
      </div>
    </div>
  );
}

export default App; 