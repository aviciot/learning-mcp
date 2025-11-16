"""Simple HTTP test for search_docs - no pytest required."""
import asyncio
import json
import sys

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Install with: pip install httpx")
    sys.exit(1)


MCP_URL = "http://localhost:8013/mcp"
HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json"
}


def parse_sse_response(content: str) -> dict:
    """Parse SSE format response to extract JSON data."""
    lines = content.strip().split('\n')
    for line in lines:
        if line.startswith('data: '):
            return json.loads(line[6:])
    raise ValueError(f"No data line found in SSE response: {content}")


async def test_search_http():
    """Test search_docs via HTTP MCP protocol."""
    print("🧪 Testing MCP search_docs via HTTP Streamable protocol\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Initialize session
        print("1️⃣ Initializing MCP session...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        }
        
        response = await client.post(MCP_URL, headers=HEADERS, json=init_request)
        assert response.status_code == 200, f"Init failed: {response.status_code}"
        
        data = parse_sse_response(response.text)
        assert "result" in data, "No result in init response"
        
        # Extract session from cookies
        session_cookies = response.cookies
        print(f"   ✅ Session initialized with {data['result']['serverInfo']['name']}")
        print(f"   📝 Session cookies: {dict(session_cookies)}\n")
        
        # Step 2: Call search_docs
        print("2️⃣ Calling search_docs tool...")
        search_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_docs",
                "arguments": {
                    "q": "projects",
                    "profile": "avi-cohen",
                    "top_k": 3
                }
            }
        }
        
        response = await client.post(MCP_URL, headers=HEADERS, json=search_request)
        if response.status_code != 200:
            print(f"   ❌ Status: {response.status_code}")
            print(f"   Response: {response.text}")
        assert response.status_code == 200, f"Search failed: {response.status_code}"
        
        data = parse_sse_response(response.text)
        print(f"   ✅ Received response (id={data['id']})\n")
        
        # Step 3: Parse and validate results
        print("3️⃣ Validating search results...")
        assert "result" in data, "No result in search response"
        result = data["result"]
        
        assert "content" in result, "No content in result"
        content_items = result["content"]
        assert isinstance(content_items, list), "Content should be list"
        assert len(content_items) > 0, "Content should not be empty"
        
        search_data = json.loads(content_items[0]["text"])
        
        assert "results" in search_data, "No results field"
        assert "metadata" in search_data, "No metadata field"
        assert search_data["metadata"]["profile"] == "avi-cohen"
        assert search_data["metadata"]["query"] == "projects"
        assert len(search_data["results"]) <= 3, f"Too many results: {len(search_data['results'])}"
        
        print(f"   ✅ Found {len(search_data['results'])} results\n")
        
        # Step 4: Display results
        print("📊 Search Results:")
        print(f"   Query: '{search_data['metadata']['query']}'")
        print(f"   Profile: {search_data['metadata']['profile']}")
        print(f"   Results: {len(search_data['results'])}\n")
        
        for i, r in enumerate(search_data["results"], 1):
            print(f"   {i}. Score: {r['score']:.4f}")
            print(f"      Doc: {r['doc_id']}")
            text_preview = r['text'][:100].replace('\n', ' ')
            print(f"      Text: {text_preview}...\n")
        
        # Validate result structure
        if len(search_data["results"]) > 0:
            first = search_data["results"][0]
            assert "text" in first, "Missing 'text' field"
            assert "score" in first, "Missing 'score' field"
            assert "doc_id" in first, "Missing 'doc_id' field"
            assert isinstance(first["score"], float), "Score should be float"
            assert 0.0 <= first["score"] <= 1.0, f"Score out of range: {first['score']}"
            
            # Check relevance ordering
            if len(search_data["results"]) > 1:
                scores = [r["score"] for r in search_data["results"]]
                assert scores == sorted(scores, reverse=True), "Results not sorted by score"
        
        print("✅ All validations passed!")
        print("\n🎉 search_docs is working correctly via HTTP!")
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_search_http())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
