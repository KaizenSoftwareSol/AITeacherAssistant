# streamlit_app/app.py

import json

import requests
import streamlit as st

# Page configuration
st.set_page_config(page_title="AI Teacher", page_icon="🎓", layout="wide")

# API base URL
API_BASE_URL = "http://localhost:8001/api/v1"


def main():
    st.title("🎓 AI Teacher - Learning Platform")
    st.markdown("---")

    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page", ["Home", "Login", "Register", "AI Chat", "Courses"]
    )

    if page == "Home":
        show_home()
    elif page == "Login":
        show_login()
    elif page == "Register":
        show_register()
    elif page == "AI Chat":
        show_ai_chat()
    elif page == "Courses":
        show_courses()


def show_home():
    st.header("Welcome to AI Teacher")
    st.markdown(
        """
    AI Teacher is an intelligent learning platform that helps you learn with the power of AI.
    
    ### Features:
    - 🤖 AI-powered content generation
    - 📚 Interactive courses and lessons
    - 💬 AI chat assistant
    - 📊 Progress tracking
    - 🎯 Personalized learning paths
    """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Get Started")
        st.markdown(
            """
        1. Register for a new account
        2. Login to access your dashboard
        3. Start learning with AI assistance
        """
        )

    with col2:
        st.subheader("Quick Actions")
        if st.button("Login"):
            st.session_state.page = "Login"
        if st.button("Register"):
            st.session_state.page = "Register"


def show_login():
    st.header("Login")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            try:
                response = requests.post(
                    f"{API_BASE_URL}/auth/login",
                    data={"username": email, "password": password},
                )

                if response.status_code == 200:
                    data = response.json()
                    st.session_state.access_token = data["access_token"]
                    st.session_state.user = data["user"]
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Login failed. Please check your credentials.")
            except Exception as e:
                st.error(f"Error: {str(e)}")


def show_register():
    st.header("Register")

    with st.form("register_form"):
        email = st.text_input("Email")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["student", "user", "manager", "admin"])
        submit = st.form_submit_button("Register")

        if submit:
            try:
                response = requests.post(
                    f"{API_BASE_URL}/auth/register",
                    json={
                        "email": email,
                        "username": username,
                        "password": password,
                        "role": role,
                    },
                )

                if response.status_code == 200:
                    st.success("Registration successful! Please login.")
                else:
                    st.error("Registration failed. Please try again.")
            except Exception as e:
                st.error(f"Error: {str(e)}")


def show_ai_chat():
    st.header("AI Chat Assistant")

    if "access_token" not in st.session_state:
        st.warning("Please login first to access the AI chat.")
        return

    st.info(
        "🚧 AI Chat functionality is currently being upgraded. Full AI capabilities will be restored soon!"
    )

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask me anything about learning..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Placeholder response while AI is being upgraded
        with st.chat_message("assistant"):
            with st.spinner("AI features are being upgraded..."):
                response = "🚧 AI Teacher is currently being upgraded with new capabilities! The full AI chat experience will be available soon. Thank you for your patience!"
                st.markdown(response)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )


def show_courses():
    st.header("Courses")

    if "access_token" not in st.session_state:
        st.warning("Please login first to view courses.")
        return

    st.markdown("### Available Courses")
    st.info("Course management features coming soon!")


if __name__ == "__main__":
    main()
