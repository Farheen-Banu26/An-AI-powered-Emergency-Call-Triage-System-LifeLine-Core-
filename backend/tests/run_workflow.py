"""Full workflow integration test — sends a multi-turn emergency call."""

import json
import time

import httpx

BASE = "http://localhost:8000/api/call"
SID = "workflow-test-001"
client = httpx.Client(timeout=120.0)


def send(msg):
    print(f"\n[CALLER]: {msg}")
    t = time.time()
    r = client.post(f"{BASE}/message", json={"session_id": SID, "message": msg})
    print(f"  -> HTTP {r.status_code} ({time.time() - t:.1f}s)")
    return r.is_success


def status():
    r = client.get(f"{BASE}/status/{SID}")
    d = r.json()
    inc = d["incident"]
    print(f"  Status      : {inc['status']}")
    print(f"  Type        : {inc['emergency_type']}")
    print(f"  Location    : {inc['location']}")
    print(f"  Priority    : {inc['priority']}")
    print(f"  Casualties  : {inc['casualties']}")
    print(f"  Caller Name : {inc.get('caller_name')}")
    print(f"  Caller Age  : {inc.get('caller_age')}")
    print(f"  Caller Phone: {inc.get('caller_phone')}")
    print(f"  Guidance    : {inc.get('guidance')}")
    print(f"  Turns       : {d['conversation_turns']}")
    print(f"  Summary     : {inc['summary']}")
    if inc.get("routed_service"):
        print(f"  Service     : {inc['routed_service']}")
    if inc.get("dispatch_plan"):
        print(f"  Dispatch    : {json.dumps(inc['dispatch_plan'], indent=4)}")
    else:
        print(f"  Dispatch    : pending")
    return inc


def question():
    r = client.get(f"{BASE}/question/{SID}")
    data = r.json()
    q = data.get("question")
    g = data.get("guidance")
    if q:
        print(f"  [AI QUESTION]: {q}")
    if g:
        print(f"  [GUIDANCE]: {g[:120]}...")
    return q


def full_subtitle():
    r = client.get(f"{BASE}/question/{SID}/full")
    data = r.json()
    print(f"  [SUBTITLE RESPONSE]: question={data.get('question')}, audio_url={data.get('audio_url')}")
    if data.get("guidance"):
        print(f"  [GUIDANCE TEXT]: {data['guidance'][:120]}...")
    return data


def summary():
    r = client.get(f"{BASE}/summary/{SID}")
    data = r.json()
    print(f"  Summary endpoint: status={data.get('status')}, turns={data.get('turn_count')}")
    print(f"  Messages count: {len(data.get('messages', []))}")
    return data


if __name__ == "__main__":
    print("=" * 60)
    print("LIFELINE-CORE — FULL WORKFLOW TEST (Groq + MongoDB + Guidance)")
    print("=" * 60)

    # Health check
    r = client.get("http://localhost:8000/api/health")
    h = r.json()
    print(f"\nProvider: {h.get('llm_provider')} | Model: {h.get('model')}")

    # Turn 1: Rich initial report with caller details
    send(
        "Hello! There is a huge fire here at the Grand Plaza Hotel on MG Road, 4th floor. "
        "My name is Rahul, I am 28 years old. My phone number is 9876543210. "
        "People are trapped, at least 3 people unconscious, heavy smoke everywhere!"
    )
    question()
    s = status()
    assert s["emergency_type"] is not None, "Type should be extracted"
    print("  [PASS] Emergency type extracted")

    # Turn 2: More details
    send("The fire is spreading to the 5th floor now. I can hear more people screaming for help.")
    question()
    s = status()
    assert s["location"] is not None, "Location should be extracted"
    print("  [PASS] Location extracted")

    # Test subtitle endpoint
    print("\n--- Subtitle Test ---")
    full_subtitle()

    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    status()

    # Test summary endpoint
    print("\n--- Summary Endpoint ---")
    summary()

    # Verify workflow progression
    if s["status"] == "ready_to_dispatch":
        print("\n[SUCCESS] System reached READY_TO_DISPATCH!")
        if s.get("guidance"):
            print(f"  Guidance generated: YES")
        if s.get("routed_service"):
            print(f"  Routed to: {s['routed_service']}")
    else:
        print(f"\n[INFO] Status: {s['status']} — may need more turns")

    # List sessions
    r = client.get(f"{BASE}/sessions")
    print(f"\nSessions: {json.dumps(r.json(), indent=2)}")

    # Cleanup
    r = client.delete(f"{BASE}/{SID}")
    print(f"Session deleted: {r.json()}")
    print("\nDone!")
