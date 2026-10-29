#include <sys/proc_info.h>
#include <libproc.h>
#include <stddef.h>
#include <stdio.h>
int main(void) {
 printf("{\"PROC_PIDTBSDINFO\":%d,\"size\":%zu,\"pid_offset\":%zu,\"uid_offset\":%zu,\"start_sec_offset\":%zu,\"start_usec_offset\":%zu}\n",PROC_PIDTBSDINFO,sizeof(struct proc_bsdinfo),offsetof(struct proc_bsdinfo,pbi_pid),offsetof(struct proc_bsdinfo,pbi_uid),offsetof(struct proc_bsdinfo,pbi_start_tvsec),offsetof(struct proc_bsdinfo,pbi_start_tvusec));
 return 0;
}
