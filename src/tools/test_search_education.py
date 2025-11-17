#!/usr/bin/env python3
"""Test search after json_loader update"""

import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.vdb import VDB
from learning_mcp.config import get_profile

async def test_search():
    profile = get_profile('avi-cohen')
    vdb = VDB(profile)
    
    print("Searching for: 'education'")
    results = await vdb.search('education', top_k=5)
    
    print(f"\nFound {len(results)} results\n")
    print("="*80)
    
    for i, r in enumerate(results, 1):
        score = r.get('score', 0)
        text = r.get('text', '')
        metadata = r.get('metadata', {})
        
        print(f"\nResult #{i} - Score: {score:.4f}")
        print(f"Path: {metadata.get('path', 'N/A')}")
        print(f"Text: {text[:250]}")
        print("-"*80)

if __name__ == '__main__':
    asyncio.run(test_search())
