"""Scope mutations use frozen roots; frontends retain their user-decision collectors."""
from __future__ import annotations

from dataclasses import dataclass
import os
from . import config


@dataclass(frozen=True)
class ProjectMembership:
    project: str
    here: str
    root: str
    leaving: bool


def prepare_membership(project, here, *, leaving=False):
    if not leaving:
        config.check_join(project)
    here = os.path.realpath(os.path.expanduser(here))
    return ProjectMembership(project, here, config.project_root(here), leaving)


def apply_membership(plan):
    if config.project_root(plan.here) != plan.root:
        raise ValueError('project root changed; request a fresh decision')
    if plan.leaving:
        return {'root': plan.root, 'changed': config.leave(plan.project, plan.here), 'leaving': True}
    config.check_join(plan.project)
    scope, added = config.join(plan.project, plan.here)
    return {'root': plan.root, 'scope': scope, 'added': added, 'leaving': False}
