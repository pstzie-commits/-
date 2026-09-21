"""검토 결과를 Markdown 보고서로 렌더링한다."""

from __future__ import annotations

import datetime as _dt

from .checklist import ChecklistItem
from .compliance_checker import ComplianceReport, ComplianceStatus

_STATUS_ICON = {
    ComplianceStatus.COMPLIANT: "✅",
    ComplianceStatus.NON_COMPLIANT: "❌",
    ComplianceStatus.NEEDS_REVIEW: "⚠️",
    ComplianceStatus.NOT_APPLICABLE: "➖",
}


def render_markdown_report(
    document_name: str,
    checklist_items: list[ChecklistItem],
    report: ComplianceReport,
) -> str:
    items_by_id = {item.id: item for item in checklist_items}
    results_by_id = {r.item_id: r for r in report.results}

    counts = {status: 0 for status in ComplianceStatus}
    for r in report.results:
        counts[r.status] += 1

    lines = [
        f"# 규제 준수 검토 보고서: {document_name}",
        "",
        f"- 생성 시각: {_dt.datetime.now().isoformat(timespec='seconds')}",
        f"- 검토 항목 수: {len(checklist_items)}",
        (
            f"- 결과 요약: 준수 {counts[ComplianceStatus.COMPLIANT]} · "
            f"미준수 {counts[ComplianceStatus.NON_COMPLIANT]} · "
            f"확인필요 {counts[ComplianceStatus.NEEDS_REVIEW]} · "
            f"해당없음 {counts[ComplianceStatus.NOT_APPLICABLE]}"
        ),
        "",
        "> ⚠️ 본 보고서는 Claude를 이용한 1차 스크리닝 결과이며 법적 효력이 없습니다. "
        "최종 판단은 자격을 갖춘 안전관리자 및 관계 검사기관(한국가스안전공사, 고용노동부 등)의 "
        "확인을 거쳐야 합니다. 체크리스트의 근거 조문/코드 번호는 최신 원문(law.go.kr, "
        "cyber.kgs.or.kr)과 반드시 대조하세요.",
        "",
    ]

    categories: dict[str, list[str]] = {}
    for item_id, item in items_by_id.items():
        categories.setdefault(item.category, []).append(item_id)

    for category, item_ids in categories.items():
        lines.append(f"## {category}")
        lines.append("")
        for item_id in item_ids:
            item = items_by_id[item_id]
            result = results_by_id.get(item_id)
            if result is None:
                continue
            icon = _STATUS_ICON[result.status]
            lines.append(f"### {icon} [{item.id}] {item.title} — {result.status.value}")
            lines.append("")
            lines.append(f"- **요건**: {item.requirement}")
            lines.append(f"- **근거 규정**: {item.reference or '미기재'}")
            if result.evidence:
                lines.append(f"- **문서 근거**: {result.evidence}")
            lines.append(f"- **판단 근거**: {result.reasoning}")
            if result.recommendation:
                lines.append(f"- **보완 제안**: {result.recommendation}")
            lines.append("")

    return "\n".join(lines)
