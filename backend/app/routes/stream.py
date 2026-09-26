import asyncio
import logging
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from starlette.websockets import WebSocketState

from app.ai.workflow import emergency_workflow
from app.routes.dispatcher import broadcast_emergency_update
from app.services.session_service import session_store
from app.services.severity_service import SeverityService
from app.services.stt_service import STTService
from app.services.translation_service import translation_service
from app.services.tts_service import TTSService
from app.services.vad_service import VADService

logger = logging.getLogger(__name__)
router = APIRouter()
tts_service = TTSService()


DISCARDED_HALLUCINATIONS = {
    "", ".", "..", "...", "!", "?", ",", "-", "_",
    "you", "thank you", "thank you.", "thank you very much.",
    "thank you for watching", "thanks for watching", "thanks for watching!",
    "i'm not a man of a hero", "yes, i am the one", "i'm going to go", "god. god. god", "god god god",
    "i'll get it", "i'm going to get him", "i need to go", "that... that...", "what?", "i am the one",
    "subtitles by", "subtitles by the amara.org community",
    "bye", "bye.", "okay", "okay.", "silence", "music", "applause",
    "laughter", "cough", "sigh", "throat clearing", "snicker",
    "[music]", "[applause]", "[laughter]", "[silence]", "[cough]", "[sigh]",
    "(music)", "(applause)", "(laughter)", "(silence)", "(cough)",
}


def is_meaningful_transcript(text: str) -> bool:
    """Validate that transcript contains actual words and is not silence/noise hallucination."""
    if not text:
        return False
    raw_lower = text.strip().lower()
    if raw_lower in DISCARDED_HALLUCINATIONS:
        return False
    # Indic characters (Tamil, Hindi, etc.)
    if any('\u0B80' <= ch <= '\u0BFF' or '\u0900' <= ch <= '\u097F' for ch in text):
        return len(raw_lower.strip("!?. ,-_")) >= 1 and raw_lower not in DISCARDED_HALLUCINATIONS
    import re
    cleaned = re.sub(r"[^\w\s]", "", text).strip().lower()
    if len(cleaned) < 2:
        return False
    if cleaned in DISCARDED_HALLUCINATIONS:
        return False
    return True


@router.websocket("/audio")
async def stream_audio(
    websocket: WebSocket,
    session_id: str = Query(...),
    lang: str = Query("en"),
):
    """
    Main WebSocket endpoint for real-time audio ingestion.
    Orchestrates: VAD → STT → Caller/Dispatcher Translation → AI Workflow → TTS → Dispatcher broadcast.
    Supports binary PCM frames and JSON control messages (set_language, speech_end, speech_discard).
    """
    await websocket.accept()
    current_lang = lang or "en"
    logger.info("[VOICE] language=%s event=websocket_connected session_id=%s", current_lang, session_id)

    # Per-connection services
    vad = VADService()
    stt = STTService()
    severity = SeverityService()

    # Ensure session exists
    session_store.get_or_create(session_id)

    async def _safe_send(msg: dict):
        """Send JSON to the caller, silently ignoring if disconnected."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(msg)
        except Exception:
            pass

    async def _run_ai_pipeline(
        original_transcript: str,
        translated_transcript: str,
        caller_lang: str,
        dispatcher_lang: str,
        t_stt_start: float,
        t_stt_end: float,
        has_fast_path_response: bool = False,
    ):
        """Run the deep AI pipeline (RAG + Qwen 3.8-27B) asynchronously in background with bidirectional translation."""
        t_ai_start = time.time()
        logger.info(
            "[VOICE] caller_lang=%s dispatcher_lang=%s event=ai_started session_id=%s transcript=%r has_fast_path=%s",
            caller_lang, dispatcher_lang, session_id, translated_transcript[:50], has_fast_path_response
        )

        # Severity scoring (deterministic keyword analysis < 2ms evaluated on both translated & original text)
        scoring_raw = severity.evaluate(original_transcript)
        scoring_trans = severity.evaluate(translated_transcript)
        max_priority_score = max(scoring_raw["priority_score"], scoring_trans["priority_score"])
        priority_label = scoring_trans["priority_label"] if scoring_trans["priority_score"] >= scoring_raw["priority_score"] else scoring_raw["priority_label"]

        # Get current state, append message, run workflow in dispatcher selected language
        state = session_store.get_state(session_id)
        if state is None:
            return

        input_state = dict(state)
        input_state["messages"] = list(state["messages"]) + [HumanMessage(content=translated_transcript)]
        input_state["priority_score"] = max(
            state.get("priority_score") or 0, max_priority_score
        )
        input_state["priority_label"] = priority_label
        input_state["language"] = dispatcher_lang
        input_state["selected_language"] = dispatcher_lang
        input_state["detected_language"] = caller_lang
        input_state["input_language"] = caller_lang
        input_state["response_language"] = dispatcher_lang
        input_state["original_transcript"] = original_transcript
        input_state["translated_transcript"] = translated_transcript

        try:
            result = await emergency_workflow.ainvoke(input_state)

            # Translate questions and guidance from dispatcher language to caller language
            dispatcher_question = result.get("current_question")
            dispatcher_guidance = result.get("guidance")

            caller_question = None
            if dispatcher_question:
                caller_question = await translation_service.translate(
                    dispatcher_question, source_lang=dispatcher_lang, target_lang=caller_lang
                )

            caller_guidance = None
            if dispatcher_guidance:
                caller_guidance = await translation_service.translate(
                    dispatcher_guidance, source_lang=dispatcher_lang, target_lang=caller_lang
                )

            result["caller_question"] = caller_question
            result["caller_guidance"] = caller_guidance
            result["original_transcript"] = original_transcript
            result["translated_transcript"] = translated_transcript
            result["detected_language"] = caller_lang
            result["selected_language"] = dispatcher_lang
            result["language"] = dispatcher_lang
            result["response_language"] = dispatcher_lang

            with session_store._lock:
                session_store._sessions[session_id] = result
        except Exception as e:
            logger.error("[AI ERROR] [%s]: %s", session_id, e, exc_info=True)
            await _safe_send({
                "type": "vad_state",
                "state": "listening",
                "session_id": session_id,
            })
            return

        t_ai_end = time.time()
        ai_duration_ms = (t_ai_end - t_ai_start) * 1000
        stt_duration_ms = (t_stt_end - t_stt_start) * 1000
        logger.info("[VOICE] caller_lang=%s event=ai_finished session_id=%s duration_ms=%.1f", caller_lang, session_id, ai_duration_ms)

        # Broadcast enriched triage & protocol results to dispatcher dashboard(s) in dispatcher selected language
        await broadcast_emergency_update({
            "session_id": session_id,
            "transcript": translated_transcript,
            "original_transcript": original_transcript,
            "caller_language": caller_lang,
            "language": dispatcher_lang,
            "severity": result.get("priority_label"),
            "score": result.get("priority_score"),
            "summary": result.get("summary"),
            "status": result.get("status"),
            "emergency_type": result.get("emergency_type"),
            "location": result.get("location"),
            "caller_name": result.get("caller_name"),
            "caller_age": result.get("caller_age"),
            "caller_phone": result.get("caller_phone"),
            "casualties": result.get("casualties"),
            "guidance": result.get("guidance"),
            "current_question": result.get("current_question"),
            "missing_info": result.get("missing_info", []),
            "sop_steps": result.get("sop_steps"),
            "dispatch_plan": result.get("dispatch_plan", []),
            "routed_service": result.get("routed_service"),
            "fake_probability": result.get("fake_probability"),
            "fake_label": result.get("fake_label"),
            "fake_signals": result.get("fake_signals", []),
            "selected_service": result.get("selected_service"),
            "sensor_telemetry": result.get("sensor_telemetry"),
            "captured_images": result.get("captured_images", []),
            "turn_count": result.get("turn_count", 0),
            "known_facts": result.get("known_facts", {}),
            "latitude": result.get("latitude"),
            "longitude": result.get("longitude"),
            "location_accuracy": result.get("location_accuracy"),
            "location_source": result.get("location_source"),
            "location_status": result.get("location_status"),
            "location_display": result.get("location_display"),
        })

        # If fast-path already sent immediate emergency response to caller, do NOT send a duplicate second question
        if has_fast_path_response:
            logger.info("[RESPONSE SUPPRESSED] [%s] Fast-path already handled caller response for this utterance", session_id)
            await _safe_send({
                "type": "vad_state",
                "state": "listening",
                "session_id": session_id,
            })
        else:
            # Send AI response / dynamic question back to caller in CALLER'S language
            status = result.get("status", "gathering_info")
            response_text = result.get("caller_question") or result.get("caller_guidance") or result.get("current_question")
            caller_guidance = result.get("caller_guidance") or result.get("guidance")
            p_score = result.get("priority_score")
            p_label = result.get("priority_label")

            if response_text:
                # Synthesize TTS audio in the caller's spoken language
                audio_b64 = None
                try:
                    audio_b64 = tts_service.synthesize_base64_audio(response_text, language_code=caller_lang)
                except Exception as tts_err:
                    logger.warning("[TTS WARN] Failed to synthesize audio for caller (%s): %s", caller_lang, tts_err)

                await _safe_send({
                    "type": "question",
                    "text": response_text,
                    "guidance": caller_guidance,
                    "session_id": session_id,
                    "status": status,
                    "priority_score": p_score,
                    "priority_label": p_label,
                    "fake_probability": result.get("fake_probability"),
                    "fake_label": result.get("fake_label"),
                    "fake_signals": result.get("fake_signals", []),
                    "audio_base64": audio_b64,
                    "language_code": caller_lang,
                })
                await _safe_send({
                    "type": "vad_state",
                    "state": "listening",
                    "session_id": session_id,
                })
                logger.info("[RESPONSE DISPLAYED] [%s] caller_lang=%s text: %s", session_id, caller_lang, response_text[:60])
            else:
                await _safe_send({
                    "type": "vad_state",
                    "state": "listening",
                    "session_id": session_id,
                })

        # Async non-blocking MongoDB persistence
        asyncio.create_task(session_store._persist_to_mongo(session_id, result))

        logger.info(
            "[TIMING] [%s] STT: %.1fms | AI_WORKFLOW(Qwen): %.1fms | TOTAL_PIPELINE: %.1fms",
            session_id,
            stt_duration_ms,
            ai_duration_ms,
            (t_ai_end - t_stt_start) * 1000,
        )

    last_transcript: str = ""
    last_transcript_time: float = 0.0

    async def handle_speech(chunk: bytes):
        """Process a single VAD-detected speech segment."""
        nonlocal last_transcript, last_transcript_time, current_lang
        if not chunk:
            return

        t_stt_start = time.time()
        logger.info("[VOICE] language=%s event=vad_speech_started session_id=%s bytes=%d duration_ms=%.1f", current_lang, session_id, len(chunk), len(chunk) / 32.0)

        # 1. Transcribe
        try:
            stt_result = await stt.transcribe(chunk, language=current_lang)
        except Exception as stt_err:
            logger.error("[VOICE] language=%s event=stt_error session_id=%s err=%s", current_lang, session_id, stt_err)
            await _safe_send({
                "type": "vad_state",
                "state": "listening",
                "session_id": session_id,
            })
            await _safe_send({
                "type": "error",
                "message": "Speech recognition unavailable. Please try again or use text input.",
                "session_id": session_id,
            })
            return

        t_stt_end = time.time()
        transcript = (stt_result.get("transcript") or "").strip()
        stt_ms = (t_stt_end - t_stt_start) * 1000

        if not is_meaningful_transcript(transcript):
            logger.info("[VOICE] language=%s event=transcript_discarded session_id=%s text=%r", current_lang, session_id, transcript)
            await _safe_send({
                "type": "vad_state",
                "state": "listening",
                "session_id": session_id,
            })
            return

        # 2. Prevent consecutive duplicate triggers within 2.5 seconds
        now = time.time()
        if transcript.lower() == last_transcript.lower() and (now - last_transcript_time) < 2.5:
            logger.info("[VOICE] language=%s event=duplicate_discarded session_id=%s text=%r", current_lang, session_id, transcript)
            await _safe_send({
                "type": "vad_state",
                "state": "listening",
                "session_id": session_id,
            })
            return

        last_transcript = transcript
        last_transcript_time = now

        # 3. Determine caller language and dispatcher selected language
        caller_lang = translation_service.detect_language(transcript, fallback_lang=current_lang)
        original_transcript = transcript

        state = session_store.get_state(session_id) or {}
        dispatcher_lang = state.get("selected_language") or state.get("language") or "en"

        logger.info(
            "[VOICE] caller_lang=%s dispatcher_lang=%s event=transcript_received session_id=%s latency_ms=%.1f text=%r",
            caller_lang, dispatcher_lang, session_id, stt_ms, original_transcript
        )

        # 4. Send original caller transcript back to caller immediately (subtitles in native language) < 5ms
        await _safe_send({
            "type": "transcript",
            "text": original_transcript,
            "session_id": session_id,
            "language_code": caller_lang,
        })

        # 5. Translate caller transcript to dispatcher language for CAD Dashboard
        translated_transcript = await translation_service.translate(
            original_transcript, source_lang=caller_lang, target_lang=dispatcher_lang
        )

        # 6. IMMEDIATELY broadcast translated transcript to dispatcher dashboard < 5ms
        t_disp_start = time.time()
        await broadcast_emergency_update({
            "session_id": session_id,
            "transcript": translated_transcript,
            "original_transcript": original_transcript,
            "caller_language": caller_lang,
            "language": dispatcher_lang,
            "caller_status": "speaking",
            "timestamp": now,
        })
        logger.info(
            "[VOICE] caller_lang=%s dispatcher_lang=%s event=dispatcher_broadcast session_id=%s latency_ms=%.1f",
            caller_lang, dispatcher_lang, session_id, (time.time() - t_disp_start) * 1000
        )

        # 7. Immediate Deterministic Safety Fast-Path Check (< 2ms evaluated on both original & translated)
        combined_lower = f"{original_transcript} {translated_transcript}".lower()
        fast_guidance_caller = None
        fast_guidance_dispatcher = None

        is_cardiac_or_breathing = any(
            k in combined_lower for k in [
                "not breathing", "unresponsive", "cardiac arrest", "no pulse", "heart stopped",
                "can't breathe", "cannot breathe", "மூச்சு", "மயக்கம்", "மாரடைப்பு", "saans nahi", "behos", "सांस", "बेहोश"
            ]
        )
        is_fire = any(
            k in combined_lower for k in [
                "trapped in fire", "building on fire", "fire trapped", "fire", "தீ", "புகை", "ஆபத்து", "आग", "धुआं"
            ]
        )
        is_bleeding = any(
            k in combined_lower for k in [
                "arterial bleeding", "heavy bleeding", "severe bleeding", "bleeding heavily", "bleeding profusely",
                "spurting blood", "cut my hand", "cut my arm", "cut on hand", "cut on arm", "bleeding is not stopping",
                "bleeding not stopping", "bleeding won't stop", "bleeding wont stop", "bleeding", "wound", "stabbed",
                "ரத்தம்", "அதிக ரத்தம்", "காயம்", "खून", "भारी खून", "चोट"
            ]
        )
        is_active_threat = any(
            k in combined_lower for k in [
                "active shooter", "gunman", "stabbing in progress", "active attacker",
                "துப்பாக்கி", "தாக்குதல்", "हथियार", "हमலா", "गोली"
            ]
        )

        if is_cardiac_or_breathing:
            fast_guidance_dispatcher = "Check airway. If unresponsive and not breathing, lay flat and begin continuous chest compressions at 100-120 bpm."
            if caller_lang == "ta":
                fast_guidance_caller = "சுவாசப்பாதையைச் சரிபார்க்கவும். மூச்சு இல்லை என்றால், உடனடியாக நெஞ்சுப் பகுதியில் சிபிஆர் (CPR) அழுத்தத்தைத் தொடங்குங்கள்."
            elif caller_lang == "hi":
                fast_guidance_caller = "वायुमार्ग की जांच करें। यदि सांस नहीं ले रहे हैं, तो तुरंत 100-120 प्रति मिनट की गति से सीपीआर शुरू करें।"
            else:
                fast_guidance_caller = fast_guidance_dispatcher
        elif is_fire:
            fast_guidance_dispatcher = "Evacuate immediately if safe. Stay low under smoke, feel doors before opening, and do not use elevators."
            if caller_lang == "ta":
                fast_guidance_caller = "பாதுகாப்பாக இருந்தால் உடனே வெளியேறுங்கள். புகைக்குக் கீழே குனிந்து செல்லுங்கள். லிப்ட் பயன்படுத்த வேண்டாம்."
            elif caller_lang == "hi":
                fast_guidance_caller = "सुरक्षित होने पर तुरंत इमारत से बाहर निकलें। धुएं के नीचे झुककर चलें। लिफ्ट का प्रयोग न करें।"
            else:
                fast_guidance_caller = fast_guidance_dispatcher
        elif is_bleeding:
            fast_guidance_dispatcher = "Apply direct, firm, continuous pressure to the bleeding wound using a clean cloth or bandage immediately. Elevate the injured area if possible."
            if caller_lang == "ta":
                fast_guidance_caller = "சுத்தமான துணியால் காயத்தின் மீது உடனடியாக அழுத்தமாகப் பிடித்துக் கொள்ளுங்கள். முடிந்தால் காயமடைந்த பகுதியை இதய மட்டத்திற்கு மேலே உயர்த்துங்கள்."
            elif caller_lang == "hi":
                fast_guidance_caller = "साफ कपड़े से घाव पर तुरंत सीधा और लगातार दबाव डालें। यदि संभव हो तो चोट वाले हिस्से को दिल के स्तर से ऊपर उठाएं।"
            else:
                fast_guidance_caller = fast_guidance_dispatcher
        elif is_active_threat:
            fast_guidance_dispatcher = "Move to a secure locked room, silence all phones, stay low and away from doors and windows."
            if caller_lang == "ta":
                fast_guidance_caller = "பாதுகாப்பான அறைக்குச் சென்று கதவைப் பூட்டுங்கள், போனை சைலண்டில் வையுங்கள்."
            elif caller_lang == "hi":
                fast_guidance_caller = "सुरक्षित कमरे में जाएं, दरवाजा बंद करें और फोन को साइलेंट रखें।"
            else:
                fast_guidance_caller = fast_guidance_dispatcher

        # If fast-path matches, immediately transmit early guidance to caller in caller_lang & dispatcher in dispatcher_lang in < 5ms!
        if fast_guidance_caller:
            logger.info("[VOICE] caller_lang=%s event=safety_fast_path session_id=%s guidance=%s", caller_lang, session_id, fast_guidance_caller[:50])

            audio_b64 = None
            try:
                audio_b64 = tts_service.synthesize_base64_audio(fast_guidance_caller, language_code=caller_lang)
            except Exception as tts_err:
                logger.warning("[TTS WARN] Fast-path TTS failed (%s): %s", caller_lang, tts_err)

            await _safe_send({
                "type": "question",
                "text": fast_guidance_caller,
                "guidance": fast_guidance_caller,
                "session_id": session_id,
                "status": "gathering_info",
                "priority_score": 10,
                "priority_label": "CRITICAL",
                "is_fast_path": True,
                "audio_base64": audio_b64,
                "language_code": caller_lang,
            })
            await broadcast_emergency_update({
                "session_id": session_id,
                "severity": "CRITICAL",
                "score": 10,
                "guidance": fast_guidance_dispatcher,
                "is_fast_path": True,
                "language": dispatcher_lang,
                "caller_language": caller_lang,
            })
        else:
            # Send non-blocking processing indicator to caller
            await _safe_send({
                "type": "processing",
                "text": "Processing..." if caller_lang == "en" else ("செயலாக்குகிறது..." if caller_lang == "ta" else "प्रक्रिया जारी है..."),
                "session_id": session_id,
            })

        # 8. Run deep AI LangGraph processing as a non-blocking background task
        asyncio.create_task(
            _run_ai_pipeline(
                original_transcript,
                translated_transcript,
                caller_lang,
                dispatcher_lang,
                t_stt_start,
                t_stt_end,
                has_fast_path_response=bool(fast_guidance_caller),
            )
        )

    # Track background AI tasks so we can wait/cancel on disconnect
    pending_tasks: list[asyncio.Task] = []
    _original_handle_speech = handle_speech

    async def handle_speech_tracked(chunk: bytes):
        """Wrapper that keeps references to spawned background tasks."""
        before = set(asyncio.all_tasks())
        await _original_handle_speech(chunk)
        after = set(asyncio.all_tasks())
        new_tasks = after - before
        pending_tasks.extend(new_tasks)

    import json
    buffered_utterance_frames: list[bytes] = []

    try:
        while True:
            msg = await websocket.receive()
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"]:
                data = msg["bytes"]
                buffered_utterance_frames.append(data)
                # Also process through backend WebRTC VAD
                for chunk in vad.get_speech_chunks(data):
                    buffered_utterance_frames = []
                    await handle_speech_tracked(chunk)

            elif "text" in msg and msg["text"]:
                try:
                    payload = json.loads(msg["text"])
                    p_type = payload.get("type")
                    if p_type == "set_language":
                        new_lang = payload.get("language")
                        if new_lang:
                            current_lang = new_lang
                            logger.info("[VOICE] language=%s event=language_updated session_id=%s", current_lang, session_id)
                    elif p_type == "speech_end":
                        # Deliver complete speech utterance accumulated from client VAD
                        utterance_data = None
                        if buffered_utterance_frames:
                            utterance_data = b"".join(buffered_utterance_frames)
                            buffered_utterance_frames = []
                        elif vad.triggered or vad.voiced_frames:
                            utterance_data = vad.flush()

                        if utterance_data and len(utterance_data) >= 4000:
                            logger.info("[VOICE] language=%s event=speech_end_flush session_id=%s bytes=%d", current_lang, session_id, len(utterance_data))
                            await handle_speech_tracked(utterance_data)
                        else:
                            await _safe_send({"type": "vad_state", "state": "listening", "session_id": session_id})
                    elif p_type == "speech_discard":
                        buffered_utterance_frames = []
                        vad.flush()
                        await _safe_send({"type": "vad_state", "state": "listening", "session_id": session_id})
                except Exception as json_err:
                    logger.warning("[VOICE] JSON control parse error: %s", json_err)

    except WebSocketDisconnect:
        logger.info("Caller disconnected: %s", session_id)
        final_chunk = vad.close()
        if final_chunk:
            await handle_speech_tracked(final_chunk)
    except Exception as e:
        logger.error("Stream error [%s]: %s", session_id, e, exc_info=True)
    finally:
        # Clean up: cancel any still-running AI pipeline tasks
        for t in pending_tasks:
            if not t.done():
                t.cancel()
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass
