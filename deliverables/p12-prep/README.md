# IC06 공통 경계 준비 산출물

이 코드는 선택될 adapter로 옮기기 위한 DTO/codec와 메모리 conformance recorder다. 실제 transport, 인증 구현, 서비스, 권한 적용은 없다. D12 제품 요구사항은 [ADR-0021](../../docs/adr/0021-cross-machine-network-and-membership.md)으로 확정됐다. 자체 P2P·선택적 Tailscale 경로·Reason식 멤버십을 후속 구현 대상으로 삼으며 전체 P12는 미완이고 구현 goal은 일시정지 상태다. 제품 `xsm/`는 수정하지 않았다.

## API 계약

- `Endpoint.identity()`는 machine/runtime/home_id/conversation/native_ref만 반환한다. home_id는 private canonical home 문자열의 SHA-256이며 경로나 읽기 권한이 아니다. generation은 frame에 남지만 semantic identity에는 들어가지 않는다.
- `from_local(identity, local_digest, sender, receiver, raw_body)`는 기존 `envelope.request_identity` 결과를 받는다. canonical home→opaque hash 결속을 검사하고 private home은 wire에 넣지 않는다. 원경로를 읽지 않는다.
- `Request.fingerprint`는 별도 `xsm.network-semantic/v1` domain의 요청 ID/양 endpoint/canonical body SHA/파일 refs/kind/reply_to/outcome/scope/priority 결속이다. generation, raw SHA, local digest, 표시 이름/branch/status/source assurance는 identity에 포함하지 않는다. 같은 ID의 다른 semantic 내용은 거절한다.
- `body_sha256`는 전체 원문 UTF-8 bytes의 전송무결성이다. `frame_sha256`는 generation을 포함한 frame의 hash다. NFC/줄끝 및 우선순위 정규화는 복제하지 않고 기존 envelope를 사용하는 semantic verifier가 검증한다. 따라서 NFC/CRLF 등가 입력은 raw SHA가 달라도 semantic identity가 같다.
- `encode`/`decode(..., max_bytes=...)`는 send/capabilities DTO를 처리한다. 중복 키, 추가 필드, malformed/truncated JSON, 비유한 수, raw body SHA 불일치를 거절한다. parser bound는 호출자가 명시하며 제품 quota를 새로 정하지 않는다.
- `Origin`은 packet codec 밖에서 adapter가 제공한다. 객체 생성 자체는 인증이 아니다. `origin_verifier`가 실제 transport 근거를 확인해야 한다. 본문이나 임의 approval/source/signature 태그는 인증 근거가 되지 않는다.
- `assess`의 membership/person/owner/repository/collaboration/backend/disclosure/local_digest/generation verifier는 정확히 True/False/그 외를 verified/rejected/unknown으로 표시한다. 예외도 unknown이다. repository verifier는 검증된 명시 mapping만 사용해야 한다. Git URL/폴더명/username으로 추론하지 않는다. unknown owner/repository는 그대로 unknown이며 disclosure 근거가 없으면 private다. publication은 collaboration 허가가 아니다.
- `Boundary.register_send`는 origin/semantic 검증 뒤 동일 ID 결속만 기록한다. 전송이나 허가를 실행하지 않는다. resume은 원 ID/원 요청을 보존하고 generation 변경을 승인 재확인 상태로 표시한다.
- `Boundary.observe`/`status`는 accepted/queued/delivered/actual_reply를 분리한다. actual reply는 별도 reply DTO, 원 reply_to, 역방향 exact semantic endpoint 쌍, origin/semantic/freshness 검증이 필요하다. freshness가 unknown이면 actual reply로 승격하지 않는다. 이 status는 로컬 conformance 결과이며 원격 status wire/authentication 프로토콜은 미구현이다.
- `Capability`/`capabilities`는 검증된 관측만 observed 등 상태로 표시한다. generation이 바뀌면 기존 관측을 상속하지 않는다. human approval/file-read permission은 항상 unknown이다.

Verifier가 전달받는 함수 인자는 구현의 `assess`, `capabilities`, `Boundary.observe` signature가 계약이다. 테스트의 `adapter-observed-*` 문자열 검사는 fixture일 뿐 실제 인증 방식이 아니다. recorder는 비영속 단일 프로세스 검사용이며 재시작 ledger나 backend 정책을 구현하지 않는다.

## 실제 로컬 함수와 연결한 입출력 예제

전용 테스트 `ContractTest.request()`는 fixture native handle 둘과 원문 `"cafe\u0301\r\n"`, ref `(manifest:11111111111111111111111111111111, 64자리 digest, 1, 100)`를 실제 기존 함수에 넘긴다.

```python
identity = envelope.request_identity("r1", private_sender, private_receiver,
                                     raw_body, attachments=refs)
request = from_local(identity, envelope.request_digest(identity),
                     opaque_sender, opaque_receiver, raw_body)
wire = encode(request)
decoded = decode(wire, max_bytes=len(wire))
```

실행 출력 표본:

```json
{
  "id": "r1",
  "sender_home_id": "303c0dee9736720f6d53624591d3cc180903fdd9f7b4cabd749197901862d550",
  "receiver_home_id": "98765f008ed203be9bd5fbfcc26ca28f3a79f7a547e68e73ba2a9f7c5c87737a",
  "raw_body_sha256": "c172288d238143d5a24d3368b1288ee2cea2bdbb279af7b8ff4ef7953c40921b",
  "canonical_body_sha256": "850f7dc43910ff890f8879c0ed26fe697c93a067ad93a7d50f466a7028a9bf4e",
  "local_digest": "18b89ba6b2b5854dd033818bce524cf03c61e79ffa21f1d9be982fe8b0dd3c19",
  "network_semantic_digest": "27440959097b4278223aa6b7a86ac570caaba990a51663130857cea1e0566a6f",
  "transport_attempted": false
}
```

local digest는 기존 계약 그대로 opaque audit 값으로 보존하며 private mapping이 있는 verifier만 재검증한다. network digest와의 동일성을 주장하지 않는다. 예제의 wire에 실제 home 경로가 없다는 검사가 포함된다.

## 실행 결과

2026-10-29 실행:

```text
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s deliverables/p12-prep -p 'test_network_contract.py' -q
Python 3.9.6: Ran 22 tests — OK

PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.14 -m unittest discover -s deliverables/p12-prep -p 'test_network_contract.py' -q
Python 3.14.6: Ran 22 tests — OK
```

실행된 negative conformance에는 authenticated machine과 본문 origin 충돌 거절, 추가 origin/approval 필드 decode 거절, 본문 signature/승인/path 태그의 권한 승격 금지 및 파일 open 0회, 동일 ID의 endpoint/body/ref 교체 거절, unknown owner/repo 비공개, backend delivery를 actual reply로 오인하지 않는 검사가 있다. 실제 머신 간 성공으로 세지 않는다.

원본 파일을 바꾸지 않는 메모리 변이도 실행했다. generation을 semantic identity에 넣은 변이는 resume 검사에서 error 1개로 검출됐다. origin machine 대조를 제거한 변이는 위조 origin 검사에서 failure 1개로 검출됐다. 두 변이 모두 검출됐으며 제품 파일/서비스/설정/권한 변경과 외부 송신은 없었다.
