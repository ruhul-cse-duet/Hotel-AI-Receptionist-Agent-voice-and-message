"""
Hotel AI Receptionist Agent
Multi-turn agentic loop: LLM → Tools → LLM → Response
Maintains conversation context across voice and WhatsApp channels.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any

from ai.llm_provider import get_llm_provider
from ai.tools import HOTEL_TOOLS, get_tool_executor
from ai.prompts import get_system_prompt, VOICE_BREVITY_REMINDER
from database.mongodb import get_db
from database.models import (
    Conversation, ConversationMessage, ConversationContext,
    MessageRole, ConversationChannel, ConversationStatus
)
from database.tenancy import get_hotel_profile

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

        # Handle manager contact requests deterministically
        if self._is_manager_contact_request(user_message):
            manager_reply = self._build_manager_contact_reply()
            await self._save_turn(
                session_id=session_id,
                user_message=user_message,
                assistant_message=manager_reply,
                tool_calls=[],
            )
            return manager_reply, []

        # Pricing requests need dates; ask instead of guessing
        if self._is_pricing_request(user_message) and not self._contains_date(user_message):
            prompt = (
                "Sir, to share accurate pricing I need your check-in and check-out dates. "
                "Which dates are you considering, and which room type do you prefer?"
            )
            await self._save_turn(
                session_id=session_id,
                user_message=user_message,
                assistant_message=prompt,
                tool_calls=[],
            )
            return prompt, []

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
                temperature=0.6,
                max_tokens=512 if self.is_voice else 1024,
            )

            assistant_content = response["content"]
            tool_calls = response.get("tool_calls")

            if not tool_calls:
                fallback_calls, cleaned = self._extract_fallback_tool_calls(assistant_content)
                if fallback_calls:
                    tool_calls = fallback_calls
                    assistant_content = cleaned

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

        # Enforce strict response style (sir + no forbidden words)
        assistant_content = self._enforce_response_style(assistant_content)

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
        hotel = get_hotel_profile()
        system = get_system_prompt(
            channel=self.channel.value,
            hotel_name=hotel["name"],
            receptionist_name=hotel["receptionist_name"],
            hotel_address=hotel["address"],
            checkin_time=hotel["checkin_time"],
            checkout_time=hotel["checkout_time"],
            currency=hotel["currency"],
            hotel_phone=hotel["phone"],
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

    def _is_manager_contact_request(self, text: str) -> bool:
        if not text:
            return False
        norm = text.lower()
        keywords = [
            "manager",
            "duty manager",
            "supervisor",
            "gm",
            "general manager",
            "management",
            "owner",
        ]
        bangla = [
            "ম্যানেজার",
            "ম্যানেজার নম্বর",
            "ম্যানেজারের নম্বর",
            "ম্যানেজার নাম্বার",
            "ম্যানেজার নাম্বারটা",
            "ম্যানেজার ফোন",
            "ম্যানেজার মোবাইল",
        ]
        if any(k in norm for k in keywords):
            if "number" in norm or "contact" in norm or "phone" in norm or "mobile" in norm:
                return True
        if any(k in norm for k in bangla):
            return True
        return False

    def _is_pricing_request(self, text: str) -> bool:
        if not text:
            return False
        norm = text.lower()
        keywords = [
            "price",
            "pricing",
            "rate",
            "cost",
            "tariff",
            "booking price",
            "room price",
            "per night",
            "per-night",
            "how much",
        ]
        bangla = [
            "প্রাইস",
            "দাম",
            "রেট",
            "ভাড়া",
            "কত",
            "খরচ",
        ]
        return any(k in norm for k in keywords) or any(k in norm for k in bangla)

    def _contains_date(self, text: str) -> bool:
        if not text:
            return False
        # Simple checks for YYYY-MM-DD or month name mention
        if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text):
            return True
        if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", text, re.IGNORECASE):
            return True
        return False

    def _build_manager_contact_reply(self) -> str:
        profile = get_hotel_profile()
        phone = profile.get("phone") or ""
        if phone:
            return f"Sir, you can reach our manager at {phone}. Would you like me to help with anything else?"
        return "Sir, I can connect you to our manager from the front desk. Please share the best number to reach you."

    def _enforce_response_style(self, text: str) -> str:
        if not text:
            return "Sir, how may I assist you today?"
        cleaned = text
        cleaned = re.sub(r"\bA\.I\.\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bAI\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bartificial intelligence\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if not re.search(r"\bsir\b", cleaned, flags=re.IGNORECASE):
            cleaned = f"Sir, {cleaned}"
        return cleaned

    def _extract_fallback_tool_calls(self, content: str) -> Tuple[Optional[List[Dict]], str]:
        if not content:
            return None, content
        pattern = re.compile(
            r"<\|tool_call_start\|>\s*(?:\[(?P<call>.*?)\]|(?P<call2>.*?))\s*<\|tool_call_end\|>",
            re.DOTALL,
        )
        match = pattern.search(content)
        if not match:
            return None, content

        call_text = (match.group("call") or match.group("call2") or "").strip()
        if not call_text:
            cleaned = pattern.sub("", content).strip()
            return None, cleaned

        fn_match = re.match(r"([a-zA-Z0-9_]+)\((.*)\)", call_text, re.DOTALL)
        if not fn_match:
            cleaned = pattern.sub("", content).strip()
            return None, cleaned

        fn_name = fn_match.group(1)
        args_str = fn_match.group(2).strip()
        args = self._parse_tool_args(args_str)

        tool_calls = [{
            "id": f"fallback_{fn_name}",
            "function": {"name": fn_name, "arguments": json.dumps(args)},
            "type": "function",
        }]

        cleaned = pattern.sub("", content)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return tool_calls, cleaned

    def _parse_tool_args(self, args_str: str) -> Dict:
        if not args_str:
            return {}

        args: Dict[str, Any] = {}
        parts = []
        current = ""
        in_quotes = False
        quote_char = ""

        for ch in args_str:
            if ch in ("\"", "'"):
                if in_quotes and ch == quote_char:
                    in_quotes = False
                elif not in_quotes:
                    in_quotes = True
                    quote_char = ch
            if ch == "," and not in_quotes:
                parts.append(current)
                current = ""
                continue
            current += ch
        if current:
            parts.append(current)

        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"' ")
            if value.lower() in ("true", "false"):
                args[key] = value.lower() == "true"
            else:
                try:
                    if "." in value:
                        args[key] = float(value)
                    else:
                        args[key] = int(value)
                except ValueError:
                    args[key] = value
        return args

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
