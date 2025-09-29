from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
import httpx
from enum import Enum
from learning_mcp.config import settings
import logging

logger = logging.getLogger("learning_mcp.api_exec")

router = APIRouter()



class HttpMethod(str, Enum):
    GET="GET"

class ApiRequest(BaseModel):
    profile: str = Field(..., description="Profile name from learning.yaml")
    method: HttpMethod = Field(HttpMethod.GET, description="HTTP method")
    path: str = Field(..., description="API path starting with / (e.g., /public/core/v3/users)")
    query: Optional[Dict[str, Any]] = Field(None, description="Query string params")
    headers: Optional[Dict[str, str]] = Field(None, description="Extra headers (merged)")
    body: Optional[Any] = Field(None, description="JSON body for non-GET")
    read_only: bool = Field(False, description="If true, only GET allowed")
    timeout_seconds: float = Field(20.0, ge=1, le=120, description="Request timeout (seconds)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "profile": "informatica-cloud",
                    "method": "GET",
                    "path": "/public/core/v3/users",
                    "query": {},
                    "headers": {"Accept": "application/json"},
                    "read_only": True
                }
            ]
        }
    }


def _get_profile_cfg(profile_name: str) -> Dict[str, Any]:
    cfg = settings.load_profiles()
    profiles = {p["name"]: p for p in (cfg.get("profiles") or []) if p.get("name")}
    if profile_name not in profiles:
        raise HTTPException(status_code=400, detail=f"Unknown profile '{profile_name}'")
    return profiles[profile_name]

def _default_headers(profile_cfg: Dict[str, Any]) -> Dict[str, str]:
    auth = (profile_cfg.get("auth") or {})
    h = {"Accept": "application/json"}
    if auth.get("header") and auth.get("value"):
        h[auth["header"]] = auth["value"]
    return h

@router.post(
    "/api_request",
    operation_id="api_request",
    summary="Safe API call executor (read-only by default)",
    description="Executes a vendor API call using the given profile. "
                "By default read_only=true, which only allows GET requests. "
                "Use with caution if enabling other methods."
)

async def api_request(req: ApiRequest):
    m = (req.method or "GET").upper()
    if req.read_only and m != "GET":
        raise HTTPException(status_code=400, detail=f"read_only=true forbids method '{m}'")

    prof = _get_profile_cfg(req.profile)
    base = (prof.get("base_url") or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail=f"Profile '{req.profile}' missing base_url")

    path = req.path if req.path.startswith("/") else f"/{req.path}"
    url = f"{base}{path}"

    headers = _default_headers(prof)
    if req.headers:
        headers.update({k: v for k, v in req.headers.items() if v is not None})


 # Log dry-run
    logger.info(f"[DRY-RUN] {m} {url} params={req.query} headers={headers} body={req.body}")

    # Return the dry-run request details
    return {
        "status": "dry-run",
        "method": m,
        "url": url,
        "query": req.query or {},
        "headers": headers,
        "body": req.body,
        "note": "This is a dry-run. No HTTP request was made."
    }

    # try:
    #     async with httpx.AsyncClient(timeout=req.timeout_seconds) as client:
    #         if m == "GET":
    #             resp = await client.get(url, params=req.query, headers=headers)
    #         elif m == "DELETE":
    #             resp = await client.delete(url, params=req.query, headers=headers)
    #         else:
    #             resp = await client.request(m, url, params=req.query, headers=headers, json=req.body)
    #     out = {"status": "ok", "status_code": resp.status_code, "headers": dict(resp.headers)}
    #     ct = resp.headers.get("content-type", "").lower()
    #     if "application/json" in ct:
    #         try:
    #             out["json"] = resp.json()
    #         except Exception:
    #             out["text"] = resp.text
    #     else:
    #         out["text"] = resp.text
    #     return out
    # except httpx.HTTPError as e:
    #     return {"status": "error", "error": str(e)}
