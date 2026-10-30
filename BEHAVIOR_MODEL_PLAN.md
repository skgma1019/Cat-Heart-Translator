# 고양이 행동 모델 준비 계획

현재 데이터 목록에는 CAT 행동 코드 12종, Training 21,544개와 Validation 2,700개의 클립, 약 186만 CAT JPG 프레임이 있다. 실제 JSON 내용은 ARCH Training 한 코드만 확인됐다. **다른 11개 코드와 Validation의 행동 문구·ID 구조를 점검하기 전에는 학습하지 않는다.** `tools/audit_cat_labels.py`는 Windows `E:` 드라이브의 라벨 ZIP만 읽어 코드별 실제 `metadata.action`, 종, JSON 오류, 파일명 연결, 명시적 ID 필드와 분할 교집합을 작은 JSON 보고서로 저장한다. 원본 ZIP은 풀거나 수정하지 않는다.

RTX 4060 Laptop에는 전체 186만 프레임을 처음부터 학습하는 방식보다, 각 클립에서 시간 간격을 두고 8~12프레임을 읽는 파일럿이 현실적이다. 라벨 확인 후 사전학습된 가벼운 이미지 인코더와 시간 축 집계기를 사용해 **클립 단위 12코드 분류**부터 검증한다. 처음에는 인코더를 고정하고 작은 배치와 혼합 정밀도를 사용한다. 클래스 수가 ARCH 203개부터 GROOMING 5,832개까지 달라 가중 손실과 클래스별 지표가 필요하다. 기존 Validation을 이용한 정확도만으로 일반화 성능을 단정하지 않는다.

ARCH JSON의 행동명은 `metadata.action`에 있고 각 프레임 annotation에는 키포인트·바운딩박스가 있다. 프레임마다 독립적인 행동 라벨이 있다고 가정하면 안 된다. 웹의 시간대별 확률은 클립 모델에 슬라이딩 윈도를 적용할 수 있지만, **시간 구간 수준의 라벨과 검증이 확보되기 전에는 검증된 시간대별 예측이라고 표시하지 않는다.** 현재 울음 모델과 행동 모델은 별도로 유지한다.

행동 코드의 한국어 표시 이름은 데이터 설명서와 모든 클래스의 실제 JSON 문구를 확인해 정한다. 감정 정보는 행동 라벨에 섞지 않는다. 고양이 개체 ID가 없으면 개체 기준 누출을 배제할 수 없으므로 이를 평가 한계로 보고한다. 실제 영상 업로드를 위한 프레임 추출·추론·결과 시각화는 모델 검증 후 구현한다.

## Windows에서 다음에 실행할 점검

Python이 설치되어 있지 않다면 Windows PowerShell에서 `winget install --id Python.Python.3.12 -e`로 설치한 후 새 PowerShell을 연다. 저장소의 `tools/audit_cat_labels.py` 파일만 다운로드 폴더에 저장한다. 데이터는 `E:`에 그대로 둔다.

```powershell
py -3.12 "$env:USERPROFILE\Downloads\audit_cat_labels.py" --root "E:\냥심번역기 데이터셋\반려동물 구분을 위한 동물 영상"
```

출력은 `Downloads\cat-behavior-label-audit.json` 한 파일이다. 정상적으로 전체가 보이면 `CAT label archives: 24; failures: 0`이 표시된다. 이 보고서에는 행동 문구 빈도, JSON 필드, `file_video` 중복, 명시적인 ID 필드의 Training/Validation 교집합이 포함된다. **보고서를 확인하고 데이터 분할 기준을 정한 다음에만** 학습 코드를 확정한다. 이 스크립트는 원본 ZIP을 읽기만 하며 학습이나 압축 해제를 하지 않는다. 업로드된 ARCH ZIP 180개 JSON으로 동작을 검증했으나, 전체 24개 ZIP은 이 클라우드 환경에서 실행하지 못했다.
