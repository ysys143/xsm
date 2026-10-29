# Ghidra 네이티브 후속 분석

> 후속 결과: 시간 제한 없이 재실행한 두 프로젝트의 자동 분석·전체 함수 목록 추출·저장을 완료했다. 아래 600초 기록은 초기 실패 이력이다. 전체 자동 분석의 종료와 함수 의미의 전수 검증은 다르다. [실행 메타데이터](full-native-analysis.json), [동작 대조](followup-findings.md).

- 일자: 2026-10-24
- 도구: Ghidra 12.2, JDK 25.0.5.0.2, macOS arm64
- 상태: 두 복사본의 기본 자동 분석 완료. 후속 실행은 시간 제한을 지정하지 않았고 실제 timeout 플래그가 false다. 초기 선택 함수 추출 근거도 보존한다.

## 설치와 복구

Homebrew로 Ghidra와 JDK 25를 설치했다. JDK 25를 포함한 18개 의존성이 설치·갱신됐다. 기본 셸의 Java는 기존 17.0.15를 유지하고 Ghidra 실행에만 JDK 25를 사용했다. [설치 기록](ghidra-install.json).

첫 병렬 기동 중 엔진 프로세스는 JDK 설정 디렉터리 생성에 실패했다. 이후 해당 디렉터리의 존재와 현재 사용자 소유임을 확인하고 엔진만 다시 실행했다. 실제 보안 권한이나 사용자 설정 규칙을 우회하지 않았다.

설치물의 Decompiler/os가 비어 있었고 공식 12.2 ZIP에도 macOS native가 없었다. 공식 아카이브 SHA를 확인한 뒤 이 사실을 대조했다. 설치에 포함된 동일 버전 C++ 소스를 사설 빌드 폴더에 복사하고 macOS ARM64용 decompiler와 Sleigh를 빌드해 누락 경로에 설치했다. 배포물에 없는 파일을 임의의 제3자 바이너리로 대체하지 않았다.

| 구성 | 실제 결과 |
|---|---|
| Homebrew 설치 | exit 0. 기능 확인에서 native decompiler 부재 발견 |
| 공식 ZIP | SHA256 일치. Linux/Windows native만 확인 |
| ARM64 decompiler 소스 빌드 | exit 0, 약 25.5초 |
| ARM64 Sleigh 소스 빌드 | exit 0, 약 6.5초 |
| Ghidra decompiler 사용 | CLI 선택 함수 8개 의사코드 추출 성공 |

설치 경로는 `/opt/homebrew/opt/ghidra`이며 사용자 실행 진입점은 `ghidraRun`이다. Headless는 `/opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless`다. 사용자 프로필에 별도 alias나 Java 기본값을 쓰지 않았다. 제거할 때 `brew uninstall ghidra`는 Ghidra를 제거하고 의존성은 별도로 남긴다. 향후 Ghidra 버전 갱신 시 직접 빌드한 native 구성의 존재와 동작을 다시 확인해야 한다.

## CLI: 네이티브 진입점과 포함된 JavaScript

원본 CLI SHA는 기존 분석과 일치한다. Ghidra는 `AARCH64:LE:64:AppleSilicon`으로 인식했다. 전체 자동 분석은 파일당 600초 제한에 도달했다. 처음 인식한 함수는 2,631개이며 전체 Bun 런타임 함수 목록이라고 볼 수 없다. 복구한 native backend로 저장된 프로젝트를 다시 열어 선택 함수를 디컴파일했다.

진입점은 `0x10000463c`다. 자동 분석이 함수로 만들지 못한 직접 호출 대상 6개는 진입점의 실제 call instruction을 대조한 뒤 분석 프로젝트에서 함수를 정의했다. `native_call_target_*`는 이 스크립트가 붙인 이름이며 원래 심볼이 아니다. 호출되지 않은 헤더 주소 `0x100000000`은 대조 조건으로 주었지만 복구하지 않았다.

| 네이티브 함수 | 진입점 call 위치 | 디컴파일 |
|---|---|---|
| 0x10000463c | 진입점 또는 확인된 callee | True |
| 0x1000046a4 | 0x100004658 | True |
| 0x100004a4c | 0x100004674 | True |
| 0x1000051f8 | 0x100004678 | True |
| 0x1000052a0 | 0x10000467c | True |
| 0x1000053dc | 0x100004698 | True |
| 0x101c36400 | 0x100004694 | True |
| 0x10026d204 | 진입점 또는 확인된 callee | True |

이 함수들은 인수·환경·시그널·pthread·종료 등 native 시작 경로다. Reason의 동기 질문·가입·serve 로직은 아래 JavaScript 자료 영역의 별도 코드 경로로 분석한다. native 의사코드가 원래 소스이거나 계정 서버의 구현을 복원한 결과라고 주장하지 않는다.

## CLI: 여섯 모듈의 메모리 매핑

| 모듈 | 파일 오프셋 | Ghidra 주소 | 메모리 블록 | 추출 SHA와 일치 |
|---|---:|---|---|---|
| network-command | 63214722 | 0x103dfd482 | __bun | True |
| ask-worker | 70020205 | 0x10447ac6d | __bun | True |
| network-core | 63204729 | 0x103dfad79 | __bun | True |
| entry-runtime | 63185191 | 0x103df6127 | __bun | True |
| cloud-relay | 69977926 | 0x104470746 | __bun | True |
| network-sign-in | 69990151 | 0x104473707 | __bun | True |

여섯 영역 모두 non-executable `__bun`에 있고 추출한 프로그램 텍스트와 바이트 SHA가 일치했다. 시작 주소에 native 함수가 없다는 사실은 해당 JavaScript 기능이 없거나 실행되지 않는다는 뜻이 아니다. 함수별 동작은 [배포물의 JS 호출 경로](cli-analysis.md)와 기존 실제 실행 기록으로 대조한다.

## 엔진

원본과 같은 SHA의 엔진 복사본을 복구한 native backend로 새 프로젝트에 분석했다. 자동 분석은 600초에 중단됐고 함수 9,982개가 인식된 상태였다. 선택한 12개 함수는 C 의사코드 추출을 완료했지만 타입 전파·겹치는 전역 심볼·미복구 분기 등의 경고가 있어 원래 소스와 동등하다고 보지 않는다.

바이너리의 LC_FUNCTION_STARTS를 ULEB128으로 읽으면 17,426개의 시작 주소가 있다. 이는 Ghidra 함수 수와 분모가 같은 지표가 아니므로 분석 완성률을 계산하지 않는다. 문자열 참조 명령은 있지만 함수가 없던 세 곳을 linker 경계로 복구했다. 주소와 명령 포함 여부를 검사했고, 프로젝트에서 붙인 `linker_function_*`는 원래 Rust 심볼이 아니다.

| 단서 | 복구한 함수 시작 | 참조 명령 | 확인 범위 |
|---|---|---|---|
| not a member of this team | 0x100248d0c | 0x100249204 | 의사코드의 호출이 거부 코드 0x193(403), 문자열 주소 0x100bb4436, 길이 0x19(25)를 함께 전달 |
| PostToolUse | 0x100225c70 | 0x100226c1c | tool 판정에서 PostToolUse 자료 주소를 고르는 경로 |
| PostToolUse | 0x1002cce94 | 0x1002ce078 | 이벤트명 자료를 구성하는 경로. 구체적인 설정 부작용은 source와 별도 대조 |

첫 경로는 [0.12.10의 PeerProto.accept](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/net.rs)가 멤버가 아닌 연결을 403으로 닫는 코드와 부합한다. 두 PostToolUse 경로는 [hook.rs](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/hook.rs)·[setup.rs](https://github.com/reason-machines/reason-network/blob/72ca2b3fb36d6e3cbfa44aa82c68d27aafe5e690/src/setup.rs)의 이벤트 번역·등록 경로와 대조한다. 이 비교로 원래 함수명을 복원했다고 주장하지 않는다.

CODEX_HOME 자료는 0x100c2b892에 있고 0x1002c7970 및 0x1002be04c 등에서 참조된다. 이 사실만으로 대상별 홈을 전달 명령에 설정했다고 볼 수 없다. 기존 실제 Codex 전달 실패의 단일 원인은 여전히 미확정이다. falling back to hooks와 outside this session 문자열도 찾았으나 선택 검색에서 직접 참조는 확보하지 못했다. --thread는 해당 비실행 블록의 정확 바이트 검색에서 찾지 못했다. 검색 부재를 기능 부재나 flag 미사용의 증거로 취급하지 않는다.

초기 자동 분석의 실제 종료 진단은 `Analysis timed out at 600 seconds. Processing not completed`였다. exporter의 성공·선택 함수의 decompile_completed와 당시 종료 상태를 함께 보존한다. 이후 아래 시간 제한 없는 분석으로 미완 자동 분석을 끝냈다.

## 시간 제한 없는 전체 자동 분석

저장된 두 프로젝트를 `-process`로 다시 열었다. `-analysisTimeoutPerFile`을 제거하고 기본 analyzer를 유지했다. Ghidra의 실제 `analysisTimeoutOccurred()`, 실행 종료 코드, Analysis/Post-analysis/Save succeeded 로그와 전체 함수 목록 행 수를 대조했다. [FullNativeInventory.java](FullNativeInventory.java)는 선택 개수 제한 없이 목록을 내보낸다.

| 대상 | 후속 실행 시간 | 함수 관리자 수 | 전체 목록 행 수 | 시간 초과 | 실행·사후 분석·저장 |
|---|---:|---:|---:|---|---|
| CLI 0.2.557 | 1,846.864초 | 67,229 | 66,226 | false | 모두 성공, exit 0 |
| 엔진 0.12.10 | 685.915초 | 17,997 | 17,727 | false | 모두 성공, exit 0 |

함수 관리자 수와 주소 순회 목록은 외부 함수 등의 포함 범위가 다르다. linker 시작 수와도 분모가 같지 않으므로 완성률을 만들지 않는다. 위 수는 기본 자동 분석이 만든 결과이며 모든 함수의 의미가 맞다는 보장이 아니다. 초기 선택 C 추출 20개를 전체 함수 검토 수로 표현하지 않는다.

전체 목록·요약·실행 로그의 SHA와 종료 결과는 [full-native-analysis.json](full-native-analysis.json)에 있다. 원시 프로젝트와 목록은 사설 조사 경로에 보존한다. 대상 두 바이너리의 SHA는 원본과 일치했다. Ghidra의 타입·외부 라이브러리·미복구 분기 경고는 여전히 해석의 한계다.

## xsm 반영

원래 R01–R43과 ADR-0015–0023의 채택 상태는 유지한다. 이번 결과는 R03·R31의 멤버십 거부, R33의 훅 번역·등록, R37의 배포물 출처, R38의 증거 강도에 추가 근거를 준다. Ghidra 설치 성공과 실제 decompiler 동작이 달랐던 사례는 설치·진단 경로를 실제 호출로 확인해야 한다는 검증 근거다. 연구 도구 자체를 xsm의 사용자 의존성으로 추가하지 않는다.

## 재현과 한계

[NativeEvidence.java](NativeEvidence.java)는 대상 SHA·메모리 구간·문자열 참조·선택 함수·디컴파일 결과를 수집한다. 데이터 포인터 한 단계를 거친 참조는 명시적으로 표시한다. 선택 함수 수와 문자열별 검색 수를 제한하며, 전체 함수·전체 동작을 검증했다고 해석하지 않는다. 원본 바이너리를 실행하거나 수정하지 않는다.

CLI 자동 분석에는 symbol table markup·이미지 패턴·외부 라이브러리 미로드 경고가 있었다. 외부 라이브러리가 Ghidra 프로젝트에 없다는 진단은 사용자 머신에 그 라이브러리가 없다는 뜻이 아니다. native 의사코드는 경고와 미복구 경로를 포함할 수 있어 source·실제 통신 증거와 함께 판단한다.

재현용 초기 입력은 [CLI](ghidra-cli-input.json)와 [엔진](ghidra-engine-input.json)에 있다. 대상 파일은 기존 SHA와 대조한 복사본을 사용한다. 다음은 저장된 프로젝트의 전체 자동 분석을 다시 실행하는 명령의 형태다. 경로는 실제 평가 폴더로 바꾼다. 초기 분석의 완료·시간 초과 여부는 실행기가 실제 결과를 기록하며, 과거 결과를 강제로 설정하지 않는다.

```sh
GHIDRA_HEADLESS_MAXMEM=6G /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless <project-dir> engine-native -process reason-network-0.12.10 -max-cpu 6 -scriptPath <this-document-directory> -postScript FullNativeInventory.java <output-dir>
```

CLI는 프로젝트 `cli`, 대상 `reason-cli-0.2.557`로 같은 방법을 실행했다. 새 프로젝트는 우선 해당 복사본을 import한다. 초기 선택 증거를 재현할 때만 NativeEvidence.java와 입력 JSON을 사용하며 그 출력은 전체 목록과 구분한다. linker 함수 시작 경계와 실제 문자열 참조 명령이 다르면 복구 결과를 그대로 성공으로 쓰지 말고 다시 확인한다. 자동 인식 함수 수·생성 함수 여부는 도구와 분석 상태에 따라 달라질 수 있다. [native 메타데이터](ghidra-native-evidence.json)와 [수집 검증](ghidra-validation.json)은 이번 실행의 결과다.

Ghidra 프로젝트·원시 로그·의사코드는 사설 평가 경로에 보존한다. 저장소에는 원본 바이너리나 CLI 의사코드 전체를 복제하지 않고 근거 메타데이터와 분석을 남긴다.

공식 근거: [Ghidra 12.2 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.2_build), [Ghidra headless API](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.2_build/Ghidra/Features/Base/src/main/java/ghidra/app/util/headless/HeadlessScript.java).
