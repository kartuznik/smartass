"""Message handlers for Telegram + LangGraph integration."""

from __future__ import annotations

import logging
from typing import cast

from aiogram import Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from agents.multi_agent import (
    MultiAgentState,
    build_initial_multi_agent_state,
    build_multi_agent_graph,
)

logger = logging.getLogger(__name__)
router = Router()
multi_agent_graph = build_multi_agent_graph()


def _format_result_markdown(result: MultiAgentState) -> str:
    topic = result["topic"]
    research_data = result["research_data"]
    draft = result["draft"]
    return (
        "## ✅ Готово\n"
        f"**Тема:** {topic}\n\n"
        "### 🔬 Research\n"
        f"{research_data}\n\n"
        "### 📝 Draft\n"
        f"{draft}"
    )


async def _run_research_flow(message: Message, topic: str) -> None:
    if not topic.strip():
        await message.answer(
            "Укажи тему после команды.\nПример: `/research агенты в поддержке клиентов`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    user_id = message.from_user.id if message.from_user else 0
    initial_state = build_initial_multi_agent_state(topic=topic.strip(), user_id=user_id)

    progress_message = await message.answer("🔍 Анализирую тему...")
    await message.answer_chat_action(action=ChatAction.TYPING)

    try:
        result = cast(
            MultiAgentState,
            await multi_agent_graph.ainvoke(initial_state),
        )
        await progress_message.edit_text(
            _format_result_markdown(result),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("Multi-agent graph execution failed for user_id=%s", user_id)
        await progress_message.edit_text("Произошла ошибка, попробуйте позже.")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Я multi-agent ассистент.\n"
        "Отправь `/research <тема>`, и я запущу цепочку Researcher -> Writer -> Reviewer.",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("research"))
async def research_command_handler(message: Message, command: CommandObject) -> None:
    topic = (command.args or "").strip()
    await _run_research_flow(message, topic)


@router.message(lambda message: bool(message.text and not message.text.startswith("/")))
async def plain_text_handler(message: Message) -> None:
    await _run_research_flow(message, message.text or "")
