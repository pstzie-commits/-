"""RUNTIME - run for every document you want reviewed.

Uploads the target engineering document (and checklist YAMLs) to a Managed
Agents session, kicks off an Outcome so the harness grades the report until
it meets the rubric, streams progress, then downloads the report from
/mnt/session/outputs/.

Usage:
    python -m managed_agent.run_session --file examples/sample_spec.txt
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
IDS_FILE = HERE / "agent_ids.json"
DEFAULT_CHECKLISTS = [
    REPO_ROOT / "checklists" / "kgs_gas_facility.yaml",
    REPO_ROOT / "checklists" / "osha_kr.yaml",
]

RUBRIC = """# 컴플라이언스 보고서 평가 기준 (초안 - 필요시 기준을 조정하세요)

- `/mnt/session/outputs/`에 Markdown 보고서 파일(`compliance_report.md`)이 존재한다.
- `/workspace/checklists/`의 모든 체크리스트 항목이 ID 기준으로 보고서에 정확히 한 번씩 등장한다
  (누락되거나 중복된 항목이 없다).
- 각 항목에 상태(준수/미준수/확인필요/해당없음 중 하나), 요건, 근거 규정, 문서 근거, 판단 근거가
  포함되어 있다.
- 상태가 미준수 또는 확인필요인 항목에는 구체적인 보완 제안이 포함되어 있다.
- 문서에 명시되지 않은 내용을 근거 없이 준수/미준수로 단정한 항목이 없다(근거 불충분 시
  확인필요로 표시되어 있어야 한다).
- 보고서 서두에 "법적 효력이 없다"는 취지의 안내문과 체크리스트 최신성 확인 필요 안내가
  포함되어 있다.
- 체크리스트나 문서에 없는 내용을 지어내지 않았다.
"""


def load_ids() -> dict:
    agent_id = os.environ.get("AGENT_ID")
    environment_id = os.environ.get("ENVIRONMENT_ID")
    if agent_id and environment_id:
        return {"agent_id": agent_id, "environment_id": environment_id}

    if not IDS_FILE.exists():
        raise SystemExit(
            f"{IDS_FILE}가 없습니다. 먼저 `python -m managed_agent.setup`을 실행하거나 "
            "AGENT_ID / ENVIRONMENT_ID 환경변수를 설정하세요."
        )
    return json.loads(IDS_FILE.read_text(encoding="utf-8"))


def upload_resources(
    client: anthropic.Anthropic, document_path: Path, checklist_paths: list[Path]
) -> list[dict]:
    resources = []
    for path in checklist_paths:
        with open(path, "rb") as f:
            uploaded = client.beta.files.upload(file=f)
        resources.append(
            {"type": "file", "file_id": uploaded.id, "mount_path": f"/workspace/checklists/{path.name}"}
        )

    with open(document_path, "rb") as f:
        uploaded = client.beta.files.upload(file=f)
    resources.append(
        {"type": "file", "file_id": uploaded.id, "mount_path": f"/workspace/document/{document_path.name}"}
    )
    return resources


def run(document_path: Path, checklist_paths: list[Path], output_dir: Path) -> int:
    ids = load_ids()
    client = anthropic.Anthropic()

    environment_id = ids["environment_id"]
    agent_ref: dict = {"type": "agent", "id": ids["agent_id"]}
    if ids.get("agent_version"):
        agent_ref["version"] = ids["agent_version"]

    resources = upload_resources(client, document_path, checklist_paths)

    session = client.beta.sessions.create(
        agent=agent_ref,
        environment_id=environment_id,
        title=f"KGS/OSHA 규제 준수 검토: {document_path.name}",
        resources=resources,
        initial_events=[
            {
                "type": "user.define_outcome",
                "description": (
                    f"{document_path.name} 문서를 /workspace/checklists/의 체크리스트 기준으로 "
                    "검토하고 /mnt/session/outputs/compliance_report.md에 보고서를 작성하세요."
                ),
                "rubric": {"type": "text", "content": RUBRIC},
                "max_iterations": 5,
            }
        ],
    )
    print(f"세션 생성: {session.id}")
    print(f"진행 상황: https://platform.claude.com/workspaces/default/sessions/{session.id}")

    with client.beta.sessions.events.stream(session_id=session.id) as stream:
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="", flush=True)
            elif event.type == "span.outcome_evaluation_end":
                print(f"\n[평가 결과: {event.result}] {event.explanation}\n")
            elif event.type == "session.status_terminated":
                print("\n세션 종료.")
                break
            elif event.type == "session.status_idle":
                if event.stop_reason.type == "requires_action":
                    continue
                print(f"\n세션 idle (stop_reason={event.stop_reason.type}).")
                break

    # SSE emits status_idle slightly before the session's queryable status
    # reflects it; poll briefly before touching output files.
    for _ in range(10):
        current = client.beta.sessions.retrieve(session_id=session.id)
        if current.status != "running":
            break
        time.sleep(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for attempt in range(3):
        files = client.beta.files.list(scope_id=session.id, betas=["managed-agents-2026-04-01"])
        if files.data:
            for f in files.data:
                content = client.beta.files.download(f.id)
                dest = output_dir / f.filename
                content.write_to_file(str(dest))
                print(f"다운로드 완료: {dest}")
                downloaded += 1
            break
        time.sleep(2)

    if downloaded == 0:
        print("경고: 세션 출력 파일을 찾지 못했습니다. Console에서 세션 상태를 확인하세요.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="검토할 문서 경로")
    parser.add_argument(
        "--checklist",
        nargs="+",
        default=None,
        help="체크리스트 YAML 경로 (기본값: checklists/kgs_gas_facility.yaml, checklists/osha_kr.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        default="managed_agent_reports",
        help="다운로드한 보고서를 저장할 로컬 디렉터리",
    )
    args = parser.parse_args()

    checklist_paths = (
        [Path(p) for p in args.checklist] if args.checklist else DEFAULT_CHECKLISTS
    )
    return run(Path(args.file), checklist_paths, Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
