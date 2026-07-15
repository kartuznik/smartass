"""Manual live-check script for provider/model configuration."""

from __future__ import annotations

import time

from dotenv import load_dotenv
from openai import APIStatusError

from agents.llm_config import LLMConfig
from agents.simple_agent import run_simple_agent


def main() -> None:
    load_dotenv()

    provider = LLMConfig.get_provider()
    model_name = LLMConfig.get_model_name()
    print(f"Provider: {provider}")
    print(f"Model: {model_name}")

    query = "Сколько будет 25 * 4?"
    started_at = time.perf_counter()

    try:
        # Validate credentials and API reachability before agent execution.
        model = LLMConfig.create_chat_model(temperature=0)
        _ = model.invoke("Reply with exactly one token: ok")

        # Force math branch to verify deterministic math path end-to-end.
        result = run_simple_agent(query, classifier_fn=lambda _: "math")
        elapsed = time.perf_counter() - started_at

        print(f"Execution time: {elapsed:.2f}s")
        print(f"Result: {result['tool_result']}")
    except ValueError as exc:
        print("Configuration error:", exc)
        print("Hint: set OPENAI_API_KEY in ai-agents-lab/.env")
    except APIStatusError as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code == 402:
            print("Provider returned 402 Insufficient Balance. Top up your account.")
        else:
            print("API status error:", exc)
    except Exception as exc:
        print("Unexpected error while running live check:", exc)


if __name__ == "__main__":
    main()
