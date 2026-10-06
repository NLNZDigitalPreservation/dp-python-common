import logging
from time import sleep, time

from .exiting import ServiceThread


class GilHoldDetector:
    def __init__(self, check_interval=0.1, log_threshold=0.1):
        """
        :param check_interval: How often to check for GIL locks
        :param log_threshold: How many seconds longer than the check_interval
           before logging to console that the GIL has been locked.
        """
        self.check_interval = check_interval
        self.log_threshold = log_threshold

        self.total_lock_time = 0
        """The total time in seconds where the GIL has been detected as being locked"""

        self.total_measuring_time = 0
        """The total time spent measuring the GIL"""

        self._running = True
        self._thread = ServiceThread(name="GilHoldDetector", target=self._detect_locks)
        self._thread.start()

    def _detect_locks(self):
        last_lock = time()
        while self._running:
            # Sleep and time how long the sleep lasted
            start = time()
            sleep(self.check_interval)
            end = time()

            # Calculate elapsed time and how much longer than expected the sleep lasted
            elapsed = end - start
            time_past_threshold = elapsed - self.check_interval
            self.total_measuring_time += elapsed

            # Check if the user should be warned due to a GIL lock
            if time_past_threshold > self.log_threshold:
                self.total_lock_time += time_past_threshold

                logging.info(
                    f"GIL lock detected! "
                    f"Lock time: {round(time_past_threshold, 2)}, "
                    f"Time since last lock: {round(start - last_lock, 2)}, "
                    f"Session Lock Time: {self.total_lock_time},"
                    f"Total Time Measuring: {self.total_measuring_time}"
                )
                last_lock = end

    def close(self):
        self._running = False
        self._thread.join()
