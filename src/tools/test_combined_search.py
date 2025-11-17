#!/usr/bin/env python3
"""Test GitHub + Document search together"""

import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.github_client import GitHubClient
from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def combined_search_test():
    """Test combining GitHub search + document search"""
    
    print("🔍 Combined Search Test: 'RAG projects'")
    print("="*80)
    
    # 1. Search GitHub
    print("\n📦 Searching GitHub repositories...")
    print("-"*80)
    github = GitHubClient()
    repos = await github.search_repositories("RAG user:aviciot", limit=3)
    
    print(f"Found {len(repos)} GitHub repositories:")
    for repo in repos:
        print(f"\n  🔹 {repo['full_name']}")
        print(f"     {repo['description']}")
        print(f"     ⭐ {repo['stars']} | 🍴 {repo['forks']} | 📝 {repo['language']}")
        print(f"     🔗 {repo['url']}")
    
    # 2. Search Your Documents  
    print("\n\n📄 Searching your documents...")
    print("-"*80)
    prof = get_profile('avi-cohen')
    embedder = Embedder(EmbeddingConfig.from_profile(prof))
    vdb = VDB(
        url=prof['vectordb']['url'],
        collection=prof['vectordb']['collection'],
        dim=384,
        distance='Cosine'
    )
    
    query_vecs = await embedder.embed(["RAG projects machine learning"])
    results = vdb.search(query_vec=query_vecs[0], top_k=3)
    
    print(f"Found {len(results)} relevant document chunks:")
    for i, r in enumerate(results, 1):
        text = r.payload.get('text', '')
        score = r.score
        path = r.payload.get('path', 'N/A')
        print(f"\n  {i}. Score: {score:.3f}")
        print(f"     Path: {path}")
        print(f"     Text: {text[:150]}...")
    
    await embedder.close()
    
    print("\n" + "="*80)
    print("✅ Combined search complete!")
    print("\n💡 Your Omni API can now:")
    print("   • Search GitHub repos for code examples")
    print("   • Search your documents for concepts/explanations")
    print("   • Combine both for comprehensive answers!")


if __name__ == "__main__":
    asyncio.run(combined_search_test())
