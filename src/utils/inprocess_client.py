# utils/inprocess_client.py
"""Reusable helper to call FastAPI routes in-process (no network).

Example user question: "How can I call my api_context route without going through localhost?"
"""
import httpx
from fastapi import FastAPI
from typing import Optional, Dict, Any

async def call_inprocess(
    app: FastAPI,
    route_name: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    """
    Call a FastAPI route in-process using httpx + ASGITransport.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        url = app.url_path_for(route_name)
        resp = await client.request(method, url, params=params, json=json)
        return resp
