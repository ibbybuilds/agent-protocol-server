"""Assistant endpoints for Agent Protocol"""
from uuid import uuid4
from datetime import datetime, UTC
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Body
import uuid
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Assistant, AssistantCreate, AssistantUpdate, AssistantList, AssistantSearchRequest, AgentSchemas, User
from ..services.langgraph_service import get_langgraph_service
from ..core.auth_deps import get_current_user
from ..core.orm import Assistant as AssistantORM, AssistantVersion as AssistantVersionORM, get_session

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
    
    # Check if an assistant already exists for this user, graph and config pair
    existing_stmt = select(AssistantORM).where(
        AssistantORM.user_id == user.identity,
        or_(
            (AssistantORM.graph_id == graph_id) & (AssistantORM.config == config),
            AssistantORM.assistant_id == assistant_id
        )
    )
    existing = await session.scalar(existing_stmt)
    
    if existing:
        if request.if_exists == "do_nothing":
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
        user_id=user.identity,
        metadata_dict=request.metadata,
        version=1
    )
    
    session.add(assistant_orm)
    await session.commit()
    await session.refresh(assistant_orm)

    # Create initial version record
    assistant_version_orm = AssistantVersionORM(
        assistant_id=assistant_id,
        version=1,
        graph_id=graph_id,
        config=config,
        context=context,
        created_at=datetime.now(UTC),
        name=name,
        description=request.description,
        metadata_dict=request.metadata
    )
    session.add(assistant_version_orm)
    await session.commit()
    
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


@router.post("/assistants/search", response_model=List[Assistant])
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

    if request.metadata:
        stmt = stmt.where(AssistantORM.metadata_dict.op("@>")(request.metadata))
    
    # Apply pagination
    offset = request.offset or 0
    limit = request.limit or 20
    stmt = stmt.offset(offset).limit(limit)
    
    result = await session.scalars(stmt)
    paginated_assistants = [to_pydantic(a) for a in result.all()]
    
    return paginated_assistants


@router.post("/assistants/count", response_model=int)
async def count_assistants(
    request: AssistantSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Count assistants with filters"""
    stmt = select(func.count()).where(AssistantORM.user_id == user.identity)

    if request.name:
        stmt = stmt.where(AssistantORM.name.ilike(f"%{request.name}%"))

    if request.description:
        stmt = stmt.where(AssistantORM.description.ilike(f"%{request.description}%"))

    if request.graph_id:
        stmt = stmt.where(AssistantORM.graph_id == request.graph_id)

    if request.metadata:
        stmt = stmt.where(AssistantORM.metadata_dict.op("@>")(request.metadata))

    total = await session.scalar(stmt)
    return total or 0


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


@router.patch("/assistants/{assistant_id}", response_model=Assistant)
async def update_assistant(
        assistant_id: str,
        request: AssistantUpdate,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session)
):
    """Update assistant by ID"""
    metadata = request.metadata or {}
    config = request.config or {}
    context = request.context or {}

    if config.get("configurable") and context:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both configurable and context. Use only one.",
        )

    # Keep config and context up to date with one another
    if config.get("configurable"):
        context = config["configurable"]
    elif context:
        config["configurable"] = context

    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")

    now = datetime.now(UTC)
    version_stmt = select(func.max(AssistantVersionORM.version)).where(
        AssistantVersionORM.assistant_id == assistant_id
    )
    max_version = await session.scalar(version_stmt)
    new_version = (max_version or 1) + 1  if max_version is not None else 1

    new_version_details = {
        "assistant_id": assistant_id,
        "version": new_version,
        "graph_id": request.graph_id or assistant.graph_id,
        "config": config,
        "context": context,
        "created_at": now,
        "name": request.name or assistant.name,
        "description": request.description or assistant.description,
        "metadata_dict": metadata
    }

    assistant_version_orm = AssistantVersionORM(**new_version_details)
    session.add(assistant_version_orm)
    await session.commit()

    assistant_update = update(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    ).values(
        name=new_version_details["name"],
        description=new_version_details["description"],
        graph_id=new_version_details["graph_id"],
        config=new_version_details["config"],
        context=new_version_details["context"],
        version=new_version,
        updated_at=now,
    )
    await session.execute(assistant_update)
    await session.commit()
    updated_assistant = await session.scalar(stmt)
    return to_pydantic(updated_assistant)


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


@router.post("/assistants/{assistant_id}/latest", response_model=Assistant)
async def set_assistant_latest(
        assistant_id: str,
        version: int = Body(..., embed=True, description="The version number to set as latest"),
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session)
):
    """Set the given version as the latest version of an assistant"""
    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")

    version_stmt = select(AssistantVersionORM).where(
        AssistantVersionORM.assistant_id == assistant_id,
        AssistantVersionORM.version == version
    )
    assistant_version = await session.scalar(version_stmt)
    if not assistant_version:
        raise HTTPException(404, f"Version '{version}' for Assistant '{assistant_id}' not found")

    assistant_update = update(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    ).values(
        name=assistant_version.name,
        description=assistant_version.description,
        config=assistant_version.config,
        context=assistant_version.context,
        graph_id=assistant_version.graph_id,
        version=version,
        updated_at=datetime.now(UTC)
    )
    await session.execute(assistant_update)
    await session.commit()
    updated_assistant = await session.scalar(stmt)
    return to_pydantic(updated_assistant)


@router.post("/assistants/{assistant_id}/versions", response_model=List[Assistant])
async def list_assistant_versions(
    assistant_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """List all versions of an assistant"""
    stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == assistant_id,
        AssistantORM.user_id == user.identity
    )
    assistant = await session.scalar(stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{assistant_id}' not found")

    stmt = select(AssistantVersionORM).where(
        AssistantVersionORM.assistant_id == assistant_id
    ).order_by(AssistantVersionORM.version.desc())
    result = await session.scalars(stmt)
    versions = result.all()

    if not versions:
        raise HTTPException(404, f"No versions found for Assistant '{assistant_id}'")

    # Convert to Pydantic models
    version_list = [
        Assistant(
            assistant_id=assistant_id,
            name=v.name,
            description=v.description,
            config=v.config,
            context=v.context,
            graph_id=v.graph_id,
            user_id=user.identity,
            version=v.version,
            created_at=v.created_at,
            updated_at=v.created_at
        ) for v in versions
    ]

    return version_list


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
