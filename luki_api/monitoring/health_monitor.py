"""
Service health monitoring for LUKi API Gateway
Tracks health status of all downstream services
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum
import httpx

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Service health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceHealthCheck:
    """Health check for a single service"""
    
    def __init__(
        self,
        name: str,
        url: str,
        timeout: float = 5.0,
        check_interval: int = 30
    ):
        self.name = name
        self.url = url
        self.timeout = timeout
        self.check_interval = check_interval
        
        self.status = ServiceStatus.UNKNOWN
        self.last_check: Optional[datetime] = None
        self.last_success: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.consecutive_failures = 0
        self.response_time_ms: Optional[float] = None
    
    async def check_health(self) -> ServiceStatus:
        """
        Perform health check
        
        Returns:
            Current service status
        """
        try:
            start_time = asyncio.get_event_loop().time()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.url}/health")
            
            elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self.response_time_ms = elapsed_ms
            self.last_check = datetime.utcnow()
            
            if response.status_code == 200:
                self.status = ServiceStatus.HEALTHY
                self.last_success = datetime.utcnow()
                self.consecutive_failures = 0
                self.last_error = None
                
                logger.debug(
                    f"Health check passed for {self.name}",
                    extra={"service": self.name, "response_time_ms": elapsed_ms}
                )
            else:
                self.status = ServiceStatus.DEGRADED
                self.consecutive_failures += 1
                self.last_error = f"HTTP {response.status_code}"
                
                logger.warning(
                    f"Health check degraded for {self.name}: {response.status_code}",
                    extra={"service": self.name, "status_code": response.status_code}
                )
        
        except asyncio.TimeoutError:
            self.status = ServiceStatus.UNHEALTHY
            self.consecutive_failures += 1
            self.last_error = "Timeout"
            self.last_check = datetime.utcnow()
            
            logger.error(
                f"Health check timeout for {self.name}",
                extra={"service": self.name, "timeout": self.timeout}
            )
        
        except Exception as e:
            self.status = ServiceStatus.UNHEALTHY
            self.consecutive_failures += 1
            self.last_error = str(e)
            self.last_check = datetime.utcnow()
            
            logger.error(
                f"Health check failed for {self.name}: {e}",
                extra={"service": self.name, "error": str(e)}
            )
        
        return self.status
    
    def get_status_dict(self) -> Dict:
        """Get status as dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "response_time_ms": self.response_time_ms
        }


class HealthMonitor:
    """Monitors health of all downstream services"""
    
    def __init__(self):
        self.services: Dict[str, ServiceHealthCheck] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
    
    def register_service(
        self,
        name: str,
        url: str,
        timeout: float = 5.0,
        check_interval: int = 30
    ):
        """Register a service for health monitoring"""
        self.services[name] = ServiceHealthCheck(
            name=name,
            url=url,
            timeout=timeout,
            check_interval=check_interval
        )
        logger.info(f"Registered service for health monitoring: {name}")
    
    async def check_all_services(self) -> Dict[str, ServiceStatus]:
        """
        Check health of all registered services
        
        Returns:
            Dictionary mapping service names to statuses
        """
        results = {}
        
        for name, service in self.services.items():
            status = await service.check_health()
            results[name] = status
        
        return results
    
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        if self._running:
            logger.warning("Health monitoring already running")
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started health monitoring")
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped health monitoring")
    
    async def _monitoring_loop(self):
        """Continuous monitoring loop"""
        while self._running:
            try:
                await self.check_all_services()
                
                # Wait before next check (use minimum interval from all services)
                min_interval = min(
                    (s.check_interval for s in self.services.values()),
                    default=30
                )
                await asyncio.sleep(min_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    def get_overall_status(self) -> ServiceStatus:
        """
        Get overall system health status
        
        Returns:
            Worst status among all services
        """
        if not self.services:
            return ServiceStatus.UNKNOWN
        
        statuses = [s.status for s in self.services.values()]
        
        if any(s == ServiceStatus.UNHEALTHY for s in statuses):
            return ServiceStatus.UNHEALTHY
        elif any(s == ServiceStatus.DEGRADED for s in statuses):
            return ServiceStatus.DEGRADED
        elif all(s == ServiceStatus.HEALTHY for s in statuses):
            return ServiceStatus.HEALTHY
        else:
            return ServiceStatus.UNKNOWN
    
    def get_health_report(self) -> Dict:
        """
        Get comprehensive health report
        
        Returns:
            Dictionary with overall status and service details
        """
        return {
            "overall_status": self.get_overall_status().value,
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                name: service.get_status_dict()
                for name, service in self.services.items()
            }
        }
    
    def get_unhealthy_services(self) -> List[str]:
        """Get list of unhealthy service names"""
        return [
            name for name, service in self.services.items()
            if service.status == ServiceStatus.UNHEALTHY
        ]


# Global health monitor instance
health_monitor = HealthMonitor()
