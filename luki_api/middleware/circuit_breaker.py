"""
Circuit breaker middleware for LUKi API Gateway
Prevents cascade failures by monitoring downstream service health
"""

import logging
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class ServiceCircuitBreaker:
    """Circuit breaker for a single service"""
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 60.0
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change: datetime = datetime.utcnow()
    
    def record_success(self):
        """Record successful request"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(
                f"Circuit breaker for {self.service_name}: success {self.success_count}/{self.success_threshold}",
                extra={"service": self.service_name, "state": self.state.value}
            )
            
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()
        
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            if self.failure_count > 0:
                self.failure_count = 0
    
    def record_failure(self):
        """Record failed request"""
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            logger.warning(
                f"Circuit breaker for {self.service_name}: failure {self.failure_count}/{self.failure_threshold}",
                extra={"service": self.service_name, "state": self.state.value}
            )
            
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()
        
        elif self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens circuit
            self._transition_to_open()
    
    def can_attempt(self) -> bool:
        """Check if request should be attempted"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self._should_attempt_reset():
                self._transition_to_half_open()
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout_seconds
    
    def _transition_to_open(self):
        """Transition to OPEN state"""
        self.state = CircuitState.OPEN
        self.success_count = 0
        self.last_state_change = datetime.utcnow()
        
        logger.error(
            f"Circuit breaker OPENED for {self.service_name} after {self.failure_count} failures",
            extra={
                "service": self.service_name,
                "failure_count": self.failure_count,
                "timeout_seconds": self.timeout_seconds
            }
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.failure_count = 0
        self.last_state_change = datetime.utcnow()
        
        logger.info(
            f"Circuit breaker for {self.service_name} entering HALF_OPEN state",
            extra={"service": self.service_name}
        )
    
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = datetime.utcnow()
        
        logger.info(
            f"Circuit breaker CLOSED for {self.service_name} - service recovered",
            extra={"service": self.service_name}
        )
    
    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_state_change": self.last_state_change.isoformat(),
            "timeout_seconds": self.timeout_seconds
        }


class CircuitBreakerManager:
    """Manages circuit breakers for all services"""
    
    def __init__(self):
        self.breakers: Dict[str, ServiceCircuitBreaker] = {}
    
    def get_breaker(self, service_name: str) -> ServiceCircuitBreaker:
        """Get or create circuit breaker for service"""
        if service_name not in self.breakers:
            self.breakers[service_name] = ServiceCircuitBreaker(service_name)
        return self.breakers[service_name]
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers"""
        return {
            name: breaker.get_status()
            for name, breaker in self.breakers.items()
        }
    
    async def execute_with_breaker(
        self,
        service_name: str,
        func: Callable,
        *args,
        **kwargs
    ):
        """
        Execute function with circuit breaker protection
        
        Args:
            service_name: Name of the service
            func: Async function to execute
            *args, **kwargs: Arguments to pass to function
        
        Returns:
            Function result
        
        Raises:
            Exception: If circuit is open or function fails
        """
        breaker = self.get_breaker(service_name)
        
        if not breaker.can_attempt():
            raise Exception(
                f"Circuit breaker is OPEN for {service_name}. "
                f"Service is temporarily unavailable."
            )
        
        try:
            result = await func(*args, **kwargs)
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()
