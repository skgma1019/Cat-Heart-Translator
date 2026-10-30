# 고양이 행동 모델 준비 계획

현재 데이터 목록에는 CAT 행동 코드 12종, Training 21,544개와 Validation 2,700개의 클립, 약 186만 CAT JPG 프레임이 있다. 사용자 현지 실행 보고서로 CAT 라벨 ZIP 24개, JSON 24,244개를 전수 점검했다. 종은 모두 CAT이며 JSON 파싱 오류는 0건이다. 코드별 실제 행동 문구와 수량은 [DATASET_AUDIT.md](DATASET_AUDIT.md)에 기록했다. 다만 명시적인 고양이 ID가 없어 개체별 분할 누출을 배제할 수 없다. `tools/audit_cat_labels.py`는 원본 ZIP을 풀거나 수정하지 않는다.

RTX 4060 Laptop에는 전체 186만 프레임을 처음부터 학습하는 방식보다, 각 클립에서 시간 간격을 두고 8~12프레임을 읽는 파일럿이 현실적이다. 라벨 확인 후 사전학습된 가벼운 이미지 인코더와 시간 축 집계기를 사용해 **클립 단위 12코드 분류**부터 검증한다. 처음에는 인코더를 고정하고 작은 배치와 혼합 정밀도를 사용한다. 클래스 수가 ARCH 203개부터 GROOMING 5,832개까지 달라 가중 손실과 클래스별 지표가 필요하다. 기존 Validation을 이용한 정확도만으로 일반화 성능을 단정하지 않는다.

ARCH JSON의 행동명은 `metadata.action`에 있고 각 프레임 annotation에는 키포인트·바운딩박스가 있다. 프레임마다 독립적인 행동 라벨이 있다고 가정하면 안 된다. 웹의 시간대별 확률은 클립 모델에 슬라이딩 윈도를 적용할 수 있지만, **시간 구간 수준의 라벨과 검증이 확보되기 전에는 검증된 시간대별 예측이라고 표시하지 않는다.** 현재 울음 모델과 행동 모델은 별도로 유지한다.

행동 코드의 한국어 표시 이름은 전수 보고서의 `metadata.action` 최빈 문구를 잠정 사용하되, 공식 설명서가 있으면 대조한다. 감정 정보는 행동 라벨에 섞지 않는다. 고양이 개체 ID가 없으므로 개체 기준 누출을 배제할 수 없다고 평가 한계에 명시한다. 학습 전에 원천 ZIP의 프레임과 라벨 JSON을 연결하는 매니페스트를 만들고, `file_video` 이름이 JSON 파일명과 다른 77개를 검토한다. 실제 영상 업로드를 위한 프레임 추출·추론·결과 시각화는 모델 검증 후 구현한다.

## 완료된 Windows 라벨 점검

사용자가 Python 3.12에서 아래 명령을 실행해 보고서를 제공했다. 데이터는 `E:`에 그대로 있다.

```powershell
py -3.12 "$env:USERPROFILE\Downloads\audit_cat_labels.py" --root "E:\냥심번역기 데이터셋\반려동물 구분을 위한 동물 영상"
```

출력 `cat-behavior-label-audit.json`에서 CAT 라벨 ZIP 24개와 실패 0건을 확인했다. `file_video` 경로와 기본 이름의 Training/Validation 교집합은 각각 0건이다. 이 스크립트는 원본 ZIP을 읽기만 하며 학습이나 압축 해제를 하지 않는다. 전체 ZIP에 대한 실행은 사용자 Windows에서 수행됐고, 클라우드에서는 결과 보고서만 검토했다. 다음은 현지 `E:` 데이터에서 프레임·라벨 연결 매니페스트와 소규모 학습 파일럿을 검증하는 단계다.

## 프레임·라벨 매니페스트 검사

`tools/build_cat_behavior_manifest.py`는 24개 CAT 원천 ZIP과 대응 라벨 ZIP을 **압축 해제 없이 읽고**, 클립별 프레임 수·타임스탬프·행동 문구·ZIP 경로를 CSV에 기록한다. 각 원천 ZIP에서 JPEG 헤더 1개를 기본 표본 검사한다. 표준 라이브러리만 필요하며 결과는 `Downloads`에 저장한다.

```powershell
py -3.12 "$env:USERPROFILE\Downloads\build_cat_behavior_manifest.py" --root "E:\냥심번역기 데이터셋\반려동물 구분을 위한 동물 영상"
```

정상 기대치는 `Clips: 24244; problems: 0`이다. 다운로드 폴더의 `cat-behavior-manifest-report.json`을 공유하면 오류와 예외를 확인할 수 있다. CSV는 현지 학습 입력으로 보관한다. 이 단계는 모든 JPG를 디코딩하지 않으며 ZIP 내부 경로와 표본 헤더만 검증한다. 별도로 제공된 전체 ZIP 내부 목록의 CAT JPG **1,866,408개**가 스크립트의 프레임 파일명 규칙과 맞는 것은 클라우드에서 검증했다.

사용자가 Windows에서 매니페스트 생성을 실행해 `Clips: 24244; problems: 0`을 확인했다. 이에 따라 소규모 GPU 파일럿 학습 코드를 `tools/train_cat_behavior_pilot.py`에 준비했다. 이 코드는 각 코드에서 최대 Training 100개, Validation 30개 클립을 고정 시드로 뽑고, ZIP에서 클립당 8프레임을 디코딩한다. 사전학습 MobileNetV3 Small을 고정한 뒤 프레임 특징 평균과 선형 분류기를 학습한다. 샘플 수가 작은 **기본 가능성 검사**이며, 시간대별 행동 모델이나 최종 성능으로 해석하지 않는다. 결과 JSON에는 Validation 정확도, macro F1, 클래스별 재현율과 혼동행렬이 기록된다. 학습된 체크포인트도 `Downloads\cat-behavior-pilot`에 저장된다.

Windows PowerShell에서 Python 3.12용 CUDA PyTorch와 이미지 의존성을 설치한 뒤 실행한다. NVIDIA 드라이버가 오래됐다면 설치 전에 업데이트해야 할 수 있다. 기존 울음 모델과 원본 데이터에는 영향을 주지 않는다.

```powershell
py -3.12 -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
py -3.12 -m pip install pillow numpy
py -3.12 "$env:USERPROFILE\Downloads\train_cat_behavior_pilot.py" --root "E:\냥심번역기 데이터셋\반려동물 구분을 위한 동물 영상"
```

첫 실행 시 사전학습 인코더 가중치를 내려받는다. CUDA가 확인되지 않으면 훈련을 시작하지 않고 오류를 낸다. 클라우드에서는 원본 영상 ZIP과 RTX 4060이 없으므로 전체 학습을 실행하지 못했다. 파일럿 결과를 확인한 뒤 학습 방식과 분할 한계를 검토하고, 충분한 성능이 입증되어야 웹의 영상 분석 기능에 연결한다. 모델 점수는 현재 보정된 확률이 아니다.

### Windows 파일럿 결과 (사용자 제공 지표)

사용자가 RTX 4060 Laptop에서 CUDA PyTorch `2.5.1+cu121`로 학습을 완료하고 `cat-behavior-pilot-metrics.json`을 제공했다. Training 1,200개, Validation 353개, 클립당 8프레임 조건에서 **정확도 37.39%, macro F1 0.3702**였다. Validation에서 ARCH는 23개, 나머지 코드는 각 30개다. 12종 균등 무작위 기준 8.33%보다는 높지만, 12종 행동 분석을 사용자에게 제공하기에는 오류가 많다. 특히 ARMSTRETCH 재현율 23.3%, GETDOWN/LAYDOWN 26.7%, GROOMING/SITDOWN 30.0%였다. 가장 높은 ROLL도 56.7%다. 이 체크포인트를 웹 API에 연결하거나 확률 그래프로 공개하지 않는다.

다음 실험에서는 더 많은 학습 클립을 사용하고, 프레임 특징의 단순 평균이 놓치는 움직임 순서를 보존하는 시간 모델을 비교해야 한다. 현재 데이터는 클립 단위 라벨이므로 시간 구간별 정답과 일반 영상에 대한 성능은 별도로 검증해야 한다. 같은 고양이가 두 분할에 섞였는지도 여전히 알 수 없다. 학습 과정에서 프레임 자체의 품질·중복·클래스 혼동을 표본 검토하고, 데이터 설명서가 있다면 공식 분할 기준을 먼저 대조한다.
