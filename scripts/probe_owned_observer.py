"""Operator-only diagnostics for an exact probe-owned service in isolated state.

Never expose these records through public/model operations. Imports are lazy so
probe programs can set isolated roots before loading any backend module.
"""
from pathlib import Path


class OwnedProbeObserver:
    def __init__(self, state_root, parent_ref, name, worker_id):
        self.state_root = Path(state_root).resolve()
        self.parent_ref, self.name, self.worker_id = parent_ref, name, worker_id

    def worker(self):
        from xsm import paths
        if Path(paths.HOME).resolve() != self.state_root:
            raise RuntimeError('probe observer refuses a different state root')
        from xsm import workers
        value = workers.load(self.name)
        if (not value or value.get('mode') != 'owned' or value.get('owned') is not True or value.get('id') != self.worker_id
                or value.get('parent_ref') != self.parent_ref
                or (value.get('owner') or {}).get('ref') != self.parent_ref):
            raise RuntimeError('probe owned service identity changed')
        return value

    def request(self, request_id):
        worker = self.worker()
        from xsm import owned_requests
        value = owned_requests.status(worker['owner'], request_id, sender=worker['owner'])
        if value.get('worker', {}).get('id') != self.worker_id:
            raise RuntimeError('probe request does not belong to the selected service')
        return value

    def stop_children(self):
        worker = self.worker()
        from xsm import owned_requests, workers, identity
        requests = []
        for row in owned_requests.list_requests(worker['owner'], worker['owner']):
            value = owned_requests.status(worker['owner'], row['id'], sender=worker['owner'])
            if value.get('worker', {}).get('id') == self.worker_id:
                requests.append(value)
        # Close queued launch gates before selecting children, including an RPC
        # whose response was lost before the probe could collect its child.
        for value in requests:
            if value['status'] in ('queued','reserved','acknowledged','running') or (value['status']=='unknown' and value['slot_occupied']):
                workers.cancel_owned(self.name, worker['owner'], value['id'])
        children = set()
        for value in requests:
            child = self.request(value['id']).get('child') or {}
            if type(child.get('pid')) is int and isinstance(child.get('lstart'), str) and child['lstart']:
                children.add((child['pid'], child['lstart']))
        for pid, birth in children:
            if identity.pid_alive(pid) and identity.process_matches(pid, birth) is True:
                workers._terminate(pid, birth)
        return all(not identity.pid_alive(pid) or identity.process_matches(pid, birth) is False
                   for pid, birth in children)
