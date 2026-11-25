# 완료 증거 (main a35e397, 2026-11-25 14:41)

## 1. 갈래별 원래 모델: 깨지는 규칙 (req.py red SM-MODEL)
```
concurrent/Scn_a.cfg: AtMostOneHandoverPerSession, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded
concurrent/Scn_b.cfg: AddressAndPlaceAgree, AddressLeadsAway, HandedOverHoldsNoPlace, QuestionHolderIsAddressTarget, LateAnswerRecorded
concurrent/Scn_c.cfg: HandedOverHoldsNoPlace, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, LateAnswerRecorded
concurrent/XsmConcurrentHandover.cfg: AtMostOneHandoverPerSession, AddressAndPlaceAgree, QuestionHolderIsAddressTarget, AddressLeadsAway, HandedOverHoldsNoPlace, LateAnswerRecorded
migration/XsmHeldDeliver.cfg: YesIsFinal
migration/XsmTransfer.cfg: DeliveredMeansShown, HeldFollowsOwner
remote/XsmRemote.cfg: ViewsAgree, AnswerRecorded
remote/XsmRemoteStranger.cfg: ViewsAgree, AnswerRecorded
remote/scenarioAskedAfter.cfg: ViewsAgree, AnswerRecorded
remote/scenarioChain.cfg: ViewsAgree, AnswerRecorded
remote/scenarioLost.cfg: ViewsAgree, AnswerRecorded
remote/scenarioUnread.cfg: QuestionAnswerable
round1/XsmHandover.cfg: AnswerRecorded, HeldStaysHeld
scope-groups/XsmScopeGroups.cfg: LateAnswerReachesSuccessor, GroupShowsEveryAnswer, GroupStatusTruthful
teams/XsmHandoverBoard.cfg: EveryOwnerItemClosed, MovedItemIsClosed, NoContentLeftBehind
teams/XsmHandoverPlaces.cfg: PlaceAndItemsMoveTogether, BCanReachWhatMoved, NoPlaceLeftBehind
teams/XsmHandoverTeamSync.cfg: HandoverStands, BHoldsTheSeatEverywhere, SameTeamAtRest
exit=0
```

## 2. 수정 의미 모델 19개 (req.py check SM-MODEL)
```
exit=0
```

## 3. 갈래 재현 시험을 0.6.1(2a858d3) 전체 체크아웃에서 실행

재현 시험은 결함이 일어난다고 단언하므로, 0.6.1에서 통과하면 그 갈래의 결함이 재현된 것이다. 수는 상속한 기존 시험을 포함한다. (`git archive`는 `.gitattributes`의 `tests/ export-ignore` 때문에 `tests/`가 빠져 쓸 수 없어 `git worktree add --detach`로 꺼냈다.)
```
round1/replay_test.py: Ran 28 tests in 2.267s OK 
concurrent/replay_test.py: Ran 32 tests in 2.412s OK 
scope-groups/replay_test.py: Ran 35 tests in 3.806s OK 
migration/replay_test.py: Ran 66 tests in 5.803s OK 
remote/replay_test.py: Ran 11 tests in 0.949s OK 
teams/replay_board_test.py: Ran 30 tests in 2.156s OK 
teams/replay_places_test.py: Ran 30 tests in 1.896s OK 
teams/replay_teamsync_test.py: Ran 27 tests in 2.391s OK 
```

## 4. P0 RED 시험 모듈을 main에서 실행 (RED 표시가 모두 지워진 채 통과)
```
test_state_model_handover: Ran 38 tests in 9.574s OK 
test_state_model_questions: Ran 33 tests in 9.270s OK 
test_state_model_held: Ran 15 tests in 1.661s OK 
test_state_model_remote: Ran 10 tests in 1.156s OK 
test_state_model_remote_succession: Ran 8 tests in 0.752s OK 
test_state_model_teams: Ran 17 tests in 4.319s OK 
expectedFailure decorators left: 0
```
