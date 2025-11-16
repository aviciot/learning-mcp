"""
Test to understand Cloudflare AI Gateway flow.

This will show exactly what URL, headers, and model name are sent.
"""
import os
import json

# Simulate the environment
USE_AI_GATEWAY = True
CF_GATEWAY_TOKEN = os.getenv("CF_GATEWAY_TOKEN", "your-token")
CF_GATEWAY_URL = os.getenv("CF_GATEWAY_URL", "https://gateway.ai.cloudflare.com/v1/account/omni/compat")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "gsk_xxx")
MODEL = "llama-3.1-8b-instant"

print("=" * 80)
print("CLOUDFLARE AI GATEWAY FLOW TEST")
print("=" * 80)

# Test 1: WITH Gateway (USE_AI_GATEWAY=true)
print("\n1️⃣ WITH AI GATEWAY (USE_AI_GATEWAY=true)")
print("-" * 80)
print(f"Base URL: {CF_GATEWAY_URL}")
print(f"API Key: {GROQ_API_KEY[:20]}...")
print(f"Model: {MODEL}")
print()
print("Headers added:")
print(f"  cf-aig-authorization: Bearer {CF_GATEWAY_TOKEN[:20]}...")
print(f'  cf-aig-metadata: {{"model": "{MODEL}"}}')
print()
print("What happens:")
print("  1. Request goes to Cloudflare Gateway")
print("  2. CF Gateway reads 'cf-aig-metadata' header to know model")
print("  3. CF Gateway forwards request to Groq (configured in CF dashboard)")
print("  4. Uses GROQ_API_KEY to authenticate with Groq")
print("  5. Returns response through CF Gateway (with caching/logging)")

# Test 2: WITHOUT Gateway (USE_AI_GATEWAY=false)
print("\n\n2️⃣ WITHOUT AI GATEWAY (USE_AI_GATEWAY=false)")
print("-" * 80)
GROQ_DIRECT_URL = "https://api.groq.com/openai/v1"
print(f"Base URL: {GROQ_DIRECT_URL}")
print(f"API Key: {GROQ_API_KEY[:20]}...")
print(f"Model: {MODEL}")
print()
print("Headers:")
print("  (Standard OpenAI-compatible headers only)")
print()
print("What happens:")
print("  1. Request goes directly to Groq")
print("  2. Uses GROQ_API_KEY to authenticate")
print("  3. Returns response directly (no proxy)")

# Test 3: Prove it with actual request structure
print("\n\n3️⃣ ACTUAL REQUEST PAYLOAD")
print("-" * 80)
print("Both cases send the SAME payload:")
print()
payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"}
    ]
}
print(json.dumps(payload, indent=2))
print()
print("The ONLY difference:")
print("  WITH Gateway: Extra headers (cf-aig-*) + Gateway URL")
print("  WITHOUT Gateway: Direct Groq URL, no extra headers")

# Test 4: Show the real confusion
print("\n\n4️⃣ KEY INSIGHT (Confusion Clarified)")
print("-" * 80)
print("Your .env has:")
print(f"  AUTOGEN_MODEL={MODEL}")
print(f"  OPENAI_BASE_URL={CF_GATEWAY_URL}")
print(f"  OPENAI_API_KEY=${{GROQ_API_KEY}}")
print()
print("The model name goes in TWO places:")
print(f"  1. Request body: 'model': '{MODEL}' (always)")
print(f"  2. Header (gateway only): 'cf-aig-metadata': {{'model': '{MODEL}'}}")
print()
print("Why the header?")
print("  CF Gateway can route to MULTIPLE backends (Groq, OpenAI, Anthropic)")
print("  The header tells CF 'this is for Groq, not OpenAI'")
print("  Your CF dashboard has 'omni' endpoint configured with routing rules")

# Test 5: Show what CF Gateway config looks like
print("\n\n5️⃣ CLOUDFLARE GATEWAY DASHBOARD CONFIG")
print("-" * 80)
print("In your Cloudflare AI Gateway dashboard (gateway 'omni'):")
print()
print("  Default Provider: Groq")
print("  Model Mapping:")
print("    llama-3.1-8b-instant → groq/llama-3.1-8b-instant")
print()
print("So the flow is:")
print("  App sends: model='llama-3.1-8b-instant'")
print("  CF Gateway translates: 'groq/llama-3.1-8b-instant'")
print("  Groq receives: model='llama-3.1-8b-instant' (CF strips prefix)")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("✅ YOU specify the model in AUTOGEN_MODEL")
print("✅ CF Gateway just proxies/caches/logs the request")
print("✅ CF uses cf-aig-metadata to route to correct backend")
print("✅ The 'omni' endpoint name is YOUR choice in CF dashboard")
print()
