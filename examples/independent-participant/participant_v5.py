"""Own v5 bounded upload client, derived from public contracts, stdlib only.

The transport is our previously authored participant_v3; no xsm SDK is imported.
Plans contain snapshots of caller-supplied bytes, never source paths. Preparation
never sends a message, retries unknown body delivery, or acknowledges anything.
"""
import argparse
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from participant_v3 import Peer as Transport, RpcError, server_command, decode_json


class UploadUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class FileSnapshot:
    name: str
    data: bytes
    source_version: str | None = None

    def metadata(self):
        result={'name':self.name,'size':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest()}
        if self.source_version is not None:
            result['source_version']=self.source_version
        return result


@dataclass(frozen=True)
class UploadPlan:
    target: str
    request_id: str
    text: str
    files: tuple
    previous_manifest: str | None = None
    attachment_fallback: str | None = None

    @classmethod
    def snapshot(cls, target, request_id, text, files, *, previous_manifest=None, attachment_fallback=None):
        if not isinstance(target,str) or not target:
            raise ValueError('nonempty target required')
        if not isinstance(request_id,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,160}',request_id) is None:
            raise ValueError('invalid request ID')
        if not isinstance(text,str):
            raise ValueError('text must be a string')
        if attachment_fallback not in (None,'inline'):
            raise ValueError('unsupported explicit fallback')
        if previous_manifest is not None and not isinstance(previous_manifest,str):
            raise ValueError('previous manifest must be an opaque string')
        snapshots=[]
        for item in files:
            if not isinstance(item,dict) or set(item)-{'name','data','source_version'}:
                raise ValueError('only name/data/source_version are accepted; no paths')
            if not isinstance(item.get('name'),str) or not 1<=len(item['name'])<=4096:
                raise ValueError('invalid entry name')
            if not isinstance(item.get('data'),(bytes,bytearray,memoryview)):
                raise ValueError('entry data must already be caller-read bytes')
            data=bytes(item['data'])
            if len(data)>1048576:
                raise ValueError('file exceeds public 1 MiB bound')
            label=item.get('source_version')
            if label is not None and (not isinstance(label,str) or len(label)>4096):
                raise ValueError('invalid source version label')
            snapshots.append(FileSnapshot(item['name'],data,label))
        if not 1<=len(snapshots)<=16 or sum(len(f.data) for f in snapshots)>4194304:
            raise ValueError('bundle exceeds public entry/4 MiB limits')
        return cls(target,request_id,text,tuple(snapshots),previous_manifest,attachment_fallback)

    def params(self,session):
        result={'session':session['session'],'target':self.target,'request_id':self.request_id,
                'text':self.text,'entries':[f.metadata() for f in self.files]}
        if self.previous_manifest is not None:result['previous_manifest']=self.previous_manifest
        if self.attachment_fallback is not None:result['attachment_fallback']=self.attachment_fallback
        return result


@dataclass(frozen=True)
class Prepared:
    result: dict
    upload: str | None


class Peer(Transport):
    def call(self,method,params=None,error=None):
        result=super().call(method,params,error=error)
        if method=='initialize' and error is None:
            self.upload_limits=result.get('limits',{}).copy()
        return result

    def require_uploads(self):
        limits=getattr(self,'upload_limits',{})
        expected={'fileUploadChunkBytes':196608,'fileUploadBudgetBytes':4194304,'fileUploadSlots':16}
        for field,value in expected.items():
            if type(limits.get(field)) is not int or limits[field]!=value:
                raise UploadUnavailable('v5 upload extension missing or incompatible: '+field)
        return limits

    def upload_open(self,session,plan):
        self.require_uploads()
        result=self.call('files.upload.open',plan.params(session))
        self._progress_or_frozen(result,plan)
        return result

    def _progress_or_frozen(self,result,plan):
        if not isinstance(result,dict) or result.get('request_id')!=plan.request_id:
            raise ValueError('upload response request binding mismatch')
        if result.get('state')=='frozen':
            if re.fullmatch(r'[0-9a-f]{32}',result.get('manifest_id','')) is None:
                raise ValueError('invalid frozen manifest ID')
            return
        if result.get('state')!='uploading' or re.fullmatch(r'[0-9a-f]{32}',result.get('upload','')) is None:
            raise ValueError('invalid upload progress')
        offsets=result.get('offsets')
        if not isinstance(offsets,list) or len(offsets)!=len(plan.files) or any(
            type(offset) is not int or not 0<=offset<=len(file.data) for offset,file in zip(offsets,plan.files)):
            raise ValueError('invalid resume offsets')
        if result.get('chunk_bytes')!=self.require_uploads()['fileUploadChunkBytes']:
            raise ValueError('unexpected upload chunk bound')

    def upload_write(self,session,upload,entry,offset,data):
        limits=self.require_uploads()
        if not isinstance(data,bytes) or len(data)>limits['fileUploadChunkBytes']:
            raise ValueError('bounded byte chunk required')
        return self.call('files.upload.write',{'session':session['session'],'upload':upload,
            'entry':entry,'offset':offset,'base64':base64.b64encode(data).decode('ascii')})

    def upload_commit(self,session,upload):
        self.require_uploads()
        return self.call('files.upload.commit',{'session':session['session'],'upload':upload})

    def upload_status(self,session,request_id):
        self.require_uploads()
        result=self.call('files.upload.status',{'session':session['session'],'request_id':request_id})
        if result.get('request_id')!=request_id or result.get('state') not in ('unknown','uploading','frozen'):
            raise ValueError('invalid upload status')
        return result

    def upload_abort(self,session,upload):
        self.require_uploads()
        result=self.call('files.upload.abort',{'session':session['session'],'upload':upload})
        if result.get('aborted') is not True or result.get('body_sent') is not False:
            raise ValueError('invalid upload abort result')
        return result

    def prepare_files(self,session,plan):
        """Resume/prepare only. A failed RPC is surfaced, not treated as rollback.

        The immutable plan can be passed again explicitly. No automatic reconnect,
        abandon, abort, send or ACK is inferred from an ambiguous failure.
        """
        opened=self.upload_open(session,plan)
        if opened['state']=='frozen':
            return Prepared(opened,None)
        token=opened['upload']
        chunk=self.require_uploads()['fileUploadChunkBytes']
        for entry,(file,start) in enumerate(zip(plan.files,opened['offsets'])):
            for offset in range(start,len(file.data),chunk):
                data=file.data[offset:offset+chunk]
                result=self.upload_write(session,token,entry,offset,data)
                if result.get('upload')!=token or result.get('entry')!=entry or result.get('offset')!=offset+len(data):
                    raise ValueError('upload write correlation/offset mismatch')
        result=self.upload_commit(session,token)
        self._progress_or_frozen(result,plan)
        if result.get('state')!='frozen' or result.get('body_sent') is not False:
            raise ValueError('commit did not report frozen preparation without body send')
        return Prepared(result,token)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable',required=True)
    parser.add_argument('--conversation',default='v5-cli-fixture')
    args=parser.parse_args()
    peer=Peer(server_command(args.server_executable))
    try:
        initialization=peer.initialize()
        session=peer.open(args.conversation)
        print(json.dumps({'initialize':initialization,'session':session}),flush=True)
        for line in __import__('sys').stdin:
            request=decode_json(line)
            if request['method']=='$notification':
                print(json.dumps({'notification':peer.notification()},ensure_ascii=False),flush=True)
                continue
            params=request.get('params',{})
            if params.get('session')=='$session':params['session']=session['session']
            try:result={'result':peer.call(request['method'],params)}
            except RpcError as error:result={'error':error.error}
            print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        peer.close()
