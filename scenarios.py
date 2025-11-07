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
    # Create a more aggressive worker for spike scenarios
    async def spike_worker(idx: int) -> None:
        # Run continuously until cancelled
        error_count = 0
        max_errors = 5  # Stop after too many consecutive errors
        
        while error_count < max_errors:
            try:
                await worker(idx)
                error_count = 0  # Reset on success
            except asyncio.CancelledError:
                raise
            except Exception:
                error_count += 1
                await asyncio.sleep(0.5)  # Longer delay on error
                continue
            await asyncio.sleep(0.1)  # Slightly longer delay between iterations
    
    # Start base load - keep running throughout all cycles
    base_tasks = [asyncio.create_task(spike_worker(i)) for i in range(base_connections)]
    
    try:
        for cycle in range(cycles):
            print(f"[Spike] Cycle {cycle + 1}/{cycles}: Base load running with {base_connections} connections")
            await asyncio.sleep(2)  # Brief stable period
            
            # Spike - add extra connections
            print(f"[Spike] Adding spike of {spike_connections} connections for {spike_duration_sec}s")
            spike_tasks = [
                asyncio.create_task(spike_worker(base_connections + cycle * spike_connections + i)) 
                for i in range(spike_connections)
            ]
            
            # Let spike run for the duration
            await asyncio.sleep(spike_duration_sec)
            
            # Cancel spike tasks
            print(f"[Spike] Removing spike connections")
            for t in spike_tasks:
                t.cancel()
            await asyncio.gather(*spike_tasks, return_exceptions=True)
            
            # Shorter recovery period
            if cycle < cycles - 1:
                print(f"[Spike] Recovery period (2s)")
                await asyncio.sleep(2)
    finally:
        # Clean up base tasks
        for t in base_tasks:
            t.cancel()
        await asyncio.gather(*base_tasks, return_exceptions=True)


async def stress(
    start_connections: int,
    step: int,
    max_connections: int,
    step_duration_sec: int,
    worker: QueryTask,
) -> None:
    # Create a more aggressive worker for stress test
    async def stress_worker(idx: int) -> None:
        # Run continuously until cancelled
        error_count = 0
        max_errors = 5  # Stop after too many consecutive errors
        
        while error_count < max_errors:
            try:
                await worker(idx)
                error_count = 0  # Reset on success
            except asyncio.CancelledError:
                raise
            except Exception:
                error_count += 1
                await asyncio.sleep(0.5)  # Longer delay on error
                continue
            await asyncio.sleep(0.1)  # Slightly longer delay between iterations
    
    current = start_connections
    tasks = []
    
    try:
        while current <= max_connections:
            print(f"[Stress] Increasing load to {current} connections for {step_duration_sec}s")
            
            # Cancel old tasks first
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Create new tasks for current level
            tasks = [asyncio.create_task(stress_worker(i)) for i in range(current)]
            
            # Let it run for step duration
            await asyncio.sleep(step_duration_sec)
            
            current += step
    finally:
        # Clean up all tasks
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["ramp_up", "sustained", "spike", "stress"]


