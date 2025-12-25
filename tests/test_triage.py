import pytest

from debate.models import Conversation, Task
from debate.triage import Complexity, TaskTriager


@pytest.mark.asyncio
async def test_triage_trivial_keyword() -> None:
    triager = TaskTriager()
    task = Task(id="task", slug="fix-typo", title="Fix typo in README", status="scoping")
    conversations = [
        Conversation(
            id="conv",
            task_id="task",
            role="human",
            content="Fix typo in README.md",
            phase="scoping",
        )
    ]

    result = await triager.classify(None, task, conversations)  # type: ignore[arg-type]
    assert result.complexity == Complexity.TRIVIAL
