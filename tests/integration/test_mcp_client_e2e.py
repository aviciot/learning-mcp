"""
End-to-end MCP client tests using FastMCP in-memory testing.

Based on "Stop Vibe-Testing Your MCP Server" by Jeremiah Lowin:
https://www.jlowin.dev/blog/stop-vibe-testing-mcp-servers

Key principles:
- In-memory testing (no network overhead, no subprocess management)
- Direct connection to server instance for maximum fidelity  
- Fast, deterministic, repeatable tests
- Tests actual MCP protocol layer, not just functions

Prerequisites:
  1. Qdrant must have ingested data (for search tests)
  2. Cloudflare credentials must be valid (for embeddings)

Usage:
  docker compose exec learning-mcp pytest tests/integration/test_mcp_client_e2e.py -v
"""

import os
import sys
import pytest

# Add src to path to import mcp_server
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

# FastMCP client for in-memory testing
try:
    from fastmcp import Client
    from mcp.types import TextContent, Tool
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False
    Client = None
    TextContent = None

# Import the actual MCP server instance
try:
    from mcp_server import mcp
    MCP_SERVER_AVAILABLE = True
except ImportError:
    MCP_SERVER_AVAILABLE = False
    mcp = None

pytestmark = pytest.mark.skipif(
    not (FASTMCP_AVAILABLE and MCP_SERVER_AVAILABLE),
    reason="FastMCP client or MCP server not available"
)


@pytest.mark.asyncio
async def test_mcp_server_lists_tools():
    """
    Test that MCP server exposes expected tools.
    
    This validates:
    - Server initializes correctly
    - Tools are registered in MCP protocol
    - Tool schemas are valid
    """
    # Use in-memory client connected directly to server instance
    async with Client(mcp) as client:
        tools = await client.list_tools()
        
        # Check we have tools
        assert len(tools) > 0, "MCP server should expose at least one tool"
        
        tool_names = [t.name for t in tools]
        print(f"✓ Found {len(tools)} tools: {tool_names}")
        
        # Check for expected tools
        assert "plan_api_call" in tool_names, "plan_api_call tool should be available"
        assert "search_docs" in tool_names, "search_docs tool should be available"


@pytest.mark.asyncio
async def test_search_docs_tool():
    """
    Test search_docs tool via MCP protocol.
    
    This catches:
    - VDB connection issues
    - Embedding failures
    - Serialization errors
    - Protocol-level bugs
    """
    async with Client(mcp) as client:
        # Call search_docs tool
        result = await client.call_tool(
            "search_docs",
            arguments={
                "query": "job status",
                "profile": "informatica-cloud",
                "top_k": 5
            }
        )
        
        # Result is a CallToolResult object with .content list
        assert result.content, "Should return content"
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent), "Result should be TextContent"
        
        content_text = result.content[0].text
        print(f"✓ Search returned {len(content_text)} chars")
        
        # Check for common error patterns
        assert "AttributeError" not in content_text, "VDB AttributeError detected!"
        assert "tuple' object has no attribute" not in content_text
        assert len(content_text) > 100, "Search results too short (may be empty)"


@pytest.mark.asyncio
async def test_plan_api_call_tool():
    """
    Test plan_api_call tool via MCP protocol.
    
    This is the full end-to-end test that would have caught:
    - VDB QueryResponse bug
    - Gateway authentication issues
    - AutoGen format problems
    - Serialization issues
    """
    async with Client(mcp) as client:
        # Call plan_api_call tool
        result = await client.call_tool(
            "plan_api_call",
            arguments={
                "goal": "get job status",
                "profile": "informatica-cloud"
            }
        )
        
        # Result is a CallToolResult object with .content list
        assert result.content, "Should return content"
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent), "Result should be TextContent"
        
        content_text = result.content[0].text
        print(f"✓ Got response (length={len(content_text)})")
        print(f"  First 200 chars: {content_text[:200]}")
        
        # Check for common failure patterns
        assert "AttributeError" not in content_text, "VDB AttributeError still present!"
        assert "tuple' object has no attribute 'payload'" not in content_text
        assert "Error code: 400" not in content_text, "Gateway 400 error still present!"
        assert "Chat completion bad format" not in content_text, "Gateway format error!"
        assert "Connection error" not in content_text, "Gateway connection error!"
        
        # If AutoGen is enabled, check for plan structure
        if os.getenv("USE_AUTOGEN") == "1":
            # Should contain plan details (not just "N/A")
            assert '"endpoint":' in content_text or "endpoint" in content_text.lower(), \
                "No endpoint found in plan (AutoGen may have failed)"
            assert content_text != "N/A", "Plan should not be N/A"


@pytest.mark.asyncio
async def test_plan_api_call_handles_invalid_profile():
    """
    Test error handling for invalid profile.
    
    This validates:
    - Graceful error handling
    - Clear error messages
    - No stack traces leaked to LLM
    """
    async with Client(mcp) as client:
        result = await client.call_tool(
            "plan_api_call",
            arguments={
                "goal": "test query",
                "profile": "nonexistent-profile-12345"
            }
        )
        
        assert result.content
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        
        content_text = result.content[0].text
        
        # Should contain error message, not stack trace
        assert "error" in content_text.lower() or "not found" in content_text.lower(), \
            "Should return error message for invalid profile"
        assert "Traceback" not in content_text, "Should not leak Python stack traces"


@pytest.mark.asyncio
async def test_plan_api_call_edge_cases():
    """
    Test edge cases that LLMs might generate.
    
    The "lizard in the bar" test - unusual inputs that should be handled gracefully.
    """
    async with Client(mcp) as client:
        # Empty goal
        result = await client.call_tool(
            "plan_api_call",
            arguments={
                "goal": "",
                "profile": "informatica-cloud"
            }
        )
        assert result.content and len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        
        # Very long goal (stress test)
        long_goal = "test " * 1000
        result = await client.call_tool(
            "plan_api_call",
            arguments={
                "goal": long_goal,
                "profile": "informatica-cloud"
            }
        )
        assert result.content and len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        
        # Special characters
        result = await client.call_tool(
            "plan_api_call",
            arguments={
                "goal": "test with 日本語 and émojis 🦎",
                "profile": "informatica-cloud"
            }
        )
        assert result.content and len(result.content) > 0
        assert isinstance(result.content[0], TextContent)


if __name__ == "__main__":
    # Run tests directly for debugging
    import asyncio
    
    async def main():
        print("Running MCP E2E tests (in-memory)...\n")
        
        if not FASTMCP_AVAILABLE:
            print("❌ FastMCP not installed: pip install fastmcp")
            return 1
        
        if not MCP_SERVER_AVAILABLE:
            print("❌ MCP server not importable")
            return 1
        
        try:
            await test_mcp_server_lists_tools()
            print("✓ List tools test passed\n")
            
            await test_search_docs_tool()
            print("✓ Search docs test passed\n")
            
            await test_plan_api_call_tool()
            print("✓ Plan API call test passed\n")
            
            await test_plan_api_call_handles_invalid_profile()
            print("✓ Error handling test passed\n")
            
            await test_plan_api_call_edge_cases()
            print("✓ Edge cases test passed\n")
            
            print("All tests passed!")
            return 0
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    sys.exit(asyncio.run(main()))
