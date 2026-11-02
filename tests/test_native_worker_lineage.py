"""Host-observed lineage narrows worker budget, never peer scope or approval."""
import os
from pathlib import Path
from unittest import mock
from tests.test_protocol import ProtocolFixture


class NativeWorkerLineageTest(ProtocolFixture):
    def setUp(self):
        super().setUp()
        from xsm import registry,workers
        owner=registry.upsert('codex',self.tmp+'/owner','owner',os.getpid(),self.tmp)
        with mock.patch.object(workers,'_check_installed'),mock.patch.dict(os.environ,{k:'' for _,keys in workers.FRAMEWORKS for k in keys}):
            self.worker=workers.create_owned('claude',caller=owner,name='lineage',home=self.tmp+'/native')
        self.worker['runtime']='fixture';self.worker['owned_sessions']=['native-root'];workers.save(self.worker)
        self.profile=self.worker['home']

    def native(self,name,parent=None,profile=None,cwd=None):
        fields=dict(runtime='fixture',profile=profile or self.profile,conversation=name,cwd=cwd or self.tmp,
                    capabilities=['messaging','inbox','native-lineage'])
        if parent is not None:fields['parent_conversation']=parent
        return self.connection.dispatch('session.open',fields)

    def record(self,opened):return self.connection.sessions[opened['session']].record

    def test_native_child_and_grandchild_keep_owned_budget_without_ambient_worker(self):
        from xsm import workers
        self.native('native-root')
        child=self.native('native-child','native-root');grandchild=self.native('native-grandchild','native-child')
        with mock.patch.dict(os.environ,{'XSM_WORKER':''}):
            for opened in (child,grandchild):
                self.assertEqual(workers.for_record(self.record(opened))['id'],self.worker['id'])
                with self.assertRaisesRegex(workers.WorkerError,'max_depth'):workers.depth_budget(self.record(opened))

    def test_lineage_does_not_link_another_workspace_or_profile(self):
        from xsm import config,workers
        root=self.native('native-root');other=Path(self.tmp,'other');other.mkdir()
        child=self.native('child','native-root',cwd=str(other))
        self.assertEqual(workers.for_record(self.record(child))['id'],self.worker['id'])
        self.assertIsNone(config.scope_for(self.record(root),self.record(child))[0])
        self.native('native-root',profile=self.profile+'-different')
        unrelated=self.native('child','native-root',profile=self.profile+'-different')
        self.assertIsNone(workers.for_record(self.record(unrelated)))

    def test_parent_is_retained_on_resume_and_cannot_be_reassigned(self):
        from xsm.protocol import ProtocolError
        child=self.native('child','native-root')
        self.connection.dispatch('session.close',{'session':child['session']})
        resumed=self.native('child')
        self.assertIn('protocol_parent',self.record(resumed))
        self.connection.dispatch('session.close',{'session':resumed['session']})
        with self.assertRaisesRegex(ProtocolError,'parent identity changed'):self.native('child','different-root')

    def test_missing_or_cyclic_parent_is_not_an_ordinary_top_level_budget(self):
        from xsm import workers
        missing=self.native('missing-child','unavailable')
        with self.assertRaisesRegex(workers.WorkerError,'unavailable'):workers.for_record(self.record(missing))
        left=self.native('left','right');self.native('right','left')
        with self.assertRaisesRegex(workers.WorkerError,'cycle'):workers.for_record(self.record(left))

    def test_parent_is_host_metadata_with_explicit_negotiation(self):
        from xsm.protocol import ProtocolError
        with self.assertRaises(ProtocolError):self.native('self','self')
        with self.assertRaises(ProtocolError):self.native('bad',True)
        with self.assertRaisesRegex(ProtocolError,'native-lineage'):
            self.connection.dispatch('session.open',{'runtime':'fixture','profile':self.profile,'conversation':'no-cap',
                'cwd':self.tmp,'capabilities':['messaging'],'parent_conversation':'native-root'})
