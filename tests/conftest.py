"""Pytest configuration and shared fixtures."""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def sample_pdf_path():
    """Path to sample PDF for testing."""
    return Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.fixture
def sample_json_path():
    """Path to sample JSON for testing."""
    return Path(__file__).parent / "fixtures" / "sample.json"


@pytest.fixture
def test_config():
    """Sample configuration for testing."""
    return {
        "embedding": {
            "backend": {"primary": "ollama", "fallback": None},
            "model": "nomic-embed-text",
            "dim": 768
        },
        "vectordb": {
            "url": "http://localhost:6333",
            "collection": "test-collection"
        },
        "chunking": {
            "strategy": "sentence",
            "max_tokens": 256
        }
    }


@pytest.fixture
def sample_chunks():
    """Sample document chunks for testing."""
    return [
        {
            "text": "This is the first chunk of text.",
            "metadata": {"doc_id": "doc1", "chunk_idx": 0}
        },
        {
            "text": "This is the second chunk of text.",
            "metadata": {"doc_id": "doc1", "chunk_idx": 1}
        },
        {
            "text": "This is the third chunk of text.",
            "metadata": {"doc_id": "doc1", "chunk_idx": 2}
        }
    ]


@pytest.fixture
def sample_vectors():
    """Sample embedding vectors for testing."""
    return [
        [0.1] * 768,
        [0.2] * 768,
        [0.3] * 768
    ]
