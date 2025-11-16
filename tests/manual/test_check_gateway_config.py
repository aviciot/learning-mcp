"""
Query Cloudflare AI Gateway to see what's ACTUALLY configured there.
This will answer: Does the gateway have Groq API key stored or not?
"""
import asyncio
import httpx
import json
import os

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "f21d49b726fe7907882f02b84f5ea754")
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "ZtaaYWcTat7D3xrmzD_NULx2dExtelb5CvKVqnIN")

async def query_gateway_config():
    """Query Cloudflare API to see gateway configuration"""
    print("=" * 80)
    print("🔍 CHECKING YOUR CLOUDFLARE AI GATEWAY CONFIGURATION")
    print("=" * 80)
    print()
    
    # List all AI Gateways
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai-gateway/gateways"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"Querying: {url}")
    print()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("success"):
                gateways = data.get("result", [])
                print(f"✅ Found {len(gateways)} gateway(s) in your account:")
                print()
                
                for gw in gateways:
                    print("-" * 80)
                    print(f"📍 Gateway Name: {gw.get('name')}")
                    print(f"   ID: {gw.get('id')}")
                    print(f"   Created: {gw.get('created_at')}")
                    print(f"   Modified: {gw.get('modified_at')}")
                    
                    # Check if there's cached config
                    print(f"\n   ⚙️  Configuration:")
                    print(f"   - Cache TTL: {gw.get('cache_ttl', 'N/A')}")
                    print(f"   - Cache Invalidate On Update: {gw.get('cache_invalidate_on_update', 'N/A')}")
                    print(f"   - Collect Logs: {gw.get('collect_logs', 'N/A')}")
                    print(f"   - Rate Limiting: {gw.get('rate_limiting_interval', 'N/A')}")
                    
                    # The KEY question: Does it have provider credentials?
                    if 'providers' in gw:
                        print(f"\n   🔐 Provider Credentials Stored: {gw.get('providers')}")
                    else:
                        print(f"\n   🔐 Provider Credentials: NOT STORED IN GATEWAY")
                        print(f"      (You must pass API keys in each request)")
                    
                    print()
                
                print("=" * 80)
                print("🎯 CONCLUSION")
                print("=" * 80)
                print()
                
                # Check if any gateway has stored credentials
                has_stored_creds = any('providers' in gw and gw['providers'] for gw in gateways)
                
                if has_stored_creds:
                    print("✅ Your gateway HAS stored provider credentials!")
                    print("   You DON'T need to pass Groq API key in requests.")
                else:
                    print("❌ Your gateway does NOT store provider credentials!")
                    print("   You MUST pass Groq API key in each request.")
                    print()
                    print("   This explains why CF_GATEWAY_TOKEN + GROQ_API_KEY are both needed:")
                    print("   - CF_GATEWAY_TOKEN: Authenticates to YOUR gateway")
                    print("   - GROQ_API_KEY: Passed through gateway to Groq")
                
            else:
                print(f"❌ API Error: {data.get('errors')}")
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(query_gateway_config())
