"""Test search for 'technical skills' query."""
import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def main():
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
    
    print("\n" + "="*70)
    print("Query: 'technical skills'")
    print("="*70)
    
    q_vecs = await embedder.embed(['technical skills'])
    results = vdb.search(query_vec=q_vecs[0], top_k=3)
    
    for i, r in enumerate(results, 1):
        text = r.payload.get("text", "")[:200]
        print(f"\n{i}. Score: {r.score:.4f}")
        print(f"   Text: {text}...")
    
    await embedder.close()


if __name__ == "__main__":
    asyncio.run(main())
