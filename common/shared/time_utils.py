import logging
import signal
from collections import deque
from time import time
from typing import Deque, Optional


class SignalTimeout:
    def __init__(self, timeout, raise_exception=True):
        self.timeout = timeout
        self.raise_exception = raise_exception

    def __enter__(self):
        signal.signal(signal.SIGALRM, handler=self._handler)
        signal.setitimer(signal.ITIMER_REAL, self.timeout)

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.setitimer(signal.ITIMER_REAL, 0)
        if exc_type is TimeoutError and not self.raise_exception:
            return True
        return False

    # noinspection PyMethodMayBeStatic
    def _handler(self, _signum, _frame):
        message = f"Execution took longer than {self.timeout} seconds, timeout!"
        raise TimeoutError(message)


class Timeout:
    """This module is intended to be used as such:
    >>> timeout = Timeout(30)
    >>> while timeout:
    >>>     # Do things
    >>>     pass
    The timeout object will return false after the alloted time, ending the
    loop. This can be useful for tests.
    """

    def __init__(self, time_seconds, raise_error=True, print_timeout=False):
        """
        :param time_seconds: How long until the timeout returns False for bool()
        :param print_timeout: If you want a printout when the timer has timed
        out
        :param raise_error: If you want the timer to raise an error if bool()
        ever returns false
        """
        self.start: float = time()
        self.time_seconds: float = time_seconds
        self.raise_error: bool = raise_error
        self.print_timeout: float = print_timeout

    def reset(self):
        """Resets the timeout counter, making the new start time the current
        time.
        """
        self.start = time()

    @property
    def elapsed(self) -> float:
        return time() - self.start

    def __bool__(self) -> bool:
        elapsed = self.elapsed
        still_going = elapsed < self.time_seconds

        if not still_going and self.print_timeout:
            logging.warning(f"Timer timed out! Time: {elapsed}")
        if not still_going and self.raise_error:
            raise TimeoutError(
                f"Timer of {self.time_seconds} seconds timed out at {elapsed} seconds!"
            )
        return still_going


class Timer:
    """A context object used to time how long operations take.
    >>> timer = Timer()
    >>> with timer:
    ...     # Some long operation
    ...     pass
    >>> timer.elapsed
    >>> timer.fps
    >>> timer.total_elapsed
    >>> timer.average_fps
    >>> timer.average
    """

    def __init__(self, name: str = "", rolling_average=None):
        """
        :param name: The name of the timer, for __repr__ or named_timer(...) use
        :param rolling_average: If the rolling average is None, then all samples
        are used. If the rolling average is an int, then it will only keep the
        last X samples
        """
        self.name = name
        self.rolling_average: int = rolling_average
        self._samples: Deque[float] = deque(maxlen=rolling_average)
        self.start: Optional[float] = None
        self.end: Optional[float] = None

    def __repr__(self) -> str:
        """A helpful report that includes the timer name and sample information"""
        return (
            f"Timer(name={self.name}, "
            f"average_fps={round(self.average_fps, 2)}, "
            f"fps={round(self.fps, 2)}, "
            f"samples={len(self._samples)})"
        )

    @property
    def rolling_samples(self) -> Deque[float]:
        return self._samples

    @property
    def elapsed(self) -> float:
        """Return the total time taken by this function so far"""
        if self.end is None:
            return time() - self.start
        return self.end - self.start

    @property
    def total_elapsed(self) -> float:
        """Return the total elapsed time spent running this operation"""
        return sum(self._samples)

    @property
    def average(self) -> float:
        """Returns the average time taken by operations using this timer."""
        if len(self.rolling_samples) == 0:
            return -1
        return sum(self.rolling_samples) / len(self.rolling_samples)

    @property
    def average_fps(self) -> float:
        """Return the average FPS so far"""
        return 1 / self.average

    @property
    def fps(self) -> float:
        """Return the instantaneous FPS of the latest operation"""
        return 1 / self.elapsed

    def sample(self):
        if self.start is None:
            self.start = time()
        else:
            self.end = time()
            self._samples.append(self.end - self.start)
            self.start, self.end = self.end, None

    def __enter__(self) -> "Timer":
        self.start = time()
        self.end = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end = time()
        self._samples.append(self.end - self.start)


_global_timers = {}


def named_timer(name: str, *args, **kwargs) -> Timer:
    """Keeps track of a global timer. This function is useful for measuring the same
    piece of code in a hot-path that gets run many times.

    Example:
    >>> with named_timer("cool-code-snippet") as timer:
    ...     interesting_code = ...
    ...     cool_function_call()
    >>> print(timer)
    Timer(name=cool-code-snippet, average_fps=15650.39, fps=15650.39, samples=1)

    In this example, the named timer will collect information about the code within the
    contex over time, and be able to produce useful information such as the average FPS,
    or total elapsed time over all runs.

    :param name: The key to get the global timer
    """
    global _global_timers
    if name not in _global_timers:
        _global_timers[name] = Timer(*args, name=name, **kwargs)
    return _global_timers[name]
