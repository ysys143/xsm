# A21-07 IPv6 소켓 고장 주입 첫 결과

첫 실행은 통과하지 못했다. 작은 C 라이브러리는 컴파일됐고, 두 소유 엔진에서 `interpose-loaded`가 각각 기록됐다. 그러나 소켓 호출 기록이 전혀 없어 `socket(AF_INET6)`에 `EAFNOSUPPORT`가 실제 적용됐다는 근거는 없다. 두 제품 서비스는 준비 단계에서 `service-exit-4`로 종료했다. 이 결과를 IPv6 실패를 견딘 제품 성공이나 제품 결함으로 판정하지 않는다.

- 실제 호스트는 주입 없는 `socket(AF_INET6)` 생성이 가능했다. 앞선 물리 실측의 공인 IPv6 미관측과는 별개다.
- 기존 저장소 release의 private 복사본을 사용했다. SHA-256은 `f17f03fafcdf3a31e374d6cbc0ccbbbd8000ba6a7eba5d9b44605e742c409aed`다. 앞선 공개 relay 표본의 `c963...` 바이너리와 합치지 않는다.
- Python 소스 52개를 새 private 폴더로 동결했고 복사 뒤 변경은 없었다. 제품 소스는 수정하지 않았다.
- Python이 시작한 뒤 native 자식용 `DYLD_INSERT_LIBRARIES`만 설정했다. 전역 IPv6·방화벽·사용자 프로필·인증 설정을 바꾸지 않았다.
- 소유한 IPv4 UDP 포트 62599를 먼저 점유해 대체 경로도 보려 했으나, 실제 엔진의 ready·IPv4 bind·init·join·ping·port fallback까지 도달하지 못했다.
- 서비스 PID 46059·46142는 exit 4였고, 라이브러리 적재를 기록한 엔진 PID 46085·46172도 종료 확인됐다. control socket은 남지 않았다. 점유한 대조 포트는 해제 후 다시 bind할 수 있었다.
- 키·초대 값을 읽거나 복사하지 않았다. 새 상태와 기존 증거를 보존했으며 같은 조건을 재실행하지 않았다.

[첫 결과 JSON](first-result-summary.json), [실행 결과](result.json), [소스·바이너리 manifest](manifest.json), [C 소스](noipv6.c), [실행 코드](fault-run.py).

이 시도의 남은 문제는 실제 엔진 소켓 호출에 interpose가 적용됐음을 먼저 입증하는 것이다. 첫 결과만 요청된 범위에 따라 추가 실험은 실행하지 않았다. 실제 IPv6 부재 호스트의 수용 근거도 여전히 별도 필요하다.
