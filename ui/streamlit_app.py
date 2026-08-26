"""
Streamlit UI for the WMS Natural-Language Query Interface.

Deliberately a thin HTTP client, not embedded pipeline logic — talks to the
FastAPI backend (WMS_API_URL) over the network so the API stays the single
source of truth and can be deployed/scaled independently of the UI.
"""
import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("WMS_API_URL", "http://localhost:8000")
REQUEST_TIMEOUT_S = 30

EXAMPLE_QUESTIONS = [
    "What are our top 5 hot picks this month?",
    "Which receipts took longer than 4 hours to put away in the last 30 days?",
    "How many C-class items are stored in frozen aisle A?",
    "What's the average picks per hour by zone?",
    "Which items are expiring in the next 7 days?",
]

st.set_page_config(page_title="WMS Natural-Language Query", page_icon="📦", layout="wide")

st.title("📦 WMS Natural-Language Query Interface")
st.caption(
    "Ask a plain-English question about warehouse operations. The system converts it to "
    "SQL, safety-validates it, runs it against live WMS data, and explains the result."
)

if "question" not in st.session_state:
    st.session_state.question = ""

with st.sidebar:
    st.subheader("Example questions")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"example_{q}"):
            st.session_state.question = q

    st.divider()
    st.subheader("Recent queries")
    try:
        audit = requests.get(f"{API_URL}/audit", params={"limit": 10}, timeout=REQUEST_TIMEOUT_S)
        audit.raise_for_status()
        for entry in audit.json():
            icon = "✅" if entry["execution_success"] else "⚠️"
            st.caption(f"{icon} {entry['user_question']}")
    except requests.RequestException as e:
        st.caption(f"Couldn't load audit history: {e}")


def confidence_badge(confidence: float) -> str:
    if confidence >= 0.75:
        return f"🟢 High confidence ({confidence:.0%})"
    if confidence >= 0.4:
        return f"🟡 Medium confidence ({confidence:.0%})"
    return f"🔴 Low confidence ({confidence:.0%})"


question = st.text_input(
    "Ask a question about your warehouse",
    value=st.session_state.question,
    placeholder="e.g. What are our top 5 hot picks this month?",
)

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Generating SQL, validating, and running against live data..."):
        try:
            resp = requests.post(
                f"{API_URL}/query", json={"question": question}, timeout=REQUEST_TIMEOUT_S
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.RequestException as e:
            st.error(f"Request to the API failed: {e}")
            result = None

    if result is not None:
        st.markdown(confidence_badge(result["confidence"]))

        if not result["answerable"]:
            st.warning(
                "This question can't be answered from the current WMS schema — "
                "no fabricated answer was generated."
            )
        elif not result["validation_passed"]:
            st.error("Generated SQL failed safety validation and was not executed.")
            for err in result["validation_errors"]:
                st.write(f"- {err}")
        elif not result["execution_success"]:
            st.error(f"SQL executed but failed: {result['error']}")

        if result["sql"]:
            st.subheader("Generated SQL")
            st.code(result["sql"], language="sql")
            for warning in result["validation_warnings"]:
                st.caption(f"⚠️ {warning}")

        if result["explanation"]:
            st.subheader("Answer")
            st.write(result["explanation"])

        if result["rows"]:
            st.subheader(f"Results ({result['row_count']} row{'s' if result['row_count'] != 1 else ''})")
            st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True)

        st.caption(
            f"Provider: {result['llm_provider']} · Latency: {result['latency_ms']}ms"
        )
