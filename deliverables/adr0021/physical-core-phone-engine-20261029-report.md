# Android 실제 xsm-net 실행 파일과 기초 기동 결과

실제 제품 `xsm-net`을 `aarch64-linux-android`로 빌드하고 폰에서 두 번 실행했다. `relay=off`에서 IPv4·IPv6 bind, 주소 조회, 기기키 서명 검증, 변조 입력 거절, 재시작 후 공개키 유지가 통과했다. SDK 샘플이나 대체 네트워크 프로그램으로 성공을 대신하지 않았다.

15분 내 첫 실행 목표는 달성하지 못했다. Mac 정적 musl 교차 빌드는 완료했지만 폰의 Termux 로더가 ET_EXEC를 거절했고 직접 실행도 권한 오류로 막혔다. 같은 실패 조건의 반복 대신, 이미 설치된 폰 clang·NDK sysroot와 private tmp에 풀어 쓴 공식 Termux Rust로 실제 제품을 빌드했다.

## 바로 사용할 경로

```text
XSM_NET_BINARY=/data/data/com.termux/files/usr/tmp/xsm-net-product-co8sb0zw/target/aarch64-linux-android/release/xsm-net
SHA256=19c259be759a63cc149db1e846db48a3e35be5712d62c9572085250d0e31247a
LD_LIBRARY_PATH=/data/data/com.termux/files/usr/tmp/xsm-net-product-co8sb0zw/runtime-lib:/data/data/com.termux/files/usr/lib
SSL_CERT_FILE=/data/data/com.termux/files/usr/etc/tls/cert.pem
LD_PRELOAD=/data/data/com.termux/files/usr/lib/libtermux-exec.so
```

실행 파일은 13,041,688바이트다. ELF type 3인 Android PIE, AArch64이며 interpreter는 `/system/bin/linker64`다. 동적 의존성은 `libdl.so`, `libm.so`, `libc.so`로 확인됐다. 실제 시험에서는 위 LD·CA 환경을 프로세스에만 지정했다. main의 HOME·TMPDIR·XSM_HOME은 main의 별도 private root를 유지한다. Rust compiler의 private 라이브러리 디렉터리를 제품 실행 환경에 넣지 않았다.

main이 준비한 `/data/data/com.termux/files/usr/tmp/xsm-adr21-k4pe34iu/payload`나 그 root의 key/state는 수정하지 않았다. 이 검사의 기기키는 별도의 `xsm-net-product-co8sb0zw/native-smoke-state`에 생성됐고 값은 열거나 복사하거나 출력하지 않았다.

## 실제 실행에서 확인한 것

| 항목 | 결과 |
|---|---|
| 실제 실행 PID | 17352, 17373 |
| 각 실행 `ready` | 모두 출력 |
| UDP bind | IPv4 `0.0.0.0`, IPv6 `[::]`, port 0 실제 할당 |
| sign/verify | 두 실행 모두 실제 native 서명과 검증 성공 |
| 변조 입력 | 두 실행 모두 거절 |
| 주소의 기기 신원 | ready의 공개키와 일치 |
| 재시작 후 키 | 같은 공개키 유지 |
| 종료 | 두 PID 모두 shutdown 후 exit 0, reap 완료 |
| stderr | 두 실행 모두 0바이트 |
| key 파일·root 권한 | 0600 / 0700 |

이 검사는 외부 피어 RPC를 수행하지 않았다. 다른 NAT 환경은 main이 별도 확인한 상태이며, 그 환경의 실제 제품 왕복 성공으로 이 기동 결과를 확대하지 않는다.

## DNS·CA·JNI의 검증 경계

- native bind와 기기키 서명은 실제 실행으로 통과했다.
- 이번 두 실행은 `--relay off`였다. DNS 동작과 외부 HTTPS relay 인증서 검증은 아직 검사하지 않았다.
- 표준 Termux CA bundle `/data/data/com.termux/files/usr/etc/tls/cert.pem`의 읽기 가능 여부를 확인하고 child process의 `SSL_CERT_FILE`로 지정했다. 환경 변수를 지정했다는 사실만으로 특정 TLS backend가 그 파일을 사용했다고 판정하지 않는다.
- Android target의 JNI 관련 가설은 이 bind·서명 경로에서는 재현되지 않았다. 실제 DNS·HTTPS relay 경로에서의 판정은 main runner의 결과와 구분해야 한다.
- TLS·인증서 검증을 끄는 옵션, 자체 인증서 신뢰 추가, Rust TLS 코드 수정은 하지 않았다.

## 빌드 경로와 공식 해시

Mac 교차 빌드에서는 공식 Zig 0.15.2, 공식 Rust 1.95.0 compiler·host std·musl std를 private tmp에 준비하고 공개된 archive SHA-256을 검증했다. Homebrew rustc와 공식 std 사이의 메타데이터 불일치를 확인한 뒤 compiler도 같은 공식 배포본으로 맞췄다. cc-rs의 target 표기 차이와 CRT 중복은 private linker wrapper에서만 해결했다. 제품 Rust 소스는 고치지 않았다.

그 결과 생성한 정적 ELF의 SHA는 `90c3f31c6be974eddfd03156b002c5b8e5d881e975e5ac63175877bc06e1b051`이다. 폰에 전달한 바이트 SHA까지 일치했지만, Termux의 시스템 로더는 `unexpected e_type: 2`, 직접 실행은 `Permission denied`로 거절했다. 이 파일은 사용 가능한 엔진으로 보고하지 않는다. [공식 Termux 실행 환경 문서](https://github.com/termux/termux-packages/wiki/Termux-execution-environment)가 설명하는 시스템 로더 경로와 구분해 원오류를 보존했다.

최종 경로는 전역 설치 없는 Termux Rust 패키지 추출이다. main이 Python 의존성으로 이미 설치한 clang 21.1.8, LLVM, NDK sysroot 29-2를 그대로 사용했다.

| private 패키지 | 바이트 | 공식 패키지 SHA-256 |
|---|---:|---|
| rust 1.96.0 | 121,216,068 | `a3a9055f4a991487f18ea37a69cb2e883cb1b3026d076556f4f923575e5ad672` |
| rust-std-aarch64-linux-android 1.96.0 | 4,913,892 | `47b92b85c692337c055455e49e4cd81ff10f32bc909d4b084ab359ed43d6df0d` |
| libandroid-execinfo 0.1-3 | 14,980 | `ff761f3975e5d0fc12b41274804a97ccfe23beac3e7e50c0d306ad84660a4668` |

세 archive는 현재 공식 Termux 패키지 metadata의 SHA와 실제 다운로드 SHA가 모두 일치했다. `dpkg-deb -x`로 새 private root 아래에만 풀었고, 전역 패키지 DB에는 설치하지 않았다. 이후 `dpkg-query rust`는 미설치 상태였다.

실제 compiler는 `rustc 1.96.0 (ac68faa20 2026-05-25)`, Cargo는 `1.96.0 (30a34c682 2026-05-25)`, host/target은 `aarch64-linux-android`다. release profile의 opt-level 1, strip symbols, jobs 4로 실제 제품을 빌드했으며 260.388초가 걸렸다. 기본 opt-level 3 성능 결과와 섞지 않는다.

Rust source와 Cargo.lock의 파일별 SHA는 Mac 동결본 및 실행 종료 시의 repository source와 일치했다. `iroh 1.4.1`, 현재 `float_roundtrip`, 기존 제품 TLS·서명 검증을 유지했다. stdlib·CRT·실행 로더 장애를 제품 소스 수정으로 덮지 않았다.

## 증거

- [요약 결과와 source/package SHA](physical-core-phone-engine-20261029-results.json)
- Mac private raw: `/private/tmp/xsm-phone-cross-52bfe12o/raw/`
- 폰 private raw: `/data/data/com.termux/files/usr/tmp/xsm-net-product-co8sb0zw/raw/`
- 폰 compiler·source·target·실행 파일은 같은 새 private root 아래에 있다.

사용자 프로필, 기존 인증·SSH·코드·네트워크 설정을 바꾸지 않았다. private Rust 준비 과정에서 전역 `pkg install`이나 `apt install`을 수행하지 않았고, 사용자 세션에 신호를 보내지 않았다. 실제 phone→Mac 제품 왕복과 HTTPS relay 경로의 최종 평가는 main이 별도로 진행할 범위다.
