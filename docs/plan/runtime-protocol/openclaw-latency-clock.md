# OpenClaw Python 저장·Node queue 관측의 clock 경계

상태: 다음100표본을 위한 clock 조사다. 새 OpenClaw idle wake 지연 표본은 아직 없다.
서로 다른 프로세스의 nanoseconds를 clock 이름 확인 없이 빼지 않는다.

실제 고정 Node24.22.2의 libuv 버전은1.52.1이었다. Node의 hrtime BigInt는
[HrtimeBigIntImpl](https://github.com/nodejs/node/blob/v24.22.2/src/node_process_methods.cc)에서
uv_hrtime을 호출한다. [libuv core](https://github.com/libuv/libuv/blob/v1.52.1/src/unix/core.c)는
precise 경로를 사용한다.

| 관측 환경 | native Node clock 구현 | Python에서 대조할 clock |
|---|---|---|
| macOS |[libuv Darwin](https://github.com/libuv/libuv/blob/v1.52.1/src/unix/darwin.c)의 mach_continuous_time|CLOCK_MONOTONIC_RAW|
| Linux |[libuv Linux](https://github.com/libuv/libuv/blob/v1.52.1/src/unix/linux.c)의 precise CLOCK_MONOTONIC|CLOCK_MONOTONIC|

[Apple Libc](https://github.com/apple-oss-distributions/Libc/blob/main/gen/clock_gettime.c)의
RAW 매핑도 같은 Mach 함수를 사용한다. 이 Apple 링크는 고정 OS 소스 tag가 아니라
공개 main의 구현 대조이며, 실제 선택은 로컬 런타임 관측과 함께 확인한다.

현재 Mac에서 Python CLOCK_MONOTONIC과 Node hrtime은 약10.28초 차이가 관측됐다.
이를 native queue 지연으로 보고하면 잘못된 값이다. RAW before/after로 Node 읽기를
감쌌을 때는5회 모두 구간 안이었다. 원시는
`deliverables/protocol-foundation/openclaw-native-wake/clock-domain-mac.json`이다.
이5개는 clock 정렬 관측이며 queue 지연의100표본으로 세지 않는다.

다음 측정은 실제 canonical store 반환과 native queue commit readback에서 각각
같은 clock을 기록하고, idle·실제 turn/ACK·원문당 단일 admission을 확인해야 한다.
Linux 정렬 관측과 양OS100개가 없으면 이 조사만으로 p95 통과라 하지 않는다.
Hermes의 기존 두 Python 프로세스 측정은 양쪽 CLOCK_MONOTONIC을 썼으므로 이
Node clock 차이를 그 표본에 적용하거나 수치를 임의로 보정하지 않는다.
