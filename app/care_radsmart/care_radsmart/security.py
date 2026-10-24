"""Who may do what in RAD-SMART, in CARE's facility permission model.

CARE has no radiation-therapy-technologist role, so technologists are the
facility's Staff and Nurse roles (a facility can add its own role and grant it
these permissions). Doctors approve courses; technologists or doctors approve
breakdown responses and day plans, as the department asked.
"""

import enum

from care.security.authorization.base import AuthorizationController, AuthorizationHandler
from care.security.permissions.constants import Permission, PermissionContext
from care.security.roles.role import (
    ADMIN_ROLE,
    ADMINISTRATOR,
    DOCTOR_ROLE,
    FACILITY_ADMIN_ROLE,
    NURSE_ROLE,
    STAFF_ROLE,
)

ADMINS = [ADMIN_ROLE, FACILITY_ADMIN_ROLE, ADMINISTRATOR]


class RadsmartPermissions(enum.Enum):
    can_view_radsmart = Permission(
        "Can view RAD-SMART",
        "See machines, treatment courses, the day's plan and breakdown proposals",
        PermissionContext.FACILITY,
        [DOCTOR_ROLE, NURSE_ROLE, STAFF_ROLE, *ADMINS],
    )
    can_operate_radsmart = Permission(
        "Can operate RAD-SMART",
        "Record arrival, room-in and room-out times, set machine status, approve "
        "breakdown responses and day plans (technologists and doctors)",
        PermissionContext.FACILITY,
        [DOCTOR_ROLE, NURSE_ROLE, STAFF_ROLE, *ADMINS],
    )
    can_approve_radsmart_course = Permission(
        "Can approve RAD-SMART courses",
        "Enter and approve a patient's treatment course, constraints and standing slot (doctors)",
        PermissionContext.FACILITY,
        [DOCTOR_ROLE, *ADMINS],
    )


class RadsmartAccess(AuthorizationHandler):
    def _has(self, perm, user, facility):
        return self.check_permission_in_facility_organization([perm.name], user, facility=facility)

    def can_view_radsmart(self, user, facility) -> bool:
        return self._has(RadsmartPermissions.can_view_radsmart, user, facility)

    def can_operate_radsmart(self, user, facility) -> bool:
        return self._has(RadsmartPermissions.can_operate_radsmart, user, facility)

    def can_approve_radsmart_course(self, user, facility) -> bool:
        return self._has(RadsmartPermissions.can_approve_radsmart_course, user, facility)


AuthorizationController.register_internal_controller(RadsmartAccess)
