"""CLI: 플랜트·가스 인프라 엔지니어링 문서의 KGS/산업안전보건법 준수 여부 검증.

사용 예:
    python -m kgs_compliance_agent --file spec.pdf --checklist kgs osha \
        --output report.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

from .checklist import load_checklists
from .compliance_checker import DocumentTooLargeError, run_compliance_check
from .document_loader import load_document
from .report import render_markdown_report

CHECKLIST_DIR = Path(__file__).resolve().parent.parent / "checklists"
CHECKLIST_ALIASES = {
    "kgs": CHECKLIST_DIR / "kgs_gas_facility.yaml",
    "osha": CHECKLIST_DIR / "osha_kr.yaml",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="엔지니어링 문서의 KGS 코드 / 산업안전보건법 준수 여부를 검증합니다."
    )
    parser.add_argument("--file", required=True, help="검토할 문서 경로 (.pdf/.docx/.txt/.md)")
    parser.add_argument(
        "--checklist",
        nargs="+",
        default=["kgs", "osha"],
        help=(
            "적용할 체크리스트. 별칭(kgs, osha) 또는 YAML 파일 경로를 하나 이상 지정 "
            "(기본값: kgs osha)"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Markdown 보고서 저장 경로 (미지정 시 표준출력)",
    )
    return parser


def resolve_checklist_paths(names: list[str]) -> list[Path]:
    paths = []
    for name in names:
        if name in CHECKLIST_ALIASES:
            paths.append(CHECKLIST_ALIASES[name])
        else:
            p = Path(name)
            if not p.exists():
                raise FileNotFoundError(f"체크리스트 파일을 찾을 수 없습니다: {name}")
            paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        checklist_paths = resolve_checklist_paths(args.checklist)
        checklist_items = load_checklists(checklist_paths)
        document = load_document(args.file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    if not document.text.strip():
        print("오류: 문서에서 추출된 텍스트가 없습니다 (스캔 이미지 PDF일 수 있습니다).",
              file=sys.stderr)
        return 1

    client = anthropic.Anthropic()

    try:
        report = run_compliance_check(client, document.text, checklist_items)
    except DocumentTooLargeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as exc:
        print(f"Claude API 오류: {exc.message}", file=sys.stderr)
        return 1

    markdown = render_markdown_report(document.path.name, checklist_items, report)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"보고서 저장 완료: {args.output}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
