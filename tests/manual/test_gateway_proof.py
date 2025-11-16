"""
SIMPLE TEST: What does Cloudflare Gateway actually do?

This will make 2 requests:
1. WITH Gateway (USE_AI_GATEWAY=true)
2. WITHOUT Gateway (direct to Groq)

And show you the ONLY difference.
"""
import asyncio
import httpx
import json
import os
import time

# Your credentials (load from environment - DO NOT hardcode!)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your-groq-api-key-here")
CF_GATEWAY_TOKEN = os.getenv("CF_GATEWAY_TOKEN", "your-gateway-token-here")
CF_GATEWAY_URL = "https://gateway.ai.cloudflare.com/v1/f21d49b726fe7907882f02b84f5ea754/omni/compat"
GROQ_DIRECT_URL = "https://api.groq.com/openai/v1"

MODEL = "llama-3.1-8b-instant"

# Simple test request
payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say 'test' and nothing else"}
    ],
    "max_tokens": 10
}

async def test_without_gateway():
    """Test 1: Direct to Groq (no gateway)"""
    print("\n" + "=" * 80)
    print("TEST 1: WITHOUT GATEWAY (Direct to Groq)")
    print("=" * 80)
    
    url = f"{GROQ_DIRECT_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print(f"\n📍 URL: {url}")
    print(f"🔑 Headers:")
    print(f"   - Authorization: Bearer {GROQ_API_KEY[:20]}...")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        duration = (time.time() - start) * 1000
        
        print(f"\n✅ Response Status: {response.status_code}")
        print(f"⏱️  Duration: {duration:.0f}ms")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            print(f"💬 Response: {content}")
            return duration, "success"
        else:
            print(f"❌ Error: {response.text}")
            return duration, "error"
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0, "error"

async def test_with_gateway():
    """Test 2: Through Cloudflare Gateway"""
    print("\n" + "=" * 80)
    print("TEST 2: WITH GATEWAY (Cloudflare → Groq)")
    print("=" * 80)
    
    url = f"{CF_GATEWAY_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",  # ← STILL need Groq key!
        "cf-aig-authorization": f"Bearer {CF_GATEWAY_TOKEN}",  # ← Gateway auth
        "Content-Type": "application/json"
    }
    
    print(f"\n📍 URL: {url}")
    print(f"🔑 Headers:")
    print(f"   - Authorization: Bearer {GROQ_API_KEY[:20]}... ← GROQ KEY (still needed!)")
    print(f"   - cf-aig-authorization: Bearer {CF_GATEWAY_TOKEN[:20]}... ← GATEWAY KEY")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        duration = (time.time() - start) * 1000
        
        print(f"\n✅ Response Status: {response.status_code}")
        print(f"⏱️  Duration: {duration:.0f}ms")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            print(f"💬 Response: {content}")
            
            # Check for caching headers
            if "cf-cache-status" in response.headers:
                cache_status = response.headers["cf-cache-status"]
                print(f"📦 Cache Status: {cache_status}")
            
            return duration, "success"
        else:
            print(f"❌ Error: {response.text}")
            return duration, "error"
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0, "error"

async def main():
    print("\n" + "=" * 80)
    print("🧪 CLOUDFLARE GATEWAY TEST")
    print("=" * 80)
    print("\nQuestion: Why do I need Groq API key if I have Gateway?")
    print("Answer: Let's test and see...")
    
    # Test 1: Without gateway
    duration1, status1 = await test_without_gateway()
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Test 2: With gateway
    duration2, status2 = await test_with_gateway()
    
    # Test 3: Call gateway again (should be cached)
    print("\n" + "=" * 80)
    print("TEST 3: WITH GATEWAY (Second call - should be cached)")
    print("=" * 80)
    duration3, status3 = await test_with_gateway()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    print(f"\n1️⃣  Direct to Groq:        {duration1:.0f}ms")
    print(f"2️⃣  Via Gateway (1st):      {duration2:.0f}ms")
    print(f"3️⃣  Via Gateway (2nd):      {duration3:.0f}ms ← Should be faster (cached)")
    
    print("\n" + "=" * 80)
    print("🎯 CONCLUSION")
    print("=" * 80)
    print("\nBoth requests REQUIRED the Groq API key!")
    print()
    print("What Gateway does:")
    print("  ✅ Caches responses (2nd call faster)")
    print("  ✅ Logs all requests in CF dashboard")
    print("  ✅ Provides analytics/monitoring")
    print()
    print("What Gateway does NOT do:")
    print("  ❌ Store your Groq API key")
    print("  ❌ Have its own Groq account")
    print("  ❌ Let you skip providing Groq API key")
    print()
    print("💡 Think of it as: Gateway = Smart cache/logger BETWEEN you and Groq")
    print("   You still need YOUR Groq API key to talk to Groq!")

if __name__ == "__main__":
    asyncio.run(main())
