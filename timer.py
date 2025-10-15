import time
from typing import Optional, Callable
import logging

# Set up a logger for the module
logger = logging.getLogger(__name__)

class Timer:
    """
    A context manager to measure the execution time of a code block.

    This timer uses `time.perf_counter()` for high-precision measurement.
    It can be configured to log the elapsed time upon exiting the context.

    Usage:
        >>> import logging
        >>> logging.basicConfig(level=logging.INFO)
        >>> with Timer(name="data_processing"):
        ...     # some time-consuming operations
        ...     time.sleep(0.1)
        INFO:root:Timer 'data_processing' took 0.1001 seconds.

        >>> timer = Timer(verbose=False)
        >>> with timer:
        ...     time.sleep(0.1)
        >>> print(f"Elapsed time: {timer.elapsed:.4f}s")
        Elapsed time: 0.1001s
    """
    def __init__(self, name: Optional[str] = None, verbose: bool = True, logger_func: Optional[Callable[[str], None]] = None):
        """
        Initializes the Timer.

        Args:
            name (Optional[str]): A descriptive name for the timed block.
                                  Used in the output message.
            verbose (bool): If True, logs the elapsed time upon exiting the context.
            logger_func (Optional[Callable[[str], None]]): A custom logging function
                                                          to use. If None and verbose is True, 
                                                          logging.getLogger(__name__).info is used.
        """
        self.name = name
        self.verbose = verbose
        self.logger_func = logger_func if logger_func is not None else logger.info
        self._start_time: Optional[float] = None
        self.elapsed: Optional[float] = None

    def __enter__(self):
        """Starts the timer when entering the context."""
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stops the timer and records/logs the elapsed time."""
        if self._start_time is None:
            # This should not happen in normal context manager usage
            return False

        end_time = time.perf_counter()
        self.elapsed = end_time - self._start_time

        if self.verbose:
            name_str = f"'{self.name}' " if self.name else ""
            message = f"Timer {name_str}took {self.elapsed:.4f} seconds."
            self.logger_func(message)

        # Do not suppress exceptions
        return False
