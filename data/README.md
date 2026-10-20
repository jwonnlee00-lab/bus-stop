# 대전 버스 공공데이터 수집 결과

- 실제 수집일: 2026-10-21 (Asia/Seoul). 요청별 정확한 시각은 raw/20260901/requests.json 참조.
- 데이터 운행일자: 2026-09-01. 최신 제공일로 확정한 것은 아님.
- 2026-10-21 및 2026-10-01 조회는 HTTP 200이지만 Error.code=50, NO_DATA_FOUND 반환.
- 출처: https://www.data.go.kr/data/15142030/openapi.do 및 https://www.data.go.kr/data/15142031/openapi.do
- 공식 명세는 sources/*.openapi.json, 경유정류장 활용가이드는 sources/stops-guide.pdf에 보관.
- API 원본 응답은 raw/ 아래에 보관. 인증키는 요청 기록에서 제외.

## 파일과 컬럼

CSV는 Excel에서 한글을 읽을 수 있도록 UTF-8 BOM으로 저장했다. ID는 문자열로 읽어야 한다.

| 파일 | 데이터 행 수 | 컬럼 |
|---|---:|---|
| bus_routes.csv | 118 | opr_ymd, ctpv_cd, sgg_cd, rte_id, rte_no, rte_nm, dptre_sttn_id, dptre_sttn_nm, arvl_sttn_id, arvl_sttn_nm |
| bus_route_stops.csv | 9,425 | opr_ymd, rte_id, rte_no, rte_nm, sttn_seq, sttn_id, sttn_nm, ctpv_cd, sgg_cd, emd_cd, ctpv_nm, sgg_nm, emd_nm, trfc_mns_se_cd |
| bus_stops.csv | 2,795 | sttn_id, sttn_nm, ctpv_cd, ctpv_nm, sgg_cd, sgg_nm, emd_cd, emd_nm |

bus_routes.json에는 노선, 경유 기록, 정류장, 출처, 기준일, 검증 결과가 포함된다.
bus_stops.csv는 경유 기록에서 sttn_id로 중복 제거한 정류장 명부다. 두 승인 API에는 좌표가 없어 위치 좌표는 확보하지 못했다.
경유 기록은 대전 5개 구를 각각 조회한 결과이며 시외 구간은 포함하지 않는다. 원본의 순번을 유지하고 rte_id, sttn_seq 순서로 정렬했다.

## ID 검증

- 노선 목록의 118개 노선 모두 경유 기록과 rte_id로 연결된다.
- 경유 기록에는 노선 목록에 없는 노선 ID가 추가로 51개 존재한다. 다른 노선에 임의로 연결하거나 삭제하지 않았다.
- 노선 목록의 출발·도착 정류장 ID 중 6개는 이번 대전 내부 정류장 명부에 없다. 시외 구간 등 원인 확정은 하지 않았다.
- 모든 경유 기록의 ctpv_cd는 30이다.
- (rte_id, sttn_seq) 중복 0건, 동일 sttn_id의 정류장명 충돌 0건.
- bus_route_stops.csv의 모든 sttn_id는 bus_stops.csv에 연결된다.
- 구체적인 불일치 ID와 106번 전체 경유 기록은 validation.json 참조.

## 106번 확인

노선 ID 30300041, 노선명 106번(목원대비래동).

| 정류장 | ID | 순번 |
|---|---|---:|
| 복합터미널 | 8001097 | 30 |
| 비래동종점 | 원본 경유 기록 참조 | 40, 41 |
| 복합터미널 | 8001096 | 52 |
| 아이빌딩 | 8002159 | 62 |

복합터미널(52) → 아이빌딩(62)이 같은 노선에서 순서대로 확인된다. 이 구간은 비래동종점 이후 목원대 쪽으로 돌아가는 구간이다. 제시된 '비래동 종점 방향' 안내와는 맞지 않으므로 탑승 방향을 재확인해야 한다. 순번 30에서 승차하면 비래동종점을 거친 뒤 아이빌딩으로 이어지는 형태이며 종점 통과 탑승 가능 여부는 이 API로 알 수 없다.
운행시간·대기시간·도보시간·미라클빌딩까지의 접근 경로는 이 두 API로 검증하지 않았다. AI 경로 추천은 구현하지 않았다.

## 재수집

프로젝트 루트 .env의 DATA_GO_KR_API_KEY 또는 DATA_GO_KR_SERVICE_KEY를 읽는다. 키는 출력하지 않는다.

```text
python scripts/collect_bus.py --date 20260901
python scripts/verify_bus.py
```

수집이 성공한 경우에만 검증 스크립트를 실행한다. 원본 응답은 Response/resultCode=200 형식으로, 포털 Swagger의 소문자 response 형식과 차이가 있어 이를 반영했다. 기존 프로젝트 애플리케이션 코드는 변경하지 않았다.
