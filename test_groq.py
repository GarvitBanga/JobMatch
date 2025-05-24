#!/usr/bin/env python3
"""
Test script to verify Groq integration for job extraction
"""

import os
import asyncio
import requests
from dotenv import load_dotenv

load_dotenv()

async def test_groq_extraction():
    """Test Groq API for job content extraction"""
    
    # Sample job data
    test_job = {
        "title": "Senior Software Engineer",
        "company": "Amazon", 
        "location": "Seattle, WA",
        "description": """
        Amazon is seeking a Senior Software Engineer to join our team building next-generation cloud infrastructure.
        
        BASIC QUALIFICATIONS:
        • 5+ years of professional software development experience
        • Programming experience with at least one modern language such as Java, C++, or C# including object-oriented design
        • Experience with distributed systems design and implementation
        • Bachelor's degree in Computer Science or equivalent
        
        PREFERRED QUALIFICATIONS:
        • Master's degree in Computer Science or related field
        • Experience with AWS services and cloud architecture
        • Knowledge of microservices architecture patterns
        • Experience with containerization technologies like Docker and Kubernetes
        • Strong understanding of system design and scalability
        
        RESPONSIBILITIES:
        • Design and implement scalable distributed systems
        • Collaborate with cross-functional teams to deliver high-quality software
        • Mentor junior engineers and provide technical leadership
        • Participate in code reviews and architectural discussions
        • Optimize system performance and reliability
        
        We offer competitive compensation, comprehensive benefits, and opportunities for professional growth in a fast-paced, innovative environment.
        """
    }
    
    print("🧪 Testing Groq Integration")
    print("=" * 50)
    
    # Check if Groq API key is available
    groq_api_key = os.getenv('GROQ_API_KEY')
    
    if not groq_api_key:
        print("❌ GROQ_API_KEY not found in environment")
        print("📋 To set up Groq:")
        print("   1. Visit: https://console.groq.com/")
        print("   2. Sign up (free)")
        print("   3. Generate API key")
        print("   4. Add to .env: GROQ_API_KEY=your_key_here")
        return False
    
    print(f"✅ GROQ_API_KEY found: {groq_api_key[:20]}...")
    
    # Test extraction
    try:
        print("\n🔄 Testing job extraction with Groq...")
        
        # Create extraction prompt
        extraction_prompt = f"""Extract the most important information from this job posting for accurate candidate matching. Focus on technical requirements, experience levels, and key responsibilities while preserving context.

Job Title: {test_job['title']}
Company: {test_job['company']}

Original Job Description:
{test_job['description']}

Extract and summarize in under 1000 characters:

1. Core technical requirements (languages, frameworks, tools)
2. Experience level needed (years, specific domains)
3. Key responsibilities and what the person will actually do
4. Must-have vs nice-to-have qualifications
5. Any important context about team, company, or project scope

Focus only on information that helps determine if a candidate is a good fit. Be concise but preserve important technical nuance.

Extracted Summary:"""

        # Call Groq API
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3-70b-8192",
            "messages": [
                {"role": "system", "content": "You are an expert technical recruiter. Extract key job information while preserving context for accurate candidate matching."},
                {"role": "user", "content": extraction_prompt}
            ],
            "max_tokens": 800,
            "temperature": 0.1,
            "top_p": 0.9
        }
        
        response = requests.post(groq_url, headers=headers, json=payload, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            extracted_content = result['choices'][0]['message']['content'].strip()
            
            print("✅ Groq extraction successful!")
            print(f"📊 Original length: {len(test_job['description'])} characters")
            print(f"📊 Extracted length: {len(extracted_content)} characters")
            print(f"📊 Compression ratio: {len(extracted_content)/len(test_job['description'])*100:.1f}%")
            print(f"\n📄 Extracted Content:")
            print("-" * 40)
            print(extracted_content)
            print("-" * 40)
            
            return True
        else:
            print(f"❌ Groq API error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Groq test failed: {str(e)}")
        return False

async def test_health_endpoint():
    """Test the health endpoint to see extraction methods status"""
    
    print("\n🏥 Testing Health Endpoint")
    print("=" * 50)
    
    try:
        # Test if server is running
        health_url = "http://localhost:8000/health"
        response = requests.get(health_url, timeout=5)
        
        if response.status_code == 200:
            health_data = response.json()
            print("✅ Server is running!")
            print(f"📊 Extraction Methods Status:")
            
            methods = health_data.get('features', {}).get('extraction_methods', {})
            for method, available in methods.items():
                status = "✅" if available else "❌"
                print(f"   {status} {method}: {available}")
            
            print(f"\n💡 Recommendation: {health_data.get('recommended_setup', {}).get('extraction_quality', 'N/A')}")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Start with: python main_simple.py")
        return False
    except Exception as e:
        print(f"❌ Health check failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Groq Integration Test Suite")
    print("=" * 60)
    
    # Run tests
    asyncio.run(test_groq_extraction())
    asyncio.run(test_health_endpoint())
    
    print("\n✅ Test suite complete!")
    print("\n📋 Next steps:")
    print("1. Get free Groq API key: https://console.groq.com/")
    print("2. Add to .env: GROQ_API_KEY=your_key_here")
    print("3. Restart your server: python main_simple.py")
    print("4. Your system will automatically use Groq for extraction!") 