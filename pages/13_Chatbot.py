"""Trang Chatbot — trợ lý hỏi đáp về TrustProfile và blockchain."""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google import genai
from state import init_state, get_network
from chatbot import chat, DEFAULT_MODELS

init_state()
st.header("🤖 Trợ lý TRUSTMEBRO")
st.caption("Hỏi về blockchain, về dự án này, hoặc nhập Credential ID để kiểm tra.")


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)


api_key = get_secret("GEMINI_API_KEY")
if not api_key:
    st.error("Chưa có GEMINI_API_KEY. Thêm vào `.streamlit/secrets.toml` rồi chạy lại.")
    st.stop()

client = genai.Client(api_key=api_key)
forced_model = get_secret("GEMINI_MODEL")
network = get_network()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

SUGGESTIONS = [
    "Merkle Root dùng để làm gì?",
    "PoW khác PoS thế nào?",
    "Dự án này demo theo thứ tự nào?",
    "Hiện tại chain có bao nhiêu credential?",
]
if not st.session_state.chat_history:
    st.markdown("**Gợi ý câu hỏi:**")
    for s in SUGGESTIONS:
        st.markdown(f"- {s}")

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    is_error = False
    with st.chat_message("assistant"):
        with st.spinner("Đang suy nghĩ..."):
            try:
                answer = chat(client, network, st.session_state.chat_history,
                              models=([forced_model] if forced_model else []) + DEFAULT_MODELS)
            except Exception as e:
                is_error = True
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    answer = "Đã chạm giới hạn miễn phí của Gemini. Đợi khoảng 1 phút rồi hỏi lại nhé."
                else:
                    answer = "Chatbot đang gặp sự cố, bạn thử lại sau nhé. Các trang khác vẫn dùng bình thường."
        st.markdown(answer)

    if is_error:
        st.session_state.chat_history.pop()  
    else:
        st.session_state.chat_history.append({"role": "assistant", "content": answer})

if st.sidebar.button("🗑️ Xoá hội thoại"):
    st.session_state.chat_history = []
    st.rerun()
