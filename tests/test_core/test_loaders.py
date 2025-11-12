"""Unit tests for document loaders."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json

import sys
sys.path.insert(0, 'src')
from learning_mcp.document_loaders import collect_chunks, known_document_count
from learning_mcp.json_loader import load_json
from learning_mcp.pdf_loader import load_pdf_structured


def test_known_document_count():
    """Test counting documents in profile."""
    profile = {
        "documents": [
            {"type": "pdf", "path": "/app/data/doc1.pdf"},
            {"type": "json", "path": "/app/data/doc2.json"},
            {"type": "pdf", "path": "/app/data/doc3.pdf"}
        ]
    }
    
    count = known_document_count(profile)
    assert count == 3


def test_load_json_basic():
    """Test loading simple JSON file."""
    json_content = json.dumps({
        "name": "Test Person",
        "skills": ["Python", "FastAPI"],
        "experience": {"years": 5, "role": "Engineer"}
    })
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/path.json")
            
            assert len(chunks) > 0
            assert all("text" in chunk for chunk in chunks)
            assert all("metadata" in chunk for chunk in chunks)


def test_load_json_with_metadata():
    """Test JSON loader includes metadata."""
    json_content = json.dumps({"name": "Test"})
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/test.json")
            
            for chunk in chunks:
                assert chunk["metadata"]["source"] == "/fake/test.json"


def test_load_json_nested_structure():
    """Test JSON loader handles nested objects."""
    json_content = json.dumps({
        "person": {
            "name": "Alice",
            "address": {
                "city": "NYC",
                "country": "USA"
            }
        }
    })
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/nested.json")
            
            # Should flatten nested structure into chunks
            assert len(chunks) > 0
            text_content = " ".join(chunk["text"] for chunk in chunks)
            assert "Alice" in text_content or "person" in text_content


def test_load_json_array():
    """Test JSON loader handles arrays."""
    json_content = json.dumps([
        {"name": "Item 1"},
        {"name": "Item 2"},
        {"name": "Item 3"}
    ])
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/array.json")
            
            assert len(chunks) >= 3  # Should have at least one chunk per item


def test_load_json_invalid():
    """Test JSON loader handles invalid JSON."""
    invalid_json = "{ invalid json content"
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=invalid_json)):
            with pytest.raises(json.JSONDecodeError):
                load_json("/fake/invalid.json")


def test_load_pdf_structured_basic():
    """Test loading PDF file (mocked)."""
    # Mock pypdf PdfReader
    with patch('learning_mcp.pdf_loader.PdfReader') as mock_reader:
        # Setup mock PDF with 2 pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2 content"
        
        mock_reader.return_value.pages = [mock_page1, mock_page2]
        
        chunks = load_pdf_structured(
            "/fake/test.pdf", 
            chunk_size=256, 
            chunk_overlap=50,
            doc_id="test-doc"
        )
        
        assert len(chunks) > 0
        assert all("text" in chunk for chunk in chunks)
        assert all("metadata" in chunk for chunk in chunks)


def test_load_pdf_metadata():
    """Test PDF loader includes metadata."""
    with patch('learning_mcp.pdf_loader.PdfReader') as mock_reader:
        mock_page = Mock()
        mock_page.extract_text.return_value = "Test content"
        mock_reader.return_value.pages = [mock_page]
        
        chunks = load_pdf_structured(
            "/fake/test.pdf", 
            chunk_size=256, 
            chunk_overlap=50,
            doc_id="test-doc"
        )
        
        for chunk in chunks:
            assert chunk["metadata"]["source"] == "/fake/test.pdf"
            assert "page" in chunk["metadata"]


def test_collect_chunks_mixed_types():
    """Test collect_chunks handles mixed document types."""
    profile = {
        "name": "test-profile",
        "documents": [
            {"type": "json", "path": "/app/tests/fixtures/sample.json"}
        ]
    }
    
    # Mock file reading
    json_content = json.dumps({"test": "data"})
    with patch("builtins.open", mock_open(read_data=json_content)):
        chunks, stats = collect_chunks(profile, chunk_size=256, chunk_overlap=50)
        
        assert len(chunks) > 0
        assert "files_total" in stats
        assert "pages_total" in stats


def test_load_pdf_empty_pages():
    """Test PDF loader handles empty pages gracefully."""
    with patch('learning_mcp.pdf_loader.PdfReader') as mock_reader:
        mock_page = Mock()
        mock_page.extract_text.return_value = ""  # Empty page
        mock_reader.return_value.pages = [mock_page]
        
        chunks = load_pdf_structured(
            "/fake/empty.pdf", 
            chunk_size=256, 
            chunk_overlap=50,
            doc_id="empty-doc"
        )
        
        # Should handle empty pages without crashing
        assert isinstance(chunks, list)


def test_json_loader_preserves_structure():
    """Test JSON loader preserves important structure info."""
    json_content = json.dumps({
        "projects": [
            {"name": "Project A", "status": "active"},
            {"name": "Project B", "status": "completed"}
        ]
    })
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/projects.json")
            
            # Check that project information is preserved in chunks
            all_text = " ".join(chunk["text"] for chunk in chunks)
            assert "Project A" in all_text or "projects" in all_text


def test_json_loader_handles_empty_object():
    """Test JSON loader handles empty JSON object."""
    json_content = json.dumps({})
    
    with patch("learning_mcp.json_loader.Path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json_content)):
            chunks = load_json("/fake/empty.json")
            
            # Should return at least one chunk even for empty JSON
            assert isinstance(chunks, list)


def test_collect_chunks_stats():
    """Test collect_chunks returns stats."""
    profile = {
        "name": "test-profile",
        "documents": [
            {"type": "json", "path": "/app/tests/fixtures/sample.json"}
        ]
    }
    
    json_content = json.dumps({"test": "data"})
    with patch("builtins.open", mock_open(read_data=json_content)):
        chunks, stats = collect_chunks(profile, chunk_size=256, chunk_overlap=50)
        
        assert isinstance(stats, dict)
        assert "files_total" in stats
        assert stats["files_total"] > 0

