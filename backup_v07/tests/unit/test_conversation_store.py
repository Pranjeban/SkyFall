from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory.conversation_store import ConversationStore


class ConversationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "skyfall-test.db"
        self.store = ConversationStore(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_conversation_and_active_state(self) -> None:
        conversation = self.store.create_conversation()
        self.store.set_active_conversation(conversation.id)

        self.assertEqual(self.store.get_active_conversation_id(), conversation.id)
        self.assertEqual(conversation.title, "New conversation")
        self.assertTrue(conversation.copilot_session_id.startswith("skyfall-"))

    def test_user_message_sets_title_and_is_retrievable(self) -> None:
        conversation = self.store.create_conversation()
        message_id = self.store.add_message(
            conversation.id,
            "user",
            "Fetch all Function Apps from Azure",
        )

        refreshed = self.store.get_conversation(conversation.id)
        messages = self.store.get_messages(conversation.id)

        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.title, "Fetch all Function Apps from Azure")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, message_id)
        self.assertEqual(messages[0].role, "user")

    def test_assistant_message_and_session_initialization(self) -> None:
        conversation = self.store.create_conversation()
        self.store.add_message(conversation.id, "user", "Hello Skyfall")
        self.store.add_message(conversation.id, "assistant", "Hello. How can I help?")
        self.store.set_sdk_session_initialized(conversation.id, True)

        refreshed = self.store.get_conversation(conversation.id)

        self.assertEqual(refreshed.message_count, 2)
        self.assertTrue(refreshed.sdk_session_initialized)
        self.assertEqual(self.store.get_messages(conversation.id)[1].role, "assistant")

    def test_new_conversations_have_unique_sdk_session_ids(self) -> None:
        first = self.store.create_conversation()
        second = self.store.create_conversation()
        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.copilot_session_id, second.copilot_session_id)

    def test_get_or_create_active_conversation(self) -> None:
        first = self.store.get_or_create_active_conversation()
        second = self.store.get_or_create_active_conversation()
        self.assertEqual(first.id, second.id)

    def test_delete_conversation_removes_local_messages(self) -> None:
        conversation = self.store.create_conversation()
        self.store.add_message(conversation.id, "user", "This will be removed locally")
        self.store.set_active_conversation(conversation.id)

        self.store.delete_conversation(conversation.id)

        self.assertIsNone(self.store.get_conversation(conversation.id))
        self.assertEqual(self.store.get_messages(conversation.id), [])
        self.assertIsNone(self.store.get_active_conversation_id())

    def test_invalid_role_is_rejected(self) -> None:
        conversation = self.store.create_conversation()
        with self.assertRaises(ValueError):
            self.store.add_message(conversation.id, "tool", "not a user or assistant message")


if __name__ == "__main__":
    unittest.main()
