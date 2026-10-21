"""Fire several calls at the same moment, to check what the service does with a race."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


def run_together[T](calls: Sequence[Callable[[], T]]) -> list[T]:
    """Run every call in its own thread, released together; results come back in call order.

    The barrier makes the requests leave at (almost) the same instant instead of one after the
    other as the pool starts its threads, so the service really sees them overlap.
    """
    start = Barrier(len(calls))

    def go(call: Callable[[], T]) -> T:
        start.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(go, call) for call in calls]
        return [future.result() for future in futures]
