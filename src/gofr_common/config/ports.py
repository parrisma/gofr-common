"""
GOFR Service Port Configuration
================================

Centralized port allocation for all GOFR services.

Port Allocation Strategy:
- Each service gets a base port in increments of 10
- MCP (Model Context Protocol) = base + 0
- MCPO (MCP Orchestrator) = base + 1
- Web (Web UI/API) = base + 2

This ensures:
1. Consistent port spacing across all services
2. Easy addition of new services
3. No port conflicts
4. Clear service identification by port range
"""

from typing import Dict, NamedTuple


class ServicePorts(NamedTuple):
    """Port configuration for a single service."""

    mcp: int
    mcpo: int
    web: int

    @property
    def base(self) -> int:
        """Return the base port for this service."""
        return self.mcp

    def as_dict(self) -> Dict[str, int]:
        """Return ports as dictionary."""
        return {
            'mcp': self.mcp,
            'mcpo': self.mcpo,
            'web': self.web
        }

    def as_env_dict(self, prefix: str) -> Dict[str, str]:
        """
        Return ports as environment variable dictionary.

        Args:
            prefix: Environment variable prefix (e.g., 'GOFR_DOC')

        Returns:
            Dictionary of environment variables
        """
        return {
            f'{prefix}_MCP_PORT': str(self.mcp),
            f'{prefix}_MCPO_PORT': str(self.mcpo),
            f'{prefix}_WEB_PORT': str(self.web)
        }


# Port allocation starts at 8040 with increments of 10
_BASE_PORT = 8040
_PORT_INCREMENT = 10

# Service port assignments
PORTS = {
    'gofr-doc': ServicePorts(
        mcp=8040,
        mcpo=8041,
        web=8042
    ),
    'gofr-plot': ServicePorts(
        mcp=8050,
        mcpo=8051,
        web=8052
    ),
    'gofr-np': ServicePorts(
        mcp=8060,
        mcpo=8061,
        web=8062
    ),
    'gofr-dig': ServicePorts(
        mcp=8070,
        mcpo=8071,
        web=8072
    ),
    'gofr-iq': ServicePorts(
        mcp=8080,
        mcpo=8081,
        web=8082
    ),
}

# Test Port Strategy: Prod + 100
# gofr-doc test: 8140-8142
# gofr-plot test: 8150-8152
# ...

# Infrastructure Ports
# ChromaDB: 8000 (Test: 8100)
# Vault: 8201 (Test: 8301)
# Neo4j: 7474/7687 (Test: 7574/7787)


def get_ports(service_name: str) -> ServicePorts:
    """
    Get port configuration for a service.

    Args:
        service_name: Name of the service (e.g., 'gofr-doc')

    Returns:
        ServicePorts configuration

    Raises:
        KeyError: If service name is not registered
    """
    return PORTS[service_name]


def register_service(service_name: str, base_port: int) -> ServicePorts:
    """
    Register a new service with port allocation.

    Args:
        service_name: Name of the service
        base_port: Base port for the service (must be multiple of 10)

    Returns:
        ServicePorts configuration

    Raises:
        ValueError: If base_port is not valid or conflicts with existing
    """
    if base_port % 10 != 0:
        raise ValueError(f"Base port must be a multiple of 10, got {base_port}")

    # Check for conflicts
    for name, ports in PORTS.items():
        if ports.base == base_port:
            raise ValueError(
                f"Port {base_port} already allocated to service '{name}'"
            )
        if base_port < ports.base + 3 and base_port + 3 > ports.base:
            raise ValueError(
                f"Port range {base_port}-{base_port+2} conflicts with "
                f"service '{name}' ({ports.base}-{ports.base+2})"
            )

    service_ports = ServicePorts(
        mcp=base_port,
        mcpo=base_port + 1,
        web=base_port + 2
    )
    PORTS[service_name] = service_ports
    return service_ports


def list_services() -> Dict[str, ServicePorts]:
    """
    List all registered services and their ports.

    Returns:
        Dictionary of service names to ServicePorts
    """
    return PORTS.copy()


def next_available_base() -> int:
    """
    Get the next available base port.

    Returns:
        Next available base port (multiple of 10)
    """
    if not PORTS:
        return _BASE_PORT

    max_base = max(ports.base for ports in PORTS.values())
    return max_base + _PORT_INCREMENT


# Convenience accessors for each service
GOFR_DOC_PORTS = PORTS['gofr-doc']
GOFR_PLOT_PORTS = PORTS['gofr-plot']
GOFR_NP_PORTS = PORTS['gofr-np']
GOFR_DIG_PORTS = PORTS['gofr-dig']
GOFR_IQ_PORTS = PORTS['gofr-iq']


__all__ = [
    'ServicePorts',
    'PORTS',
    'get_ports',
    'register_service',
    'list_services',
    'next_available_base',
    'GOFR_DOC_PORTS',
    'GOFR_PLOT_PORTS',
    'GOFR_NP_PORTS',
    'GOFR_DIG_PORTS',
    'GOFR_IQ_PORTS',
]
