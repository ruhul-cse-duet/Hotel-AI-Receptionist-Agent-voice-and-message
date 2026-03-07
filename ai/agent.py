"""
Hotel AI Receptionist Agent
Multi-turn agentic loop: LLM → Tools → LLM → Response
Maintains conversation context across voice and WhatsApp channels.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from ai.llm_provider import get_llm_provider
from ai.tools import HOTEL_TOOLS, get_tool_executor
from ai.prompts import get_system_prompt, VOICE_BREVITY_REMINDER
from database.mongodb import get_db
from database.models import (
    Conversation, ConversationMessage, ConversationContext,
    MessageRole, ConversationChannel, ConversationStatus
)
from config import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5  # prevent infinite loops


class HotelAgent:
    """
    Agentic AI Hotel Receptionist
    - Maintains per-session conversation history
    - Runs tool-use loop automatically
    - Works for both voice calls and WhatsApp
    """

    def __init__(self, channel: ConversationChannel):
        self.channel = channel
        # Lazily initialize LLM provider to avoid heavy imports during test collection
        self._llm = None
        self.executor = get_tool_executor()
        self.is_voice = (channel == ConversationChannel.VOICE)

    @property
    def llm(self):
        """Lazy LLM provider accessor"""
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        phone: str,
    ) -> Tuple[str, List[Dict]]:
        """
        Process one user turn and return (assistant_response, tool_calls_used).
        Handles the full agentic loop internally.
        """
        db = get_db()

        # Load conversation
        conv_doc = await db.conversations.find_one({"session_id": session_id})
        if not conv_doc:
            logger.warning(f"Session {session_id} not found, creating new")
            conv_doc = await self._create_conversation(session_id, phone)

        # Build message history for LLM
        messages = self._build_messages(conv_doc, user_message)

        # Agentic tool-use loop
        all_tool_calls = []
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            response = await self.llm.chat_completion(
                messages=messages,
                tools=HOTEL_TOOLS,
                tool_choice="auto",
                temperature=0.7,
                max_tokens=512 if self.is_voice else 1024,
            )

            assistant_content = response["content"]
            tool_calls = response.get("tool_calls")

            # No tool calls → final response
            if not tool_calls:
                break

            # Execute tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            })

            tool_results = []
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                logger.info(f"🔧 Tool: {fn_name}({args})")
                result = await self.executor.execute(fn_name, args)
                logger.info(f"🔧 Result: {result[:200]}")

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
                all_tool_calls.append({"name": fn_name, "args": args, "result": result})

            messages.extend(tool_results)

        # For voice: make response natural and concise
        if self.is_voice and len(assistant_content) > 300:
            assistant_content = await self._shorten_for_voice(assistant_content, messages)

        # Save conversation turn to MongoDB
        await self._save_turn(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_content,
            tool_calls=all_tool_calls,
        )

        # Update context from latest tool results
        await self._update_context(session_id, all_tool_calls)

        return assistant_content, all_tool_calls

    def _build_messages(self, conv_doc: Dict, new_user_message: str) -> List[Dict]:
        """Construct full message array for LLM"""
        system = get_system_prompt(
            channel=self.channel.value,
            hotel_name=settings.HOTEL_NAME,
            hotel_address=settings.HOTEL_ADDRESS,
            checkin_time=settings.HOTEL_CHECKIN_TIME,
            checkout_time=settings.HOTEL_CHECKOUT_TIME,
            currency=settings.HOTEL_CURRENCY,
        )

        messages = [{"role": "system", "content": system}]

        # Add conversation history (last 20 messages to stay in context)
        history = conv_doc.get("messages", [])[-20:]
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

        # Add voice brevity reminder every few turns for voice channel
        if self.is_voice and len(history) % 4 == 0:
            messages.append({"role": "system", "content": VOICE_BREVITY_REMINDER})

        messages.append({"role": "user", "content": new_user_message})
        return messages

    async def _shorten_for_voice(self, text: str, messages: List[Dict]) -> str:
        """Ask LLM to shorten response for voice"""
        shorten_prompt = f"""
Shorten this for spoken voice (max 2-3 sentences, no lists, natural speech):
"{text}"
Return ONLY the shortened version, nothing else.
"""
        resp = await self.llm.chat_completion(
            messages=[{"role": "user", "content": shorten_prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return resp["content"] or text

    async def _create_conversation(self, session_id: str, phone: str) -> Dict:
        db = get_db()
        conv = Conversation(
            session_id=session_id,
            phone=phone,
            channel=self.channel,
            context=ConversationContext(guest_phone=phone),
        )
        doc = conv.model_dump(by_alias=True)
        await db.conversations.insert_one(doc)
        return doc

    async def _save_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        tool_calls: List[Dict],
    ):
        db = get_db()
        now = datetime.utcnow()

        user_msg = ConversationMessage(
            role=MessageRole.USER,
            content=user_message,
            timestamp=now,
        )
        assistant_msg = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=assistant_message,
            timestamp=now,
            tool_calls=tool_calls if tool_calls else None,
        )

        await db.conversations.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "$each": [user_msg.model_dump(), assistant_msg.model_dump()]
                    }
                },
                "$set": {"updated_at": now},
            }
        )

    async def _update_context(self, session_id: str, tool_calls: List[Dict]):
        """Extract booking context from tool results and save to conversation"""
        db = get_db()
        context_updates = {}

        for tc in tool_calls:
            if tc["name"] == "create_booking":
                try:
                    result = json.loads(tc["result"])
                    if result.get("success"):
                        context_updates["context.booking_id"] = result.get("booking_id")
                        context_updates["context.conversation_stage"] = "booked"
                        # Track booking in conversation
                        await db.conversations.update_one(
                            {"session_id": session_id},
                            {"$addToSet": {"booking_ids": result["booking_id"]}}
                        )
                except Exception:
                    pass

            elif tc["name"] == "check_room_availability":
                try:
                    args = tc["args"]
                    context_updates["context.check_in_date"] = args.get("check_in_date")
                    context_updates["context.check_out_date"] = args.get("check_out_date")
                    context_updates["context.conversation_stage"] = "collecting_info"
                except Exception:
                    pass

        if context_updates:
            await db.conversations.update_one(
                {"session_id": session_id},
                {"$set": context_updates}
            )

    async def end_conversation(self, session_id: str):
        """Mark conversation as completed"""
        db = get_db()
        await db.conversations.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": ConversationStatus.COMPLETED,
                    "ended_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            }
        )


def get_voice_agent() -> HotelAgent:
    return HotelAgent(channel=ConversationChannel.VOICE)


def get_whatsapp_agent() -> HotelAgent:
    return HotelAgent(channel=ConversationChannel.WHATSAPP)
