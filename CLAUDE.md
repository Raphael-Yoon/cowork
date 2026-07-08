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

> [!NOTE]
> 추천종목(Top 10) 선정 파이프라인(`pool_collect.py`/`select_top_10.py`/`pool_save.py`/`audit_save.py`, `Report/` 문서 포함)은
> 담당자 이동에 따라 **개발2팀 `trade/` 저장소로 전체 이관**되었다. 관련 로직은 `trade/추천종목_선정_작업지침서.md` 참조.

## 4. 환경 관리 원칙 (Local)

- **보존 대상**: `Evidence/` 폴더 전체, `Paper/` 원본 엑셀 조서, `RCM/` 폴더
- **삭제 대상**: 임시 생성한 데이터 매핑용 `.py` 파일 및 테스트 결과 엑셀
