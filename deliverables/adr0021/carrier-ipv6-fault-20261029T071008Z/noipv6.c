#include <sys/socket.h>
#include <sys/types.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static int audit_fd = -1;
static int (*actual_socket)(int,int,int) = NULL;
static void emit(const char *event,int family,int type,int error) {
    int saved=errno;
    if(audit_fd>=0) {
        char line[256];
        int length=snprintf(line,sizeof(line),"{\"event\":\"%s\",\"pid\":%d,\"family\":%d,\"type\":%d,\"errno\":%d}\n",event,(int)getpid(),family,type,error);
        if(length>0 && length<(int)sizeof(line)) (void)write(audit_fd,line,(size_t)length);
    }
    errno=saved;
}
__attribute__((constructor)) static void loaded(void) {
    const char *path=getenv("CARRIER_IPV6_TRACE");
    if(path) audit_fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW,0600);
    actual_socket=(int(*)(int,int,int))dlsym(RTLD_NEXT,"socket");
    emit("interpose-loaded",0,0,0);
}
static int blocked_socket(int family,int type,int protocol) {
    if(family==AF_INET6) {
        emit("ipv6-socket-denied",family,type,EAFNOSUPPORT);
        errno=EAFNOSUPPORT;
        return -1;
    }
    if(!actual_socket) actual_socket=(int(*)(int,int,int))dlsym(RTLD_NEXT,"socket");
    if(!actual_socket) {errno=ENOSYS;return -1;}
    int result=actual_socket(family,type,protocol);
    int error=errno;
    emit("socket-passed",family,type,result<0?error:0);
    errno=error;
    return result;
}
__attribute__((used)) static const struct {const void *replacement;const void *replacee;} interposition
    __attribute__((section("__DATA,__interpose"))) = {(const void *)&blocked_socket,(const void *)&socket};
