"""Unit tests for embeddings module."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

import sys
sys.path.insert(0, 'src')
from learning_mcp.embeddings import Embedder, EmbeddingConfig, EmbeddingError


@pytest.fixture
def ollama_config():
    """Embedding config using Ollama backend."""
    return EmbeddingConfig(
        dim=768,
        primary="ollama",
        fallback="cloudflare",
        ollama_host="http://localhost:11434",
        ollama_model="nomic-embed-text"
    )


@pytest.fixture
def cloudflare_config():
    """Embedding config using Cloudflare backend."""
    return EmbeddingConfig(
        dim=768,
        primary="cloudflare",
        fallback=None,
        cf_account_id="test-account",
        cf_api_token="test-token",
        cf_model="@cf/baai/bge-base-en-v1.5"
    )


@pytest.mark.asyncio
async def test_embedder_init_ollama(ollama_config):
    """Test Embedder initializes with Ollama config."""
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        assert embedder.cfg == ollama_config
        assert embedder.primary == "ollama"
        assert embedder.fallback == "cloudflare"


@pytest.mark.asyncio
async def test_embedder_init_cloudflare(cloudflare_config):
    """Test Embedder initializes with Cloudflare config."""
    with patch.dict('os.environ', {
        'CF_ACCOUNT_ID': 'test-account',
        'CF_API_TOKEN': 'test-token'
    }):
        embedder = Embedder(cloudflare_config)
        
        assert embedder.primary == "cloudflare"
        assert embedder.fallback is None


@pytest.mark.asyncio
async def test_embed_single_text_ollama(ollama_config):
    """Test embedding single text with Ollama."""
    embedder = Embedder(ollama_config)
    
    # Mock the internal _embed_ollama method
    async def mock_embed_ollama(texts, concurrency):
        return [[0.1] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_embed_ollama):
        vectors = await embedder.embed(["test text"])
        
        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert all(isinstance(v, float) for v in vectors[0])


@pytest.mark.asyncio
async def test_embed_single_text_cloudflare(cloudflare_config):
    """Test embedding single text with Cloudflare."""
    embedder = Embedder(cloudflare_config)
    
    # Mock the internal _embed_cloudflare method
    async def mock_embed_cloudflare(texts, concurrency):
        return [[0.1] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_cloudflare', side_effect=mock_embed_cloudflare):
        vectors = await embedder.embed(["test text"])
        
        assert len(vectors) == 1
        assert len(vectors[0]) == 768


@pytest.mark.asyncio
async def test_embed_batch_texts(ollama_config):
    """Test embedding batch of texts."""
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        texts = ["text 1", "text 2", "text 3"]
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            vectors = await embedder.embed(texts)
            
            assert len(vectors) == 3
            assert all(len(v) == 768 for v in vectors)


@pytest.mark.asyncio
async def test_embed_with_cache(ollama_config):
    """Test embedding uses cache when available."""
    embedder = Embedder(ollama_config)
    
    texts = ["cached text", "new text"]
    ids = ["id1", "id2"]
    cache = {"id1": [0.5] * 768}  # id1 is cached
    
    # Mock for uncached text
    async def mock_embed_ollama(texts, concurrency):
        return [[0.1] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_embed_ollama):
        vectors = await embedder.embed(texts, ids=ids, cache=cache)
        
        assert len(vectors) == 2
        # First vector should be from cache
        assert vectors[0] == [0.5] * 768
        # Second vector should be newly embedded
        assert vectors[1] == [0.1] * 768


@pytest.mark.asyncio
async def test_embed_dimension_validation(ollama_config):
    """Test embedding raises error on dimension mismatch."""
    embedder = Embedder(ollama_config)
    
    # Mock return wrong dimension
    async def mock_embed_wrong_dim(texts, concurrency):
        return [[0.1] * 512 for _ in texts]  # Wrong dim (512 instead of 768)
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_embed_wrong_dim):
        with pytest.raises(EmbeddingError, match="dimension mismatch"):
            await embedder.embed(["test"])


@pytest.mark.asyncio
async def test_embed_fallback_on_primary_failure(ollama_config):
    """Test fallback to secondary backend on primary failure."""
    embedder = Embedder(ollama_config)
    
    # Mock primary failure
    async def mock_primary_fail(texts, concurrency):
        raise Exception("Ollama down")
    
    # Mock fallback success
    async def mock_fallback_success(texts, concurrency):
        return [[0.2] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_primary_fail):
        with patch.object(embedder, '_embed_cloudflare', side_effect=mock_fallback_success):
            vectors = await embedder.embed(["test"])
            
            assert len(vectors) == 1
            assert vectors[0] == [0.2] * 768


@pytest.mark.asyncio
async def test_embed_respects_concurrency_limit(ollama_config):
    """Test embedding respects EMBED_CONCURRENCY limit."""
    embedder = Embedder(ollama_config)
    
    texts = ["text 1", "text 2", "text 3", "text 4"]
    
    # Mock embed to verify it's called
    async def mock_embed_ollama(texts, concurrency):
        assert concurrency >= 1  # Verify concurrency parameter exists
        return [[0.1] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_embed_ollama):
        vectors = await embedder.embed(texts)
        assert len(vectors) == 4


@pytest.mark.asyncio
async def test_embed_empty_list(ollama_config):
    """Test embedding empty list returns empty list."""
    embedder = Embedder(ollama_config)
    
    vectors = await embedder.embed([])
    
    assert vectors == []


@pytest.mark.asyncio
async def test_embed_single_text_with_retry(ollama_config):
    """Test embedding retries on transient failure."""
    embedder = Embedder(ollama_config)
    
    call_count = 0
    
    async def mock_embed_with_retry(texts, concurrency):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Temporary failure")
        return [[0.1] * 768 for _ in texts]
    
    with patch.object(embedder, '_embed_ollama', side_effect=mock_embed_with_retry):
        # With fallback=None and retries, should eventually succeed
        embedder.fallback = None  # Disable fallback to test retry logic
        vectors = await embedder.embed(["test"])
        
        assert len(vectors) == 1
        assert call_count >= 2  # Should have retried
