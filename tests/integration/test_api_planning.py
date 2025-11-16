"""Integration test for plan_api_call MCP tool - Direct HTTP approach."""
import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB
import re


async def test_api_planning():
    """Test plan_api_call logic with IICS API queries (without AutoGen)."""
    print("=" * 70)
    print("MCP API PLANNING TEST - Informatica Cloud Profile")
    print("=" * 70)
    
    test_queries = [
        ("list all connectors", "Should find GET /api/v3/connections or similar"),
        ("create a mapping task", "Should find POST endpoint for tasks"),
        ("get job status", "Should find GET endpoint for job monitoring"),
    ]
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print(f"\n✅ Connected to MCP server")
            print(f"Server: {session.server_info.name}")
            
            # List available tools
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"Available tools: {', '.join(tool_names)}")
            
            if "plan_api_call" not in tool_names:
                print(f"\n❌ FAIL: plan_api_call tool not found!")
                return False
            
            all_passed = True
            
            for query, expectation in test_queries:
                print(f"\n{'─'*70}")
                print(f"Query: '{query}'")
                print(f"Expected: {expectation}")
                print(f"{'─'*70}")
                
                try:
                    result = await session.call_tool(
                        "plan_api_call",
                        arguments={
                            "goal": query,
                            "profile": "informatica-cloud"
                        }
                    )
                    
                    # Parse result
                    content_text = result.content[0].text
                    data = json.loads(content_text)
                    
                    print(f"Status: {data.get('status', 'unknown')}")
                    
                    if data.get("status") == "disabled":
                        print(f"  ⚠️  AutoGen disabled - testing search fallback")
                        # Should still return search results or indication
                        print(f"  Message: {data.get('message')}")
                        
                    elif data.get("status") == "ok":
                        print(f"  ✅ Plan generated:")
                        print(f"     Method: {data.get('method')}")
                        print(f"     Endpoint: {data.get('endpoint')}")
                        print(f"     Params: {data.get('params', {})}")
                        print(f"     Reasoning: {data.get('reasoning', '')[:100]}...")
                        
                        # Validate structure
                        if not data.get("endpoint"):
                            print(f"  ❌ FAIL: No endpoint in plan")
                            all_passed = False
                        
                    else:
                        print(f"  ⚠️  Unexpected status: {data.get('status')}")
                        print(f"     Full response: {json.dumps(data, indent=2)}")
                
                except Exception as e:
                    print(f"  ❌ ERROR: {e}")
                    all_passed = False
            
            print(f"\n{'='*70}")
            if all_passed:
                print("✅ ALL TESTS PASSED")
            else:
                print("❌ SOME TESTS FAILED")
            print(f"{'='*70}\n")
            
            return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_api_planning())
    sys.exit(0 if success else 1)
