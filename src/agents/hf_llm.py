# src/agents/hf_llm.py
from typing import Optional
from huggingface_hub import InferenceClient  # router-based client[web:98]


class SimpleHFLLM:
    """
    Minimal wrapper around Hugging Face InferenceClient.
    Exposes .invoke(prompt: str) -> str.
    """

    def __init__(self, model_id: str, api_token: Optional[str] = None):
        self.client = InferenceClient(
            model=model_id,
            token=api_token,
        )

    def invoke(self, prompt: str) -> str:
        out = self.client.text_generation(
            prompt,
            max_new_tokens=64,
            temperature=0.4,
        )
        return out
