"""Run-related Pydantic models for Agent Protocol"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """Request model for creating runs"""
    assistant_id: str = Field(..., description="Assistant to execute")
    input: Optional[Dict[str, Any]] = Field(
        None,
        description="Input data for the run. Optional when resuming from a checkpoint.",
    )
    config: Optional[Dict[str, Any]] = Field({}, description="LangGraph execution config")
    context: Optional[Dict[str, Any]] = Field({}, description="LangGraph execution context")
    checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="Checkpoint configuration (e.g., {'checkpoint_id': '...', 'checkpoint_ns': ''})",
    )
    stream: bool = Field(False, description="Enable streaming response")
    stream_mode: Optional[str | list[str]] = Field(None, description="Requested stream mode(s) as per LangGraph")
    on_disconnect: Optional[str] = Field(
        None,
        description="Behavior on client disconnect: 'cancel' or 'continue' (default).",
    )


class Run(BaseModel):
    """Run entity model"""
    run_id: str
    thread_id: str
    assistant_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}
    context: Optional[Dict[str, Any]] = {}
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RunList(BaseModel):
    """Response model for listing runs"""
    runs: List[Run]
    total: int


class RunStatus(BaseModel):
    """Simple run status response"""
    run_id: str
    status: str
    message: Optional[str] = None
