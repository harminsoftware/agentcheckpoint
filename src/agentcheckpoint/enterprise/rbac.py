"""Role Based Access Control (RBAC) Engine.

Manages permissions for the dashboard and API operations based on user roles.
Licensed under BSL 1.1. Commercial use requires a valid license key.
"""

from typing import List, Optional
from enum import Enum

from .license import require_enterprise


class Role(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Action(str, Enum):
    READ_RUNS = "read_runs"
    READ_STATE = "read_state"
    RESUME_RUN = "resume_run"
    DELETE_RUN = "delete_run"
    EDIT_STATE = "edit_state"  # For Intervene
    MANAGE_BILLING = "manage_billing"


# Default RBAC Policy Matrix
DEFAULT_POLICY = {
    Role.ADMIN: [
        Action.READ_RUNS, Action.READ_STATE, Action.RESUME_RUN,
        Action.DELETE_RUN, Action.EDIT_STATE, Action.MANAGE_BILLING
    ],
    Role.DEVELOPER: [
        Action.READ_RUNS, Action.READ_STATE, Action.RESUME_RUN, Action.EDIT_STATE
    ],
    Role.VIEWER: [
        Action.READ_RUNS, Action.READ_STATE
    ]
}


class RBACEngine:
    """Evaluates access control rules for users and actions."""

    def __init__(self, custom_policy: Optional[dict] = None):
        # Enforce license check at initialization
        require_enterprise("Role Based Access Control (RBAC)")
        self.policy = custom_policy or DEFAULT_POLICY

    def check_permission(self, user_roles: List[str], required_action: Action) -> bool:
        """Check if any of the user's roles grant the required action."""
        for role_str in user_roles:
            try:
                role = Role(role_str.lower())
                allowed_actions = self.policy.get(role, [])
                if required_action in allowed_actions:
                    return True
            except ValueError:
                continue  # Ignore unrecognized roles from SSO
        
        return False
