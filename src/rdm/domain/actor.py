"""The authenticated actor for one request (§17).

A credential belongs to a human user. It may optionally act *as* one of that
human's agents (PAT ``act_as_user_id`` or the OAuth consent selection). Project
roles are always resolved from the **human's** membership rows; the agent row
exists only to grant project visibility. Agent identity matters for attribution
and for the DONE completion gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from rdm.domain.entities import ProjectMember, User
from rdm.domain.enums import ProjectRole

_ALL_PROJECT_ROLES: tuple[str, ...] = tuple(role.value for role in ProjectRole)


@dataclass(frozen=True)
class Actor:
    human: User
    identity: User
    memberships: Mapping[str, ProjectMember] = field(default_factory=dict)
    # Agents whose ``manager_user_id`` is ``human.id`` (§17.101). A human may
    # operate items assigned to these agents when acting as themselves.
    managed_agent_ids: frozenset[str] = field(default_factory=frozenset)
    token_id: str = ""
    token_kind: str = "pat"
    client_id: str | None = None
    family_id: str | None = None

    # --- identity aliases (what logs/attribution should show) -------------

    @property
    def id(self) -> str:
        return self.identity.id

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def type(self) -> str:
        return self.identity.type

    @property
    def email(self) -> str | None:
        return self.identity.email

    @property
    def is_agent(self) -> bool:
        return self.identity.is_agent

    @property
    def is_act_as(self) -> bool:
        return self.identity.id != self.human.id

    def manages_agent(self, user_id: str | None) -> bool:
        """Whether ``user_id`` is an agent managed by this actor's human.

        Only valid when the human acts as themselves: an agent identity may not
        operate its sibling agents' work just because they share a manager.
        """
        return not self.is_act_as and user_id is not None and user_id in self.managed_agent_ids

    def can_act_for_user(self, user_id: str | None) -> bool:
        """True for the acting identity itself or an agent it manages."""
        return user_id is not None and (user_id == self.id or self.manages_agent(user_id))

    # --- organization -----------------------------------------------------

    @property
    def org_id(self) -> str:
        return self.human.org_id

    @property
    def human_id(self) -> str:
        return self.human.id

    @property
    def org_roles(self) -> list[str]:
        return list(self.human.org_roles)

    @property
    def is_org_owner(self) -> bool:
        return self.human.is_org_owner

    def has_org_role(self, *roles: str) -> bool:
        wanted = set(roles)
        return self.is_org_owner or bool(wanted & set(self.human.org_roles))

    # --- projects ---------------------------------------------------------

    def membership(self, project_id: str) -> ProjectMember | None:
        return self.memberships.get(project_id)

    def is_member(self, project_id: str) -> bool:
        return project_id in self.memberships or self.is_org_owner

    def project_roles(self, project_id: str) -> list[str]:
        """Roles the human holds in a project; org owners get every role."""
        if self.is_org_owner:
            return list(_ALL_PROJECT_ROLES)
        membership = self.memberships.get(project_id)
        return list(membership.roles) if membership else []

    def project_ids(self) -> list[str]:
        return list(self.memberships.keys())
