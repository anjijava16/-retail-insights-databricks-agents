"""Streamlit chat UI for the retail insights agent. Runs as a Databricks App.

Start locally with:
    DATABRICKS_WAREHOUSE_ID=... RETAIL_SCHEMA=retail_dev \\
    uv run streamlit run src/retail_insights/app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Databricks Apps runs this file from the bundle root without installing the
# package, so make `src/` importable.
SRC = Path(__file__).resolve().parents[2]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd  # noqa: E402  (streamlit ships with pandas)
import streamlit as st  # noqa: E402

from retail_insights.agent.factory import build_agent_from_env, resolve_schema  # noqa: E402

EXAMPLES = [
    "What was net revenue and average order value over the last 7 days?",
    "Which region had the highest gross margin in the last 30 days?",
    "Top 5 products by net revenue in Electronics",
    "How many customers are At Risk and what do they spend on average?",
    "Compare online vs in-store revenue last week",
]

st.set_page_config(page_title="Retail Insights Agent", layout="wide")


@st.cache_resource
def get_agent():
    return build_agent_from_env()


def render_steps(steps) -> None:
    if not steps:
        return
    with st.expander(f"How I got this ({len(steps)} tool call{'s' if len(steps) > 1 else ''})"):
        for i, s in enumerate(steps, 1):
            status = "ok" if s.ok else "error"
            st.markdown(f"**{i}. `{s.tool}`** · {s.seconds:.2f}s · {status}")
            st.json(s.arguments, expanded=False)
            if s.sql:
                st.code(s.sql, language="sql")
            if s.ok and s.result.get("rows"):
                st.dataframe(pd.DataFrame(s.result["rows"]), use_container_width=True)
            elif not s.ok:
                st.warning(s.result["error"])


with st.sidebar:
    st.header("Retail Insights")
    st.caption(
        "Ask about sales, products and customers. Answers come from the gold tables "
        "built by the ETL job, through a SQL warehouse."
    )
    st.markdown(f"**Schema:** `{resolve_schema()}`")
    st.subheader("Try asking")
    for q in EXAMPLES:
        if st.button(q, use_container_width=True):
            st.session_state.pending = q
    if st.button("Clear chat"):
        st.session_state.messages = []

st.session_state.setdefault("messages", [])

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        render_steps(m.get("steps"))

question = st.chat_input("Ask a question about the business") or st.session_state.pop(
    "pending", None
)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Only text turns go back as history; tool traces stay out of the prompt.
    history = [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]
    ][-8:]
    with st.chat_message("assistant"), st.spinner("Querying the warehouse..."):
        try:
            result = get_agent().run(question, history=history)
            answer, steps = result.answer, result.steps
        except Exception as e:
            answer, steps = f"Something went wrong: `{e}`", []
        st.markdown(answer)
        render_steps(steps)
    st.session_state.messages.append({"role": "assistant", "content": answer, "steps": steps})
