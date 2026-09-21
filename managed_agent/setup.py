"""ONE-TIME SETUP - run once, save the printed IDs.

Creates the reusable Environment and Agent objects on Anthropic's Managed
Agents platform. Prefer `ant beta:environments create` / `ant beta:agents
create` with the YAML files in this directory if the `ant` CLI is available
(see shared/anthropic-cli.md in the claude-api skill) - this script is the
SDK fallback for when it isn't.

Usage:
    python -m managed_agent.setup
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
import yaml

HERE = Path(__file__).resolve().parent
IDS_FILE = HERE / "agent_ids.json"


def main() -> None:
    if IDS_FILE.exists():
        existing = json.loads(IDS_FILE.read_text(encoding="utf-8"))
        print(f"이미 생성된 설정이 있습니다 ({IDS_FILE}): {existing}")
        print("다시 만들려면 해당 파일을 삭제한 뒤 재실행하세요.")
        return

    client = anthropic.Anthropic()

    env_config = yaml.safe_load((HERE / "cloud.environment.yaml").read_text(encoding="utf-8"))
    environment = client.beta.environments.create(
        name=env_config["name"],
        config=env_config["config"],
    )
    print(f"환경 생성 완료: {environment.id}")

    agent_config = yaml.safe_load((HERE / "kgs_compliance.agent.yaml").read_text(encoding="utf-8"))
    agent = client.beta.agents.create(
        name=agent_config["name"],
        model=agent_config["model"],
        system=agent_config["system"],
        tools=agent_config["tools"],
    )
    print(f"에이전트 생성 완료: {agent.id} (version {agent.version})")

    IDS_FILE.write_text(
        json.dumps(
            {"environment_id": environment.id, "agent_id": agent.id, "agent_version": agent.version},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"ID를 {IDS_FILE}에 저장했습니다.")


if __name__ == "__main__":
    main()
