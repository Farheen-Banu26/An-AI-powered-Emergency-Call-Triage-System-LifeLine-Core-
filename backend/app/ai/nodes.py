"""
LangGraph nodes for the emergency dispatch pipeline.

Pipeline:
    caller message → ANALYST → COMPLETENESS_CHECKER → SUMMARIZER
                         ↓ (if missing info)              ↓ (if enough info)
                    QUESTION_GENERATOR              SERVICE_ROUTER → GUIDANCE
                         ↓                               ↓
                        END                             END

6 Nodes:
  1. analyst_node        — Extracts structured data from caller's words
  2. completeness_node   — Decides: ask more questions vs. dispatch
  3. question_node       — Generates ONE follow-up question for the caller
  4. router_node         — Routes to correct emergency service + SOPs
  5. summarizer_node     — Produces dispatcher-ready briefing
  6. guidance_node       — Generates real-time safety instructions for the caller
"""

import json
import logging
import re
import traceback

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.prompts import (
    ANALYST_PROMPT,
    GUIDANCE_PROMPT,
    QUESTION_GENERATOR_PROMPT,
    ROUTER_PROMPT,
    ROUTER_RAG_PROMPT,
    SOP_DATABASE,
    SUMMARIZER_PROMPT,
)
from app.ai.state import IncidentState
from app.config import get_settings
from app.services.fake_call_service import FakeCallDetector
from app.services.rag_service import retrieve_context

logger = logging.getLogger(__name__)


# ── Shared Helpers ────────────────────────────────────────────────

def _get_llm(temperature: float = 0.3):
    """
    Create the LLM client based on LLM_PROVIDER env setting.
    Returns a ChatOllama or ChatGroq instance (both share the langchain interface).
    """
    settings = get_settings()

    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=temperature,
        )
    else:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            num_gpu=settings.ollama_num_gpu,
        )


def _clean_llm_text(text: str) -> str:
    """Remove <think>...</think> blocks and strip whitespace."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response — handles fences, thinking tags, etc."""
    text = _clean_llm_text(text)

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Markdown code fence
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Any JSON object
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    return {}


# ── NODE 1: ANALYST ──────────────────────────────────────────────

def analyst_node(state: IncidentState) -> dict:
    """
    Extracts structured emergency data from the caller's message.
    Merges with existing state — never overwrites with null.
    """
    llm = _get_llm(temperature=0.2)

    # Build context: tell the LLM what we already know
    existing_context = (
        f"\n\n## Already Extracted (from previous turns)\n"
        f"- emergency_type: {state.get('emergency_type', 'unknown')}\n"
        f"- location: {state.get('location', 'unknown')}\n"
        f"- details: {state.get('details', 'unknown')}\n"
        f"- priority: {state.get('priority', 'unknown')}\n"
        f"- caller_name: {state.get('caller_name', 'unknown')}\n"
        f"- caller_age: {state.get('caller_age', 'unknown')}\n"
        f"- caller_phone: {state.get('caller_phone', 'unknown')}\n"
        f"- casualties: {state.get('casualties', 'unknown')}\n"
        f"\nUpdate any field with NEW information from the latest message. "
        f"Keep existing values if the caller didn't mention them again."
    )

    messages = [
        SystemMessage(content=ANALYST_PROMPT + existing_context)
    ] + list(state["messages"])

    response = llm.invoke(messages)
    parsed = _parse_json(response.content)

    # Build update — only overwrite non-null fields from LLM
    update: dict = {"turn_count": state.get("turn_count", 0) + 1}

    field_map = {
        "emergency_type": str,
        "location": str,
        "details": str,
        "caller_name": str,
        "caller_phone": str,
        "estimated_arrival": str,
    }

    for field, _ in field_map.items():
        val = parsed.get(field)
        if val and val != "null" and val != "unknown":
            # Merge details with existing if both are present
            if field == "details" and state.get("details"):
                existing = state["details"]
                if val.lower() not in existing.lower():
                    update[field] = f"{existing}. {val}"
                else:
                    update[field] = existing
            else:
                update[field] = val

    # Numeric fields
    if parsed.get("priority") is not None and isinstance(parsed.get("priority"), (int, float)):
        update["priority"] = max(1, min(5, int(parsed["priority"])))

    if parsed.get("casualties") is not None and isinstance(parsed.get("casualties"), (int, float)):
        update["casualties"] = int(parsed["casualties"])

    if parsed.get("caller_age") is not None and isinstance(parsed.get("caller_age"), (int, float)):
        update["caller_age"] = int(parsed["caller_age"])

    # Missing info
    update["missing_info"] = parsed.get("missing_info", [])

    # LLM's fake call score (analyst's judgment)
    llm_fake = parsed.get("fake_score")
    if llm_fake is not None:
        try:
            update["_llm_fake_score"] = float(llm_fake)
        except (ValueError, TypeError):
            pass
    
    logger.info(f"Analyst extracted data: {parsed}")
    logger.info(f"State update generated: {update}")

    return update


# ── Per-session fake call detectors (keyed by a hash of the messages)
# In a real production system you'd store these in the session store.
# Here we use a module-level dict keyed by id(state["messages"]) which
# resets each graph invocation anyway — so we instantiate fresh per call
# and rely on the session-level detector in stream.py / calls.py.

# ── NODE 1b: FAKE CALL DETECTOR ─────────────────────────────────

def fake_call_node(state: IncidentState) -> dict:
    """
    Runs multi-signal fake call detection on the latest turn.
    Combines keyword matching, behavioral analysis, and the LLM's own
    fake_score from the analyst node.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    # Get the latest caller message
    latest_text = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_text = msg.content
            break

    if not latest_text:
        return {}

    # Create a detector instance — for cross-turn analysis, the stream/calls
    # route maintains a persistent detector per session and feeds it.
    # Here we run a single-turn check that also incorporates the LLM score.
    detector = FakeCallDetector()

    # Feed all prior turns for behavioral analysis
    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content != latest_text:
            detector.evaluate_turn(
                msg.content,
                emergency_type=state.get("emergency_type"),
                location=state.get("location"),
                details=state.get("details"),
                turn_count=0,
                llm_fake_score=None,
            )

    # Now evaluate the latest turn with the LLM fake score
    llm_fake = state.get("_llm_fake_score")  # set by analyst_node
    result = detector.evaluate_turn(
        latest_text,
        emergency_type=state.get("emergency_type"),
        location=state.get("location"),
        details=state.get("details"),
        turn_count=state.get("turn_count", 0),
        llm_fake_score=llm_fake,
    )

    return {
        "fake_probability": result["fake_probability"],
        "fake_label": result["fake_label"],
        "fake_signals": result["fake_signals"],
    }


# ── NODE 2: COMPLETENESS CHECKER ────────────────────────────────

def completeness_node(state: IncidentState) -> dict:
    """
    Checks if we have enough critical info to dispatch.

    Required for dispatch:
      - emergency_type (MUST have)
      - location (MUST have)
      - priority (MUST have)
      - At least MIN_TURNS conversation turns (prevents instant dispatch)
      - Call must NOT be flagged as LIKELY_FAKE

    Nice to have (don't block dispatch):
      - details, caller_name, casualties
    """
    MIN_TURNS = 3  # Always gather at least 3 turns before dispatching

    has_type = state.get("emergency_type") is not None
    has_location = state.get("location") is not None
    has_priority = state.get("priority") is not None
    turn_count = state.get("turn_count", 0)

    # 1. Basic requirements (Type, Location, Priority)
    if not (has_type and has_location and has_priority):
        return {"status": "gathering_info"}

    # 2. Minimum conversation turns — always ask follow-up questions first
    #    This prevents premature dispatch when location is auto-appended
    #    by the frontend on the very first message.
    if turn_count < MIN_TURNS:
        return {"status": "gathering_info"}

    # 3. FAKE CALL BLOCK — never dispatch if call is flagged as likely fake
    fake_label = state.get("fake_label", "GENUINE")
    if fake_label == "LIKELY_FAKE":
        logger.warning("Dispatch BLOCKED — call flagged as LIKELY_FAKE")
        return {"status": "gathering_info"}

    # 4. Critical Contextual Requirements (Casualties for high-stakes events)
    current_type = (state.get("emergency_type") or "").strip()

    # All incident types involving potential bodily harm need casualty info
    critical_types = ["Fire", "Medical", "Police", "Traffic", "Natural Disaster"]

    if current_type in critical_types:
        if state.get("casualties") is None:
            return {"status": "gathering_info"}

    # 5. Caller name is nice to have for callback — ask if still early
    if state.get("caller_name") is None and turn_count < 5:
        return {"status": "gathering_info"}

    # 6. Ready to dispatch — clear the follow-up question so stale ones aren't re-sent
    return {"status": "ready_to_dispatch", "current_question": None}


# ── NODE 3: QUESTION GENERATOR ──────────────────────────────────

def question_node(state: IncidentState) -> dict:
    """
    Generates ONE focused follow-up question for the caller.
    The question is sent to the TTS route for voice conversion.
    """
    llm = _get_llm(temperature=0.4)

    prompt = QUESTION_GENERATOR_PROMPT.format(
        emergency_type=state.get("emergency_type", "Unknown"),
        location=state.get("location", "Unknown"),
        details=state.get("details", "Unknown"),
        priority=state.get("priority", "Not assigned"),
        casualties=state.get("casualties", "Unknown"),
        missing_info=", ".join(state.get("missing_info", [])) or "None identified",
        turn_count=state.get("turn_count", 0),
    )

    messages = [SystemMessage(content=prompt)] + list(state["messages"])
    response = llm.invoke(messages)

    question = _clean_llm_text(response.content)

    # Clean up any quotes or prefixes the LLM might add
    question = question.strip('"\'')
    if question.lower().startswith("question:"):
        question = question[9:].strip()

    return {"current_question": question}


# ── NODE 4: SERVICE ROUTER ──────────────────────────────────────

def router_node(state: IncidentState) -> dict:
    """
    Routes the incident to the appropriate emergency service using RAG context.
    Determines parallel dispatch plan based on retrieved protocols.
    """
    llm = _get_llm(temperature=0.1)

    # 1. Retrieve RAG Context
    # Query using type, details, location
    query = f"{state.get('emergency_type', '')} {state.get('details', '')} {state.get('location', '')}"
    try:
        context = retrieve_context(query)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)
        context = "No protocol found (RAG error)."

    # 2. Generate Dispatch Plan
    prompt = ROUTER_RAG_PROMPT.format(
        emergency_type=state.get("emergency_type", "Unknown"),
        location=state.get("location", "Unknown"),
        details=state.get("details", "Unknown"),
        priority=state.get("priority", "Not assigned"),
        casualties=state.get("casualties", "Unknown"),
        context=context,
    )

    try:
        logger.info(f"Routing with query: {query}")
        response = llm.invoke([SystemMessage(content=prompt)])
        parsed = _parse_json(response.content)
        
        dispatch_plan = parsed.get("dispatch_plan", [])
        if not isinstance(dispatch_plan, list):
            dispatch_plan = []

        routing_notes = parsed.get("routing_notes", "")
        logger.info(f"Dispatch Plan: {dispatch_plan}")

        # 3. Determine Primary Service (for backward compatibility / summary)
        # Sort by priority (1 is highest, so lowest number)
        primary_service = "General Emergency"
        if dispatch_plan:
            # Sort by priority, explicit int conversion fallback
            # Treat priority as int, lower is better. Default to 5 if missing.
            sorted_plan = sorted(
                dispatch_plan, 
                key=lambda x: int(x.get("priority", 5)) if str(x.get("priority", "5")).isdigit() else 5
            )
            if sorted_plan:
                primary_service = sorted_plan[0].get("service", "General Emergency")

        # 4. Attach Legacy SOPs (Optional, for UI consistency)
        sop_steps = SOP_DATABASE.get(primary_service, SOP_DATABASE.get("Other", []))

        return {
            "dispatch_plan": dispatch_plan,
            "retrieved_context": context,
            "routed_service": primary_service,
            "sop_steps": sop_steps,
            "dispatcher_notes": routing_notes,
        }
    except Exception as e:
        err_msg = f"Router Node Error: {e}\n{traceback.format_exc()}"
        logger.error(err_msg)
        raise e


# ── NODE 5: SUMMARIZER ─────────────────────────────────────────

def summarizer_node(state: IncidentState) -> dict:
    """
    Generates a concise dispatcher-ready briefing and final question.
    """
    llm = _get_llm(temperature=0.3)

    prompt = SUMMARIZER_PROMPT.format(
        emergency_type=state.get("emergency_type", "Unknown"),
        location=state.get("location", "Unknown"),
        details=state.get("details", "Unknown"),
        priority=state.get("priority", "Not assigned"),
        casualties=state.get("casualties", "Unknown"),
        routed_service=state.get("routed_service", "Pending"),
    )

    response = llm.invoke([SystemMessage(content=prompt)])
    parsed = _parse_json(response.content)

    update = {}
    if parsed.get("summary"):
        update["summary"] = parsed["summary"]
    if parsed.get("dispatcher_notes"):
        update["dispatcher_notes"] = parsed["dispatcher_notes"]

    return update


# ── NODE 6: GUIDANCE ────────────────────────────────────────────

def guidance_node(state: IncidentState) -> dict:
    """
    Generates real-time safety guidance for the caller.
    This is spoken to the caller via TTS while they wait for officials.
    Includes conversation history so it can answer the caller's questions.
    """
    llm = _get_llm(temperature=0.3)

    prompt = GUIDANCE_PROMPT.format(
        emergency_type=state.get("emergency_type", "Unknown"),
        location=state.get("location", "Unknown"),
        details=state.get("details", "Unknown"),
        priority=state.get("priority", "Not assigned"),
        casualties=state.get("casualties", "Unknown"),
        routed_service=state.get("routed_service", "Pending"),
    )

    # Include conversation so the LLM can answer the caller's latest question
    messages = [SystemMessage(content=prompt)] + list(state["messages"])
    response = llm.invoke(messages)
    guidance_text = _clean_llm_text(response.content)

    # Strip any JSON wrapper if LLM wraps it
    if guidance_text.startswith("{"):
        parsed = _parse_json(guidance_text)
        guidance_text = parsed.get("guidance", guidance_text)

    return {"guidance": guidance_text, "current_question": guidance_text}
