import asyncio
from typing import Awaitable, Callable


QueryTask = Callable[[int], Awaitable[None]]


async def ramp_up(
    start_connections: int,
    end_connections: int,
    duration_sec: int,
    worker: QueryTask,
) -> None:
    steps = max(1, end_connections - start_connections)
    delay = duration_sec / steps
    current = start_connections
    tasks = set()
    while current <= end_connections:
        tasks.add(asyncio.create_task(worker(current)))
        await asyncio.sleep(delay)
        current += 1
    await asyncio.gather(*tasks)


async def sustained(connections: int, duration_sec: int, worker: QueryTask) -> None:
    stop_event = asyncio.Event()

    async def run_worker(idx: int) -> None:
        await worker(idx)
        # Keep it alive for the duration
        await stop_event.wait()

    tasks = [asyncio.create_task(run_worker(i)) for i in range(connections)]
    try:
        await asyncio.sleep(duration_sec)
    finally:
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def spike(
    base_connections: int,
    spike_connections: int,
    spike_duration_sec: int,
    cycles: int,
    worker: QueryTask,
) -> None:
    # Start base load once - keep running throughout all cycles
    base_tasks = [asyncio.create_task(worker(i)) for i in range(base_connections)]
    
    for cycle in range(cycles):
        await asyncio.sleep(1)  # Small delay before spike
        
        # Spike - add extra connections
        spike_tasks = [asyncio.create_task(worker(base_connections + cycle * spike_connections + i)) for i in range(spike_connections)]
        
        # Let spike run for the duration
        await asyncio.sleep(spike_duration_sec)
        
        # Cancel spike tasks, but let base tasks continue
        for t in spike_tasks:
            t.cancel()
        # Wait for spike tasks to finish canceling
        await asyncio.gather(*spike_tasks, return_exceptions=True)
        
        # Wait a bit before next cycle (recovery period)
        if cycle < cycles - 1:
            await asyncio.sleep(5)
    
    # Wait for base tasks to complete
    await asyncio.gather(*base_tasks, return_exceptions=True)


async def stress(
    start_connections: int,
    step: int,
    max_connections: int,
    step_duration_sec: int,
    worker: QueryTask,
) -> None:
    current = start_connections
    while current <= max_connections:
        tasks = [asyncio.create_task(worker(i)) for i in range(current)]
        await asyncio.sleep(step_duration_sec)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current += step


__all__ = ["ramp_up", "sustained", "spike", "stress"]


