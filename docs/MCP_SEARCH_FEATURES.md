# MCP Search Features & Enhancement Proposals

## Current Implementation (V2.0)

### ✅ Existing Features

1. **Semantic Search via Vector Embeddings**
   - Profile-specific embedding models (Ollama or Cloudflare)
   - Qdrant vector database for similarity search
   - Configurable embedding dimensions per profile
   - Cosine/Euclidean/Dot distance metrics

2. **MCP Tool: `search_docs`**
   - Natural language queries
   - Profile-based document collections
   - Configurable `top_k` results (max 20)
   - Returns: scored results with text, metadata, doc_id

3. **Multi-Profile Support**
   - Isolated collections per profile
   - Profile-specific chunking strategies
   - Independent embedding backends
   - Per-profile vector dimensions

4. **Async/Concurrent Operations**
   - Concurrent embedding generation
   - Rate-limited API calls (pacing)
   - Non-blocking search operations

5. **Robust Error Handling**
   - Primary/fallback embedding backends
   - Retry logic with exponential backoff
   - Dimension validation
   - Profile not found errors

---

## 🚀 Proposed Enhancements

### 1. **Advanced Filtering & Metadata Search**

#### Current Limitation
Search returns global results from entire collection without metadata filtering.

#### Proposed Features
```python
@mcp.tool
async def search_docs(
    q: str,
    profile: str,
    top_k: int = 5,
    filters: Optional[dict] = None,  # NEW
    ctx: Context = None
) -> dict:
    """
    Filters support:
    - doc_id: Specific document(s)
    - doc_type: PDF, JSON, etc.
    - date_range: Ingestion timestamp
    - custom_metadata: Any user-defined fields
    """
```

**Example Usage:**
```json
{
  "q": "machine learning projects",
  "profile": "avi-cohen",
  "filters": {
    "doc_type": "pdf",
    "metadata.year": {"$gte": 2020}
  }
}
```

**Implementation Complexity:** Medium
- Modify `vdb.search()` to accept Qdrant filter conditions
- Update `routes/search_api.py` to parse filter parameter
- Document filter syntax in API docs

---

### 2. **Hybrid Search (Keyword + Semantic)**

#### Motivation
Pure vector search can miss exact keyword matches. Hybrid search combines:
- **Semantic**: Understanding meaning and context
- **Keyword**: Exact term matching (BM25, TF-IDF)

#### Proposed Implementation
```python
@mcp.tool
async def search_docs_hybrid(
    q: str,
    profile: str,
    top_k: int = 5,
    semantic_weight: float = 0.7,  # Semantic vs keyword balance
    ctx: Context = None
) -> dict:
    """
    Hybrid search combining vector similarity and keyword matching.
    
    Args:
        semantic_weight: 0.0-1.0, higher = more semantic, lower = more keyword
    """
```

**Algorithm:**
1. Perform vector search → semantic_scores
2. Perform BM25 keyword search → keyword_scores
3. Combine: `final_score = (semantic_weight * semantic_score) + ((1 - semantic_weight) * keyword_score)`
4. Re-rank and return top_k

**Implementation Complexity:** High
- Requires full-text index (Qdrant payload indexing)
- BM25 scoring algorithm implementation
- Score normalization across methods
- Extensive testing for relevance quality

**Alternative:** Use Qdrant's built-in payload filtering as pseudo-keyword search

---

### 3. **Query Result Highlighting**

#### Feature
Return text snippets with highlighted query terms for better context.

#### Proposed Output
```json
{
  "results": [
    {
      "text": "Full chunk text...",
      "highlighted": "...led multiple <mark>machine learning projects</mark> involving...",
      "score": 0.87,
      "doc_id": "avi_profile.json"
    }
  ]
}
```

**Implementation Complexity:** Low-Medium
- Extract key terms from query embedding (challenging for semantic)
- Alternative: Simple string matching on query words
- Wrap matches in `<mark>` tags
- Return both full text and highlighted version

---

### 4. **Search Result Caching**

#### Current Issue
Identical queries re-compute embeddings and search every time.

#### Proposed Solution
```python
# Add to search_docs tool
@lru_cache(maxsize=100)  # Or use Redis/TTL cache
async def _cached_search(query_hash: str, profile: str, top_k: int) -> dict:
    """Cache search results for N minutes."""
```

**Benefits:**
- Faster response for repeated queries
- Reduced embedding API calls (cost savings)
- Lower Qdrant load

**Implementation Complexity:** Low
- Use `functools.lru_cache` or `cachetools.TTLCache`
- Hash query + profile + top_k as cache key
- Add cache invalidation on new ingests
- Optional: Redis for distributed caching

**Configuration:**
```yaml
search:
  cache:
    enabled: true
    ttl_seconds: 300  # 5 minutes
    max_size: 100
```

---

### 5. **Multi-Vector Search (Multiple Queries)**

#### Use Case
Agent wants to search for multiple related concepts in one call.

#### Proposed Feature
```python
@mcp.tool
async def search_docs_multi(
    queries: List[str],  # Multiple queries
    profile: str,
    top_k_per_query: int = 5,
    merge_strategy: str = "deduplicate",  # or "ranked", "union"
    ctx: Context = None
) -> dict:
    """
    Search multiple queries and combine results.
    
    merge_strategy:
    - "deduplicate": Remove duplicates, keep highest score
    - "ranked": Interleave results from each query
    - "union": Concatenate all results
    """
```

**Example:**
```json
{
  "queries": [
    "machine learning experience",
    "Python projects",
    "AI research"
  ],
  "profile": "avi-cohen",
  "merge_strategy": "deduplicate"
}
```

**Implementation Complexity:** Medium
- Parallelize embedding + search for each query
- Implement merge strategies
- Handle score normalization across queries

---

### 6. **Relevance Feedback & Re-ranking**

#### Feature
Allow agent to provide feedback on search results to improve relevance.

#### Proposed API
```python
@mcp.tool
async def rerank_results(
    original_query: str,
    profile: str,
    result_ids: List[str],
    positive_ids: List[str],  # Results marked as relevant
    negative_ids: List[str],  # Results marked as irrelevant
    ctx: Context = None
) -> dict:
    """
    Re-rank results based on user feedback.
    Uses Rocchio algorithm or learned model.
    """
```

**Implementation Complexity:** High
- Implement Rocchio relevance feedback algorithm
- Or: Fine-tune embedding model (complex, requires infrastructure)
- Store feedback for continuous improvement

---

### 7. **Search Analytics & Logging**

#### Feature
Track search queries, results, and agent interactions for debugging and improvement.

#### Proposed Schema
```python
# SQLite table: search_logs
{
  "id": "uuid",
  "timestamp": "2025-11-14T10:30:00Z",
  "profile": "avi-cohen",
  "query": "machine learning projects",
  "top_k": 5,
  "results_count": 5,
  "latency_ms": 245,
  "embedding_backend": "ollama",
  "client_info": {"name": "claude-desktop", "version": "1.0"}
}
```

**Benefits:**
- Identify popular queries
- Detect slow searches
- Monitor embedding backend performance
- A/B test different chunking/embedding strategies

**Implementation Complexity:** Low
- Add logging to `search_docs` tool
- Store in SQLite (similar to jobs_db.py)
- Optional: Export to analytics platform

---

### 8. **Contextual Snippet Extraction**

#### Current Limitation
Results return full chunk text (may be large or lack context).

#### Proposed Enhancement
Return smaller, query-focused snippets with surrounding context.

#### Algorithm
1. Find sentence(s) most relevant to query within chunk
2. Extract 1-2 sentences before/after for context
3. Return snippet + full text

**Example:**
```json
{
  "text": "Full 500-word chunk...",
  "snippet": "...joined the company in 2020. Led multiple machine learning projects involving NLP. Focused on...",
  "snippet_char_range": [150, 250]
}
```

**Implementation Complexity:** Medium
- Sentence tokenization (spaCy, NLTK)
- Compute sentence-level embeddings
- Find best matching sentence
- Extract context window

---

### 9. **Cross-Profile Search**

#### Use Case
Search across multiple profiles simultaneously (e.g., "search all documentation").

#### Proposed Feature
```python
@mcp.tool
async def search_docs_multi_profile(
    q: str,
    profiles: List[str],  # Multiple profiles
    top_k_per_profile: int = 5,
    ctx: Context = None
) -> dict:
    """
    Search across multiple profile collections.
    Returns results grouped by profile.
    """
```

**Output:**
```json
{
  "query": "API authentication",
  "results_by_profile": {
    "dahua-camera": [...],
    "avi-cohen": [...],
    "iics": [...]
  },
  "combined_top_k": [...]  # Merged top results
}
```

**Implementation Complexity:** Medium
- Parallel search across collections
- Score normalization (different embedding models)
- Handle profile-specific metadata

---

### 10. **Streaming Search Results**

#### Feature
Stream results as they're found (useful for large result sets or slow embeddings).

#### Proposed Implementation
```python
@mcp.tool(streaming=True)  # If fastmcp supports
async def search_docs_stream(
    q: str,
    profile: str,
    top_k: int = 20,
    ctx: Context = None
) -> AsyncIterator[dict]:
    """
    Stream search results as they become available.
    """
    # Yield results incrementally
    for result in search_results:
        yield {"result": result, "index": i, "total": top_k}
```

**Benefits:**
- Lower perceived latency
- Better UX for large result sets
- Agent can process results incrementally

**Implementation Complexity:** Medium
- Requires streaming support in fastmcp
- Modify VDB search to return iterator
- Handle partial results gracefully

---

## 📊 Priority Matrix

| Feature | Impact | Complexity | Priority |
|---------|--------|------------|----------|
| **Search Result Caching** | High | Low | ⭐⭐⭐⭐⭐ P0 |
| **Advanced Filtering** | High | Medium | ⭐⭐⭐⭐ P1 |
| **Query Highlighting** | Medium | Low | ⭐⭐⭐ P2 |
| **Search Analytics** | Medium | Low | ⭐⭐⭐ P2 |
| **Contextual Snippets** | Medium | Medium | ⭐⭐⭐ P2 |
| **Multi-Query Search** | Medium | Medium | ⭐⭐ P3 |
| **Cross-Profile Search** | Low | Medium | ⭐⭐ P3 |
| **Hybrid Search** | High | High | ⭐ P4 |
| **Relevance Feedback** | Low | High | P5 |
| **Streaming Results** | Low | Medium | P5 |

---

## 🛠️ Implementation Roadmap

### Phase 1: Quick Wins (1-2 weeks)
- [ ] Search result caching (TTL-based)
- [ ] Query highlighting (simple keyword matching)
- [ ] Search analytics logging

### Phase 2: Enhanced Filtering (2-3 weeks)
- [ ] Metadata filtering in search_docs
- [ ] Date range filters
- [ ] Document type filters
- [ ] API documentation and examples

### Phase 3: Advanced Features (4-6 weeks)
- [ ] Contextual snippet extraction
- [ ] Multi-query search with merge strategies
- [ ] Cross-profile search
- [ ] Performance benchmarking

### Phase 4: Research & Experimentation (8+ weeks)
- [ ] Hybrid search (BM25 + vector)
- [ ] Relevance feedback system
- [ ] Streaming search results
- [ ] ML-based re-ranking

---

## 📝 Configuration Examples

### Proposed `config/learning.yaml` additions:

```yaml
profiles:
  avi-cohen:
    # ... existing config ...
    
    search:  # NEW search-specific settings
      cache:
        enabled: true
        ttl_seconds: 300
        max_size: 100
      
      highlighting:
        enabled: true
        max_snippet_length: 200
      
      analytics:
        enabled: true
        log_to_db: true
      
      filters:
        allowed_fields:
          - doc_id
          - doc_type
          - ingest_timestamp
          - metadata.year
      
      default_top_k: 5
      max_top_k: 50  # Increase from current 20
      
      hybrid_search:
        enabled: false  # Future feature
        semantic_weight: 0.7
```

---

## 🧪 Testing Recommendations

### Current Test Coverage Gaps
1. No integration tests for MCP tools (tests/test_mcp_tools.py are skipped)
2. No performance/load testing for search
3. No relevance quality testing

### Proposed Tests
```python
# tests/test_search_features.py

@pytest.mark.asyncio
async def test_search_caching():
    """Verify cache hits for identical queries."""
    result1 = await search_docs("test", "avi-cohen", 5)
    result2 = await search_docs("test", "avi-cohen", 5)
    assert result1 == result2  # Should be cached

@pytest.mark.asyncio
async def test_search_with_filters():
    """Test metadata filtering."""
    results = await search_docs(
        "projects",
        "avi-cohen",
        filters={"doc_type": "json"}
    )
    assert all(r["doc_type"] == "json" for r in results["results"])

@pytest.mark.benchmark
async def test_search_performance():
    """Benchmark search latency."""
    import time
    start = time.time()
    await search_docs("machine learning", "avi-cohen", 10)
    elapsed = time.time() - start
    assert elapsed < 1.0, "Search should complete under 1 second"
```

---

## 📚 Additional Resources

### Relevant Technologies
- **Qdrant Filtering**: https://qdrant.tech/documentation/concepts/filtering/
- **BM25 Algorithm**: https://en.wikipedia.org/wiki/Okapi_BM25
- **Rocchio Feedback**: https://nlp.stanford.edu/IR-book/html/htmledition/rocchio-classification-1.html
- **Hybrid Search**: https://weaviate.io/blog/hybrid-search-explained

### Similar MCP Implementations
- Anthropic's filesystem MCP server (caching, filtering)
- GitHub MCP server (multi-query, pagination)
- Brave Search MCP (hybrid search patterns)

---

## ✅ Summary

**Current State:** V2.0 provides solid foundation with semantic search, multi-profile support, and async operations.

**Recommended Next Steps:**
1. Implement caching (highest ROI)
2. Add advanced filtering (most requested)
3. Create comprehensive integration tests
4. Document usage patterns for AI agents

**Long-term Vision:** Transform from basic vector search to intelligent, context-aware retrieval system with agent feedback loops and continuous improvement.
