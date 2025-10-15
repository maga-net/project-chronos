import time
import logging
from functools import wraps
from typing import Callable, Any, Type

# Configure a default logger for the module to use if none is provided.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - chronos-timing - %(levelname)s - %(message)s'
)
default_logger = logging.getLogger(__name__)

def timeit(logger: logging.Logger = None, format_str: str = "Function '{func_name}' executed in {duration:.4f}s"):
    """
    A decorator to measure and log the execution time of a function.

    This decorator can be used to easily profile functions and understand
    performance bottlenecks.

    Args:
        logger (logging.Logger, optional): The logger to use for output. 
                                           If None, a default module-level logger is used.
        format_str (str, optional): A format string for the log message.
                                    Available placeholders: {func_name}, {duration}.

    Returns:
        Callable: The decorated function.
    """
    # If a logger is not provided, use the default module logger
    log = logger or default_logger

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            """Wrapper function that adds timing logic."""
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                duration = end_time - start_time
                log_message = format_str.format(
                    func_name=func.__name__,
                    duration=duration
                )
                log.info(log_message)
        return wrapper
    return decorator
