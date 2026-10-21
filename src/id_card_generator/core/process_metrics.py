"""CPU load and memory usage of the running process.

The production workspace shows how hard the renderer is working.  The numbers
come from the standard library, so no extra dependency is needed:

* the CPU load is the share of one core that the process used since the last
  sample,
* the memory is the peak resident set size of the process.
"""

import sys
import time
from typing import Tuple


class ProcessMetrics:
    """Samples the CPU load and the memory usage of this process."""

    def __init__(self) -> None:
        self._last_cpu = time.process_time()
        self._last_time = time.monotonic()
        self._has_sample = False

    def sample(self) -> Tuple[float, float]:
        """Return the CPU load (percent of one core) and the memory in MB."""
        now = time.monotonic()
        cpu = time.process_time()

        elapsed = max(now - self._last_time, 1e-6)
        used = max(cpu - self._last_cpu, 0.0)

        self._last_cpu = cpu
        self._last_time = now

        if not self._has_sample:
            # The first sample has no interval to measure, so it reports 0.
            self._has_sample = True
            return 0.0, self.memory_mb()

        return min(100.0, used / elapsed * 100.0), self.memory_mb()

    @staticmethod
    def memory_mb() -> float:
        """Return peak resident memory in megabytes when the platform supports it."""
        try:
            import resource
        except ImportError:  # Windows does not provide the resource module.
            return 0.0

        try:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except (OSError, ValueError):  # pragma: no cover - platform specific
            return 0.0

        # macOS reports bytes, Linux reports kilobytes.
        if sys.platform == "darwin":
            return usage / (1024.0 * 1024.0)
        return usage / 1024.0
