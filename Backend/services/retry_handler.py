"""
Retry handler with exponential backoff for API calls.
Provides decorators and utilities for robust error handling.
"""
import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any
import time

logger = logging.getLogger("uvicorn.error")

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior"""
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        timeout: float = 60.0
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.timeout = timeout


def async_retry(config: RetryConfig = None):
    """
    Decorator for async functions with exponential backoff retry logic.
    
    Usage:
        @async_retry(RetryConfig(max_attempts=3, initial_delay=1.0))
        async def my_api_call():
            ...
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = config.initial_delay
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    # Execute with timeout
                    return await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=config.timeout
                    )
                except asyncio.TimeoutError as e:
                    last_exception = e
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{config.max_attempts} "
                        f"timed out after {config.timeout}s"
                    )
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{config.max_attempts} "
                        f"failed: {type(e).__name__}: {str(e)}"
                    )
                
                # Don't sleep after the last attempt
                if attempt < config.max_attempts:
                    logger.info(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    # Exponential backoff
                    delay = min(delay * config.exponential_base, config.max_delay)
            
            # All attempts failed
            logger.error(
                f"{func.__name__} failed after {config.max_attempts} attempts. "
                f"Last error: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent repeated calls to failing services.
    """
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info(f"Circuit breaker for {func.__name__} entering HALF_OPEN state")
            else:
                raise Exception(f"Circuit breaker OPEN for {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info(f"Circuit breaker for {func.__name__} entering HALF_OPEN state")
            else:
                raise Exception(f"Circuit breaker OPEN for {func.__name__}")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Reset failure count on success"""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            logger.info("Circuit breaker closed after successful call")
    
    def _on_failure(self):
        """Increment failure count and open circuit if threshold reached"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(
                f"Circuit breaker OPENED after {self.failure_count} failures. "
                f"Will attempt recovery in {self.recovery_timeout}s"
            )
