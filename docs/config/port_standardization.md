# GOFR Port Standardization Summary

## Overview

All GOFR services now use a consistent port allocation strategy defined in `gofr-common/config/`.

## Port Allocation Strategy

**Base Port Pattern**: Each service gets 3 consecutive ports starting at a base (multiple of 10)

- **MCP Port** = Base + 0
- **MCPO Port** = Base + 1  
- **Web Port** = Base + 2

## Current Port Assignments

| Service    | Base | MCP  | MCPO | Web  | Purpose                          |
|------------|------|------|------|------|----------------------------------|
| gofr-doc   | 8040 | 8040 | 8041 | 8042 | Document generation              |
| gofr-plot  | 8050 | 8050 | 8051 | 8052 | Plotting and visualization       |
| gofr-np    | 8060 | 8060 | 8061 | 8062 | Numerical Python computations    |
| gofr-dig   | 8070 | 8070 | 8071 | 8072 | Data ingestion and processing    |
| gofr-iq    | 8080 | 8080 | 8081 | 8082 | Intelligence and query           |

## Infrastructure Ports

| Service    | Port(s)       | Test Port(s) | Purpose                          |
|------------|---------------|--------------|----------------------------------|
| ChromaDB   | 8000          | 8100         | Vector Database                  |
| Vault      | 8201          | 8301         | Secrets Management               |
| Neo4j      | 7474 (HTTP)   | 7574         | Graph Database (HTTP)            |
|            | 7687 (Bolt)   | 7787         | Graph Database (Bolt)            |

## Test Port Strategy

Test ports are allocated by adding **100** to the production port number. This allows running tests in parallel with production services without conflict.

| Service    | Base (Test) | MCP (Test) | MCPO (Test) | Web (Test) |
|------------|-------------|------------|-------------|------------|
| gofr-doc   | 8140        | 8140       | 8141        | 8142       |
| gofr-plot  | 8150        | 8150       | 8151        | 8152       |
| gofr-np    | 8160        | 8160       | 8161        | 8162       |
| gofr-dig   | 8170        | 8170       | 8171        | 8172       |
| gofr-iq    | 8180        | 8180       | 8181        | 8182       |

## Reserved Ports for Future Services

- 8090-8092: Reserved (Test: 8190-8192)
- 8100-8102: Used by ChromaDB Test
- 8110-8139: Available for future services (Test: 8210-8239)

## Configuration Files Updated

### gofr-common (Central Configuration)

1. **Python Module**: `src/gofr_common/config/ports.py`
   - Provides `ServicePorts` class
   - Exports `GOFR_*_PORTS` constants
   - Functions: `get_ports()`, `register_service()`, `list_services()`

2. **Shell Script**: `config/gofr_ports.sh`
   - Exports all port environment variables
   - Provides `gofr_ports_list()` and `gofr_get_ports()` helpers
   - Source this in bash scripts for consistent port configuration

3. **Docker Swarm**: `docker/gofr-swarm.yml`
   - Updated all service port mappings
   - Updated n8n MCP endpoint URLs
   - Updated OpenWebUI MCPO endpoint URLs

### Per-Project Updates

#### gofr-doc

- **Updated**: `scripts/gofr-doc.env` → Ports: 8040-8042
- **Updated**: `scripts/run_tests.sh` → Sources centralized ports
- **Updated**: `test/mcp/*.py` → Default ports: 8040, 8042

#### gofr-plot  

- **Updated**: `scripts/run_tests.sh` → Ports: 8050-8052
- **Existing**: Tests already using correct ports

#### gofr-np

- **Updated**: `scripts/gofrnp.env` → Ports: 8060-8062 (no change)
- **Existing**: Already using correct allocation

#### gofr-dig

- **Updated**: `scripts/gofr-dig.env` → Ports: 8070-8072 (was 8030-8032)

#### gofr-iq

- **Updated**: `scripts/gofriq.env` → Ports: 8080-8082 (was 8060-8062)

## Usage Examples

### Python (via gofr-common)

```python
from gofr_common.config import get_ports, GOFR_DOC_PORTS

# Get ports for a service
doc_ports = get_ports('gofr-doc')
print(f"MCP: {doc_ports.mcp}, MCPO: {doc_ports.mcpo}, Web: {doc_ports.web}")

# Or use predefined constants
print(f"GOFR-DOC MCP: {GOFR_DOC_PORTS.mcp}")

# Get as environment dict
env_vars = GOFR_DOC_PORTS.as_env_dict('GOFR_DOC')
# {'GOFR_DOC_MCP_PORT': '8040', 'GOFR_DOC_MCPO_PORT': '8041', 'GOFR_DOC_WEB_PORT': '8042'}
```

### Bash (via gofr_ports.sh)

```bash
# Source the centralized configuration
source /path/to/gofr-common/config/gofr_ports.sh

# Ports are now available as environment variables
echo "GOFR-DOC MCP Port: ${GOFR_DOC_MCP_PORT}"

# List all services and their ports
gofr_ports_list

# Get ports for a specific service
gofr_get_ports gofr-plot
```

## Adding New Services

### Option 1: Using Python API

```python
from gofr_common.config import register_service, next_available_base

# Get next available base port
base = next_available_base()  # Returns 8090

# Register new service
new_service_ports = register_service('gofr-new', base)
```

### Option 2: Manual Addition

1. Add to `gofr-common/src/gofr_common/config/ports.py`:

   ```python
   'gofr-new': ServicePorts(mcp=8090, mcpo=8091, web=8092)
   ```

2. Add to `gofr-common/config/gofr_ports.sh`:

   ```bash
   export GOFR_NEW_MCP_PORT="${GOFR_NEW_MCP_PORT:-8090}"
   export GOFR_NEW_MCPO_PORT="${GOFR_NEW_MCPO_PORT:-8091}"
   export GOFR_NEW_WEB_PORT="${GOFR_NEW_WEB_PORT:-8092}"
   ```

3. Update `gofr-common/docker/gofr-swarm.yml` with new service definition

## Migration Notes

### Services That Changed Ports

- **gofr-dig**: 8030-8032 → 8070-8072
- **gofr-iq**: 8060-8062 → 8080-8082
- **gofr-doc**: 8000-8002 → 8040-8042

### Services That Kept Ports

- **gofr-plot**: 8050-8052 (aligned with new scheme)
- **gofr-np**: 8060-8062 (aligned with new scheme)

### Validation Steps

1. **Stop all containers**: `docker stop gofr-doc-dev gofr-plot-dev gofr-np-dev gofr-dig-dev gofr-iq-dev`
2. **Clear port bindings**: Check with `docker ps` and `netstat -tuln | grep 80[0-9][0-9]`
3. **Restart with new ports**: Containers will bind to updated ports automatically
4. **Verify**: `docker ps` should show new port mappings
5. **Test**: Run test suites to ensure connectivity

## Benefits

1. **Consistency**: All services follow the same port allocation pattern
2. **Scalability**: Easy to add new services without port conflicts
3. **Discoverability**: Port ranges clearly identify which service is running
4. **Maintainability**: Centralized configuration reduces duplication
5. **Documentation**: Self-documenting through consistent patterns

## References

- Python API: `gofr-common/src/gofr_common/config/ports.py`
- Shell Config: `gofr-common/config/gofr_ports.sh`
- Docker Swarm: `gofr-common/docker/gofr-swarm.yml`
