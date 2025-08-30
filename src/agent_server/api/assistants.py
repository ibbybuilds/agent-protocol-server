"""Assistant endpoints for Agent Protocol"""
from uuid import uuid4
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends
import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Assistant, AssistantCreate, AssistantList, AssistantSearchRequest, AssistantSearchResponse, AgentSchemas, User
from ..services.langgraph_service import get_langgraph_service
from ..core.auth_deps import get_current_user
from ..core.orm import Assistant as AssistantORM, get_session

router = APIRouter()


def to_pydantic(row: AssistantORM) -> Assistant:
    """Convert SQLAlchemy ORM object to Pydantic model with proper type casting."""
    row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    # Cast UUIDs to str so they match the Pydantic schema
    if "assistant_id" in row_dict and row_dict["assistant_id"] is not None:
        row_dict["assistant_id"] = str(row_dict["assistant_id"])
    if "user_id" in row_dict and isinstance(row_dict["user_id"], uuid.UUID):
        row_dict["user_id"] = str(row_dict["user_id"])
    return Assistant.model_validate(row_dict)


@router.post("/assistants", response_model=Assistant)
async def create_assistant(
    request: AssistantCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create a new assistant"""
    
    # Get LangGraph service to validate graph
    langgraph_service = get_langgraph_service()
    available_graphs = langgraph_service.list_graphs()
    
    # Use graph_id as the main identifier
    graph_id = request.graph_id
    
    if graph_id not in available_graphs:
        raise HTTPException(
            400,
            f"Graph '{graph_id}' not found in aegra.json. Available: {list(available_graphs.keys())}"
        )
    
    # Validate graph can be loaded
    try:
        graph = await langgraph_service.get_graph(graph_id)
    except Exception as e:
        raise HTTPException(400, f"Failed to load graph: {str(e)}")

    config = request.config
    context = request.context

    if config.get("configurable") and context:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both configurable and context. Prefer setting context alone. Context was introduced in LangGraph 0.6.0 and is the long term planned replacement for configurable.",
        )

    # Keep config and context up to date with one another
    if config.get("configurable"):
        context = config["configurable"]
    elif context:
        config["configurable"] = context
    
    # Generate assistant_id if not provided
    assistant_id = request.assistant_id or str(uuid4())
    
    # Generate name if not provided
    name = request.name or f"Assistant for {graph_id}"
    
    # Check if an assistant already exists for this user+graph pair
    existing_stmt = select(AssistantORM).where(
        AssistantORM.user_id == user.identity,
        AssistantORM.graph_id == graph_id,
    )
    existing = await session.scalar(existing_stmt)
    
    if existing:
        if request.if_exists == "do_nothing":
            return to_pydantic(existing)
        elif request.if_exists == "replace":
            # Update existing assistant
            existing.name = name
            existing.description = request.description
            existing.config = request.config or {}
            existing.graph_id = graph_id
            existing.updated_at = datetime.utcnow()
            await session.commit()
            return to_pydantic(existing)
        else:  # error (default)
            raise HTTPException(409, f"Assistant '{assistant_id}' already exists")
    
    # Create assistant record
    assistant_orm = AssistantORM(
        assistant_id=assistant_id,
        name=name,
        description=request.description,
        config=config,
        context=context,
        graph_id=graph_id,
        user_id=user.identity
    )
    
    session.add(assistant_orm)
    await session.commit()
    await session.refresh(assistant_orm)
    
    return to_pydantic(assistant_orm)


@router.get("/assistants", response_model=AssistantList)
async def list_assistants(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """List user's assistants"""
    # Filter assistants by user
    stmt = select(AssistantORM).where(AssistantORM.user_id == user.identity)
    result = await session.scalars(stmt)
    user_assistants = [to_pydantic(a) for a in result.all()]
    
    return AssistantList(
        assistants=user_assistants,
        total=len(user_assistants)
    )


@router.post("/assistants/search", response_model=AssistantSearchResponse)
async def search_assistants(
    request: AssistantSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Search assistants with filters"""
    # Start with user's assistants
    stmt = select(AssistantORM).where(AssistantORM.user_id == user.identity)
    
    # Apply filters
    if request.name:
        stmt = stmt.where(AssistantORM.name.ilike(f"%{request.name}%"))
    
    if request.description:
        stmt = stmt.where(AssistantORM.description.ilike(f"%{request.description}%"))
    
    if request.graph_id:
        stmt = stmt.where(AssistantORM.graph_id == request.graph_id)
    
    # Get total count before pagination
    count_stmt = select(AssistantORM).where(AssistantORM.user_id == user.identity)
    if request.name:
        count_stmt = count_stmt.where(AssistantORM.name.ilike(f"%{request.name}%"))
    if request.description:
        count_stmt = count_stmt.where(AssistantORM.description.ilike(f"%{request.description}%"))
    if request.graph_id:
        count_stmt = count_stmt.where(AssistantORM.graph_id == request.graph_id)
    
    total = len(await session.scalars(count_stmt).all())
    
    # Apply pagination
    offset = request.offset or 0
    limit = request.limit or 20
    stmt = stmt.offset(offset).limit(limit)
    
    result = await session.scalars(stmt)
    paginated_assistants = [to_pydantic(a) for a in result.all()]
    
    return AssistantSearchResponse(
        assistants=paginated_assistants,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/assistants/{assistant_id}", response_model=Assistant)
async def get_assistant(
    assistant_id: str, 
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get assistant by ID"""
    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    return to_pydantic(assistant)


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(
    assistant_id: str, 
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Delete assistant by ID"""
    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    await session.delete(assistant)
    await session.commit()
    return {"status": "deleted"}


@router.get("/assistants/{assistant_id}/schemas", response_model=AgentSchemas)
async def get_assistant_schemas(
    assistant_id: str, 
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get input, output, state and config schemas for an assistant"""
    
    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")
    
    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    
    try:
        graph = await langgraph_service.get_graph(assistant.graph_id)
        
        # Extract schemas from LangGraph definition
        schemas = AgentSchemas(
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "User input message"}
                },
                "required": ["input"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "output": {"type": "string", "description": "Agent response"}
                }
            },
            state_schema={"type": "object", "additionalProperties": True},
            config_schema={
                "type": "object",
                "properties": {
                    "configurable": {
                        "type": "object",
                        "properties": {
                            "thread_id": {"type": "string"},
                            "user_id": {"type": "string"}
                        }
                    }
                }
            }
        )
        
        return schemas
        
    except Exception as e:
        raise HTTPException(400, f"Failed to extract schemas: {str(e)}")