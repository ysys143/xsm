"""Synthetic file-result decoder fixtures and own in-memory defect mutations."""
import argparse
import base64
import copy
import hashlib
import io
import json
import types
import unittest
from pathlib import Path
import participant_v6


def fixtures():
    text='한글\n'.encode('utf-8');binary=b'\x00\xff\x80'
    entries=[]
    for identifier,name,data,label in [('d'*32,'한글.txt',text,'source α'),('e'*32,'binary.bin',binary,None)]:
        entries.append({'id':identifier,'version':2,'name':name,'original_name':name,'source_version':label,
            'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'copy':True,'input_source':'caller-inline'})
    manifest={'schema':'xsm.files/v1','id':'a'*32,'version':2,'previous':'b'*32,
        'owner':{'runtime':'fixture','home_id':'c'*64,'session_id':'opaque-original-owner'},
        'binding':{'request_id':'synthetic-manifest','body_sha256':hashlib.sha256(b'fixture body').hexdigest()},
        'created_at':1700000000.125,'expires_at':1700604800.125,'files':entries,'size':len(text)+len(binary)}
    # Fixture construction only; the consumer never reserializes to verify a hash.
    raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    digest=hashlib.sha256(raw).hexdigest();manifest['sha256']=digest
    ordinary={'storage_id':'f'*32,'manifest':manifest,'inbox_pending':0}
    canonical={'storage_id':'f'*32,'canonical_format':'xsm.files/v1','manifest_sha256':digest,
               'encoding':'base64','content':base64.b64encode(raw).decode('ascii'),'inbox_pending':0}
    entry={'storage_id':'f'*32,'entry_id':entries[0]['id'],'encoding':'text','content':text.decode('utf-8')}
    reference={'path':'manifest:'+manifest['id'],'id':manifest['id'],'version':2,'sha256':digest,'size':manifest['size']}
    return ordinary,canonical,entry,reference,raw


def suite(module,schema):
    class Decoder(unittest.TestCase):
        def setUp(self):
            self.consumer=module.FileConsumer(schema)
            self.ordinary,self.canonical,self.entry,self.reference,self.raw=fixtures()
        def verify(self,ordinary=None,canonical=None,expected_sha=None):
            return self.consumer.verify_manifest(ordinary or self.ordinary,canonical or self.canonical,storage_id='f'*32,
                manifest_id='a'*32,expected_sha256=expected_sha or self.ordinary['manifest']['sha256'])
        def rewritten_raw(self,raw):
            ordinary=copy.deepcopy(self.ordinary);canonical=copy.deepcopy(self.canonical)
            digest=hashlib.sha256(raw).hexdigest()
            ordinary['manifest']['sha256']=digest;canonical['manifest_sha256']=digest
            canonical['content']=base64.b64encode(raw).decode('ascii')
            return ordinary,canonical,digest
        def test_three_result_kinds_and_reference(self):
            for result in (self.ordinary,self.canonical,self.entry):module.validate_schema(result,schema)
            got=self.verify()
            self.assertEqual(got['preimage'],self.raw)
            self.assertTrue(module.json_equal(got['parsed_preimage'],{k:v for k,v in self.ordinary['manifest'].items() if k!='sha256'}))
            self.consumer.verify_reference(self.reference,self.ordinary['manifest'])
            data=self.consumer.verify_entry(self.entry,storage_id='f'*32,metadata=self.ordinary['manifest']['files'][0],encoding='text')
            self.assertEqual(data,'한글\n'.encode('utf-8'))
        def test_independent_sha_uses_exact_bytes(self):
            # JSON whitespace leaves the complete value identical but changes bytes.
            bad=copy.deepcopy(self.canonical);bad['content']=base64.b64encode(b' '+self.raw).decode('ascii')
            with self.assertRaises(module.FileContractError):self.verify(canonical=bad)
        def test_expected_and_reported_digests_are_bound(self):
            with self.assertRaises(module.FileContractError):self.verify(expected_sha='0'*64)
            bad=copy.deepcopy(self.canonical);bad['manifest_sha256']='0'*64
            with self.assertRaises(module.FileContractError):self.verify(canonical=bad)
        def test_every_non_digest_manifest_field_is_preserved(self):
            changes=[('owner',lambda m:m['owner'].__setitem__('home_id','1'*64)),
                ('binding',lambda m:m['binding'].__setitem__('request_id','different-request')),
                ('created_at',lambda m:m.__setitem__('created_at',m['created_at']+0.25)),
                ('expires_at',lambda m:m.__setitem__('expires_at',m['expires_at']+1)),
                ('previous',lambda m:m.__setitem__('previous',None)),
                ('version',lambda m:m.__setitem__('version',3)),
                ('source_version',lambda m:m['files'][0].__setitem__('source_version','changed caller label')),
                ('original_name',lambda m:m['files'][0].__setitem__('original_name','changed.txt')),
                ('input_source',lambda m:m['files'][0].__setitem__('input_source','cli-os-read')),
                ('entry_name',lambda m:m['files'][0].__setitem__('name','other.txt'))]
            for label,change in changes:
                with self.subTest(field=label):
                    bad=copy.deepcopy(self.ordinary);change(bad['manifest'])
                    with self.assertRaises(module.FileContractError):self.verify(ordinary=bad)
        def test_only_top_level_sha256_is_excluded(self):
            # Entry sha256 remains part of the full compared value.
            bad=copy.deepcopy(self.ordinary);bad['manifest']['files'][0]['sha256']='0'*64
            with self.assertRaises(module.FileContractError):self.verify(ordinary=bad)
            raw=json.dumps(self.ordinary['manifest'],ensure_ascii=False,separators=(',',':')).encode('utf-8')
            ordinary,canonical,digest=self.rewritten_raw(raw)
            with self.assertRaises(module.FileContractError):self.verify(ordinary,canonical,digest)
        def test_base64_is_strict(self):
            bad=copy.deepcopy(self.canonical);bad['content']='!!!!'+bad['content']
            with self.assertRaises(module.FileContractError):self.verify(canonical=bad)
        def test_manifest_bytes_require_utf8_not_utf16(self):
            raw=b'\xfe\xff'+self.raw.decode('utf-8').encode('utf-16-be')
            ordinary,canonical,digest=self.rewritten_raw(raw)
            with self.assertRaises(module.FileContractError):self.verify(ordinary,canonical,digest)
        def test_duplicate_manifest_keys_rejected(self):
            raw=b'{"version":2,'+self.raw[1:]
            ordinary,canonical,digest=self.rewritten_raw(raw)
            with self.assertRaises(module.FileContractError):self.verify(ordinary,canonical,digest)
        def test_storage_and_manifest_id_version_bindings(self):
            bad=copy.deepcopy(self.canonical);bad['storage_id']='0'*32
            with self.assertRaises(module.FileContractError):self.verify(canonical=bad)
            with self.assertRaises(module.FileContractError):
                self.consumer.verify_manifest(self.ordinary,self.canonical,storage_id='f'*32,manifest_id='0'*32,
                    expected_sha256=self.ordinary['manifest']['sha256'])
            with self.assertRaises(module.FileContractError):
                self.consumer.verify_manifest(self.ordinary,self.canonical,storage_id='f'*32,manifest_id='a'*32,
                    version=1,expected_sha256=self.ordinary['manifest']['sha256'])
        def test_schema_discriminators_unknown_fields_and_boolean_numbers(self):
            cases=[]
            mixed=copy.deepcopy(self.canonical);mixed['entry_id']='d'*32;cases.append(mixed)
            bad=copy.deepcopy(self.ordinary);bad['unknown']='field';cases.append(bad)
            bad=copy.deepcopy(self.canonical);bad['canonical_format']='RFC8785';cases.append(bad)
            bad=copy.deepcopy(self.ordinary);bad['manifest']['files'][0]['copy']=1;cases.append(bad)
            bad=copy.deepcopy(self.ordinary);bad['manifest']['files'][0]['size']=True;cases.append(bad)
            bad=copy.deepcopy(self.ordinary);del bad['manifest']['owner'];cases.append(bad)
            for value in cases:
                with self.assertRaises(module.FileContractError):module.validate_schema(value,schema)
        def test_integral_number_is_a_schema_integer_but_boolean_is_not(self):
            ordinary=copy.deepcopy(self.ordinary)
            ordinary['manifest']['version']=2.0
            ordinary['manifest']['files'][0]['size']=float(ordinary['manifest']['files'][0]['size'])
            # JSON numeric values are equal; byte hash still uses supplied bytes.
            self.verify(ordinary=ordinary)
            ordinary['manifest']['version']=True
            with self.assertRaises(module.FileContractError):self.verify(ordinary=ordinary)
        def test_entry_size_hash_and_request_failures(self):
            meta=self.ordinary['manifest']['files'][0]
            for change in ({'content':'changed bytes'},{'storage_id':'0'*32},{'entry_id':'0'*32},{'encoding':'base64','content':'!!!!'}):
                bad=dict(self.entry,**change)
                with self.assertRaises(module.FileContractError):self.consumer.verify_entry(bad,storage_id='f'*32,metadata=meta,encoding='text')
        def test_reference_values_are_semantically_bound(self):
            for change in ({'path':'manifest:'+'b'*32},{'version':3},{'size':0},{'sha256':'0'*64}):
                bad=dict(self.reference,**change)
                with self.assertRaises(module.FileContractError):self.consumer.verify_reference(bad,self.ordinary['manifest'])
        def test_passive_annotations_are_not_consumption(self):
            claim={'id':'notice-original','token':'opaque-token','owner':{'type':'fixture','id':'owner'},'generation':'g','digest':'9'*64}
            for value in (self.ordinary,self.canonical,self.entry):
                annotated=copy.deepcopy(value)
                annotated.update(inbox_pending=None,inbox_notice='fixture only',inbox_pending_known=1,
                    inbox_pending_diagnostics=['fixture diagnostic'],incoming={'messages':['peer text'],'claims':[claim]})
                module.validate_schema(annotated,schema)
            calls=[]
            class MockPeer:
                def operation(fake,session,operation,**params):
                    calls.append((operation,params))
                    return copy.deepcopy(self.canonical if params.get('manifest_bytes') else self.ordinary)
            self.consumer.read_manifest(MockPeer(),{'session':'fixture'},storage_id='f'*32,manifest_id='a'*32,
                expected_sha256=self.ordinary['manifest']['sha256'],outgoing=True)
            self.assertEqual([name for name,params in calls],['xsm_files','xsm_files'])
            self.assertEqual(calls[1][1],{'storage_id':'f'*32,'outgoing':True,'manifest_bytes':True})
    return unittest.defaultTestLoader.loadTestsFromTestCase(Decoder)


def run(module,schema):
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite(module,schema))
    return {'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'output':stream.getvalue()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    schema=json.loads((args.bundle/'file-result.schema.json').read_text(encoding='utf-8'))
    source=Path(participant_v6.__file__).read_text(encoding='utf-8')
    results={'baseline':run(participant_v6,schema),'mutants':{}}
    mutations={
        'byte_sha_not_checked':("if not digest==canonical['manifest_sha256']==manifest['sha256']==expected_sha256:","if False:"),
        'complete_value_not_compared':("if not json_equal(decoded,expected):","if False:"),
        'permissive_base64':("base64.b64decode(content,validate=True)","base64.b64decode(content,validate=False)"),
        'json_bytes_autodetection':("decoded=decode_frame(raw)","decoded=__import__('json').loads(raw)"),
        'storage_binding_ignored':("if ordinary['storage_id']!=storage_id or canonical['storage_id']!=storage_id:","if False:"),
        'unknown_fields_accepted':("if rule.get('additionalProperties') is False and value.keys()-props.keys():","if False:"),
    }
    for name,(before,after) in mutations.items():
        if source.count(before)!=1:raise AssertionError('mutation binding missing '+name)
        module=types.ModuleType('own_v6_mutant_'+name)
        exec(compile(source.replace(before,after),'<own v6 decoder mutation>','exec'),module.__dict__)
        results['mutants'][name]=run(module,schema)
    results['status']='passed' if results['baseline']['passed'] and all(not r['passed'] for r in results['mutants'].values()) else 'failed'
    with args.output.open('x',encoding='utf-8') as handle:json.dump(results,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'status':results['status'],'baseline_tests':results['baseline']['tests'],
                      'mutants_detected':sum(not r['passed'] for r in results['mutants'].values())}))
    return 0 if results['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
