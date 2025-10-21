# streamlit_app/app.py

from datetime import datetime

import requests
import streamlit as st

# Page configuration
st.set_page_config(page_title="AI Teacher Assistant", page_icon="🎓", layout="wide")

# API base URL
API_BASE_URL = "http://localhost:8001/api/v1"


# ==================== Helper Functions ====================


def get_auth_headers():
    """Get authorization headers with token."""
    if "access_token" in st.session_state:
        return {"Authorization": f"Bearer {st.session_state.access_token}"}
    return {}


def check_authentication():
    """Check if user is authenticated."""
    return "access_token" in st.session_state and "user" in st.session_state


def logout():
    """Logout user and clear session."""
    st.session_state.clear()
    st.rerun()


def format_file_size(size_bytes):
    """Format file size in human-readable format."""
    if size_bytes is None:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def format_datetime(dt_str):
    """Format datetime string."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str


# ==================== Main Application ====================


def main():
    """Main application entry point."""
    # Check authentication
    if not check_authentication():
        show_login()
    else:
        show_dashboard()


# ==================== Login Page ====================


def show_login():
    """Show login page."""
    st.title("🎓 AI Teacher Assistant")
    st.markdown("---")

    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.header("Login")
        st.markdown("Please login to access the AI Teacher Assistant platform.")

        with st.form("login_form"):
            email = st.text_input("Email", placeholder="teacher@example.com")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)

            if submit:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    with st.spinner("Logging in..."):
                        try:
                            response = requests.post(
                                f"{API_BASE_URL}/auth/login",
                                data={"username": email, "password": password},
                            )

                            if response.status_code == 200:
                                data = response.json()
                                st.session_state.access_token = data["access_token"]
                                st.session_state.token_type = data["token_type"]

                                # Fetch user details
                                user_response = requests.get(
                                    f"{API_BASE_URL}/auth/me",
                                    headers=get_auth_headers(),
                                )

                                if user_response.status_code == 200:
                                    st.session_state.user = user_response.json()
                                    st.success("Login successful!")
                                    st.rerun()
                                else:
                                    st.error("Failed to fetch user details.")
                            else:
                                error_detail = response.json().get(
                                    "detail", "Login failed"
                                )
                                st.error(f"Login failed: {error_detail}")
                        except requests.exceptions.ConnectionError:
                            st.error(
                                "Cannot connect to the server. "
                                "Please make sure the API is running."
                            )
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

        st.markdown("---")
        st.info("💡 **Tip**: Use your teacher credentials to access the platform.")


# ==================== Dashboard ====================


def show_dashboard():
    """Show main dashboard after login."""
    # Sidebar
    with st.sidebar:
        st.title("🎓 AI Teacher Assistant")
        st.markdown("---")

        # User info
        user = st.session_state.get("user", {})
        st.write(f"**Welcome, {user.get('username', 'User')}!**")
        st.write(f"Role: {user.get('role', 'N/A')}")
        st.markdown("---")

        # Navigation
        page = st.radio(
            "Navigation",
            ["📄 Document Management", "🎯 Lecture Generation"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            logout()

    # Show selected page
    if page == "📄 Document Management":
        show_document_management()
    elif page == "🎯 Lecture Generation":
        show_lecture_generation()


# ==================== Document Management ====================


def show_document_management():
    """Show document management section."""
    st.title("📄 Document Management")
    st.markdown("Upload and manage your documents for lecture generation.")
    st.markdown("---")

    # Create tabs for upload and view
    tab1, tab2, tab3 = st.tabs(
        ["📤 Upload File", "🌐 Upload Website", "📚 My Documents"]
    )

    with tab1:
        show_file_upload()

    with tab2:
        show_website_upload()

    with tab3:
        show_documents_list()


def show_file_upload():
    """Show file upload form."""
    st.subheader("Upload Document File")
    st.markdown("Upload PDF, PPTX, or DOCX files for processing.")

    with st.form("file_upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "pptx", "docx"],
            help="Supported formats: PDF, PPTX, DOCX",
        )
        title = st.text_input("Title", placeholder="Enter document title")
        description = st.text_area(
            "Description (Optional)", placeholder="Enter document description"
        )
        submit = st.form_submit_button("Upload Document", use_container_width=True)

        if submit:
            if not uploaded_file:
                st.error("Please select a file to upload.")
            elif not title:
                st.error("Please enter a title for the document.")
            else:
                with st.spinner("Uploading document..."):
                    try:
                        files = {
                            "file": (
                                uploaded_file.name,
                                uploaded_file,
                                uploaded_file.type,
                            )
                        }
                        data = {"title": title}
                        if description:
                            data["description"] = description

                        response = requests.post(
                            f"{API_BASE_URL}/documents/upload/file",
                            headers=get_auth_headers(),
                            files=files,
                            data=data,
                        )

                        if response.status_code == 201:
                            st.success(f"✅ Document uploaded successfully!")
                            doc_data = response.json()
                            st.json(doc_data)
                        else:
                            error_detail = response.json().get(
                                "detail", "Upload failed"
                            )
                            st.error(f"Upload failed: {error_detail}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")


def show_website_upload():
    """Show website URL upload form."""
    st.subheader("Upload Website URL")
    st.markdown("Extract content from a website URL.")

    with st.form("website_upload_form", clear_on_submit=True):
        url = st.text_input("Website URL", placeholder="https://example.com")
        title = st.text_input("Title", placeholder="Enter document title")
        description = st.text_area(
            "Description (Optional)", placeholder="Enter document description"
        )
        submit = st.form_submit_button("Upload Website", use_container_width=True)

        if submit:
            if not url:
                st.error("Please enter a website URL.")
            elif not title:
                st.error("Please enter a title for the document.")
            else:
                with st.spinner("Processing website..."):
                    try:
                        data = {"url": url, "title": title}
                        if description:
                            data["description"] = description

                        response = requests.post(
                            f"{API_BASE_URL}/documents/upload/website",
                            headers=get_auth_headers(),
                            data=data,
                        )

                        if response.status_code == 201:
                            st.success(f"✅ Website content uploaded successfully!")
                            doc_data = response.json()
                            st.json(doc_data)
                        else:
                            error_detail = response.json().get(
                                "detail", "Upload failed"
                            )
                            st.error(f"Upload failed: {error_detail}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")


def show_documents_list():
    """Show list of user's documents."""
    st.subheader("My Documents")

    # Refresh button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    with st.spinner("Loading documents..."):
        try:
            response = requests.get(
                f"{API_BASE_URL}/documents/",
                headers=get_auth_headers(),
            )

            if response.status_code == 200:
                documents = response.json()

                if not documents:
                    st.info("No documents found. Upload your first document!")
                else:
                    st.success(f"Found {len(documents)} document(s)")

                    # Display documents as cards
                    for doc in documents:
                        with st.expander(f"📄 {doc['title']} ({doc['document_type']})"):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.write(f"**ID:** {doc['id']}")
                                st.write(f"**Type:** {doc['document_type']}")
                                st.write(f"**Status:** {doc['status']}")
                                st.write(
                                    f"**Size:** "
                                    f"{format_file_size(doc.get('file_size'))}"
                                )

                            with col2:
                                st.write(
                                    f"**Created:** "
                                    f"{format_datetime(doc['created_at'])}"
                                )
                                st.write(
                                    f"**Updated:** "
                                    f"{format_datetime(doc['updated_at'])}"
                                )
                                if doc.get("description"):
                                    st.write(f"**Description:** {doc['description']}")

            else:
                error_detail = response.json().get("detail", "Failed to load documents")
                st.error(f"Error: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


# ==================== Lecture Generation ====================


def show_lecture_generation():
    """Show lecture generation section."""
    st.title("🎯 Lecture Generation")
    st.markdown("Generate lectures from your documents using AI.")
    st.markdown("---")

    # Load documents for selection
    with st.spinner("Loading your documents..."):
        try:
            response = requests.get(
                f"{API_BASE_URL}/documents/",
                headers=get_auth_headers(),
            )

            if response.status_code == 200:
                documents = response.json()

                if not documents:
                    st.warning(
                        "No documents found. Please upload documents first "
                        "in the Document Management section."
                    )
                    return

                # Filter only completed documents
                completed_docs = [
                    doc for doc in documents if doc["status"] == "COMPLETED"
                ]

                if not completed_docs:
                    st.warning(
                        "No completed documents found. Please wait for your "
                        "uploaded documents to finish processing."
                    )
                    return

                # Show document selection
                st.subheader("Select Document(s)")

                # Create document selection
                doc_options = {
                    f"{doc['title']} ({doc['document_type']})": doc["id"]
                    for doc in completed_docs
                }

                selected_doc_name = st.selectbox(
                    "Choose a document",
                    options=list(doc_options.keys()),
                    help="Select the document to generate lecture from",
                )

                selected_doc_id = doc_options[selected_doc_name]

                # Show selected document details
                selected_doc = next(
                    doc for doc in completed_docs if doc["id"] == selected_doc_id
                )

                with st.expander("📄 Selected Document Details", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Title:** {selected_doc['title']}")
                        st.write(f"**Type:** {selected_doc['document_type']}")
                        st.write(f"**Status:** {selected_doc['status']}")
                    with col2:
                        st.write(
                            f"**Created:** "
                            f"{format_datetime(selected_doc['created_at'])}"
                        )
                        st.write(
                            f"**Size:** "
                            f"{format_file_size(selected_doc.get('file_size'))}"
                        )
                    if selected_doc.get("description"):
                        st.write(f"**Description:** {selected_doc['description']}")

                st.markdown("---")

                # Fetch chapters if document is PDF
                chapters = []
                selected_chapters = None

                if selected_doc["document_type"] == "PDF":
                    st.subheader("📖 Select Chapters")

                    with st.spinner("Loading chapters..."):
                        try:
                            chapters_response = requests.get(
                                f"{API_BASE_URL}/documents/{selected_doc_id}/chapters",
                                headers=get_auth_headers(),
                            )

                            if chapters_response.status_code == 200:
                                chapters_data = chapters_response.json()
                                chapters = chapters_data.get("chapters", [])

                                if chapters:
                                    st.success(f"Found {len(chapters)} chapter(s)")

                                    # Create chapter options with word count
                                    chapter_options = [
                                        f"{ch['chapter_name']} ({ch['word_count']:,} words)"
                                        for ch in chapters
                                    ]

                                    # Multiselect for chapter selection
                                    selected_chapter_display = st.multiselect(
                                        "Select chapters to include in the lecture",
                                        options=chapter_options,
                                        default=chapter_options,  # All selected by default
                                        help="Choose one or more chapters. All chapters are selected by default.",
                                    )

                                    # Extract just the chapter names (without word count)
                                    if selected_chapter_display:
                                        selected_chapters = [
                                            chapters[i]["chapter_name"]
                                            for i, option in enumerate(chapter_options)
                                            if option in selected_chapter_display
                                        ]

                                        st.info(
                                            f"✅ {len(selected_chapters)} chapter(s) selected"
                                        )
                                    else:
                                        st.warning(
                                            "⚠️ No chapters selected. All chapters will be used."
                                        )
                                        selected_chapters = None
                                else:
                                    st.info(
                                        "No chapters found in this document. All content will be used."
                                    )
                            else:
                                st.warning(
                                    "Could not load chapters. All document content will be used."
                                )
                        except Exception as e:
                            st.warning(
                                f"Could not load chapters: {str(e)}. All document content will be used."
                            )

                    st.markdown("---")
                else:
                    st.info("ℹ️ Chapter selection is only available for PDF documents.")
                    st.markdown("---")

                # Lecture generation form
                st.subheader("Generate Lecture")

                # Fetch courses for the teacher
                with st.spinner("Loading courses..."):
                    courses_response = requests.get(
                        f"{API_BASE_URL}/courses/",
                        headers=get_auth_headers(),
                    )

                if courses_response.status_code != 200:
                    st.error(
                        "Failed to load courses. Please ensure you have "
                        "courses created in your university."
                    )
                    return

                courses = courses_response.json()

                if not courses:
                    st.warning(
                        "No courses found. Please create courses in your "
                        "university before generating lectures."
                    )
                    return

                # Course selection dropdown (outside form for reactivity)
                course_options = {
                    f"{course['name']} ({course['code']})": course["id"]
                    for course in courses
                }

                selected_course_name = st.selectbox(
                    "Select Course",
                    options=list(course_options.keys()),
                    help="Choose the course this lecture belongs to",
                    key="course_select",
                )

                selected_course_id = course_options[selected_course_name]

                # Fetch and display semesters for the selected course
                with st.spinner("Loading semesters..."):
                    semesters_response = requests.get(
                        f"{API_BASE_URL}/courses/{selected_course_id}/semesters",
                        headers=get_auth_headers(),
                    )

                if semesters_response.status_code != 200:
                    st.error("Failed to load semesters for this course.")
                    return

                semesters = semesters_response.json()

                if not semesters:
                    st.warning(
                        "No semesters found for this course. "
                        "Please create a semester first."
                    )
                    return

                # Semester selection dropdown
                semester_options = {f"{sem['name']}": sem["id"] for sem in semesters}

                selected_semester_name = st.selectbox(
                    "Select Semester",
                    options=list(semester_options.keys()),
                    help="Choose the semester this lecture belongs to",
                    key="semester_select",
                )

                selected_semester_id = semester_options[selected_semester_name]

                # Initialize session state for duplicate handling
                if "duplicate_data" not in st.session_state:
                    st.session_state.duplicate_data = None
                if "lecture_params" not in st.session_state:
                    st.session_state.lecture_params = None

                # Now the form with title, description, and learning outcomes
                with st.form("lecture_generation_form"):
                    lecture_title = st.text_input(
                        "Lecture Title",
                        placeholder="Enter the lecture title",
                        help="Title for the generated lecture",
                    )

                    lecture_description = st.text_area(
                        "Lecture Description",
                        placeholder="Provide context and details for the AI "
                        "to generate the lecture",
                        help="Describe what you want the lecture to cover",
                        height=150,
                    )

                    learning_outcomes = st.text_area(
                        "Learning Outcomes (Optional)",
                        placeholder="By the end of this lecture, students will be able to:\n"
                        "1. Understand key concepts\n"
                        "2. Apply learned techniques\n"
                        "3. Analyze and evaluate information",
                        help="Define what students should be able to do after the lecture",
                        height=120,
                    )

                    submit = st.form_submit_button(
                        "🚀 Generate Lecture", use_container_width=True
                    )

                    if submit:
                        if not lecture_title:
                            st.error("Please enter a lecture title.")
                        elif not lecture_description:
                            st.error("Please enter a lecture description.")
                        else:
                            # Store parameters and check for duplicates
                            st.session_state.lecture_params = {
                                "document_id": selected_doc_id,
                                "title": lecture_title,
                                "description": lecture_description,
                                "learning_outcomes": (
                                    learning_outcomes if learning_outcomes else None
                                ),
                                "course_id": selected_course_id,
                                "semester_id": selected_semester_id,
                                "selected_chapters": selected_chapters,
                            }
                            # Check for duplicates
                            check_for_duplicate(
                                selected_course_id,
                                selected_semester_id,
                                lecture_title,
                                learning_outcomes if learning_outcomes else None,
                                selected_chapters,
                            )

                # Handle duplicate outside of form
                if st.session_state.duplicate_data is not None:
                    handle_duplicate_ui()
                elif (
                    st.session_state.lecture_params is not None
                    and st.session_state.duplicate_data is None
                ):
                    # No duplicate, but we have params - means check completed and no duplicate found
                    # Only generate if we just checked (not on rerun)
                    if (
                        "just_checked" in st.session_state
                        and st.session_state.just_checked
                    ):
                        params = st.session_state.lecture_params
                        st.session_state.lecture_params = None  # Clear params
                        st.session_state.just_checked = False
                        generate_lecture(
                            params["document_id"],
                            params["title"],
                            params["description"],
                            params["learning_outcomes"],
                            params["course_id"],
                            params["semester_id"],
                            params["selected_chapters"],
                        )

            else:
                error_detail = response.json().get("detail", "Failed to load documents")
                st.error(f"Error loading documents: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


def check_for_duplicate(
    course_id, semester_id, title, learning_outcomes, selected_chapters=None
):
    """Check for duplicate lectures and store result in session state."""
    with st.spinner("🔍 Checking for duplicate lectures..."):
        try:
            # Check for duplicates
            duplicate_payload = {
                "course_id": course_id,
                "semester_id": semester_id,
                "title": title,
                "learning_outcomes": learning_outcomes,
                "selected_chapters": selected_chapters,
            }

            duplicate_response = requests.post(
                f"{API_BASE_URL}/lectures/check-duplicate",
                headers=get_auth_headers(),
                json=duplicate_payload,
            )

            if duplicate_response.status_code == 200:
                duplicate_data = duplicate_response.json()

                if duplicate_data["has_duplicate"]:
                    # Store duplicate data in session state
                    st.session_state.duplicate_data = duplicate_data[
                        "duplicate_lecture"
                    ]
                    st.session_state.just_checked = False
                    st.rerun()
                else:
                    # No duplicate found
                    st.session_state.duplicate_data = None
                    st.session_state.just_checked = True
                    st.rerun()
            else:
                st.error("Could not check for duplicates. Please try again.")
                st.session_state.lecture_params = None
        except Exception as e:
            st.error(f"Error checking for duplicates: {str(e)}")
            st.session_state.lecture_params = None


def handle_duplicate_ui():
    """Display duplicate lecture information with action buttons (outside form)."""
    duplicate_lecture = st.session_state.duplicate_data

    st.warning("⚠️ A lecture with the same title already exists for this course!")

    # Display duplicate lecture information
    st.markdown("---")
    st.subheader("📚 Existing Lecture Found")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Title:** {duplicate_lecture['title']}")
        st.write(f"**Status:** {duplicate_lecture['status']}")
        st.write(f"**Created:** {format_datetime(duplicate_lecture['created_at'])}")
    with col2:
        st.write(f"**File Name:** {duplicate_lecture['file_name']}")
        st.write(f"**File Size:** {format_file_size(duplicate_lecture['file_size'])}")
        if duplicate_lecture.get("learning_outcomes"):
            st.write(
                f"**Learning Outcomes:** {duplicate_lecture['learning_outcomes'][:100]}..."
            )

    if duplicate_lecture.get("description"):
        with st.expander("📄 View Description"):
            st.write(duplicate_lecture["description"])

    st.markdown("---")
    st.info(
        "💡 **You have two options:**\n"
        "1. Download the existing lecture\n"
        "2. Delete the existing lecture and generate a new one"
    )

    # Action buttons - now outside form!
    col1, col2, col3 = st.columns([1, 2, 2])

    with col2:
        if st.button(
            "📥 Download Existing Lecture",
            use_container_width=True,
            key="download_existing",
        ):
            download_url = duplicate_lecture["download_url"]
            st.markdown(
                f"""
                <a href="{download_url}" target="_blank">
                    <button style="
                        background-color: #4CAF50;
                        border: none;
                        color: white;
                        padding: 15px 32px;
                        text-align: center;
                        text-decoration: none;
                        display: inline-block;
                        font-size: 16px;
                        margin: 4px 2px;
                        cursor: pointer;
                        border-radius: 8px;
                        width: 100%;
                    ">
                        🔗 Click Here to Download
                    </button>
                </a>
                """,
                unsafe_allow_html=True,
            )
            st.success("✅ Click the button above to download the existing lecture.")

    with col3:
        if st.button(
            "🔄 Delete and Regenerate",
            use_container_width=True,
            type="primary",
            key="delete_regenerate",
        ):
            # Delete the existing lecture and regenerate
            params = st.session_state.lecture_params
            delete_and_regenerate_lecture(
                duplicate_lecture["lecture_id"],
                params["document_id"],
                params["title"],
                params["description"],
                params["learning_outcomes"],
                params["course_id"],
                params["semester_id"],
                params["selected_chapters"],
            )

    # Add cancel button
    if st.button("❌ Cancel", use_container_width=True):
        st.session_state.duplicate_data = None
        st.session_state.lecture_params = None
        st.rerun()


def delete_and_regenerate_lecture(
    lecture_id,
    document_id,
    title,
    description,
    learning_outcomes,
    course_id,
    semester_id,
    selected_chapters,
):
    """Delete existing lecture and generate new one."""
    with st.spinner("🗑️ Deleting existing lecture..."):
        try:
            delete_response = requests.delete(
                f"{API_BASE_URL}/lectures/{lecture_id}",
                headers=get_auth_headers(),
            )

            if delete_response.status_code == 204:
                st.success("✅ Existing lecture deleted successfully!")

                # Clear duplicate data
                st.session_state.duplicate_data = None
                st.session_state.lecture_params = None

                # Now generate new lecture
                generate_lecture(
                    document_id,
                    title,
                    description,
                    learning_outcomes,
                    course_id,
                    semester_id,
                    selected_chapters,
                )
            else:
                error_detail = delete_response.json().get(
                    "detail", "Failed to delete lecture"
                )
                st.error(f"Failed to delete existing lecture: {error_detail}")
        except Exception as e:
            st.error(f"Error deleting lecture: {str(e)}")


def generate_lecture(
    document_id,
    title,
    description,
    learning_outcomes,
    course_id,
    semester_id,
    selected_chapters=None,
):
    """Generate lecture from document."""
    with st.spinner("🤖 AI is generating your lecture... This may take a few minutes."):
        try:
            payload = {
                "document_id": document_id,
                "course_id": course_id,
                "semester_id": semester_id,
                "title": title,
                "description": description,
            }

            # Add learning outcomes if provided
            if learning_outcomes:
                payload["learning_outcomes"] = learning_outcomes

            # Add selected chapters if provided
            if selected_chapters:
                payload["selected_chapters"] = selected_chapters

            response = requests.post(
                f"{API_BASE_URL}/lectures/generate",
                headers=get_auth_headers(),
                json=payload,
            )

            if response.status_code == 201:
                lecture_data = response.json()
                st.success("✅ Lecture generated successfully!")

                # Display lecture information
                st.markdown("---")
                st.subheader("📚 Generated Lecture")

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Lecture ID:** {lecture_data['lecture_id']}")
                    st.write(f"**Title:** {lecture_data['title']}")
                    st.write(f"**Status:** {lecture_data['status']}")
                    st.write(
                        f"**PDF Size:** "
                        f"{format_file_size(lecture_data['pdf_size'])}"
                    )

                with col2:
                    st.write(f"**File Name:** {lecture_data['pdf_filename']}")
                    st.write(
                        f"**Content Length:** "
                        f"{lecture_data['content_length']} chars"
                    )
                    st.write(
                        f"**Created:** "
                        f"{format_datetime(lecture_data['created_at'])}"
                    )

                st.markdown("---")

                # Get download link
                show_lecture_download(lecture_data["lecture_id"])

            else:
                error_detail = response.json().get(
                    "detail", "Lecture generation failed"
                )
                st.error(f"Failed to generate lecture: {error_detail}")
        except Exception as e:
            st.error(f"Error generating lecture: {str(e)}")


def show_lecture_download(lecture_id):
    """Show download button for generated lecture."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/lectures/{lecture_id}/download",
            headers=get_auth_headers(),
        )

        if response.status_code == 200:
            download_data = response.json()
            download_url = download_data["download_url"]

            st.subheader("📥 Download Lecture")

            col1, col2, col3 = st.columns([2, 2, 2])

            with col2:
                st.markdown(
                    f"""
                    <a href="{download_url}" target="_blank">
                        <button style="
                            background-color: #4CAF50;
                            border: none;
                            color: white;
                            padding: 15px 32px;
                            text-align: center;
                            text-decoration: none;
                            display: inline-block;
                            font-size: 16px;
                            margin: 4px 2px;
                            cursor: pointer;
                            border-radius: 8px;
                            width: 100%;
                        ">
                            📥 Download PDF
                        </button>
                    </a>
                    """,
                    unsafe_allow_html=True,
                )

            st.info(
                f"💡 Click the button above to download your lecture: "
                f"**{download_data['file_name']}**"
            )

        else:
            st.error("Failed to get download link.")
    except Exception as e:
        st.error(f"Error fetching download link: {str(e)}")


# ==================== Entry Point ====================

if __name__ == "__main__":
    main()
