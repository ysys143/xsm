
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static int audit_fd=-1;
static int resolver_self=-1;
static _Thread_local int call_depth=0;
static int intercepted_socket(int,int,int);
static void event(const char *name,int family,int type,int protocol,int result,int error){
 int saved=errno;char line[320];
 int n=snprintf(line,sizeof(line),"{\"event\":\"%s\",\"pid\":%d,\"family\":%d,\"type\":%d,\"protocol\":%d,\"result\":%d,\"errno\":%d,\"rtld_next_is_replacement\":%d}\n",name,(int)getpid(),family,type,protocol,result,error,resolver_self);
 if(audit_fd>=0 && n>0 && n<(int)sizeof(line))(void)write(audit_fd,line,(size_t)n);
 errno=saved;
}
__attribute__((constructor)) static void loaded(void){
 const char *path=getenv("CARRIER_IPV6_TRACE");if(path)audit_fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW,0600);
 void *candidate=dlsym(RTLD_NEXT,"socket");resolver_self=candidate==(void*)&intercepted_socket;
 event("interpose-loaded",0,0,0,0,0);
}
static int intercepted_socket(int family,int type,int protocol){
 if(++call_depth>1){event("direct-call-reentry",family,type,protocol,-1,ELOOP);--call_depth;errno=ELOOP;return -1;}
 event("socket-enter",family,type,protocol,0,0);
 if(family==AF_INET6){event("ipv6-socket-denied",family,type,protocol,-1,EAFNOSUPPORT);--call_depth;errno=EAFNOSUPPORT;return -1;}
 int result=socket(family,type,protocol);int error=result<0?errno:0;
 event("socket-passed",family,type,protocol,result,error);--call_depth;if(result<0)errno=error;return result;
}
__attribute__((used)) static const struct{const void *replacement;const void *replacee;} entries
__attribute__((section("__DATA,__interpose")))={(const void*)&intercepted_socket,(const void*)&socket};
