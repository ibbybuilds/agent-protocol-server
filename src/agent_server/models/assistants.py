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
    metadata: Optional[Dict[str, Any]] = Field({}, description="Metadata to use for searching and filtering assistants.")
    if_exists: Optional[str] = Field("error", description="What to do if assistant exists: error or do_nothing")


class Assistant(BaseModel):
    """Assistant entity model"""
    assistant_id: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    graph_id: str
    user_id: str
    version: int = Field(..., description="The version of the assistant.")
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_dict")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AssistantUpdate(BaseModel):
    """Request model for creating assistants"""
    name: Optional[str] = Field(None, description="The name of the assistant (auto-generated if not provided)")
    description: Optional[str] = Field(None, description="The description of the assistant. Defaults to null.")
    config: Optional[Dict[str, Any]] = Field({}, description="Configuration to use for the graph.")
    graph_id: str = Field("agent", description="The ID of the graph")
    context: Optional[Dict[str, Any]] = Field({}, description="The context to use for the graph. Useful when graph is configurable.")
    metadata: Optional[Dict[str, Any]] = Field({}, description="Metadata to use for searching and filtering assistants.")


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
    metadata: Optional[Dict[str, Any]] = Field({}, description="Metadata to use for searching and filtering assistants.")


class AgentSchemas(BaseModel):
    """Agent schema definitions for client integration"""
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent inputs")
    output_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent outputs") 
    state_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent state")
    config_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent config")