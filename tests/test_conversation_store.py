from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rednote_matrix.memory.conversation import ConversationStore


class ConversationStoreTest(unittest.TestCase):
    def test_conversation_merges_agent_input_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConversationStore(Path(tmpdir) / "app.sqlite3")
            conversation = store.upsert_conversation(
                title="桌面收纳",
                agent_input={"product_name": "桌面收纳托盘", "selling_points": ["小桌面也能放下"]},
            )
            updated = store.upsert_conversation(
                conversation.id,
                agent_input={"target_audience": "租房小桌面用户", "selling_points": []},
            )
            store.add_message(conversation.id, "user", "标题再像真人一点")
            store.add_message(conversation.id, "assistant", "已调整", {"status": "pass"})

            messages = store.list_messages(conversation.id)

            self.assertEqual(updated.agent_input["product_name"], "桌面收纳托盘")
            self.assertEqual(updated.agent_input["selling_points"], ["小桌面也能放下"])
            self.assertEqual(updated.agent_input["target_audience"], "租房小桌面用户")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[1]["payload"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
