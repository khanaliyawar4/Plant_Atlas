from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt, wait_exponential,
    before_sleep_log,
)

log = logging.getLogger(__name__)

@dataclass
class LLMReply:
    content: str
    reasoning: str | None
    usage_prompt: int | None
    usage_completion: int | None
    finish_reason: str | None

class LLMClient:

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout_s: float, max_retries: int):
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)
        self.model = model
        self.max_retries = max_retries

    def chat(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
        enable_thinking: bool = False,
        response_format_json: bool = True,
        guided_json: dict | None = None,
    ) -> LLMReply:
        retryer = retry(
            retry=retry_if_exception_type((
                APIConnectionError, APITimeoutError, RateLimitError, APIError,
            )),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=2.0, min=2.0, max=60.0),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )

        @retryer
        def _do_call():
            extra_body: dict[str, Any] = {
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
            }
            if guided_json is not None:
                extra_body["guided_json"] = guided_json

            kwargs: dict[str, Any] = dict(
                model=self.model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
            if response_format_json and guided_json is None:
                kwargs["response_format"] = {"type": "json_object"}

            return self.client.chat.completions.create(**kwargs)

        resp = _do_call()
        choice = resp.choices[0]
        msg = choice.message
        reasoning = getattr(msg, "reasoning_content", None)
        content = msg.content or ""

        usage = resp.usage
        return LLMReply(
            content=content,
            reasoning=reasoning,
            usage_prompt=getattr(usage, "prompt_tokens", None) if usage else None,
            usage_completion=getattr(usage, "completion_tokens", None) if usage else None,
            finish_reason=choice.finish_reason,
        )

    def ping(self) -> bool:
        try:
            models = self.client.models.list()
            ids = [m.id for m in models.data]
            log.info("server up, models available: %s", ids)
            return any(self.model == mid for mid in ids)
        except Exception as exc:
            log.error("server ping failed: %s", exc)
            return False
