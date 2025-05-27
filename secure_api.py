#!/usr/bin/env python3
"""
Security enhancements for JobMatch API
Makes the API more secure and extension-only
"""

# Security options to implement:

# Option 1: Extension ID Validation (Recommended)
EXTENSION_SECURITY_CONFIG = {
    "allowed_extension_ids": [
        "your-chrome-extension-id-here"  # Replace with actual extension ID
    ],
    "validate_origin": True,
    "validate_user_agent": True
}

# Option 2: API Key Authentication
API_KEY_CONFIG = {
    "require_api_key": True,
    "extension_api_key": "ext_jobmatch_secure_key_2024",  # Change this!
    "header_name": "X-JobMatch-API-Key"
}

# Option 3: CORS Restriction
CORS_CONFIG = {
    "allowed_origins": [
        "chrome-extension://your-extension-id",  # Replace with actual ID
        "moz-extension://your-extension-id"      # For Firefox if needed
    ],
    "allow_credentials": False,
    "allowed_methods": ["GET", "POST", "OPTIONS"],
    "allowed_headers": ["Content-Type", "X-JobMatch-API-Key", "X-Extension-ID"]
}

# Security middleware functions to add to main_simple.py:

def validate_extension_request(request):
    """Validate that request comes from authorized extension"""
    
    # Check Origin header
    origin = request.headers.get("origin", "")
    if not origin.startswith("chrome-extension://") and not origin.startswith("moz-extension://"):
        return False, "Invalid origin"
    
    # Check User-Agent for extension patterns
    user_agent = request.headers.get("user-agent", "")
    if "Chrome" not in user_agent and "Firefox" not in user_agent:
        return False, "Invalid user agent"
    
    # Check for extension ID in headers (if implemented)
    extension_id = request.headers.get("X-Extension-ID", "")
    if extension_id and extension_id not in EXTENSION_SECURITY_CONFIG["allowed_extension_ids"]:
        return False, "Unauthorized extension"
    
    return True, "Valid"

def validate_api_key(request):
    """Validate API key for extension requests"""
    api_key = request.headers.get(API_KEY_CONFIG["header_name"], "")
    
    if not api_key:
        return False, "Missing API key"
    
    if api_key != API_KEY_CONFIG["extension_api_key"]:
        return False, "Invalid API key"
    
    return True, "Valid API key"

# Updated CORS configuration for main_simple.py:
SECURE_CORS_MIDDLEWARE = """
# Replace the existing CORS middleware with:
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://your-extension-id-here",  # Replace with actual ID
        # Add more extension IDs if you have multiple versions
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-JobMatch-API-Key", "X-Extension-ID"],
    expose_headers=["*"],
)
"""

# Security decorator for endpoints:
SECURITY_DECORATOR = """
from functools import wraps
from fastapi import HTTPException

def require_extension_auth(func):
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        # Validate extension request
        is_valid, message = validate_extension_request(request)
        if not is_valid:
            raise HTTPException(status_code=403, detail=f"Forbidden: {message}")
        
        # Validate API key (if enabled)
        if API_KEY_CONFIG["require_api_key"]:
            is_valid_key, key_message = validate_api_key(request)
            if not is_valid_key:
                raise HTTPException(status_code=401, detail=f"Unauthorized: {key_message}")
        
        return await func(request, *args, **kwargs)
    return wrapper

# Usage: Add @require_extension_auth before sensitive endpoints
@app.post("/api/v1/upload/resume")
@require_extension_auth
async def upload_resume(request: Request, file: UploadFile = File(...)):
    # ... existing code
"""

print("""
🔒 SECURITY ENHANCEMENT OPTIONS FOR JOBMATCH API

Current Status: ❌ INSECURE (Open to all websites)

Recommended Security Levels:

1. 🟡 BASIC SECURITY (Quick Fix)
   - Restrict CORS to extension origins only
   - Add User-Agent validation
   
2. 🟠 MEDIUM SECURITY (Recommended)
   - Basic security + API key authentication
   - Extension ID validation
   - Enhanced rate limiting
   
3. 🔴 HIGH SECURITY (Enterprise)
   - Medium security + request signing
   - IP whitelisting
   - Audit logging

IMPLEMENTATION STEPS:

1. Get your Chrome Extension ID:
   - Go to chrome://extensions/
   - Enable Developer mode
   - Find your extension ID (long string like: abcdefghijklmnopqrstuvwxyz123456)

2. Choose security level and update main_simple.py

3. Update extension to send required headers

Would you like me to implement one of these security levels?
""")

# Extension-side code to add headers:
EXTENSION_HEADERS_CODE = """
// Add to extension's background.js or content.js:

const API_CONFIG = {
    baseUrl: 'https://jobmatch-production.up.railway.app/api/v1',
    apiKey: 'ext_jobmatch_secure_key_2024',  // Match server config
    extensionId: chrome.runtime.id
};

function makeSecureRequest(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        'X-JobMatch-API-Key': API_CONFIG.apiKey,
        'X-Extension-ID': API_CONFIG.extensionId,
        ...options.headers
    };
    
    return fetch(`${API_CONFIG.baseUrl}${endpoint}`, {
        ...options,
        headers
    });
}

// Usage:
makeSecureRequest('/scan/page', {
    method: 'POST',
    body: JSON.stringify(scanData)
});
""" 