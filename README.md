# bus-stop

대전 수소트램 개통 전후 대중교통 경로 비교 프로젝트의 버스 공공데이터 수집 자료입니다.

- 수집일: 2026-10-21 (Asia/Seoul)
- 운행 기준일: 2026-09-01
- 노선 118건, 대전 5개 구 내부 경유 기록 9,425건, 고유 정류장 2,795개
- 상세 컬럼, 출처, 106번 검증 및 제약 사항: [data/README.md](data/README.md)

## 실행

Python 3의 표준 라이브러리로 실행합니다. `.env.example`을 `.env`로 복사하고 공공데이터포털 인증키를 입력하세요. 실제 `.env`는 Git에서 제외됩니다.

```sh
python scripts/collect_bus.py --date 20260901
python scripts/verify_bus.py
```

수집 성공을 확인한 뒤 검증 스크립트를 실행하세요. AI 경로 추천 기능은 포함하지 않습니다.

## 정류장 좌표

`scripts/geocode_stops.py`는 대전광역시 정류소정보조회 API의 7자리 `BUS_NODE_ID`를 기존 정류장 ID와 비교해 위도·경도를 연결합니다. 기존 CSV를 읽고 `data/bus_stops_geocoded.csv`를 별도로 생성합니다. API가 제공하는 현재 위치를 사용하므로 2026-09-01 당시의 좌표를 보장하지 않습니다.

```sh
python scripts/geocode_stops.py --run 20261021 --probe
python scripts/geocode_stops.py --run 20261021
```

`.env`의 기존 인증키를 사용합니다. 먼저 복합터미널과 아이빌딩의 ID 연결을 확인하며, 두 정류장의 좌표를 확인하지 못하면 전체 조회를 중단합니다. 같은 실행 이름의 XML 응답을 재사용하고, 출력 CSV가 이미 있으면 덮어쓰지 않습니다. 새로 수집할 때는 다른 실행 이름과 별도 작업 복사본을 사용하세요. 연결 규칙과 검증 결과는 [data/GEOCODING.md](data/GEOCODING.md)에 설명합니다.

## 가상 트램 좌표

대전 2호선 45개 정거장의 추정 좌표는 [data/tram_stations_estimated.csv](data/tram_stations_estimated.csv), 검토 지도는 [data/tram_stations_review.html](data/tram_stations_review.html)에 있습니다. 218번을 제외한 44개는 승강장 중심을 확정하지 않은 도로 구간 대표점입니다. 등급·출처와 순환선·지선 연결은 [data/TRAM_COORDINATES.md](data/TRAM_COORDINATES.md)를 참고하세요.

## 트램 경로 계산

Desktop `daejeon-tram-route-lab`에서 기존 단일 순환 계산을 본선·지선 연결 그래프로 교체했습니다. 그래프가 허용하는 방향으로 이동하며, 구간별 예상 이동시간과 중간 정차시간을 합산해 경로를 선택합니다.

[트램 수정 패키지](patches/desktop-tram-only/)에는 서버 패치, 그래프 데이터, 계산 모듈, 테스트가 들어 있습니다. 기존 Desktop 프로젝트에 적용하는 방법과 검증 결과는 [변경 기록](patches/desktop-tram-only/CHANGES.md)을 참고하세요.
