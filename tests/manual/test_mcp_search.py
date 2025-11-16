"""Quick test to verify MCP search_docs function works."""
import asyncio
import sys
sys.path.insert(0, 'src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def test_search_docs():
    """Test the search_docs logic outside of MCP context."""
    print("🧪 Testing search_docs function...")
    
    # Setup (mimicking what search_docs does)
    profile = "avi-cohen"
    q = "projects"
    top_k = 3
    
    print(f"  Profile: {profile}")
    print(f"  Query: {q}")
    print(f"  Top K: {top_k}\n")
    
    try:
        # Get profile config
        prof = get_profile(profile)
        print(f"✅ Profile loaded: {profile}")
        
        # Create embedder
        ecfg = EmbeddingConfig.from_profile(prof)
        embedder = Embedder(ecfg)
        print(f"✅ Embedder created (dim={ecfg.dim}, backend={ecfg.primary})")
        
        # Embed query
        print(f"⏳ Embedding query...")
        query_vecs = await embedder.embed([q])
        query_vec = query_vecs[0]
        print(f"✅ Query embedded (vector length: {len(query_vec)})")
        
        # Create VDB
        vcfg = prof.get("vectordb", {}) or {}
        vdb = VDB(
            url=vcfg.get("url"),
            collection=vcfg.get("collection", profile),
            dim=ecfg.dim,
            distance=vcfg.get("distance", "cosine")
        )
        print(f"✅ VDB created (collection: {vcfg.get('collection', profile)})")
        
        # Search
        print(f"⏳ Searching...")
        results = vdb.search(
            query_vec=query_vec,
            top_k=top_k
        )
        print(f"✅ Search complete: {len(results)} results\n")
        
        # Display results
        print("📊 Results:")
        for i, r in enumerate(results, 1):
            text_preview = r.payload.get("text", "")[:100]
            print(f"  {i}. Score: {r.score:.4f}")
            print(f"     Text: {text_preview}...")
            print(f"     Doc: {r.payload.get('doc_id', 'N/A')}\n")
        
        await embedder.close()
        print("✅ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_search_docs())
    sys.exit(0 if success else 1)
