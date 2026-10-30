"""Cross-project todo aggregation (§17 M7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.todo_service import TodoService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import notification_out, work_item_summary_out

router = APIRouter(prefix="/api/v1", tags=["todos"])


@router.get("/todos")
async def list_todos(
    project: str | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        bundle = await TodoService(uow).bundle(actor, project_key=project)
        users: dict[str, dict] = {}

        async def summary(pair) -> dict:
            proj, item = pair
            if proj.id not in users:
                users[proj.id] = await MembershipService(uow).users_index(proj.id)
            return work_item_summary_out(item, proj, users[proj.id])

        assigned = [await summary(pair) for pair in bundle.assigned]
        overdue = [await summary(pair) for pair in bundle.overdue]
        pending = []
        for entry in bundle.pending_steps:
            pending.append(
                {
                    "step": {
                        "id": entry.step.id,
                        "key": entry.step.step_key,
                        "name": entry.step.step_name,
                        "mode": entry.step.mode,
                        "status": entry.step.status,
                    },
                    "executor_user_id": entry.executor.user_id,
                    "project_key": entry.project.key,
                    "item": await summary((entry.project, entry.item)),
                }
            )
        approvals = [row for row in pending if row["step"]["mode"] == "approval"]
    return {
        "data": {
            "assigned": assigned,
            "pending_steps": pending,
            "approvals": approvals,
            "overdue": overdue,
            "mentions": [notification_out(n) for n in bundle.mentions],
        },
        "meta": {
            "assigned": len(assigned),
            "pending_steps": len(pending),
            "approvals": len(approvals),
            "overdue": len(overdue),
            "mentions": len(bundle.mentions),
            "total": len(assigned) + len(pending) + len(overdue),
        },
    }
