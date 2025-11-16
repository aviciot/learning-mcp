"""Simple integration test using HTTP to MCP server (workaround)."""
import asyncio
import sys
sys.path.insert(0, '/app/src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


async def test_search_quality():
    """Test search results after metadata removal."""
    print("=" * 70)
    print("MCP SEARCH INTEGRATION TEST - Avi Cohen Profile")
    print("=" * 70)
    
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
    
    test_queries = [
        ("Python FastAPI Docker", "Should find skills/tech"),
        ("AI agent experience", "Should find AI work at Shift4"),
        ("Learning MCP project", "Should find project details"),
        ("skills", "Should find skills section NOT metadata"),
    ]
    
    all_passed = True
    
    for query, expectation in test_queries:
        print(f"\n{'─'*70}")
        print(f"Query: '{query}'")
        print(f"Expected: {expectation}")
        print(f"{'─'*70}")
        
        q_vecs = await embedder.embed([query])
        results = vdb.search(query_vec=q_vecs[0], top_k=3)
        
        print(f"Results: {len(results)}")
        
        for i, r in enumerate(results, 1):
            text_preview = r.payload.get("text", "")[:150].replace('\n', ' ')
            print(f"\n  {i}. Score: {r.score:.4f}")
            print(f"     Text: {text_preview}...")
        
        # Check for metadata pollution
        all_text = " ".join([r.payload.get("text", "").lower() for r in results])
        if "ingest_sections" in all_text or "collection_suffix_by_dim" in all_text:
            print(f"\n  ❌ FAIL: Found metadata pollution!")
            all_passed = False
        else:
            print(f"\n  ✅ PASS: No metadata pollution")
        
        # Check relevance for specific queries
        if query == "Python FastAPI Docker":
            if any(term in all_text for term in ["python", "fastapi", "docker"]):
                print(f"  ✅ PASS: Found relevant tech terms")
            else:
                print(f"  ❌ FAIL: Missing expected tech terms")
                all_passed = False
        
        elif query == "Learning MCP project":
            if "learning mcp" in all_text or "qdrant" in all_text:
                print(f"  ✅ PASS: Found project content")
            else:
                print(f"  ❌ FAIL: Missing project content")
                all_passed = False
    
    await embedder.close()
    
    print(f"\n{'='*70}")
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print(f"{'='*70}\n")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_search_quality())
    sys.exit(0 if success else 1)
