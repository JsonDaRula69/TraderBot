from __future__ import annotations

from traderbot.deploy.wizard_contracts import (
    DeployResult,
    StepStatus,
    WizardRequest,
    WizardStepResult,
)
from traderbot.deploy.wizard_state import DeploymentPreflight


def build_deploy_result(
    request: WizardRequest,
    steps: list[WizardStepResult],
    plan: DeploymentPreflight | None,
    *,
    input_valid: bool = True,
) -> DeployResult:
    completed = tuple(step.step for step in steps if step.status is StepStatus.COMPLETED)
    remaining = tuple(step.step for step in steps if step.status is not StepStatus.COMPLETED)
    full_workflow = len(steps) == 8 and not remaining
    return DeployResult(
        success=input_valid and not remaining,
        input_valid=input_valid,
        categories=request.categories,
        steps=tuple(steps),
        completed_steps=completed,
        deployment_complete=full_workflow,
        remaining_steps=remaining or tuple(range(len(steps) + 1, 9)),
        required_new_agent_paths=(
            {
                agent.category: agent.workspace
                for agent in plan.agents
                if not agent.existed and agent.category is not None
            }
            if plan is not None
            else dict(request.category_workspaces)
        ),
        approvals=request.approvals,
        heartbeat_every=request.heartbeat_every,
    )


__all__ = ["build_deploy_result"]
