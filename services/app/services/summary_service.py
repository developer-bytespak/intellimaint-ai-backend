
import os
from openai import OpenAI
from app.services.chat_message_service import ChatMessageService


class SummaryService:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @staticmethod
    def persist_messages_and_update_summary(
        *,
        session_id,
        user_text,
        assistant_text,
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        user_id,
        fakeSessionId,
    ):
        if not session_id:
            if not fakeSessionId:
                return
        
                # 1️⃣ Ensure session exists
        if fakeSessionId:
            session_id = fakeSessionId
        try:
            if user_id:
                ChatMessageService.create_chat_session(session_id, user_id, status="active",user_text=user_text)
        except Exception:
            return

        # 1️⃣ Save messages + tokens
        ChatMessageService.save_chat_message(
            session_id, "user", user_text
        )
        ChatMessageService.save_chat_message(
            session_id, "assistant", assistant_text,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        # 2️⃣ Summary only if needed
        messages = ChatMessageService.get_last_messages(session_id, limit=10)
        if len(messages) <= 5:
            return

        older = messages[:-5]
        text = "\n".join(f"{m['role']}: {m['content']}" for m in older)

        prompt = (
            "Summarize this conversation briefly for future context:\n\n"
            f"{text}"
        )

        try:
            resp = SummaryService.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            summary = resp.choices[0].message.content
            if summary:
                ChatMessageService.update_summary(session_id, summary)
        except Exception:
            return


