"""Integration test for plan_api_call MCP tool.

This test validates the search logic used by plan_api_call before calling AutoGen.

Requirements:
- Running Qdrant instance (vector-db service)
- Ingested data in 'informatica-cloud' collection
- Embedding backend (Ollama or Cloudflare Workers AI)

CI/CD: Uses Cloudflare Workers AI for embeddings (no Ollama needed).
"""
import asyncio
import sys
import pytest

sys.path.insert(0, 'src')

from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig
from learning_mcp.vdb import VDB


pytestmark = pytest.mark.asyncio


async def test_plan_api_call_search_logic():
    """Test that plan_api_call can search and format results without errors.
    
    This tests the core search logic that plan_api_call uses before calling AutoGen.
    If this fails, plan_api_call will fail too.
    """
    profile = "informatica-cloud"
    goal = "create mapping task"
    
    # Get profile config
    prof = get_profile(profile)
    assert prof is not None, f"Profile {profile} not found"
    
    # Create embedder
    ecfg = EmbeddingConfig.from_profile(prof)
    embedder = Embedder(ecfg)
    
    # Create VDB
    vcfg = prof.get("vectordb", {}) or {}
    vdb = VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection", profile),
        dim=ecfg.dim,
        distance=vcfg.get("distance", "cosine")
    )
    
    try:
        # Embed query (this is what plan_api_call does)
        query_vecs = await embedder.embed([goal])
        query_vec = query_vecs[0]
        
        # Search Qdrant (this is what plan_api_call does)
        results = vdb.search(query_vec=query_vec, top_k=10)
        
        # THIS IS THE CRITICAL LINE THAT WAS FAILING
        # Format results for AutoGen (extract text from payloads)
        context_chunks = [r.payload.get("text", "") for r in results]
        
        # Assertions
        assert isinstance(results, list), f"Expected list, got {type(results)}"
        assert len(results) > 0, "Expected at least one result"
        
        first_result = results[0]
        assert hasattr(first_result, 'payload'), "Result should have payload attribute"
        assert hasattr(first_result, 'score'), "Result should have score attribute"
        assert hasattr(first_result, 'id'), "Result should have id attribute"
        
        assert isinstance(first_result.payload, dict), "Payload should be dict"
        assert 'text' in first_result.payload, "Payload should have 'text' key"
        
        assert isinstance(context_chunks, list), "Context chunks should be list"
        assert all(isinstance(chunk, str) for chunk in context_chunks), "All chunks should be strings"
        
        print(f"✅ Test passed: Found {len(results)} results, formatted {len(context_chunks)} context chunks")
        
    finally:
        await embedder.close()


async def test_vdb_search_returns_list():
    """Test that vdb.search() returns a list of ScoredPoint objects.
    
    This is a regression test for the bug where query_points() returned
    QueryResponse object instead of the .points list.
    """
    profile = "informatica-cloud"
    
    prof = get_profile(profile)
    vcfg = prof.get("vectordb", {}) or {}
    ecfg = EmbeddingConfig.from_profile(prof)
    
    vdb = VDB(
        url=vcfg.get("url"),
        collection=vcfg.get("collection", profile),
        dim=ecfg.dim,
        distance=vcfg.get("distance", "cosine")
    )
    
    embedder = Embedder(ecfg)
    
    try:
        vecs = await embedder.embed(['test query'])
        results = vdb.search(query_vec=vecs[0], top_k=1)
        
        # Critical assertions
        assert isinstance(results, list), f"vdb.search() should return list, got {type(results)}"
        
        if results:
            first = results[0]
            # Should be ScoredPoint with these attributes
            assert hasattr(first, 'id'), "Result should have 'id'"
            assert hasattr(first, 'score'), "Result should have 'score'"
            assert hasattr(first, 'payload'), "Result should have 'payload'"
            
            # Payload should be dict
            assert isinstance(first.payload, dict), f"Payload should be dict, got {type(first.payload)}"
            
        print(f"✅ vdb.search() returns proper list of ScoredPoint objects")
        
    finally:
        await embedder.close()


if __name__ == "__main__":
    print("Running integration tests for plan_api_call...")
    print("\nTest 1: VDB search return type")
    asyncio.run(test_vdb_search_returns_list())
    
    print("\nTest 2: Plan API call search logic")
    asyncio.run(test_plan_api_call_search_logic())
    
    print("\n✅ All tests passed!")
