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
    """
    Gradual stress test with connection rate limiting and auto-throttling.
    Creates connections gradually instead of all at once to avoid overwhelming DB.
    """
    async def stress_worker(idx: int, error_tracker: dict) -> None:
        error_count = 0
        max_errors = 3
        
        while error_count < max_errors:
            try:
                await worker(idx)
                error_count = 0
                error_tracker['success'] += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                error_count += 1
                error_tracker['errors'] += 1
                # Back off on errors
                await asyncio.sleep(1.0)
                continue
            
            # Check error rate and throttle if needed
            total = error_tracker['success'] + error_tracker['errors']
            if total > 100:
                error_rate = error_tracker['errors'] / total
                if error_rate > 0.3:  # More than 30% error rate
                    await asyncio.sleep(0.5)  # Aggressive throttle
                elif error_rate > 0.1:  # More than 10% error rate
                    await asyncio.sleep(0.2)  # Moderate throttle
                else:
                    await asyncio.sleep(0.1)  # Normal pace
            else:
                await asyncio.sleep(0.1)
    
    current = start_connections
    tasks = []
    error_tracker = {'success': 0, 'errors': 0}
    
    try:
        while current <= max_connections:
            print(f"[Stress] Ramping up to {current} connections (adding {min(step, current - len(tasks))} new)...")
            
            # Cancel old tasks first
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Reset error tracker for new level
            error_tracker = {'success': 0, 'errors': 0}
            
            # Create new connections GRADUALLY with rate limiting
            # Max 50 connections per second to avoid overwhelming
            connections_per_batch = 50
            batches = (current + connections_per_batch - 1) // connections_per_batch
            
            tasks = []
            for batch in range(batches):
                batch_start = batch * connections_per_batch
                batch_end = min((batch + 1) * connections_per_batch, current)
                
                for i in range(batch_start, batch_end):
                    tasks.append(asyncio.create_task(stress_worker(i, error_tracker)))
                
                # Wait between batches
                if batch < batches - 1:
                    await asyncio.sleep(1.0)  # 1 second between batches
            
            print(f"[Stress] Holding at {current} connections for {step_duration_sec}s...")
            
            # Monitor during hold period
            for elapsed in range(step_duration_sec):
                await asyncio.sleep(1)
                
                # Check error rate every 10 seconds
                if elapsed % 10 == 0 and elapsed > 0:
                    total = error_tracker['success'] + error_tracker['errors']
                    if total > 0:
                        error_rate = error_tracker['errors'] / total
                        print(f"  └─ {elapsed}s: success={error_tracker['success']}, errors={error_tracker['errors']}, error_rate={error_rate:.1%}")
                        
                        # If error rate too high, abort this level
                        if error_rate > 0.5 and total > 100:
                            print(f"  └─ ERROR RATE TOO HIGH ({error_rate:.1%}), stopping stress test")
                            return
            
            current += step
    finally:
        # Clean up all tasks
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def stress_gentle(
    start_connections: int,
    step: int,
    max_connections: int,
    step_duration_sec: int,
    worker: QueryTask,
    ramp_up_time_sec: int = 30,
) -> None:
    """
    Ultra-gentle stress test for resource-constrained environments like Lightsail.
    - Very gradual connection ramp-up
    - Longer warm-up periods
    - Automatic backing off on high error rates
    """
    print(f"[Stress Gentle] Starting gentle stress test: {start_connections} → {max_connections} connections")
    print(f"[Stress Gentle] Step size: {step}, Hold time: {step_duration_sec}s, Ramp-up: {ramp_up_time_sec}s per level")
    
    async def gentle_worker(idx: int, error_tracker: dict) -> None:
        error_count = 0
        max_errors = 3
        
        while error_count < max_errors:
            try:
                await worker(idx)
                error_count = 0
                error_tracker['success'] += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                error_count += 1
                error_tracker['errors'] += 1
                await asyncio.sleep(2.0)  # Long backoff on errors
                continue
            
            # Always throttle to avoid overwhelming
            await asyncio.sleep(0.2)  # 200ms between worker iterations
    
    current = start_connections
    tasks = []
    error_tracker = {'success': 0, 'errors': 0}
    
    try:
        while current <= max_connections:
            print(f"\n[Stress Gentle] ━━━ Level: {current} connections ━━━")
            
            # Cancel old tasks
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            error_tracker = {'success': 0, 'errors': 0}
            
            # VERY gradual ramp up - 10 connections per second max
            print(f"[Stress Gentle] Ramping up over {ramp_up_time_sec}s...")
            connections_per_second = 10
            ramp_steps = (current + connections_per_second - 1) // connections_per_second
            
            tasks = []
            for step_num in range(ramp_steps):
                step_start = step_num * connections_per_second
                step_end = min((step_num + 1) * connections_per_second, current)
                
                for i in range(step_start, step_end):
                    tasks.append(asyncio.create_task(gentle_worker(i, error_tracker)))
                
                # Progress indicator
                progress = (step_end / current) * 100
                print(f"  └─ {step_end}/{current} connections ({progress:.0f}%)")
                
                await asyncio.sleep(1.0)
            
            print(f"[Stress Gentle] Holding at {current} connections for {step_duration_sec}s...")
            
            # Monitor during hold
            for elapsed in range(0, step_duration_sec, 10):
                await asyncio.sleep(min(10, step_duration_sec - elapsed))
                
                total = error_tracker['success'] + error_tracker['errors']
                if total > 0:
                    error_rate = error_tracker['errors'] / total
                    qps = error_tracker['success'] / max(1, elapsed + 10)
                    print(f"  └─ +{elapsed+10}s: QPS≈{qps:.1f}, errors={error_tracker['errors']}, error_rate={error_rate:.1%}")
                    
                    # Abort if too many errors
                    if error_rate > 0.4 and total > 50:
                        print(f"  └─ ⚠️  ERROR RATE TOO HIGH, stopping at {current} connections")
                        print(f"  └─ ℹ️  Database reached capacity around {current} connections")
                        return
            
            current += step
    finally:
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["ramp_up", "sustained", "spike", "stress", "stress_gentle"]
