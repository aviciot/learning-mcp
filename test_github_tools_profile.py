"""Test GitHub MCP tools using FastMCP in-memory client (PROFILE-BASED VERSION)."""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fastmcp import Client
from mcp_server import mcp


async def test_list_user_repos():
    """Test list_user_github_repos tool with PROFILE parameter."""
    print("\n" + "="*70)
    print("Testing list_user_github_repos (PROFILE-BASED)")
    print("="*70)
    
    async with Client(mcp) as client:
        # Test 1: List repos using avi-cohen profile
        print("\n1️⃣  Testing with profile='avi-cohen', limit=5")
        print("   (Should load username from profile config)")
        result = await client.call_tool(
            "list_user_github_repos",
            arguments={
                "profile": "avi-cohen",
                "limit": 5
            }
        )
        
        print(f"   Result type: {type(result)}")
        if result.content:
            import json
            content = result.content[0].text
            data = json.loads(content)
            print(f"   ✅ Profile: {data.get('profile')}")
            print(f"   ✅ Username (from profile): {data.get('username')}")
            print(f"   ✅ Count: {data.get('count')}")
            print(f"   ✅ Repos found: {len(data.get('repositories', []))}")
            if data.get('repositories'):
                print(f"\n   First repo:")
                first_repo = data['repositories'][0]
                print(f"     - Name: {first_repo.get('name')}")
                print(f"     - URL: {first_repo.get('url')}")
                print(f"     - Stars: {first_repo.get('stars')}")
        
        # Test 2: List repos using default profile
        print("\n2️⃣  Testing with default profile (should use avi-cohen), limit=3")
        result = await client.call_tool(
            "list_user_github_repos",
            arguments={
                "limit": 3,
                "type_filter": "owner"
            }
        )
        
        if result.content:
            content = result.content[0].text
            data = json.loads(content)
            print(f"   ✅ Profile: {data.get('profile')}")
            print(f"   ✅ Username: {data.get('username')}")
            print(f"   ✅ Count: {data.get('count')}")
            if data.get('repositories'):
                print(f"\n   Top 3 repos:")
                for repo in data['repositories'][:3]:
                    print(f"     - {repo.get('name')} ({repo.get('stars')} ⭐)")


async def test_search_repos():
    """Test search_github_repos tool with PROFILE-BASED AUTO-SCOPING."""
    print("\n" + "="*70)
    print("Testing search_github_repos (PROFILE-BASED AUTO-SCOPING)")
    print("="*70)
    
    async with Client(mcp) as client:
        print("\n🔍 Test 1: query='RAG', profile='avi-cohen', limit=5")
        print("   (Should auto-inject: user:aviciot)")
        result = await client.call_tool(
            "search_github_repos",
            arguments={
                "query": "RAG",
                "profile": "avi-cohen",
                "limit": 5
            }
        )
        
        if result.content:
            import json
            content = result.content[0].text
            data = json.loads(content)
            print(f"   ✅ Query sent to GitHub: {data.get('query')}")
            print(f"   ✅ Profile: {data.get('profile')}")
            print(f"   ✅ Count: {data.get('count')}")
            if data.get('repositories'):
                print(f"\n   Repos found:")
                for repo in data['repositories']:
                    print(f"     - {repo.get('name')} ({repo.get('stars')} ⭐)")


async def test_get_file():
    """Test get_github_file tool (unchanged - no profile parameter)."""
    print("\n" + "="*70)
    print("Testing get_github_file")
    print("="*70)
    
    async with Client(mcp) as client:
        print("\n📄 Testing with owner='aviciot', repo='learning-mcp', path='README.md'")
        result = await client.call_tool(
            "get_github_file",
            arguments={
                "owner": "aviciot",
                "repo": "learning-mcp",
                "path": "README.md"
            }
        )
        
        if result.content:
            import json
            content = result.content[0].text
            data = json.loads(content)
            print(f"   ✅ Name: {data.get('name')}")
            print(f"   ✅ Size: {data.get('size')} bytes")
            print(f"   ✅ URL: {data.get('url')}")
            if data.get('content'):
                preview = data['content'][:200]
                print(f"\n   Content preview:")
                print(f"   {preview}...")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("🧪 GitHub MCP Tools Test Suite (PROFILE-BASED VERSION)")
    print("="*70)
    
    try:
        await test_list_user_repos()
        await test_search_repos()
        await test_get_file()
        
        print("\n" + "="*70)
        print("✅ All tests completed successfully!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
