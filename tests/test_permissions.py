from __future__ import annotations

from app.services.permissions import is_admin_status


def test_admin_permission_statuses() -> None:
    assert is_admin_status("administrator")
    assert is_admin_status("owner")
    assert is_admin_status("creator")
    assert not is_admin_status("member")
    assert not is_admin_status("restricted")
