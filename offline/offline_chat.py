from ollama import chat

from core.personality_manager import get_system_prompt


class OfflineChat:

    def ask(self, prompt: str):

        messages = [
            {
                "role": "system",
                "content": get_system_prompt(),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        response = chat(
            model="qwen3:8b",
            messages=messages,
        )

        return response["message"]["content"]


offline_chat = OfflineChat()