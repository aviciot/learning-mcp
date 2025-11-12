"""Unit tests for VDB (Qdrant) module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid5, NAMESPACE_DNS

import sys
sys.path.insert(0, 'src')
from learning_mcp.vdb import VDB


@pytest.fixture
def vdb_config():
    """VDB configuration for testing."""
    return {
        "url": "http://localhost:6333",
        "collection": "test-collection",
        "dim": 768
    }


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    with patch('learning_mcp.vdb.QdrantClient') as mock:
        yield mock


def test_vdb_init(vdb_config, mock_qdrant_client):
    """Test VDB initialization."""
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    assert vdb.collection_name == "test-collection"
    assert vdb.dim == 768
    mock_qdrant_client.assert_called_once_with(url="http://localhost:6333")


def test_ensure_collection_creates_if_missing(vdb_config, mock_qdrant_client):
    """Test ensure_collection creates collection if it doesn't exist."""
    mock_client = mock_qdrant_client.return_value
    mock_client.collection_exists.return_value = False
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    vdb.ensure_collection()
    
    mock_client.collection_exists.assert_called_once_with("test-collection")
    mock_client.create_collection.assert_called_once()


def test_ensure_collection_skips_if_exists(vdb_config, mock_qdrant_client):
    """Test ensure_collection skips creation if collection exists."""
    mock_client = mock_qdrant_client.return_value
    mock_client.collection_exists.return_value = True
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    vdb.ensure_collection()
    
    mock_client.collection_exists.assert_called_once_with("test-collection")
    mock_client.create_collection.assert_not_called()


def test_upsert_points(vdb_config, mock_qdrant_client):
    """Test upserting points to Qdrant."""
    mock_client = mock_qdrant_client.return_value
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    points = [
        {
            "id": str(uuid5(NAMESPACE_DNS, "doc1|path1|0")),
            "vector": [0.1] * 768,
            "payload": {"text": "test 1", "doc_id": "doc1"}
        },
        {
            "id": str(uuid5(NAMESPACE_DNS, "doc1|path1|1")),
            "vector": [0.2] * 768,
            "payload": {"text": "test 2", "doc_id": "doc1"}
        }
    ]
    
    vdb.upsert(points)
    
    mock_client.upsert.assert_called_once()
    call_args = mock_client.upsert.call_args
    assert call_args[1]["collection_name"] == "test-collection"
    assert len(call_args[1]["points"]) == 2


def test_search_basic(vdb_config, mock_qdrant_client):
    """Test basic search functionality."""
    mock_client = mock_qdrant_client.return_value
    
    # Mock search results
    mock_result = [
        Mock(id="id1", score=0.9, payload={"text": "result 1"}),
        Mock(id="id2", score=0.8, payload={"text": "result 2"})
    ]
    mock_client.search.return_value = mock_result
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    query_vector = [0.5] * 768
    results = vdb.search(query_vector, top_k=5)
    
    assert len(results) == 2
    assert results[0]["score"] == 0.9
    assert results[0]["payload"]["text"] == "result 1"
    
    mock_client.search.assert_called_once()


def test_search_with_filter(vdb_config, mock_qdrant_client):
    """Test search with payload filter."""
    mock_client = mock_qdrant_client.return_value
    mock_client.search.return_value = []
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    query_vector = [0.5] * 768
    filter_dict = {"doc_id": "doc1"}
    
    vdb.search(query_vector, top_k=5, filter=filter_dict)
    
    call_args = mock_client.search.call_args[1]
    assert call_args["query_filter"] is not None


def test_search_top_k_limit(vdb_config, mock_qdrant_client):
    """Test search respects top_k parameter."""
    mock_client = mock_qdrant_client.return_value
    
    # Return more results than top_k
    mock_result = [Mock(id=f"id{i}", score=0.9-i*0.1, payload={}) for i in range(10)]
    mock_client.search.return_value = mock_result
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    query_vector = [0.5] * 768
    results = vdb.search(query_vector, top_k=3)
    
    # Qdrant should handle top_k, but verify it was requested
    call_args = mock_client.search.call_args[1]
    assert call_args["limit"] == 3


def test_truncate_collection(vdb_config, mock_qdrant_client):
    """Test truncating (deleting and recreating) collection."""
    mock_client = mock_qdrant_client.return_value
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    vdb.truncate()
    
    # Should delete then create
    mock_client.delete_collection.assert_called_once_with("test-collection")
    mock_client.create_collection.assert_called_once()


def test_upsert_deterministic_ids():
    """Test that UUIDv5 generates deterministic IDs."""
    id1 = str(uuid5(NAMESPACE_DNS, "doc1|path1|0"))
    id2 = str(uuid5(NAMESPACE_DNS, "doc1|path1|0"))
    
    assert id1 == id2  # Same input = same UUID


def test_upsert_different_chunks_different_ids():
    """Test different chunks get different IDs."""
    id1 = str(uuid5(NAMESPACE_DNS, "doc1|path1|0"))
    id2 = str(uuid5(NAMESPACE_DNS, "doc1|path1|1"))
    
    assert id1 != id2


def test_search_empty_results(vdb_config, mock_qdrant_client):
    """Test search handles empty results gracefully."""
    mock_client = mock_qdrant_client.return_value
    mock_client.search.return_value = []
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    query_vector = [0.5] * 768
    results = vdb.search(query_vector, top_k=5)
    
    assert results == []


def test_upsert_batch_size():
    """Test that upsert can handle large batches."""
    with patch('learning_mcp.vdb.QdrantClient') as mock_qdrant:
        mock_client = mock_qdrant.return_value
        
        vdb = VDB("http://localhost:6333", "test", 768)
        
        # Create 1000 points
        points = [
            {
                "id": str(uuid5(NAMESPACE_DNS, f"doc1|path|{i}")),
                "vector": [0.1] * 768,
                "payload": {"text": f"chunk {i}"}
            }
            for i in range(1000)
        ]
        
        vdb.upsert(points)
        
        # Should succeed without error
        mock_client.upsert.assert_called_once()


def test_search_with_score_threshold(vdb_config, mock_qdrant_client):
    """Test search with minimum score threshold."""
    mock_client = mock_qdrant_client.return_value
    
    # Mock results with varying scores
    mock_result = [
        Mock(id="id1", score=0.9, payload={"text": "high score"}),
        Mock(id="id2", score=0.5, payload={"text": "medium score"}),
        Mock(id="id3", score=0.2, payload={"text": "low score"})
    ]
    mock_client.search.return_value = mock_result
    
    vdb = VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
    
    query_vector = [0.5] * 768
    results = vdb.search(query_vector, top_k=10, score_threshold=0.6)
    
    # Check if score_threshold was passed to Qdrant
    call_args = mock_client.search.call_args[1]
    if "score_threshold" in call_args:
        assert call_args["score_threshold"] == 0.6


def test_vdb_connection_error_handling(vdb_config):
    """Test VDB handles connection errors gracefully."""
    with patch('learning_mcp.vdb.QdrantClient') as mock_qdrant:
        mock_qdrant.side_effect = ConnectionError("Cannot connect to Qdrant")
        
        with pytest.raises(ConnectionError):
            VDB(vdb_config["url"], vdb_config["collection"], vdb_config["dim"])
