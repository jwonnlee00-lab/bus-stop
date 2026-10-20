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
