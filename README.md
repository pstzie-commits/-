# 가스 인프라 규제 준수 검토 에이전트 (KGS Code / 산업안전보건법)

플랜트·가스 인프라 엔지니어링 문서(PDF/DOCX/TXT)를 입력받아, 한국가스안전공사(KGS) 시설·기술
기준(KGS Code)과 산업안전보건법 체크리스트에 따라 Claude API로 1차 규정 준수 여부를 판정하고
Markdown 보고서를 생성하는 독립 실행형 CLI 도구입니다.

## ⚠️ 중요한 한계 (반드시 읽어주세요)

- 이 도구는 **법적 효력이 없는 1차 스크리닝 보조 도구**입니다. 최종 판단은 자격을 갖춘
  안전관리자, 가스안전 기술사, 관계 검사기관(한국가스안전공사, 고용노동부 등)의 확인을
  거쳐야 합니다.
- `checklists/*.yaml`에 포함된 체크리스트는 **출발점(스타터 세트)**입니다. KGS Code는
  가스 종류(고압가스/LP가스/도시가스/수소)와 설비 용도별로 세분화되어 있고, 산업안전보건법은
  개정이 잦습니다. 사용 전 아래 원문을 반드시 대조하여 프로젝트에 맞게 갱신하세요.
  - KGS Code 원문: <https://cyber.kgs.or.kr>
  - 법령 원문: <https://law.go.kr>
- Claude는 문서에 **명시된 내용만**을 근거로 판단하도록 프롬프트가 구성되어 있으며, 근거가
  불충분하면 "확인필요"로 표시합니다. 그럼에도 오탐/누락 가능성이 있으므로 결과를 그대로
  신뢰하지 말고 반드시 검수하세요.
- 스캔 이미지로 된 PDF는 텍스트 추출이 되지 않습니다(OCR 미포함). 필요 시 별도 OCR 처리 후
  텍스트/PDF로 변환해 사용하세요.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Claude API 키가 필요합니다 (`ant auth login` 또는 `ANTHROPIC_API_KEY` 환경변수).

## 사용법

```bash
# 기본: KGS + 산업안전보건법 체크리스트 모두 적용
python -m kgs_compliance_agent --file examples/sample_spec.txt --output report.md

# 특정 체크리스트만 적용
python -m kgs_compliance_agent --file spec.pdf --checklist kgs --output report.md

# 사용자 정의 체크리스트 YAML 추가
python -m kgs_compliance_agent --file spec.docx --checklist kgs osha my_checklist.yaml
```

지원 입력 형식: `.pdf`, `.docx`, `.txt`, `.md`

출력: `--output` 미지정 시 표준출력, 지정 시 해당 경로에 Markdown 보고서 저장. 항목별로
`준수 / 미준수 / 확인필요 / 해당없음` 상태, 문서 근거 발췌, 판단 근거, 보완 제안이 포함됩니다.

## 체크리스트 커스터마이징

`checklists/kgs_gas_facility.yaml`, `checklists/osha_kr.yaml` 형식을 참고해 자체 YAML을
작성할 수 있습니다.

```yaml
categories:
  - name: "카테고리명"
    items:
      - id: MY-001              # 전체 체크리스트 내에서 고유해야 함
        title: 항목 제목
        requirement: 판단 기준을 구체적으로 서술
        reference: 근거 조문/코드 (확인 안 됐으면 그렇게 명시)
        notes: 선택 사항, 추가 참고사항
```

## 프로젝트 구조

```
kgs_compliance_agent/
  document_loader.py     # PDF/DOCX/TXT 텍스트 추출
  checklist.py            # YAML 체크리스트 로딩
  compliance_checker.py   # Claude API 호출, 구조화된 판정 결과 생성
  report.py                # Markdown 보고서 렌더링
  __main__.py              # CLI 진입점
checklists/
  kgs_gas_facility.yaml   # KGS Code 스타터 체크리스트
  osha_kr.yaml             # 산업안전보건법 스타터 체크리스트
examples/
  sample_spec.txt          # 테스트용 샘플 사양서(의도적으로 일부 항목 미비)
```

## 동작 방식

1. 문서에서 텍스트를 추출한다 (`document_loader`).
2. 지정된 체크리스트를 로드한다 (`checklist`).
3. 문서 전체 텍스트 + 체크리스트를 하나의 Claude API 요청(`messages.parse`, 구조화된 출력)에
   담아 항목별 판정을 받는다 (`compliance_checker`). 문서가 너무 커서 안전 토큰 한도를
   초과하면 자동으로 잘라내지 않고 오류로 알려주므로, 문서를 분할해 재시도해야 한다.
4. 결과를 카테고리별 Markdown 보고서로 렌더링한다 (`report`).
