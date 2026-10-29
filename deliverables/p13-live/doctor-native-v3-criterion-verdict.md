# A23-07 원criterion 재판정 — 짧은 별도 verdict

**판정: 전제에는 동의하지만 전체 종결에는 반대한다.** setup.process/home_match=observed·clean stderr·계측 성공은 원criterion의 필수 조건이 아니다. 앞선 partial 설명에서 이를 필수 종결 조건으로 취급한 근거는 철회한다. 기존 v3 원문/partial/unknown은 수정하지 않았다.

v3는 실제 target1의 설치/trust metadata 읽기, synthetic 오류집계 marker 비출력, 외부 동일 PID/lstart와 후속 실제 tool을 증명한다. 이는 해당 표본의 민감 비출력·비종료 긍정 증거이며, metadata home 경로가 출력됐다는 이유로 원문 개인정보 유출이라고 판정하지 않는다.

다만 “현재 doctor에 원문 출력 경로가 없다”는 전제가 성립하지 않는다. 최종source에서 `ledger.queued`가 본문 앞200자를 **preview**로 저장한다([ledger.py:66](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/ledger.py:66), [envelope.py:226](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/envelope.py:226)). `ledger.recent`는 이를 제거하지 않고 반환하고([ledger.py:382](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/ledger.py:382)), `install.stuck`은 **120초 넘은 queued / unknown 두 분기**에서 그 행 전체를 `undelivered/uncertain`에 넣는다([install.py:2268](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/install.py:2268)). 이 결과가 doctor report에 포함되고([install.py:2355](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/install.py:2355)), `doctor --json`은 report 전체를 그대로 직렬화한다([cli.py:1602](/private/tmp/xsm-final-receipt-frozen-i3u9pms3/xsm/cli.py:1602)). 이 경로에 preview redaction은 없다.

이는 metadata 경로가 아니라 **메시지 원문 일부**다. 본문에 개인정보·초대 등이 있으면 해당 일부가 JSON 출력에 실릴 수 있다. 실제 유출을 새로 재현했다는 뜻은 아니며, 읽기 전용 source에서 확인한 도달 가능한 경로다. v3의 두 collection은 모두0이어서 synthetic decisions 비출력이 이 분기를 검사한 증거는 아니다. 기존 setup redaction fixture도 전체 doctor의 이 branch를 검증하지 않는다.

따라서 부족한 것은 observed 값/계측/전수검사가 아니라 **원criterion 자체의 민감 원문 비출력 보장**이다. 비종료 native 표본은 인정하되 이 직접 출력 경로가 남아 있어 전체 A23-07 종결에는 반대한다. 새 모델·진단·재현·네트워크 실행0, 제품·plan·ledger 수정0이다.
