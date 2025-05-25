#!/usr/bin/env python3
"""
Quick Rate Limiting Implementation for JobMatch Backend
This adds basic rate limiting to prevent API abuse when published.
"""

import re

def add_rate_limiting_to_main():
    """Add rate limiting imports and middleware to main_simple.py"""
    
    # Read the current main_simple.py
    with open('main_simple.py', 'r') as f:
        content = f.read()
    
    # Check if rate limiting is already added
    if 'slowapi' in content:
        print("✅ Rate limiting already implemented!")
        return
    
    # Add imports at the top
    import_section = '''from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import time
from collections import defaultdict
import os

'''
    
    # Find the imports section and add our imports
    if 'from fastapi import' in content:
        content = content.replace('from fastapi import', import_section + 'from fastapi import')
    else:
        # Add at the beginning
        content = import_section + content
    
    # Add rate limiter configuration after app creation
    limiter_config = '''
# Rate limiting configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# In-memory rate limiting for API keys (simple implementation)
api_key_usage = defaultdict(list)
API_KEY_RATE_LIMIT = int(os.getenv("API_KEY_RATE_LIMIT", "100"))  # 100 requests per hour per API key

def check_api_key_rate_limit(api_key: str) -> bool:
    """Check if API key has exceeded rate limit"""
    now = time.time()
    hour_ago = now - 3600  # 1 hour ago
    
    # Clean old entries
    api_key_usage[api_key] = [timestamp for timestamp in api_key_usage[api_key] if timestamp > hour_ago]
    
    # Check if under limit
    if len(api_key_usage[api_key]) >= API_KEY_RATE_LIMIT:
        return False
    
    # Add current request
    api_key_usage[api_key].append(now)
    return True

'''
    
    # Find where app is created and add limiter config
    if 'app = FastAPI(' in content:
        content = content.replace('app = FastAPI(', limiter_config + '\napp = FastAPI(')
    elif 'app = FastAPI()' in content:
        content = content.replace('app = FastAPI()', limiter_config + '\napp = FastAPI()')
    
    # Add rate limiting to the main scan endpoint
    scan_endpoint_pattern = r'(@app\.post\(["\']\/api\/v1\/scan\/page["\'].*?\n)(async def [^(]+\([^)]*\):)'
    
    def replace_scan_endpoint(match):
        decorator = match.group(1)
        function_def = match.group(2)
        
        # Add rate limiting decorator
        new_decorator = decorator + '@limiter.limit("10/hour")  # 10 requests per hour per IP\n'
        return new_decorator + function_def
    
    content = re.sub(scan_endpoint_pattern, replace_scan_endpoint, content, flags=re.DOTALL)
    
    # Add API key rate limiting check inside the scan function
    # Find the scan function and add rate limiting check
    scan_function_pattern = r'(async def scan_page[^:]*:.*?)(# Get all relevant settings)'
    
    def add_rate_limit_check(match):
        function_start = match.group(1)
        settings_comment = match.group(2)
        
        rate_limit_check = '''
    # Rate limiting check for API usage
    user_api_key = request_data.get('user_api_key') or 'default'
    if not check_api_key_rate_limit(user_api_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 100 requests per hour per API key."
        )
    
    '''
        return function_start + rate_limit_check + settings_comment
    
    content = re.sub(scan_function_pattern, add_rate_limit_check, content, flags=re.DOTALL)
    
    # Write the updated content
    with open('main_simple.py', 'w') as f:
        f.write(content)
    
    print("✅ Rate limiting added to main_simple.py!")
    print("📊 Rate limits implemented:")
    print("   - 10 requests per hour per IP address")
    print("   - 100 requests per hour per API key")
    print("   - Configurable via API_KEY_RATE_LIMIT environment variable")

def add_requirements():
    """Add slowapi to requirements.txt"""
    
    with open('requirements.txt', 'r') as f:
        requirements = f.read()
    
    if 'slowapi' not in requirements:
        with open('requirements.txt', 'a') as f:
            f.write('\nslowapi==0.1.9\n')
        print("✅ Added slowapi to requirements.txt")
    else:
        print("✅ slowapi already in requirements.txt")

def create_env_example():
    """Create .env.example with rate limiting configuration"""
    
    env_example = '''# JobMatch Backend Configuration

# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Rate Limiting Configuration
API_KEY_RATE_LIMIT=100  # Requests per hour per API key
IP_RATE_LIMIT=10        # Requests per hour per IP address

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false

# CORS Configuration
ALLOWED_ORIGINS=["chrome-extension://*", "http://localhost:3000"]
'''
    
    with open('.env.example', 'w') as f:
        f.write(env_example)
    
    print("✅ Created .env.example with rate limiting configuration")

if __name__ == "__main__":
    print("🔒 Adding rate limiting to JobMatch backend...")
    
    try:
        add_rate_limiting_to_main()
        add_requirements()
        create_env_example()
        
        print("\n🎉 Rate limiting implementation complete!")
        print("\n⚠️  IMPORTANT NOTES:")
        print("1. This is a basic in-memory rate limiting implementation")
        print("2. For production, consider using Redis for distributed rate limiting")
        print("3. Configure API_KEY_RATE_LIMIT environment variable as needed")
        print("4. Test the rate limiting before deploying to production")
        print("\n🚀 Next steps:")
        print("1. Test the rate limiting functionality")
        print("2. Consider implementing user authentication")
        print("3. Add monitoring and logging for rate limit violations")
        
    except Exception as e:
        print(f"❌ Error adding rate limiting: {e}")
        print("Please add rate limiting manually before deploying to production!") 