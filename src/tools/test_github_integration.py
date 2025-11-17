#!/usr/bin/env python3
"""Test GitHub integration in Learning MCP"""

import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.github_client import GitHubClient


async def test_github_integration():
    """Test all GitHub tools"""
    
    print("🧪 Testing GitHub Integration")
    print("="*80)
    
    github = GitHubClient()
    
    # Test 1: Search repositories
    print("\n1️⃣ Testing: search_repositories")
    print("-"*80)
    try:
        repos = await github.search_repositories(
            query="RAG user:aviciot",
            limit=5
        )
        print(f"✅ Found {len(repos)} repositories:")
        for repo in repos:
            print(f"   • {repo['full_name']} (⭐ {repo['stars']})")
            print(f"     {repo['description'][:80]}...")
            print(f"     {repo['url']}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: List user repos
    print("\n2️⃣ Testing: list_user_repos")
    print("-"*80)
    try:
        repos = await github.list_user_repos(
            username="aviciot",
            limit=10
        )
        print(f"✅ Found {len(repos)} repositories for user 'aviciot':")
        for repo in repos[:5]:  # Show first 5
            print(f"   • {repo['name']} (⭐ {repo['stars']}) - {repo['language']}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Get file contents
    print("\n3️⃣ Testing: get_file_contents")
    print("-"*80)
    try:
        file_data = await github.get_file_contents(
            owner="aviciot",
            repo="learning-mcp",
            path="README.md"
        )
        print(f"✅ Retrieved file: {file_data['name']}")
        print(f"   Size: {file_data['size']} bytes")
        print(f"   Content preview (first 200 chars):")
        print(f"   {file_data['content'][:200]}...")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*80)
    print("✅ GitHub Integration Test Complete!")


if __name__ == "__main__":
    asyncio.run(test_github_integration())
