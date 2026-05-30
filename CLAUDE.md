# IT 감사 조서 시스템 기술 명세 (Technical Specs)

> [!IMPORTANT]
> 에이전트 페르소나, 직급 체계 및 전사 운영 규칙은 루트의 [CLAUDE.md](file:///c:/Python/CLAUDE.md)를 준수한다. 본 파일은 프로젝트별 기술 명령어 및 파일 참조용으로만 활용한다.

## 1. 빌드 및 실행 명령어 (Build & Run)

- **감사 조서 자동 생성**: `python generate_pbc_v2.py`
- **IPE(모집단) 완전성 검증**: `python validation_tool.py --ipe`
- **증빙 파일 인덱싱**: `python evidence_manager.py --index`

## 2. 테스트 및 검증 (Tests)

- **조서 데이터 정합성 테스트 (성승연 담당)**: `pytest tests/audit/`
- **샘플링 적정성 검증**: `python sampling_logic.py --validate`
- **취약점 점검 자동화 실행 (김도희 담당)**: `python security_scan.py`

## 3. 프로젝트 파일 참조 (Reference)

| 파일/폴더 | 설명 |
|------|------|
| `generate_pbc_v2.py` | 감사 조서 생성 메인 스크립트 |
| `Evidence/` | 원천 증빙 저장 폴더 |
| `Paper/` | 조서 서식 및 최종 산출물 폴더 |
| `RCM/` | 감사 통제 기술서(RCM) |
| `Paper/review_guide.md` | 통제별 상세 리뷰 가이드 |
| `RCM/RCM_Standard.xlsx` | 기본 RCM 표준 서식 |

## 4. Top 10 선정 트리거 (IT 감사팀 전용)

사용자가 **"Top 10 선정"** 또는 **"공략주 선정"** 을 요청하면 아래 절차를 반드시 따른다.

1. `trade/trade.db` → `stock_pool` 테이블에서 100개 종목 및 `stock_disclosures` 테이블에서 최근 30일간의 기업 공시 자료를 함께 조회한다.
2. AI가 네이티브 웹 검색(현재가, 수급, 뉴스)과 조회한 공시 데이터(감사의견, 소송, 배임/횡령, 수주 등)를 종합 취합한다.
3. `audit_logic.md` 섹션 3의 Hard Filter를 적용해 리스크 종목을 사전에 배제한 후, 섹션 4의 복합 스코어 알고리즘(공시 모멘텀 가감점 포함)을 적용하여 상위 10개 우량 종목을 최종 결정한다.
4. `recommendations.json` 작성 시, 종목별 `news_summary` 필드에 주요 뉴스 외에 분석한 **공시 요약 내용도 명시**하여 기록한다.
5. `python cowork/audit_save.py recommendations.json` 실행하여 DB에 최종 적재한다.

> **[금지]** 2·3단계(검색·분석·스코어링)를 위한 Python 코드를 작성하지 않는다. `audit_save.py` 호출 외 Python 코드 작성은 절대 금지.

## 5. 환경 관리 원칙 (Local)

- **보존 대상**: `Evidence/` 폴더 전체, `Paper/` 원본 엑셀 조서, `RCM/` 폴더
- **삭제 대상**: 임시 생성한 데이터 매핑용 `.py` 파일 및 테스트 결과 엑셀
