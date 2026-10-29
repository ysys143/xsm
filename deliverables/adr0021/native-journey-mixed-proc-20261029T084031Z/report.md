# libproc 관측 조건의 Claude와 Codex 혼합 실제 업무 완료

Book의 실제 Claude와 mini의 실제 Codex가 공개 후보 발견·사용자 선택·상관 준비 회신·원자료 검토·수정자료 후속 검토를 완료했다. 원자료와 수정자료는 실제 caller가 파일을 읽고 MCP 첨부로 보냈으며, Claude가 xsm_files로 직접 읽어 파일에만 있던 식별 문구를 붙여 직접 회신했다. 요청 3건과 회신 3건 모두 실제 ACK 상태다.

업무·자료·P2P 왕복은 완료됐다. 단, 장시간 baseline 대비 Book 전역 `.claude.json`의 hash가 달라져 전체 profile 데이터 쓰기 0 조건까지 검증 완료로 처리하지 않는다. 권한 설정 파일과 인증 파일 metadata는 일치했고, 이 한 파일의 변경 주체는 확인하지 못했다. 원본을 되돌리거나 보정하지 않았다.

## 실제 대화와 source

| 항목 | Book reviewer | mini requester |
|---|---|---|
| 실제 runtime | Claude Code 2.1.312 | codex-cli 0.164.0 |
| 실제 모델 | `claude-sonnet-5-5` | `gpt-6.1-sol` |
| 완료 표본의 실제 CID | `d9736a11-0c50-4196-995d-0f87a4634f07` | `01a187cf-5153-7e53-810d-405946f9e666` |
| 인증 | 기존 `.claude-3` claude.ai 구독 | 기존 `.codex-3/auth.json`의 private 참조 |
| 권한 | 기존 auto | 기존 workspace-write / never |

모델명은 native init와 provider turn_context에서 읽었다. 임의 모델명·새 allowedTools·위험 flags는 지정하지 않았다. 실제 auth/API key 값은 controller가 읽거나 복사하지 않았다. 기존 전역 proxy나 DNS 설정도 바꾸지 않았다.

실행 source manifest SHA-256은 `f4172fc9f4c49433eb90fe44a54dad5631ede60249b60a5905e3524d794c62a4`다. Python 52개와 hooks/bin/skills 13개, 총 65개이며 두 호스트 payload가 모두 일치했다. 제품 52개 파일은 수정하지 않았다. file 단계의 files/materials/network_messages/network/mcp/instructions SHA는 results-final.json에 기록했다. 실행 중 main이 마무리한 중복 TTL·quota·오프라인 내보내기 변경을 이 복사본에 섞거나 재적재하지 않았다. 이번 자료 증거는 첫 전송과 실제 사본 읽기·후속 회신이며 해당 추가 반례 검사를 대신하지 않는다.

Rust는 지정한 release `xsm-net` 복사본이다. 현재 Rust loopback relay 정책 수정 전 빌드이며 relay off, 실제 direct 경로를 사용했다. 다른 NAT와 주소 변경 결과는 main의 별도 결과다.

## read-only libproc ps 조건

기존 no-ssh-v2-proc.py와 현재 SDK C 구조체를 대조했다. BSD 구조체 size 136, PID/UID/start 필드 offset을 확인했고 같은 자기 PID에서 실제 unrestricted ps와 UID·부모·시작 시각·실제 경로를 대조했다. 같은 OS guard의 shim에서도 값이 일치했다.

shim은 libproc의 실제 커널 값만 읽는다. 자기 PID/조상과 UID·세대·실제 경로가 일치하는 허용 fixture만 렌더링한다. 전역 프로세스나 argv/environment는 출력하지 않는다. PID 1 및 args 요청의 거부도 실제 확인했다. 없는 값이나 가짜 PID·시각·조상을 만들어 내지 않는다. shim PATH는 MCP와 자기 hook Python 환경에만 적용했다.

Claude의 원래 실행명은 `.local/bin/claude` 심볼릭 링크지만 커널 물리 경로 basename은 버전 파일이었다. 이를 임의 alias로 위장하지 않았다. 동일 SHA의 실제 바이너리를 private `runtime/claude`로 복사했고, 모델 프롬프트 없는 bootstrap에서 그 실제 커널 경로·ps·guard shim이 정확히 일치함을 확인했다. 같은 guard의 실제 MCP가 그 native PID와 시작 시각을 확인했다.

전역 presence 파일을 쓰지 않는 조건에서 초기 pointer의 socket 정보가 빠졌다. 실제 살아 있는 native PID의 Unix socket FD와 UID·inode를 OS에서 확인하고, 실제 init CID·MCP 부모와 묶어 최초등록에 사용했다. socket은 native가 만든 `/tmp/cc-socks/<PID>.sock`이며 controller가 만들거나 응답을 흉내 내지 않았다. 메타데이터 증거는 copied-cli-mcp-preflight.json과 streaming-claude-registration.json에 있다.

## 공개 후보·실제 hook consent

각 호스트는 별도 Git work 저장소다. 사전 repository map은 0개다. reviewer Goal은 자기 세션 공개와 자료 검토를 자연 업무 지시로 요청했다. requester Goal은 공개 a1과 협업하겠다는 사용자 선택을 명시했다. requester 자기 공개 호출은 0회다.

reviewer는 실제 native UserPromptSubmit hook 원문이 도구에서 표시된 뒤 다음 정상 호출로 공개를 적용했다. requester도 실제 native 최신 사용자 원문을 보고 정상 connect 재호출로 선택을 적용했다. 저장된 collaboration verdict와 실제 hook prompt가 정확히 일치했다. controller는 consent.record나 답변 파일을 작성하지 않았다.

Codex의 hook은 사용자가 기존 `.codex-3`에서 이미 승인한 XSM source/hash 두 개를 동일 값으로 private 환경에 재사용했다. 새 trusted hash를 만들거나 기존 전역 승인/권한을 고치지 않았다. 실제 hook 파일도 원래 승인된 cache와 동일했다. 실제 UserPromptSubmit이 requester 원문을 기록했고, native-hook-and-argv-provenance.json에 source/hash와 최종 argv 검사를 남겼다.

| 원질문 | 종류 | 실제 회신 | 소비 확인 |
|---|---|---|---|
| `960d055aca004b34` | handshake | `9017dc72105a4f61` | 양쪽 acknowledged |
| `664b736162384904` | question | `f666be91a9e34cfe` | 양쪽 acknowledged |
| `de6caa36ed204273` | question | `ee010a0cf6f246ad` | 양쪽 acknowledged |

실제 xsm_discover 성공이 connect/ask보다 앞섰다. 같은 Codex CID의 최종 argv에는 disable code_mode_host나 위험 flag가 없다. 준비 회신은 상관 reply_to와 outcome=succeeded로 확인했다. 단순 queue·scope 허용·도구 반환을 준비 완료로 처리하지 않았다.

## 실제 자료 읽기와 후속 검토

| caller 첨부 파일 | UTF-8 bytes | 실제 파일 SHA-256 |
|---|---|---|
| review-material.md | 296 | `0b253f4be06fb900017b9becdc3cf98afe3a4f7b4ebd8bb33d78b06200667f75` |
| review-material-revised.md | 638 | `463479d4a25ef9a708d71a09832bb96ab1199ffc469b840fd3f29fe40b3f31a2` |

caller의 실제 native 파일 읽기 command 출력과 첨부 text가 각각 파일 bytes와 일치했다. Claude의 xsm_files entry 읽기 결과도 원자료·수정자료 내용과 일치했고, 파일에만 있던 `MIXDOC-643bdef6b9044a78`를 직접 회신했다. 이 식별 값은 업무 Goal에 넣지 않았다.

원자료는 2+2=5 주장과 잘못된 근거였다. Claude는 사본을 직접 읽고 단위 수·후계자 함수 근거로 오류를 지적했다. Codex가 그 근거를 반영한 수정 파일을 스스로 만들고 읽은 뒤 두 번째 MCP 첨부로 보냈다. Claude는 수정 사본을 직접 읽어 수용 가능하고 남은 오류가 없다는 최종 회신을 보냈다. 두 file bundle은 서로 다른 새 요청이며 같은 ID의 본문을 바꾸거나 TTL을 늘리지 않았다.

question-status의 cached claim 진단은 raw 그대로 보존했다. 모델은 실제 inbox 원본을 읽고 ACK해서 회신을 확인했다. controller가 claim·ACK·index·본문을 수동 보정하지 않았다.

## SSH 불가 범위와 실제 P2P carrier

actor 조건에 TCP 22/8022 outbound deny를 추가했다. 두 방향의 실제 socket connect는 같은 규칙에서 errno 1이었다. operator는 guard 밖에서 기존 SSH로 bootstrap·관측했고, 밖의 실제 TCP 22는 연결 가능했다. 전역 방화벽이나 SSH 규칙은 바꾸지 않았다.

범위를 정확히 구분한다. Book은 native SDK 부모와 상속된 MCP/hook 전체에 해당 guard를 적용했다. mini는 새 외부 guard가 Codex 자체 workspace sandbox_apply와 충돌한 실패를 보존한 뒤, 기존 workspace-write를 유지하고 추가 guard를 MCP·자기 hook 경계에 분리했다. mini의 shell은 원래 workspace-write 네트워크 제한을 유지했다. 따라서 검증 범위는 이 데이터 전달 tool 경계이며 mini native 부모 전체를 일괄 차단했다고 주장하지 않는다.

업무 3건과 직접 회신 3건의 Sidecar 발신 본문 SHA가 상대 실제 native 수신 이벤트 SHA와 일치했다. 수신 TLS origin은 발신 기기 신원과 모두 일치했다. 업무 본문/자료 사본은 P2P를 통과했다. SSH는 소스·caller 자료 fixture provisioning, private 초대, 기동·관측에만 사용했고 받은 peer 본문을 다른 모델에게 전달하지 않았다.

## live SDK·기존 CID·실패 보존

이전 no-session-persistence Claude CID는 종료가 확인된 기록으로 보존했다. 그 pending이나 RequestId를 새 Claude로 돌려보내지 않았다. 최종 세 요청은 모두 살아 있는 새 SDK CID `d9736a11-0c50-4196-995d-0f87a4634f07`을 대상으로 처음 만들어졌다. controller는 SDK stdin을 열어 둔 채 최초 사용자 Goal 한 번만 보냈고 peer 본문을 stdin으로 중계하지 않았다.

Codex는 같은 실제 CID를 유지했다. 추가 외부 guard 충돌과 helper에 남아 있던 host-disable argv 실패는 별도 원본으로 보존했다. 종료가 확인된 미완 단계만 정상 workspace-write 및 host-enabled argv로 이어갔고, 실제 discovery 노출 후 업무를 진행했다. 이전 종료된 Claude나 같은 잘못된 모델 조건을 성공으로 다시 분류하지 않았다.

옛 실패 질문 `ed42ef075aff4b47`은 원래 receiver CID에서 여전히 pending이다. 새 CID로 redirect하거나 질문/회신을 복제하지 않았다.

## profile 데이터 제한과 종료

권한 설정과 인증 파일 metadata, mini의 보존 baseline은 일치했다. 다만 Book `.claude-3/.claude.json` hash는 09:30 UTC의 오래된 baseline과 달랐고 파일 수정 시각은 13:38 UTC였다. 변경 주체를 확인할 수 없었으며 원본 내용·권한을 되돌리지 않았다. 따라서 모든 전역 profile 데이터가 불변이었다는 최종 판정은 유보한다. 쓰기 policy 조회 API의 오류 반환도 성공 증거로 쓰지 않았다.

업무·자료·P2P 검증 뒤 모든 확인된 소유 actor/MCP/SDK controller와 두 service/engine을 종료했다. 소유 PID 잔여는 0개이고 state/key·이전 실패·이번 원문 증거는 보존했다. 새 allowedTools·전역 rules·전역 proxy 설정 변경, API/auth 값 읽기·복사, controller의 본문/ACK/consent 보정은 하지 않았다.

주요 근거:

- [최종 결과](results-final.json), [분석 코드](analyze-final.py), [원 source manifest](source-manifest.json)
- [SDK/ps preflight](proc-preflight.json), [실제 Claude MCP caller preflight](copied-cli-mcp-preflight.json), [scope 거부 검사](shim-scope-negative-checks.json)
- [caller·hook·argv 출처](native-hook-and-argv-provenance.json), [기존 pending 보존](older-pending-preserved.json)
- [Book 실제 증거](book-final-evidence/mixed-evidence.json), [mini 실제 증거](mini-final-evidence/mixed-evidence.json)
- [Book 종료](book-cleanup-final.json), [mini 종료](mini-cleanup-final.json), [실행 source와 현재 source 차이](executed-source-vs-current.json)

이번 결과는 혼합 실제 업무와 기본 자료 통합을 입증한다. 중복 TTL/quota·오프라인 내보내기와 모든 profile 데이터 불변성은 별도 조건으로 남긴다. 설명·상태·보고 본문은 지정 CJK 정규식으로 검사했다. raw는 변경하지 않았다.

## A21-04 동명 조건의 실제 범위

이 표본의 실제 self 이름은 `requester`, 선택한 remote 이름은 `a1`이었다. 따라서 self와 remote를 모두 a1로 둔 counter는 미실행이다. 완료 뒤 표시 라벨을 바꾸거나 새 모델을 시작하지 않았다.

실제 discover에는 remote a1 표시가 여러 건 있었고 종료된 앞선 표본 CID도 들어 있었다. 이를 동시에 활동하는 제3자 다중 동명 선택의 증거로 확대하지 않는다.

모델의 실제 선택 인자는 `candidate:db008923597773737db22bdfdea544d3d9bde5dd89ce994c79afcbaa242a3ee4`였다. 그 후보의 실제 전체 주소는 다음과 같다.

```text
net:e4824763e4b2ea2e28e3107f0c8e44d4e9e690eaa387c2f1b7c1de0b3d4ae01d:claude:1f3efe9ffb9cf15ba352aa22f67362777ae05495d0bb84b9b5b8268090817da7:d9736a11-0c50-4196-995d-0f87a4634f07
```

후보 generation은 `8f09a980166c4cda142ef876e9ce14c033dd82a5f6b25c58ad1705fc6d4f51a2`이다. 세 원요청의 전송 packet receiver 전체 handle이 이 실제 discover handle과 같고, 수신 원본의 실제 CID도 모두 `d9736a11-0c50-4196-995d-0f87a4634f07`였다. 원문은 sender packet·receiver handoff·질문 기록에서 일치했으며 오배송은 0건이다. 상세 native discover 원본과 선택 인자·도착 대조는 [A21-04 근거](a21-04-discovery-evidence.json)에 보존했다.
