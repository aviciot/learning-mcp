# Cloudflare AI Gateway - How It Actually Works

## ⚠️ CORRECTION: USER WAS RIGHT!

**Cloudflare AI Gateway CAN store provider API keys** (Groq, OpenAI, etc.) in the Gateway configuration under "Provider Keys". When configured this way:

✅ You **only** need `CF_GATEWAY_TOKEN` to authenticate to your Gateway  
✅ Gateway automatically adds the provider API key when forwarding requests  
✅ You do **NOT** need `GROQ_API_KEY` in your app's environment  

## The Architecture

```
WITHOUT Gateway (Direct):
You → Groq (needs GROQ_API_KEY in your .env)

WITH Gateway (Provider Keys Stored):
You → Cloudflare Gateway → Groq
      (Gateway injects stored GROQ_API_KEY automatically)
```

## Correct Configuration (.env)

### ✅ WITH Gateway (Provider Keys Stored - RECOMMENDED)
```bash
USE_AI_GATEWAY=true
AUTOGEN_MODEL=llama-3.1-8b-instant
OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/abc123/omni/groq
CF_GATEWAY_TOKEN=wnMfLUc38oC3tn9_dQpw...  # Authenticate to YOUR gateway
# NO GROQ_API_KEY needed here! Gateway has it stored.
```

### WITHOUT Gateway (Direct to Groq)
```bash
USE_AI_GATEWAY=false
AUTOGEN_MODEL=llama-3.1-8b-instant
OPENAI_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=gsk_xxx...                  # ← Required for direct calls
# No CF_GATEWAY_TOKEN needed
```

## The Request Flow (With Gateway + Stored Provider Keys)

1. **Your app creates a request:**
   ```json
   {
     "model": "llama-3.1-8b-instant",
     "messages": [{"role": "user", "content": "Hello"}]
   }
   ```

2. **App sends to Gateway with these headers:**
   ```http
   POST https://gateway.ai.cloudflare.com/.../omni/groq/v1/chat/completions
   cf-aig-authorization: Bearer <CF_GATEWAY_TOKEN>     ← Authenticate to Gateway
   cf-aig-metadata: {"model": "llama-3.1-8b-instant"}  ← Route to correct provider
   Authorization: Bearer dummy-key                      ← Ignored by Gateway
   ```

3. **Cloudflare Gateway receives it:**
   - Verifies `cf-aig-authorization` token (is this your gateway?)
   - Reads `cf-aig-metadata`: "They want llama-3.1-8b-instant"
   - Checks routing: "This goes to Groq"
   - **Retrieves stored Groq API key from "Provider Keys" configuration**

4. **Gateway forwards to Groq WITH STORED KEY:**
   ```http
   POST https://api.groq.com/openai/v1/chat/completions
   Authorization: Bearer gsk_xxx...   ← Gateway injects THIS from its storage!
   {
     "model": "llama-3.1-8b-instant",
     "messages": [{"role": "user", "content": "Hello"}]
   }
   ```

5. **Groq processes** and returns response to Gateway

6. **Gateway caches the response** and returns it to your app

## Cloudflare Dashboard Configuration

**Where to configure:** AI Gateway → Your Gateway ("omni") → Provider Keys

**What you stored there:**
```
Provider: groq
API Key: gsk_xxx...  ← This is what Gateway injects automatically
```

**Benefits:**
- 🔒 API key never leaves Cloudflare's secure storage
- 🚀 Your app doesn't need to manage provider credentials
- 📊 Centralized key rotation (change in one place)
- 🔄 Easy to switch providers without changing app code

## Key Points

### YOU Control the Model
- ✅ Model name is in YOUR `.env` file (`AUTOGEN_MODEL`)
- ✅ Gateway doesn't change the model, it just routes based on it
- ✅ You can switch models without changing Gateway config

### Gateway Benefits
- **Caching**: Same question? Instant cached response
- **Analytics**: Dashboard showing all requests, costs, errors
- **Rate Limiting**: Protects against API abuse
- **Logging**: See all requests/responses
- **Cost Tracking**: Know exactly how much you're spending

### The "omni" Name
- "omni" is just YOUR chosen name for this gateway endpoint in CF dashboard
- You could have called it "my-groq-gateway" or "learning-mcp"
- It's like naming a bookmark

## Proof from Test

When we ran `test_gateway_real.py`:
```
✅ Client created successfully
🌐 Requests will go through Cloudflare AI Gateway
📍 Gateway URL: https://gateway.ai.cloudflare.com/.../omni/compat
🤖 Model in request body: llama-3.1-8b-instant
📋 Model in header (cf-aig-metadata): llama-3.1-8b-instant

Flow: App → CF Gateway → Groq → CF Gateway → App
```

The error we got was Cloudflare's error format, proving the request went through Gateway!

## If USE_AI_GATEWAY=false

Just change one line in `.env`:
```bash
USE_AI_GATEWAY=false
OPENAI_BASE_URL=https://api.groq.com/openai/v1  # Direct to Groq
```

Now the flow is:
```
App → Groq (direct, no proxy, no caching)
```

## Summary

Think of it like this:

**Without Gateway**: You call Groq directly on your phone
**With Gateway**: You call a secretary who calls Groq for you, takes notes, and caches answers

The secretary (Gateway) doesn't decide WHAT to ask Groq (that's still you via AUTOGEN_MODEL), they just handle the logistics.
