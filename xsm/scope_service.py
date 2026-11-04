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


def route_membership(plan, session):
    """Shared CLI/native behavior for inherited membership and parent requests."""
    from . import consent, delegation
    joined = plan.project in config.joined_projects(session)
    if not plan.leaving and joined:
        consent.take(session, 'join', plan.project)
        consent.clear_request(session, 'join', plan.project)
        return {'status': 'already-joined', 'text': 'already in ' + plan.project,
                'scope': {'kind': 'membership', 'project': plan.project,
                          'root': plan.root, 'active': True, 'changed': False}}
    if (not plan.leaving and not joined) or (plan.leaving and joined):
        owner = delegation.parent(session)
        if owner:
            verb = 'leave' if plan.leaving else 'join'
            consent.clear_request(session, verb, plan.project)
            return {'status': 'parent-pending', 'text': delegation.request_join(
                session, owner, plan.project, leaving=plan.leaving)}
    return {'status': 'direct'}


def apply_membership(plan):
    if config.project_root(plan.here) != plan.root:
        raise ValueError('project root changed; request a fresh decision')
    if plan.leaving:
        return {'root': plan.root, 'changed': config.leave(plan.project, plan.here), 'leaving': True}
    config.check_join(plan.project)
    scope, added = config.join(plan.project, plan.here)
    return {'root': plan.root, 'scope': scope, 'added': added, 'leaving': False}


@dataclass(frozen=True)
class ProjectLink:
    here: str
    there: str
    root: str
    other: str


def prepare_link(here, there):
    here = os.path.abspath(os.path.expanduser(here))
    there = os.path.abspath(os.path.expanduser(there))
    root, other = config.check_link(here, there)
    return ProjectLink(here, there, root, other)


def apply_link(plan, by):
    if config.check_link(plan.here, plan.there) != (plan.root, plan.other):
        raise ValueError('project root changed; request a fresh decision')
    entry, added = config.add_link(plan.root, plan.other, by)
    return {'entry': entry, 'added': added}


def drop_link(here, there):
    return config.drop_link(here, there)


@dataclass(frozen=True)
class SessionReach:
    folder: str
    root: str
    holder: tuple


def prepare_reach(session, folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    root = config.check_reach(folder)
    keys = ('ref', 'runtime', 'home', 'session_id', 'pid', 'lstart', 'state')
    return SessionReach(folder, root, tuple((key, session.get(key)) for key in keys))


def apply_reach(plan, by):
    if config.check_reach(plan.folder) != plan.root:
        raise ValueError('project root changed; request a fresh decision')
    session = dict(plan.holder)
    entry, added = config.add_reach(session['ref'], plan.root, by, session=session)
    return {'entry': entry, 'added': added}


def drop_reach(session, folder=None):
    return config.drop_reach(session.get('ref'), folder, session=session)
