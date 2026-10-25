"""S8: 非法操作矩阵：非法转换/跨项目 id/软删恢复父链/乐观锁。"""

from __future__ import annotations

from e2e.harness.context import Harness


def run(h: Harness) -> None:
    h.project("S8")
    h.member("S8", "tl", roles=["manager"])
    h.project("OTHER")

    task = h.item("S8", {"kind": "task", "title": "矩阵任务", "task_type": "backend"})
    display = task["display_id"]
    version = _version(h, display)

    # 1. illegal transition TODO -> DONE
    r = h.rest.post(
        f"/work-items/{display}/transition",
        {"to": "DONE", "row_version": version},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WORKFLOW_ILLEGAL_TRANSITION"
    assert h.db.item(display)["status"] == "TODO"

    # 2. cross-project id access (item from S8 read under OTHER context)
    foreign = h.rest.get("/projects/OTHER/work-items", params={"q": "矩阵"})
    assert foreign.status_code == 200
    assert foreign.json()["data"] == []
    missing = h.rest.post(
        "/work-items/OTHER-1/transition",
        {"to": "IN_PROGRESS", "row_version": 1},
    )
    assert missing.status_code == 404

    # 3. soft-delete then restore; parent-chain rule on a nested child
    parent = h.item("S8", {"kind": "story", "title": "父故事"})
    child = h.item(
        "S8",
        {"kind": "task", "title": "子任务", "parent": parent["display_id"],
         "task_type": "backend"},
    )
    deleted = h.rest.delete(f"/work-items/{child['display_id']}")
    assert deleted.status_code == 200
    assert h.rest.get(f"/work-items/{child['display_id']}").status_code == 404
    # Delete the parent while the child is soft-deleted, then restore child:
    h.rest.delete(f"/work-items/{parent['display_id']}")
    restored = h.rest.post(f"/work-items/{child['display_id']}/restore")
    assert restored.status_code == 404
    # Restore parent first, then child succeeds.
    h.rest.post(f"/work-items/{parent['display_id']}/restore")
    restored2 = h.rest.post(f"/work-items/{child['display_id']}/restore")
    assert restored2.status_code == 200, restored2.text

    # 4. optimistic lock: stale version is rejected.
    r = h.rest.post(
        f"/work-items/{display}/transition",
        {"to": "IN_PROGRESS", "row_version": version},
    )
    assert r.status_code == 200, r.text
    stale = h.rest.patch(
        f"/work-items/{display}",
        {"title": "旧版本修改", "row_version": version},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT_VERSION"


def _version(h: Harness, display_id: str) -> int:
    return h.rest.get(f"/work-items/{display_id}").json()["data"]["row_version"]
