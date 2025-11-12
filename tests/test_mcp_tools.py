"""Integration tests for MCP tools - requires servers running."""

import pytest

# These tests require the actual MCP server to be running
# They are integration tests, not unit tests
# Run with: docker compose up -d && pytest tests/test_mcp_tools.py

pytestmark = pytest.mark.skip(reason="Requires running MCP server - integration test")


@pytest.mark.asyncio
async def test_list_profiles():
    """Test list_profiles tool returns expected profiles."""
    async with Client(mcp) as client:
        result = await client.call_tool("list_profiles", arguments={})
        
        assert "profiles" in result
        assert len(result["profiles"]) > 0
        # Check for known profiles
        profile_names = [p["name"] for p in result["profiles"]]
        assert "avi-cohen" in profile_names


@pytest.mark.asyncio
async def test_search_docs_requires_ingest():
    """Test search_docs on potentially empty collection."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_docs",
            arguments={"q": "test", "profile": "avi-cohen", "top_k": 5}
        )
        
        # Should return results structure (empty or with data)
        assert "results" in result
        assert "metadata" in result
        assert result["metadata"]["profile"] == "avi-cohen"
        assert result["metadata"]["query"] == "test"


@pytest.mark.asyncio
async def test_search_docs_with_top_k():
    """Test search_docs respects top_k parameter."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_docs",
            arguments={"q": "Python", "profile": "avi-cohen", "top_k": 3}
        )
        
        assert "results" in result
        assert len(result["results"]) <= 3  # Should not exceed top_k


@pytest.mark.asyncio
async def test_plan_api_call_disabled_by_default():
    """Test plan_api_call returns disabled message when USE_AUTOGEN=0."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "plan_api_call",
            arguments={"goal": "enable wifi", "profile": "dahua-camera"}
        )
        
        assert result["status"] == "disabled"
        assert "USE_AUTOGEN=1" in result["message"]


@pytest.mark.asyncio
async def test_profile_resource():
    """Test profile:// resource returns YAML config."""
    async with Client(mcp) as client:
        result = await client.read_resource("profile://avi-cohen")
        
        assert isinstance(result, str)
        # YAML content should contain these keys
        assert "embedding:" in result or "name:" in result


@pytest.mark.asyncio
async def test_search_docs_invalid_profile():
    """Test search_docs with non-existent profile."""
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.call_tool(
                "search_docs",
                arguments={"q": "test", "profile": "non-existent-profile"}
            )


@pytest.mark.asyncio
async def test_list_profiles_structure():
    """Test list_profiles returns proper structure."""
    async with Client(mcp) as client:
        result = await client.call_tool("list_profiles", arguments={})
        
        assert "profiles" in result
        for profile in result["profiles"]:
            assert "name" in profile
            assert "description" in profile
            assert "document_count" in profile
            assert "embedding_backend" in profile
            assert "collection" in profile
