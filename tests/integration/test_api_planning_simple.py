"""Test API path extraction from IICS documentation."""
import asyncio
import sys
import re
sys.path.insert(0, '/app/src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def main():
    print("=" * 70)
    print("API PLANNING TEST - Informatica Cloud")
    print("=" * 70)
    
    PATH_RE = re.compile(r"(/(?:api|public|v2|v3)[^\s\"'()<>]+)")
    
    queries = [
        ("list all connectors", "Should find connections API"),
        ("create mapping task", "Should find task creation endpoint"),
        ("get activity log", "Should find activityLog endpoint"),
    ]
    
    prof = get_profile('informatica-cloud')
    ecfg = EmbeddingConfig.from_profile(prof)
    embedder = Embedder(ecfg)
    
    vcfg = prof.get('vectordb', {})
    vdb = VDB(
        url=vcfg.get('url'),
        collection=vcfg.get('collection', 'informatica-cloud'),
        dim=ecfg.dim,
        distance=vcfg.get('distance', 'cosine')
    )
    
    for query, expectation in queries:
        print(f"\n{'─'*70}")
        print(f"Query: '{query}'")
        print(f"Expected: {expectation}")
        print(f"{'─'*70}")
        
        q_vecs = await embedder.embed([query])
        results = vdb.search(query_vec=q_vecs[0], top_k=3)
        
        found_paths = []
        for i, r in enumerate(results, 1):
            text = r.payload.get("text", "")
            score = r.score
            
            matches = PATH_RE.findall(text)
            if matches:
                found_paths.extend(matches)
            
            text_preview = text[:120].replace('\n', ' ')
            print(f"\n  {i}. Score: {score:.4f}")
            print(f"     {text_preview}...")
            if matches:
                print(f"     → Paths: {matches[:2]}")
        
        if found_paths:
            unique_paths = list(set(found_paths))[:3]
            print(f"\n  ✅ Found {len(unique_paths)} API paths: {unique_paths}")
        else:
            print(f"\n  ⚠️  No API paths extracted")
    
    await embedder.close()
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
