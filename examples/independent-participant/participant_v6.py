"""Own file-result consumer: strict schema, exact digest bytes and full values.

Uses only public v6 contracts and our own previous transport/upload implementation.
No serialization of a parsed manifest is used to reconstruct legacy digest bytes.
"""
import base64
import binascii
import hashlib
import math
import re
from participant_v5 import Peer, UploadPlan, RpcError, server_command
from participant_v3 import decode_frame


class FileContractError(ValueError):
    pass


def json_equal(left,right):
    """Complete JSON value equality; booleans never equal numeric 0/1."""
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left==right
    if isinstance(left,dict) and isinstance(right,dict):
        return left.keys()==right.keys() and all(json_equal(left[k],right[k]) for k in left)
    if isinstance(left,list) and isinstance(right,list):
        return len(left)==len(right) and all(json_equal(a,b) for a,b in zip(left,right))
    if type(left) in (int,float) and type(right) in (int,float):
        return left==right
    return type(left) is type(right) and left==right


def validate_schema(value,schema,definition=None):
    """Implement exactly the keywords used by the provided file-result schema.

    Not a general Draft 2020-12 validator. Unknown keywords fail closed and no
    external reference is fetched. Caller supplies the trusted public schema.
    """
    supported={'$schema','$id','title','description','$comment','$defs','$ref','type','const','enum',
               'properties','required','additionalProperties','items','maxItems','minItems',
               'minLength','maxLength','minimum','maximum','exclusiveMinimum','pattern','oneOf','anyOf'}
    def check(value,rule,path):
        if set(rule)-supported:raise FileContractError('unsupported schema keyword at '+path)
        if '$ref' in rule:
            if not rule['$ref'].startswith('#/'):raise FileContractError('external schema reference is unsupported')
            target=schema
            for part in rule['$ref'][2:].split('/'):target=target[part.replace('~1','/').replace('~0','~')]
            check(value,target,path)
        for keyword in ('oneOf','anyOf'):
            if keyword in rule:
                matches=0
                for branch in rule[keyword]:
                    try:check(value,branch,path)
                    except FileContractError:continue
                    matches+=1
                if (keyword=='oneOf' and matches!=1) or (keyword=='anyOf' and matches==0):
                    raise FileContractError(keyword+' mismatch at '+path)
        if 'const' in rule and not json_equal(value,rule['const']):raise FileContractError('const mismatch at '+path)
        if 'enum' in rule and not any(json_equal(value,x) for x in rule['enum']):raise FileContractError('enum mismatch at '+path)
        if 'type' in rule:
            names=rule['type'] if isinstance(rule['type'],list) else [rule['type']]
            numeric=type(value) in (int,float)
            try:finite=numeric and (type(value) is int or math.isfinite(value))
            except OverflowError:finite=False
            matches={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
                     'integer':finite and (type(value) is int or value.is_integer()),'number':finite,'boolean':type(value) is bool,'null':value is None}
            if not any(matches.get(name,False) for name in names):raise FileContractError('type mismatch at '+path)
        if isinstance(value,dict):
            props=rule.get('properties',{})
            if not set(rule.get('required',[]))<=value.keys():raise FileContractError('missing field at '+path)
            if rule.get('additionalProperties') is False and value.keys()-props.keys():raise FileContractError('unknown field at '+path)
            for key in value.keys() & props.keys():check(value[key],props[key],path+'.'+key)
        if isinstance(value,list):
            if not rule.get('minItems',0)<=len(value)<=rule.get('maxItems',float('inf')):raise FileContractError('array size at '+path)
            if 'items' in rule:
                for entry in value:check(entry,rule['items'],path+'[]')
        if isinstance(value,str):
            if not rule.get('minLength',0)<=len(value)<=rule.get('maxLength',float('inf')):raise FileContractError('string length at '+path)
            if 'pattern' in rule and re.search(rule['pattern'],value) is None:raise FileContractError('pattern mismatch at '+path)
        if type(value) in (int,float):
            if 'minimum' in rule and value<rule['minimum']:raise FileContractError('below minimum at '+path)
            if 'maximum' in rule and value>rule['maximum']:raise FileContractError('above maximum at '+path)
            if 'exclusiveMinimum' in rule and value<=rule['exclusiveMinimum']:raise FileContractError('below exclusive minimum at '+path)
    rule=schema if definition is None else {'$ref':'#/$defs/'+definition}
    check(value,rule,'file-result')
    return value


def strict_base64(content):
    try:return base64.b64decode(content,validate=True)
    except (binascii.Error,ValueError,TypeError) as error:raise FileContractError('invalid strict base64') from error


class FileConsumer:
    def __init__(self,schema):
        self.schema=schema

    def verify_manifest(self,ordinary,canonical,*,storage_id,manifest_id,expected_sha256,version=None):
        validate_schema(ordinary,self.schema)
        validate_schema(ordinary,self.schema,'fileManifestResult')
        validate_schema(canonical,self.schema)
        validate_schema(canonical,self.schema,'fileCanonicalResult')
        manifest=ordinary['manifest']
        if ordinary['storage_id']!=storage_id or canonical['storage_id']!=storage_id:
            raise FileContractError('manifest storage binding mismatch')
        if manifest['id']!=manifest_id or (version is not None and manifest['version']!=version):
            raise FileContractError('manifest ID/version binding mismatch')
        raw=strict_base64(canonical['content'])
        digest=hashlib.sha256(raw).hexdigest()
        if not digest==canonical['manifest_sha256']==manifest['sha256']==expected_sha256:
            raise FileContractError('manifest byte digest mismatch')
        try:decoded=decode_frame(raw)
        except (ValueError,UnicodeError) as error:raise FileContractError('invalid manifest UTF-8 JSON') from error
        expected={key:value for key,value in manifest.items() if key!='sha256'}
        if not json_equal(decoded,expected):
            raise FileContractError('complete manifest value mismatch')
        if sum(entry['size'] for entry in manifest['files'])!=manifest['size']:
            raise FileContractError('manifest total size mismatch')
        return {'manifest':manifest,'preimage':raw,'parsed_preimage':decoded,'sha256':digest,
                'ordinary':ordinary,'canonical':canonical}

    def read_manifest(self,peer,session,*,storage_id,manifest_id,expected_sha256,version=None,outgoing=False):
        ordinary=peer.operation(session,'xsm_files',storage_id=storage_id,outgoing=outgoing)
        canonical=peer.operation(session,'xsm_files',storage_id=storage_id,outgoing=outgoing,manifest_bytes=True)
        return self.verify_manifest(ordinary,canonical,storage_id=storage_id,manifest_id=manifest_id,
                                    expected_sha256=expected_sha256,version=version)

    def verify_reference(self,reference,manifest):
        validate_schema(reference,self.schema,'fileReference')
        if (reference['id']!=manifest['id'] or reference['path']!='manifest:'+manifest['id'] or
            reference['version']!=manifest['version'] or reference['sha256']!=manifest['sha256'] or reference['size']!=manifest['size']):
            raise FileContractError('manifest reference binding mismatch')
        return reference

    def verify_entry(self,result,*,storage_id,metadata,encoding):
        validate_schema(result,self.schema)
        validate_schema(result,self.schema,'fileEntryResult')
        if result['storage_id']!=storage_id or result['entry_id']!=metadata['id'] or result['encoding']!=encoding:
            raise FileContractError('entry request binding mismatch')
        if encoding=='base64':data=strict_base64(result['content'])
        else:
            try:data=result['content'].encode('utf-8',errors='strict')
            except UnicodeError as error:raise FileContractError('invalid UTF-8 entry text') from error
        if len(data)!=metadata['size'] or hashlib.sha256(data).hexdigest()!=metadata['sha256']:
            raise FileContractError('entry size/hash mismatch')
        return data

    def read_entry(self,peer,session,*,storage_id,metadata,encoding='base64',outgoing=False):
        result=peer.operation(session,'xsm_files',storage_id=storage_id,entry_id=metadata['id'],encoding=encoding,outgoing=outgoing)
        data=self.verify_entry(result,storage_id=storage_id,metadata=metadata,encoding=encoding)
        return {'result':result,'data':data}
