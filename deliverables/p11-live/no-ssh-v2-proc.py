"""SDK-layout libproc reader restricted to our PID and registered Popen children."""
import ctypes,errno,os,subprocess,time
ALLOWED={os.getpid()};SPAWNS=[]
class BSD(ctypes.Structure):
 _fields_=[(n,ctypes.c_uint32) for n in ('flags','status','xstatus','pid','ppid','uid','gid','ruid','rgid','svuid','svgid','rfu')]+[('comm',ctypes.c_char*16),('name',ctypes.c_char*32)]+[(n,ctypes.c_uint32) for n in ('nfiles','pgid','pjobc','tdev','tpgid')]+[('nice',ctypes.c_int32),('start_sec',ctypes.c_uint64),('start_usec',ctypes.c_uint64)]
EXPECTED={'size':136,'pid':12,'uid':20,'start_sec':120,'start_usec':128}
assert ctypes.sizeof(BSD)==EXPECTED['size']
for n in ('pid','uid','start_sec','start_usec'):assert getattr(BSD,n).offset==EXPECTED[n]
LIB=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True);LIB.proc_pidinfo.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int];LIB.proc_pidinfo.restype=ctypes.c_int
REAL_POPEN=subprocess.Popen
def popen(argv,*a,**kw):
 p=REAL_POPEN(argv,*a,**kw);ALLOWED.add(p.pid);SPAWNS.append({'pid':p.pid,'parent':os.getpid(),'at':time.time(),'exe':os.path.basename(str(argv[0]))});return p
subprocess.Popen=popen
def info(pid):
 if pid not in ALLOWED:raise ValueError('outside own/owned-child PID metadata scope')
 b=BSD();ctypes.set_errno(0);n=LIB.proc_pidinfo(pid,3,0,ctypes.byref(b),ctypes.sizeof(b));error=ctypes.get_errno()
 if n==0 and error in (0,errno.ESRCH):return None
 if n!=136:raise OSError(error,'proc_pidinfo invalid return length '+str(n))
 if b.pid!=pid or b.uid!=os.getuid() or b.ruid!=os.getuid():raise ValueError('PID/UID ownership mismatch')
 return {'pid':b.pid,'ppid':b.ppid,'uid':b.uid,'ruid':b.ruid,'status':b.status,'pgid':b.pgid,'start_sec':b.start_sec,'start_usec':b.start_usec,'generation':'unix:%d.%06d'%(b.start_sec,b.start_usec),'bytes':n,'errno':error}
def start(pid):
 d=info(pid);return d['generation'] if d else None
def baseline():
 before=info(os.getpid());ps=subprocess.run(['/bin/ps','-o','lstart=','-p',str(os.getpid())],capture_output=True,text=True,timeout=5)
 text=ps.stdout.strip();expected=time.strftime('%a %b %e %H:%M:%S %Y',time.localtime(before['start_sec']))
 if ps.returncode or text!=expected:raise RuntimeError('own PID libproc versus unrestricted ps mismatch')
 return {'own':before,'unrestricted_ps_exit':ps.returncode,'unrestricted_ps_lstart':text,'match_to_second':True,'baseline_before_restriction':True,'SDK_layout':EXPECTED}
