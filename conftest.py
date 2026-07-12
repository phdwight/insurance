# Import the real (editable-installed) service packages before pytest collects
# tests. Without this, pytest's importlib mode registers the top-level service
# DIRECTORIES (api/, agent/, ...) as namespace packages in sys.modules, which
# shadows the actual packages living in <service>/src/.
import mcp_server  # noqa: F401

import agent  # noqa: F401
import api  # noqa: F401
import ingestion  # noqa: F401
import shared  # noqa: F401
