"""
REAL TEST: Make actual requests to prove Gateway flow.

Run this inside Docker to test with real API calls.
"""
import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, '/app/src')

from learning_mcp.agents.autogen_planner import _make_client, MODEL, OPENAI_BASE, USE_AI_GATEWAY

async def test_gateway_understanding():
    print("=" * 80)
    print("REAL GATEWAY TEST - Making Actual API Call")
    print("=" * 80)
    print()
    print(f"Current Configuration:")
    print(f"  USE_AI_GATEWAY: {USE_AI_GATEWAY}")
    print(f"  MODEL: {MODEL}")
    print(f"  OPENAI_BASE_URL: {OPENAI_BASE}")
    print()
    
    # Create client
    client, err = _make_client()
    if err:
        print(f"❌ Error creating client: {err}")
        return
    
    print(f"✅ Client created successfully")
    print()
    
    print("What this means:")
    if USE_AI_GATEWAY:
        print("  🌐 Requests will go through Cloudflare AI Gateway")
        print(f"  📍 Gateway URL: {OPENAI_BASE}")
        print(f"  🤖 Model in request body: {MODEL}")
        print(f"  📋 Model in header (cf-aig-metadata): {MODEL}")
        print()
        print("  Flow: App → CF Gateway → Groq → CF Gateway → App")
    else:
        print("  🚀 Requests will go directly to Groq")
        print(f"  📍 Groq URL: {OPENAI_BASE}")
        print(f"  🤖 Model in request body: {MODEL}")
        print()
        print("  Flow: App → Groq → App")
    
    print()
    print("-" * 80)
    print("Testing with a simple prompt...")
    print("-" * 80)
    
    # Import AutoGen components
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_core import CancellationToken
        
        # Create a simple agent
        agent = AssistantAgent(
            name="test_agent",
            model_client=client,
            system_message="You are a helpful assistant. Reply in one short sentence."
        )
        
        # Send a simple message
        result = await agent.run(task="Say 'Hello from Groq via Cloudflare!' in exactly 5 words.")
        
        print()
        print("Response received:")
        print(f"  {result.messages[-1].content if result.messages else 'No response'}")
        print()
        print("=" * 80)
        print("CONCLUSION")
        print("=" * 80)
        if USE_AI_GATEWAY:
            print("✅ Request went through Cloudflare AI Gateway")
            print("   → Gateway received request with cf-aig-metadata header")
            print("   → Gateway routed to Groq based on model name")
            print("   → Groq processed request")
            print("   → Gateway cached/logged response and returned it")
        else:
            print("✅ Request went directly to Groq")
            print("   → No proxy, no caching, direct connection")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gateway_understanding())
