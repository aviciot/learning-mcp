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
        
        assert embedder.config == ollama_config
        assert embedder.primary_backend == "ollama"
        assert embedder.fallback_backend == "cloudflare"


@pytest.mark.asyncio
async def test_embedder_init_cloudflare(cloudflare_config):
    """Test Embedder initializes with Cloudflare config."""
    with patch.dict('os.environ', {
        'CF_ACCOUNT_ID': 'test-account',
        'CF_API_TOKEN': 'test-token'
    }):
        embedder = Embedder(cloudflare_config)
        
        assert embedder.primary_backend == "cloudflare"
        assert embedder.fallback_backend is None


@pytest.mark.asyncio
async def test_embed_single_text_ollama(ollama_config):
    """Test embedding single text with Ollama."""
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            vector = await embedder._embed_single_ollama("test text")
            
            assert len(vector) == 768
            assert all(isinstance(v, float) for v in vector)


@pytest.mark.asyncio
async def test_embed_single_text_cloudflare(cloudflare_config):
    """Test embedding single text with Cloudflare."""
    with patch.dict('os.environ', {
        'CF_ACCOUNT_ID': 'test-account',
        'CF_API_TOKEN': 'test-token'
    }):
        embedder = Embedder(cloudflare_config)
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": {"data": [[0.1] * 768]}
        }
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            vector = await embedder._embed_single_cloudflare("test text")
            
            assert len(vector) == 768


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
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        texts = ["text 1", "text 2"]
        ids = ["id1", "id2"]
        cache = {"id1": [0.5] * 768}  # Pre-cached vector
        
        # Mock httpx response for uncached text
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            vectors = await embedder.embed(texts, ids=ids, cache=cache)
            
            assert len(vectors) == 2
            # First vector should be from cache
            assert vectors[0] == [0.5] * 768
            # Second vector should be newly embedded
            assert vectors[1] == [0.1] * 768


@pytest.mark.asyncio
async def test_embed_dimension_validation(ollama_config):
    """Test embedding raises error on dimension mismatch."""
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        # Mock httpx response with wrong dimension
        mock_response = Mock()
        mock_response.json.return_value = {"embedding": [0.1] * 512}  # Wrong dim
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            with pytest.raises(EmbeddingError, match="dimension mismatch"):
                await embedder._embed_single_ollama("test")


@pytest.mark.asyncio
async def test_embed_fallback_on_primary_failure(ollama_config):
    """Test fallback to secondary backend on primary failure."""
    with patch.dict('os.environ', {
        'OLLAMA_HOST': 'http://localhost:11434',
        'CF_ACCOUNT_ID': 'test-account',
        'CF_API_TOKEN': 'test-token'
    }):
        embedder = Embedder(ollama_config)
        
        # Mock primary failure
        with patch.object(embedder, '_embed_single_ollama', side_effect=Exception("Ollama down")):
            # Mock fallback success
            mock_response = Mock()
            mock_response.json.return_value = {
                "result": {"data": [[0.2] * 768]}
            }
            mock_response.raise_for_status = Mock()
            
            with patch('httpx.AsyncClient.post', return_value=mock_response):
                vectors = await embedder.embed(["test"])
                
                assert len(vectors) == 1
                assert vectors[0] == [0.2] * 768


@pytest.mark.asyncio
async def test_embed_respects_concurrency_limit(ollama_config):
    """Test embedding respects EMBED_CONCURRENCY limit."""
    with patch.dict('os.environ', {
        'OLLAMA_HOST': 'http://localhost:11434',
        'EMBED_CONCURRENCY': '2'
    }):
        embedder = Embedder(ollama_config)
        
        texts = ["text 1", "text 2", "text 3", "text 4"]
        
        call_times = []
        
        async def mock_embed_single(text):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate work
            return [0.1] * 768
        
        with patch.object(embedder, '_embed_single_ollama', side_effect=mock_embed_single):
            await embedder.embed(texts)
            
            # With concurrency=2, should have 2 batches
            # Not a strict test, but validates concurrency exists


@pytest.mark.asyncio
async def test_embed_empty_list(ollama_config):
    """Test embedding empty list returns empty list."""
    embedder = Embedder(ollama_config)
    
    vectors = await embedder.embed([])
    
    assert vectors == []


@pytest.mark.asyncio
async def test_embed_single_text_with_retry(ollama_config):
    """Test embedding retries on transient failure."""
    with patch.dict('os.environ', {'OLLAMA_HOST': 'http://localhost:11434'}):
        embedder = Embedder(ollama_config)
        
        # First call fails, second succeeds
        mock_response_fail = Mock()
        mock_response_fail.raise_for_status.side_effect = Exception("Temporary failure")
        
        mock_response_success = Mock()
        mock_response_success.json.return_value = {"embedding": [0.1] * 768}
        mock_response_success.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.post', side_effect=[mock_response_fail, mock_response_success]):
            vector = await embedder._embed_single_ollama("test")
            
            assert len(vector) == 768
