"""Test search for 'education' after json_loader update."""
import asyncio
import sys
sys.path.insert(0, 'src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def test_education_search():
    """Test that 'education' query now returns relevant chunks."""
    print("🧪 Testing 'education' search after json_loader update...")
    print("="*80)
    
    # Setup
    profile = "avi-cohen"
    q = "education"
    top_k = 10  # Increased to see more results
    
    print(f"Profile: {profile}")
    print(f"Query: '{q}'")
    print(f"Top K: {top_k}\n")
    
    try:
        # Get profile config
        prof = get_profile(profile)
        
        # Create embedder
        ecfg = EmbeddingConfig.from_profile(prof)
        embedder = Embedder(ecfg)
        
        # Embed query
        print("⏳ Embedding query...")
        query_vecs = await embedder.embed([q])
        query_vec = query_vecs[0]
        print(f"✅ Query embedded (vector dim: {len(query_vec)})\n")
        
        # Create VDB
        vcfg = prof.get("vectordb", {}) or {}
        vdb = VDB(
            url=vcfg.get("url"),
            collection=vcfg.get("collection", profile),
            dim=ecfg.dim,
            distance=vcfg.get("distance", "cosine")
        )
        
        # Search
        print("🔍 Searching...")
        results = vdb.search(
            query_vec=query_vec,
            top_k=top_k
        )
        print(f"✅ Found {len(results)} results\n")
        print("="*80)
        
        # Display results
        print("\n📊 RESULTS:\n")
        for i, r in enumerate(results, 1):
            text = r.payload.get("text", "")
            path = r.payload.get("path", "N/A")
            score = r.score
            
            print(f"Result #{i} - Score: {score:.4f}")
            print(f"Path: {path}")
            print(f"Text: {text[:250]}")
            print("-"*80)
        
        # Check if we got education-related results
        education_results = [r for r in results if 'education' in r.payload.get("text", "").lower()]
        
        await embedder.close()
        
        print(f"\n📈 Found {len(education_results)} results with 'education' in text")
        
        if education_results:
            print("\n✅ SUCCESS! Found education-related content:")
            for r in education_results:
                print(f"  • Score {r.score:.4f}: {r.payload.get('text', '')[:100]}")
        else:
            print("\n⚠️  WARNING: No 'education' keyword in top 10 results")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_education_search())
    sys.exit(0 if success else 1)
