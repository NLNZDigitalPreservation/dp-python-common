"""Provides functions for graceful exiting ."""

import logging
import os
import signal
import sys
from queue import Queue
from threading import Thread
from typing import NoReturn

from .time_utils import SignalTimeout

_exit_requests = Queue()
_before_exit_callbacks = []


def start_graceful_exit(is_error):
    """Requests for a graceful exit to start on the main thread."""
    _exit_requests.put(1 if is_error else 0)


def add_before_exit_callback(callback):
    """Adds a callback to be run before a graceful exit.

    :param callback: The function to run
    """
    _before_exit_callbacks.append(callback)


def on_exit(status_code: int, force: bool = False) -> NoReturn:
    """The function that will be called to exit App.

    This is used so that tests can mock it out. Believe it or not, but you don't
    want tests to randomly exit once App is supposedly shutting down.

    :param status_code: The status code to exit with
    :param force: If True, this will hard-shut-down the process. This is set
        if the callbacks for gracefully shutting down failed, and now threads
        can't reliably be known to have shut down. In those cases, it's
        important for the service to still be able to close, so that docker
        can re-start it.
    """
    if force:
        os._exit(status_code)
    else:
        sys.exit(status_code)


def wait_for_exit() -> NoReturn:
    """Blocks until a graceful exit request is received, then exit."""
    signal.signal(signal.SIGINT, lambda *args: start_graceful_exit(False))
    signal.signal(signal.SIGTERM, lambda *args: start_graceful_exit(False))

    status_code = _exit_requests.get()
    logging.info(f"An exit has been requested with status code {status_code}")

    _before_exit_callbacks.reverse()
    try:
        for callback in _before_exit_callbacks:
            logging.info(f"Calling before_exit_callback '{callback.__qualname__}'")
            timeout = SignalTimeout(timeout=1)
            with timeout:
                callback()
    except Exception as ex:
        logging.error(
            f"Exception when calling before_exit_callback "
            f"'{callback.__qualname__}': {ex}\n"
            f"Shutting down aggressively."
        )
        on_exit(status_code, force=True)

    logging.info(f"Gracefully shut down. status_code={status_code}")

    on_exit(status_code, True)


class ServiceThread(Thread):
    """A thread that provides a necessary service and is expected to run
    indefinitely. If this thread crashes, the entire application will exit.

    This class should be used instead of Thread for all background services
    that must be running in order for App to operate properly.
    """

    def __init__(self, daemon=True, *args, **kwargs):
        super().__init__(daemon=daemon, *args, **kwargs)

    def run(self):
        """A thin wrapper around Thread.run() that catches exceptions and
        initiates an application exit.
        """
        try:
            super().run()
        except Exception:
            logging.critical(
                f"Exception on service thread {self.name}, starting a graceful exit"
            )
            start_graceful_exit(True)
            raise
