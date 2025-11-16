"""Quick test of search results after metadata removal."""
import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def test_search():
    print("🔍 Testing search for 'skills' after metadata removal\n")
    
    # Setup
    prof = get_profile('avi-cohen')
    ecfg = EmbeddingConfig.from_profile(prof)
    embedder = Embedder(ecfg)
    
    vcfg = prof.get('vectordb', {})
    vdb = VDB(
        url=vcfg.get('url'),
        collection=vcfg.get('collection', 'avi-cohen'),
        dim=ecfg.dim,
        distance=vcfg.get('distance', 'cosine')
    )
    
    # Search
    q_vecs = await embedder.embed(['skills'])
    results = vdb.search(query_vec=q_vecs[0], top_k=3)
    
    print("=== Top 3 Results ===\n")
    for i, r in enumerate(results, 1):
        text_preview = r.payload.get("text", "")[:200]
        print(f"{i}. Score: {r.score:.4f}")
        print(f"   Doc: {r.payload.get('doc_id')}")
        print(f"   Text: {text_preview}...")
        print()
    
    await embedder.close()


if __name__ == "__main__":
    asyncio.run(test_search())
