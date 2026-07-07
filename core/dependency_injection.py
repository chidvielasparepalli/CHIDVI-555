"""
Dependency injection container for CHIDVI 555.

Manages object creation and dependencies.
Reduces coupling between modules.
"""

from typing import Dict, Callable, Any, Optional, Type, TypeVar
from core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class ServiceRegistry:
    """
    Dependency injection container.
    
    Manages singleton services and their dependencies.
    """
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, bool] = {}
    
    def register_service(self, name: str, service: Any, singleton: bool = True):
        """
        Register a service instance.
        
        Args:
            name: Service name
            service: Service instance
            singleton: If True, the same instance is returned each time
        """
        self._services[name] = service
        self._singletons[name] = singleton
        logger.debug(f"Registered service: {name}")
    
    def register_factory(self, name: str, factory: Callable, singleton: bool = True):
        """
        Register a factory function for creating services.
        
        Args:
            name: Service name
            factory: Callable that creates the service
            singleton: If True, factory result is cached
        """
        self._factories[name] = factory
        self._singletons[name] = singleton
        logger.debug(f"Registered factory: {name}")
    
    def get_service(self, name: str) -> Any:
        """
        Get a service by name.
        
        Returns the same instance for singletons,
        creates new instances for non-singletons.
        """
        # Check if already instantiated
        if name in self._services:
            return self._services[name]
        
        # Check if factory exists
        if name in self._factories:
            instance = self._factories[name]()
            
            # Cache if singleton
            if self._singletons.get(name, True):
                self._services[name] = instance
            
            return instance
        
        raise ValueError(f"Service not registered: {name}")
    
    def has_service(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services or name in self._factories
    
    def clear(self):
        """Clear all registered services."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()


# Global service registry
service_registry = ServiceRegistry()


def register_service(name: str, service: Any, singleton: bool = True):
    """Register a service."""
    service_registry.register_service(name, service, singleton)


def register_factory(name: str, factory: Callable, singleton: bool = True):
    """Register a factory."""
    service_registry.register_factory(name, factory, singleton)


def get_service(name: str) -> Any:
    """Get a service."""
    return service_registry.get_service(name)


def has_service(name: str) -> bool:
    """Check if service exists."""
    return service_registry.has_service(name)
