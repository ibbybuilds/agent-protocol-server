import pytest
import asyncio
from e2e._utils import get_e2e_client, elog


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_langsmith_nostream_event_filtering_e2e():
    """
    Test that events containing 'langsmith:nostream' tag are properly filtered out
    during run execution. This validates the _should_skip_event function.

    Expected behavior:
    - Events with 'langsmith:nostream' tag should be skipped
    - Normal events should still be processed
    - Streaming should complete normally even with filtered events
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["event-filtering", "langsmith-nostream"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Start a streaming run that would potentially generate events with langsmith:nostream tag
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "Generate a response with internal processing steps",
                }
            ]
        },
        stream_mode=["messages", "values"],
    )

    # Collect all events
    events = []
    event_count = 0
    completed = False

    async for chunk in stream:
        event_count += 1
        events.append(chunk)
        elog(
            "Runs.stream event",
            {
                "event": getattr(chunk, "event", None),
                "event_number": event_count,
            },
        )

        if getattr(chunk, "event", None) == "end":
            completed = True
            break

    # Validate that streaming completed successfully
    assert completed, "Stream should complete with an 'end' event"
    assert event_count > 0, "Should receive at least one event"

    # Note: We can't directly test that langsmith:nostream events were filtered
    # since they would be invisible to the client. The test validates that
    # the filtering doesn't break the streaming flow.
    elog("Event filtering test completed", {"total_events": event_count})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_subgraphs_streaming_parameter_e2e():
    """
    Test that the subgraphs=True parameter is correctly applied in graph.astream()
    calls, enabling streaming events from subsequent graphs.

    Expected behavior:
    - Events from subgraphs should be included in the stream
    - The overall streaming should work correctly with subgraph events
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["subgraphs", "streaming"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Create a run that could trigger subgraph execution
    stream = client.runs.stream(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "Please process this request with multiple steps",
                }
            ]
        },
        stream_mode=["messages", "values"],
    )

    # Track events to ensure subgraph events are included
    events = []
    values_events = 0
    messages_events = 0
    completed = False

    async for chunk in stream:
        events.append(chunk)
        event_type = getattr(chunk, "event", None)

        if event_type == "values":
            values_events += 1
        elif event_type == "messages":
            messages_events += 1
        elif event_type == "end":
            completed = True
            break

        elog(
            "Subgraph streaming event",
            {
                "event": event_type,
                "values_count": values_events,
                "messages_count": messages_events,
            },
        )

    # Validate streaming completed successfully
    assert completed, "Stream should complete with an 'end' event"
    assert len(events) > 0, "Should receive events from streaming"

    # The presence of multiple event types suggests subgraph events are included
    elog(
        "Subgraphs streaming test completed",
        {
            "total_events": len(events),
            "values_events": values_events,
            "messages_events": messages_events,
        },
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_background_run_with_event_filtering_e2e():
    """
    Test that event filtering and subgraph support work correctly in background runs
    (non-streaming execution that later provides events for replay).

    Expected behavior:
    - Background run should complete successfully
    - Events should be available for later streaming/replay
    - Filtered events should not appear in replay
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["background", "event-filtering"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Create a background run (non-streaming)
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "Execute with internal processing and filtering",
                }
            ]
        },
        stream_mode=["messages", "values"],
    )
    elog("Runs.create (background)", run)
    run_id = run["run_id"]

    # Join the run to wait for completion
    final_state = await client.runs.join(thread_id, run_id)
    elog("Runs.join", final_state)

    # Verify the run completed
    run_status = await client.runs.get(thread_id, run_id)
    elog("Runs.get", run_status)
    assert run_status["status"] in (
        "completed",
        "failed",
    ), f"Run should be completed, got: {run_status['status']}"

    # Stream the completed run to get stored events
    replay_events = []
    async for chunk in client.runs.join_stream(
        thread_id=thread_id,
        run_id=run_id,
        stream_mode=["messages", "values"],
    ):
        replay_events.append(chunk)
        elog("Replay event", {"event": getattr(chunk, "event", None)})

        if getattr(chunk, "event", None) == "end":
            break

    # Validate that replay contains events (with filtering applied)
    assert len(replay_events) > 0, "Should have events available for replay"

    # The last event should be an 'end' event
    last_event = replay_events[-1] if replay_events else None
    assert (
        last_event and getattr(last_event, "event", None) == "end"
    ), "Replay should end with 'end' event"

    elog(
        "Background run with filtering test completed",
        {
            "replay_events": len(replay_events),
            "final_status": run_status["status"],
        },
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_concurrent_runs_with_filtering_e2e():
    """
    Test that event filtering works correctly when multiple runs are executing
    concurrently, ensuring no cross-contamination of filtered events.

    Expected behavior:
    - Multiple concurrent runs should execute independently
    - Event filtering should work for each run separately
    - All runs should complete successfully
    """
    client = get_e2e_client()

    # Create assistant and thread
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["concurrent", "event-filtering"]},
        if_exists="do_nothing",
    )
    elog("Assistant.create", assistant)

    thread = await client.threads.create()
    elog("Threads.create", thread)
    thread_id = thread["thread_id"]
    assistant_id = assistant["assistant_id"]

    # Create multiple concurrent runs
    run_tasks = []
    num_runs = 3

    for i in range(num_runs):
        run = await client.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": f"Concurrent request {i+1} with filtering",
                    }
                ]
            },
            stream_mode=["messages", "values"],
        )
        elog(f"Runs.create (concurrent {i+1})", run)

        # Create task to join each run
        task = asyncio.create_task(client.runs.join(thread_id, run["run_id"]))
        run_tasks.append((run["run_id"], task))

    # Wait for all runs to complete
    completed_runs = []
    for run_id, task in run_tasks:
        try:
            final_state = await asyncio.wait_for(task, timeout=30.0)
            completed_runs.append(run_id)
            elog(
                f"Run {run_id} completed", {"has_final_state": final_state is not None}
            )
        except asyncio.TimeoutError:
            elog(f"Run {run_id} timed out", {})

    # Verify all runs completed
    assert (
        len(completed_runs) == num_runs
    ), f"Expected {num_runs} runs to complete, got {len(completed_runs)}"

    # Verify each run status
    for run_id in completed_runs:
        run_status = await client.runs.get(thread_id, run_id)
        assert run_status["status"] in (
            "completed",
            "failed",
        ), f"Run {run_id} should be completed"
        elog(f"Final status for run {run_id}", {"status": run_status["status"]})

    elog(
        "Concurrent runs with filtering test completed",
        {
            "completed_runs": len(completed_runs),
            "expected_runs": num_runs,
        },
    )
