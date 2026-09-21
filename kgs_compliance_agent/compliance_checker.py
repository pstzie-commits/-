"""Claude API를 이용해 문서 텍스트를 체크리스트 항목별로 평가한다."""

from __future__ import annotations

from enum import Enum

import anthropic
from pydantic import BaseModel

from .checklist import ChecklistItem

MODEL = "claude-opus-5"

# claude-opus-5의 컨텍스트 윈도우(1M 토큰)에서 체크리스트/시스템 프롬프트/출력 여유분을
# 남겨 두기 위한 안전 한도. 이 이상이면 문서를 분할하도록 안내하고 조용히 자르지 않는다.
MAX_DOCUMENT_TOKENS = 700_000


class ComplianceStatus(str, Enum):
    COMPLIANT = "준수"
    NON_COMPLIANT = "미준수"
    NEEDS_REVIEW = "확인필요"
    NOT_APPLICABLE = "해당없음"


class ItemResult(BaseModel):
    item_id: str
    status: ComplianceStatus
    evidence: str  # 문서에서 근거가 된 부분(발췌/요약). 근거가 없으면 빈 문자열.
    reasoning: str  # 판단 근거
    recommendation: str  # 미준수·확인필요일 때 보완 제안. 준수/해당없음이면 빈 문자열.


class ComplianceReport(BaseModel):
    results: list[ItemResult]


class DocumentTooLargeError(Exception):
    pass


SYSTEM_PROMPT_TEMPLATE = """\
당신은 플랜트·가스 인프라 엔지니어링 문서를 검토하는 규제 준수(compliance) 검토 보조자입니다.
검토 대상 규정은 한국가스안전공사(KGS)의 시설/기술/검사 기준(KGS Code)과 \
산업안전보건법 및 하위 법령입니다.

다음 체크리스트 항목 각각에 대해, 첨부된 엔지니어링 문서 텍스트만 근거로 판단하세요.

체크리스트:
{checklist_block}

각 항목에 대해 반드시 다음 규칙을 따르세요:
- status: 문서에 해당 요건이 명확히 충족되어 있으면 "준수", 명확히 위반/누락되어 있으면 "미준수", \
문서에 판단할 근거가 불충분하거나 전문가의 추가 확인이 필요하면 "확인필요", \
문서의 설비/공정 특성상 해당 항목이 적용되지 않으면 "해당없음"으로 표시하세요.
- evidence: 판단의 근거가 된 문서 내용을 가능한 한 원문에 가깝게 인용하거나 위치(예: 페이지, 절 번호)를 \
포함해 요약하세요. 근거가 없으면 빈 문자열로 두세요.
- reasoning: 왜 그 status를 선택했는지 근거 조문/코드와 연결해 설명하세요.
- recommendation: status가 "미준수" 또는 "확인필요"인 경우에만, 문서를 보완하거나 \
현장에서 확인해야 할 구체적인 조치를 제안하세요. 그 외에는 빈 문자열로 두세요.

추측하지 마세요. 문서에 명시되지 않은 사실을 임의로 준수/미준수로 단정하지 말고, \
근거가 부족하면 "확인필요"로 표시하세요. 이 검토 결과는 참고용 1차 스크리닝이며, \
최종 판단은 자격을 갖춘 안전관리자/검사기관의 확인을 거쳐야 한다는 점을 전제로 합니다.
"""


def _format_checklist(items: list[ChecklistItem]) -> str:
    lines = []
    for item in items:
        lines.append(
            f"- [{item.id}] ({item.category}) {item.title}\n"
            f"  요건: {item.requirement}\n"
            f"  근거 규정: {item.reference or '미기재 - 최신 원문 대조 필요'}"
            + (f"\n  비고: {item.notes}" if item.notes else "")
        )
    return "\n".join(lines)


def estimate_tokens(
    client: anthropic.Anthropic, document_text: str, checklist_items: list[ChecklistItem]
) -> int:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        checklist_block=_format_checklist(checklist_items)
    )
    count = client.messages.count_tokens(
        model=MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": document_text}],
    )
    return count.input_tokens


def run_compliance_check(
    client: anthropic.Anthropic,
    document_text: str,
    checklist_items: list[ChecklistItem],
) -> ComplianceReport:
    if not checklist_items:
        raise ValueError("체크리스트 항목이 비어 있습니다.")

    estimated = estimate_tokens(client, document_text, checklist_items)
    if estimated > MAX_DOCUMENT_TOKENS:
        raise DocumentTooLargeError(
            f"문서가 너무 큽니다(추정 입력 토큰 {estimated:,}개, 한도 {MAX_DOCUMENT_TOKENS:,}개). "
            "문서를 여러 섹션으로 나누어 각각 검토하세요."
        )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        checklist_block=_format_checklist(checklist_items)
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system_prompt,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[
            {
                "role": "user",
                "content": (
                    "다음은 검토 대상 엔지니어링 문서 전문입니다.\n\n"
                    f"{document_text}"
                ),
            }
        ],
        output_format=ComplianceReport,
    )

    report = response.parsed_output

    expected_ids = {item.id for item in checklist_items}
    returned_ids = {r.item_id for r in report.results}
    missing = expected_ids - returned_ids
    if missing:
        raise ValueError(
            "모델이 일부 체크리스트 항목에 대한 결과를 반환하지 않았습니다: "
            f"{sorted(missing)}"
        )

    return report
