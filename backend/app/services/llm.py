"""LLM service — GPT-5.4 for decisions, GPT-5.4 mini (reasoning=high) for workhorse tasks."""

from __future__ import annotations

import json
import logging
from typing import Any, Type, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# -----------------------------------------------
# Model instances
# -----------------------------------------------

# Frontier model — decision-making (market analysis, signal generation)
decision_llm = ChatOpenAI(
    model="gpt-5.4",
    api_key=settings.openai_api_key,
    temperature=0.2,
    max_tokens=4096,
    model_kwargs={},
)

# Workhorse model — high-volume tasks (news summarisation, data prep)
workhorse_llm = ChatOpenAI(
    model="gpt-5.4-mini",
    api_key=settings.openai_api_key,
    temperature=0.1,
    max_tokens=4096,
    model_kwargs={"reasoning": {"effort": "high"}},
)


# -----------------------------------------------
# Helpers
# -----------------------------------------------

async def llm_structured_output(
    llm: ChatOpenAI,
    schema: Type[T],
    system_prompt: str,
    user_prompt: str,
) -> T:
    """Call an LLM and parse its response into a Pydantic schema."""
    structured = llm.with_structured_output(schema)
    result = await structured.ainvoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])
    return result  # type: ignore[return-value]


async def llm_text(
    llm: ChatOpenAI,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Call an LLM and return plain text."""
    response = await llm.ainvoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])
    return response.content  # type: ignore[return-value]


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Rough cost estimation in USD."""
    rates = {
        "gpt-5.4":      {"input": 2.50 / 1_000_000, "output": 15.00 / 1_000_000},
        "gpt-5.4-mini": {"input": 0.75 / 1_000_000, "output": 4.50 / 1_000_000},
    }
    r = rates.get(model, rates["gpt-5.4-mini"])
    return prompt_tokens * r["input"] + completion_tokens * r["output"]
