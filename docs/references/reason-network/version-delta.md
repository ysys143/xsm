# 0.12.10과 0.12.11의 차이

이전 실제 통신 표본은 0.12.10이다. 최신 공개 커밋과 파일 단위 diff를 별도로 읽었다.

| 변경 | 0.12.11에서 확인한 것 | 반영 |
|---|---|---|
| 네트워크 포트 | 선택적 고정 UDP 포트, IPv4/IPv6 바인딩, 점유 시 랜덤 포트 대체 | R42, ADR-0021·0023 |
| 진단 | 실제 UDP 상태와 대체 결과의 자료형·표시 | R35·R42 |
| 폴더 제외 | 문자열·실제 경로, 상위/내부 링크, 아직 없는 경로를 대조 | R23·R43 |
| 설정 생성 | 포트 설정을 top-level에 적는 설명·템플릿 | R33·R42 |
| 릴리스 | Cargo 버전·lock 및 README 갱신 | R37 |

변경 파일은 Cargo.lock, Cargo.toml, README.md, src/config.rs, src/daemon/teamops.rs, src/main.rs, src/net.rs, src/proto.rs, src/render.rs, src/setup.rs의 10개다. 해당 차이에 포함되지 않은 전달·MCP·ask-worker 동작을 새 버전에서 수정됐다고 추정하지 않는다.

[baseline manifest](source-manifest.json), [검사 결과](test-results.json).
