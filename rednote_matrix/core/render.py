from __future__ import annotations

from rednote_matrix.core.models import AgentResult


def _display_tag(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        return ""
    return tag if tag.startswith("#") else f"#{tag}"


def render_user_copy(result: AgentResult) -> str:
    draft = result.draft
    lines: list[str] = []
    lines.append("标题：")
    for index, title in enumerate(draft.titles, 1):
        lines.append(f"{index}. {title}")
    lines.extend(["", "正文：", draft.body.strip()])
    if draft.tags:
        tags = [_display_tag(tag) for tag in draft.tags]
        lines.extend(["", "标签：", " ".join(tag for tag in tags if tag)])

    if result.status != "pass":
        lines.extend(["", "发布前提醒："])
        for risk in result.risk_items:
            lines.append(f"- {risk.text}: {risk.suggestion}")
    return "\n".join(lines).strip()
