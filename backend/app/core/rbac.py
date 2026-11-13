"""Role-Based Access Control (RBAC) Definitions and Authorization Logic

Single Organization Edition: Physio One Clinic.
Initial Roles:
- Owner: Full system access, security settings, user management.
- Admin: Operational configuration and user management, except owner-only operations.
- Operator: Inbox, contacts, conversations, appointments, and operational actions.
- Viewer: Read-only access to dashboard data.
"""
from typing import Dict, List, Set

ROLE_OWNER = "Owner"
ROLE_ADMIN = "Admin"
ROLE_OPERATOR = "Operator"
ROLE_VIEWER = "Viewer"

INITIAL_ROLES = [ROLE_OWNER, ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER]

# Default permissions assigned to each role upon system initialization
ROLE_DEFAULT_PERMISSIONS: Dict[str, List[Dict[str, str]]] = {
    ROLE_OWNER: [
        {"resource": "*", "action": "*"},  # Super wildcard: full system access
    ],
    ROLE_ADMIN: [
        {"resource": "users", "action": "create"},
        {"resource": "users", "action": "read"},
        {"resource": "users", "action": "update"},
        {"resource": "users", "action": "delete"},
        {"resource": "roles", "action": "read"},
        {"resource": "inbox", "action": "*"},
        {"resource": "contacts", "action": "*"},
        {"resource": "appointments", "action": "*"},
        {"resource": "campaigns", "action": "*"},
        {"resource": "agents", "action": "*"},
        {"resource": "knowledge", "action": "*"},
        {"resource": "followups", "action": "*"},
        {"resource": "settings", "action": "read"},
        {"resource": "settings", "action": "update"},
        {"resource": "audit_logs", "action": "read"},
    ],
    ROLE_OPERATOR: [
        {"resource": "inbox", "action": "*"},
        {"resource": "contacts", "action": "read"},
        {"resource": "contacts", "action": "create"},
        {"resource": "contacts", "action": "update"},
        {"resource": "appointments", "action": "*"},
        {"resource": "campaigns", "action": "read"},
        {"resource": "followups", "action": "read"},
        {"resource": "followups", "action": "update"},
        {"resource": "knowledge", "action": "read"},
    ],
    ROLE_VIEWER: [
        {"resource": "inbox", "action": "read"},
        {"resource": "contacts", "action": "read"},
        {"resource": "appointments", "action": "read"},
        {"resource": "campaigns", "action": "read"},
        {"resource": "knowledge", "action": "read"},
        {"resource": "settings", "action": "read"},
    ],
}


def has_permission(role_name: str, resource: str, action: str, permissions: List[Dict[str, str]]) -> bool:
    """Check whether a user with given role and permission records has required permission."""
    if role_name == ROLE_OWNER:
        return True

    for perm in permissions:
        r = perm.get("resource")
        a = perm.get("action")
        if (r == "*" or r == resource) and (a == "*" or a == action):
            return True

    return False
