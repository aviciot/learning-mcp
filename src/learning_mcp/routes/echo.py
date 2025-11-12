"""
Echo tool for Learning MCP (FastAPI route exposed via MCP).
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class EchoIn(BaseModel):
    message: str

class EchoOut(BaseModel):
    reply: str

@router.post("/api/echo", name="echo", response_model=EchoOut)
async def echo(payload: EchoIn) -> EchoOut:
    return EchoOut(reply=f"echo: {payload.message}")
