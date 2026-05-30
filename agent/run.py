"""巡查者 (Patroller) - Windows PC Security Monitoring Agent.

Entry point for starting the agent.
"""

import sys
import os

# Ensure the project root is on the path so 'agent' package is importable.
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent.main import PatrollerAgent


def main() -> None:
    """Start the Patroller agent."""
    agent = PatrollerAgent()
    agent.run()


if __name__ == "__main__":
    main()
