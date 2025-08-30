"""Assistant-related Pydantic models for Agent Protocol"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AssistantCreate(BaseModel):
    """Request model for creating assistants"""
    assistant_id: Optional[str] = Field(None, description="Unique assistant identifier (auto-generated if not provided)")
    name: Optional[str] = Field(None, description="Human-readable assistant name (auto-generated if not provided)")
    description: Optional[str] = Field(None, description="Assistant description")
    config: Optional[Dict[str, Any]] = Field({}, description="Assistant configuration")
    context: Optional[Dict[str, Any]] = Field({}, description="Assistant context")
    graph_id: str = Field(..., description="LangGraph graph ID from aegra.json")
    if_exists: Optional[str] = Field("error", description="What to do if assistant exists: error, do_nothing, or replace")


class Assistant(BaseModel):
    """Assistant entity model"""
    assistant_id: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    graph_id: str
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class AssistantList(BaseModel):
    """Response model for listing assistants"""
    assistants: list[Assistant]
    total: int


class AssistantSearchRequest(BaseModel):
    """Request model for assistant search"""
    name: Optional[str] = Field(None, description="Filter by assistant name")
    description: Optional[str] = Field(None, description="Filter by assistant description")
    graph_id: Optional[str] = Field(None, description="Filter by graph ID")
    limit: Optional[int] = Field(20, le=100, ge=1, description="Maximum results")
    offset: Optional[int] = Field(0, ge=0, description="Results offset")


class AssistantSearchResponse(BaseModel):
    """Response model for assistant search"""
    assistants: list[Assistant]
    total: int
    limit: int
    offset: int


class AgentSchemas(BaseModel):
    """Agent schema definitions for client integration"""
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent inputs")
    output_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent outputs") 
    state_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent state")
    config_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent config")