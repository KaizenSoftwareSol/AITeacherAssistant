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
        user_role = user.get('role', 'N/A')
        st.write(f"**Welcome, {user.get('username', 'User')}!**")
        st.write(f"Role: {user_role}")
        st.markdown("---")

        # Navigation based on role
        if user_role == "STUDENT":
            page = st.radio(
                "Navigation",
                ["📚 My Courses", "🎓 Enroll in Course", "💬 Chat History"],
                label_visibility="collapsed",
            )
        else:  # TEACHER or ADMIN
            page = st.radio(
                "Navigation",
                ["📄 Document Management", "🎯 Lecture Generation", "📚 Manage Lectures", "📋 Course Codes", "👥 Enrollments"],
                label_visibility="collapsed",
            )

        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            logout()

    # Show selected page based on role
    if user_role == "STUDENT":
        if page == "📚 My Courses":
            show_student_courses()
        elif page == "🎓 Enroll in Course":
            show_student_enrollment()
        elif page == "💬 Chat History":
            show_student_chat_history()
    else:  # TEACHER or ADMIN
        if page == "📄 Document Management":
            show_document_management()
        elif page == "🎯 Lecture Generation":
            show_lecture_generation()
        elif page == "📚 Manage Lectures":
            show_manage_lectures()
        elif page == "📋 Course Codes":
            show_teacher_course_codes()
        elif page == "👥 Enrollments":
            show_teacher_enrollments()


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


# ==================== Lecture Management ====================


def show_manage_lectures():
    """Show lecture management page for teachers."""
    st.title("📚 Manage Lectures")
    st.markdown("View, publish, and delete your lectures.")
    st.markdown("---")

    # Refresh button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    # Fetch teacher's lectures
    with st.spinner("Loading lectures..."):
        try:
            response = requests.get(
                f"{API_BASE_URL}/lectures/",
                headers=get_auth_headers(),
            )

            if response.status_code == 200:
                lectures = response.json()

                if not lectures:
                    st.info("No lectures found. Generate your first lecture!")
                    if st.button("🎯 Go to Lecture Generation"):
                        st.session_state['nav_page'] = "🎯 Lecture Generation"
                        st.rerun()
                    return

                # Group lectures by status
                generated = [l for l in lectures if l.get('status') == 'GENERATED']
                published = [l for l in lectures if l.get('status') == 'PUBLISHED']
                others = [l for l in lectures if l.get('status') not in ['GENERATED', 'PUBLISHED']]

                # Display summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Lectures", len(lectures))
                with col2:
                    st.metric("Published", len(published))
                with col3:
                    st.metric("Not Published", len(generated))

                st.markdown("---")

                # Tabs for different statuses
                tab1, tab2, tab3 = st.tabs([
                    f"📝 Not Published ({len(generated)})",
                    f"✅ Published ({len(published)})",
                    f"📋 All ({len(lectures)})"
                ])

                with tab1:
                    st.subheader("Not Published Lectures")
                    st.info("These lectures are not visible to students. Click 'Publish' to make them available.")
                    if generated:
                        display_lectures_list(generated, show_publish=True)
                    else:
                        st.info("All your lectures are published!")

                with tab2:
                    st.subheader("Published Lectures")
                    st.success("These lectures are visible to enrolled students.")
                    if published:
                        display_lectures_list(published, show_unpublish=True)
                    else:
                        st.info("No published lectures yet.")

                with tab3:
                    st.subheader("All Lectures")
                    display_lectures_list(lectures, show_publish=True, show_unpublish=True)

            else:
                error_detail = response.json().get("detail", "Failed to load lectures")
                st.error(f"Error: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


def display_lectures_list(lectures, show_publish=False, show_unpublish=False):
    """Display a list of lectures with actions."""
    for lecture in lectures:
        with st.expander(f"📄 {lecture.get('title', 'Untitled')} ({lecture.get('status', 'UNKNOWN')})"):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.write(f"**ID:** {lecture['id'][:8]}...")
                st.write(f"**Status:** {lecture.get('status', 'N/A')}")
                if lecture.get('description'):
                    st.write(f"**Description:** {lecture['description'][:100]}...")
                if lecture.get('chapter'):
                    st.write(f"**Chapter:** {lecture['chapter']}")
                st.write(f"**Created:** {format_datetime(lecture.get('created_at', ''))}")

            with col2:
                has_embeddings = "✅" if lecture.get('has_embeddings') else "❌"
                st.write(f"**RAG Ready:** {has_embeddings}")
                st.write(f"**Version:** {lecture.get('version', 1)}")

            st.markdown("---")

            # Action buttons
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("📥 Download", key=f"download_{lecture['id']}", use_container_width=True):
                    try:
                        dl_response = requests.get(
                            f"{API_BASE_URL}/lectures/{lecture['id']}/download",
                            headers=get_auth_headers(),
                        )
                        if dl_response.status_code == 200:
                            dl_data = dl_response.json()
                            st.markdown(
                                f'<a href="{dl_data["download_url"]}" target="_blank">'
                                f'<button style="background-color: #4CAF50; color: white; '
                                f'padding: 10px; border: none; border-radius: 5px; cursor: pointer;">'
                                f'Click to Download</button></a>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.error("Failed to get download link")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

            with col2:
                # Show publish button only for non-published lectures
                if show_publish and lecture.get('status') != 'PUBLISHED':
                    if st.button("✅ Publish", key=f"publish_{lecture['id']}", 
                               type="primary", use_container_width=True):
                        publish_lecture_action(lecture['id'], lecture.get('title'))

            with col3:
                # Show unpublish button only for published lectures
                if show_unpublish and lecture.get('status') == 'PUBLISHED':
                    if st.button("⏸️ Unpublish", key=f"unpublish_{lecture['id']}",
                               use_container_width=True):
                        unpublish_lecture_action(lecture['id'], lecture.get('title'))

            with col4:
                if st.button("🗑️ Delete", key=f"delete_{lecture['id']}", 
                           use_container_width=True):
                    # Store deletion request in session state for confirmation
                    st.session_state[f'confirm_delete_{lecture["id"]}'] = True
                    st.rerun()

            # Confirmation dialog for deletion
            if st.session_state.get(f'confirm_delete_{lecture["id"]}', False):
                st.warning(f"⚠️ Are you sure you want to delete '{lecture.get('title')}'? This action cannot be undone!")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ Yes, Delete", key=f"confirm_yes_{lecture['id']}",
                               type="primary", use_container_width=True):
                        delete_lecture_action(lecture['id'], lecture.get('title'))
                with col_no:
                    if st.button("❌ Cancel", key=f"confirm_no_{lecture['id']}",
                               use_container_width=True):
                        st.session_state.pop(f'confirm_delete_{lecture["id"]}', None)
                        st.rerun()


def publish_lecture_action(lecture_id, title):
    """Publish a lecture."""
    with st.spinner(f"Publishing '{title}'..."):
        try:
            response = requests.patch(
                f"{API_BASE_URL}/lectures/{lecture_id}/publish",
                headers=get_auth_headers(),
            )

            if response.status_code == 200:
                st.success(f"✅ '{title}' has been published and is now visible to students!")
                st.balloons()
                st.rerun()
            else:
                error_detail = response.json().get("detail", "Failed to publish lecture")
                st.error(f"Failed to publish: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


def unpublish_lecture_action(lecture_id, title):
    """Unpublish a lecture."""
    with st.spinner(f"Unpublishing '{title}'..."):
        try:
            response = requests.patch(
                f"{API_BASE_URL}/lectures/{lecture_id}/unpublish",
                headers=get_auth_headers(),
            )

            if response.status_code == 200:
                st.success(f"✅ '{title}' has been unpublished and is now hidden from students!")
                st.rerun()
            else:
                error_detail = response.json().get("detail", "Failed to unpublish lecture")
                st.error(f"Failed to unpublish: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


def delete_lecture_action(lecture_id, title):
    """Delete a lecture."""
    with st.spinner(f"Deleting '{title}'..."):
        try:
            response = requests.delete(
                f"{API_BASE_URL}/lectures/{lecture_id}",
                headers=get_auth_headers(),
            )

            if response.status_code == 204:
                st.success(f"✅ '{title}' has been deleted successfully!")
                # Clear the confirmation state
                st.session_state.pop(f'confirm_delete_{lecture_id}', None)
                st.rerun()
            else:
                error_detail = response.json().get("detail", "Failed to delete lecture")
                st.error(f"Failed to delete: {error_detail}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


# ==================== Teacher Course Code Management ====================


def show_teacher_course_codes():
    """Show teacher course code management."""
    st.title("📋 Course Codes")
    st.markdown("Manage enrollment codes for your courses. Share these codes with students.")
    st.markdown("---")
    
    try:
        # Fetch teacher's courses
        response = requests.get(
            f"{API_BASE_URL}/courses/",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            courses = response.json()
            
            if not courses:
                st.info("No courses found. Create courses in your system to see them here.")
                return
            
            # Display courses with codes
            st.subheader(f"Your Courses ({len(courses)} total)")
            
            for course in courses:
                with st.expander(f"📘 {course.get('name', 'Unnamed Course')}", expanded=False):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Course Code:** `{course.get('code', 'N/A')}`")
                        st.write(f"**Description:** {course.get('description', 'No description')}")
                        
                        # Get enrollment count
                        try:
                            enroll_response = requests.get(
                                f"{API_BASE_URL}/courses/{course['id']}/code",
                                headers=get_auth_headers()
                            )
                            if enroll_response.status_code == 200:
                                enroll_data = enroll_response.json()
                                st.write(f"**Enrolled Students:** {enroll_data.get('enrolled_students', 0)}")
                        except:
                            pass
                    
                    with col2:
                        st.code(course.get('code', 'N/A'), language='text')
                        if st.button(f"📋 Copy Code", key=f"copy_{course['id']}"):
                            st.toast(f"Code copied: {course.get('code', 'N/A')}")
                        
                        if st.button(f"✏️ Change Code", key=f"change_{course['id']}"):
                            st.session_state[f"edit_code_{course['id']}"] = True
                    
                    # Edit code form
                    if st.session_state.get(f"edit_code_{course['id']}", False):
                        with st.form(f"edit_code_form_{course['id']}"):
                            new_code = st.text_input(
                                "New Course Code",
                                value=course.get('code', ''),
                                max_chars=10,
                                help="4-10 characters, letters and numbers only"
                            )
                            
                            col_submit, col_cancel = st.columns(2)
                            with col_submit:
                                submit = st.form_submit_button("💾 Save", use_container_width=True)
                            with col_cancel:
                                cancel = st.form_submit_button("❌ Cancel", use_container_width=True)
                            
                            if submit:
                                if new_code and new_code != course.get('code'):
                                    try:
                                        update_response = requests.put(
                                            f"{API_BASE_URL}/courses/{course['id']}/code",
                                            headers=get_auth_headers(),
                                            json={"new_code": new_code.upper()}
                                        )
                                        
                                        if update_response.status_code == 200:
                                            st.success(f"✅ Course code updated to: {new_code.upper()}")
                                            st.session_state.pop(f"edit_code_{course['id']}", None)
                                            st.rerun()
                                        else:
                                            error_msg = update_response.json().get('detail', 'Update failed')
                                            st.error(f"Failed to update code: {error_msg}")
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                            
                            if cancel:
                                st.session_state.pop(f"edit_code_{course['id']}", None)
                                st.rerun()
                    
                    st.markdown("---")
                    st.markdown(
                        f"💡 **Share this code with students:** "
                        f"Tell students to use code `{course.get('code', 'N/A')}` to enroll in this course."
                    )
        
        else:
            st.error("Failed to fetch courses.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


def show_teacher_enrollments():
    """Show enrolled students for teacher's courses."""
    st.title("👥 Course Enrollments")
    st.markdown("View students enrolled in your courses.")
    st.markdown("---")
    
    try:
        # Fetch teacher's courses
        response = requests.get(
            f"{API_BASE_URL}/courses/",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            courses = response.json()
            
            if not courses:
                st.info("No courses found.")
                return
            
            # Course selector
            course_options = {f"{c['name']} ({c['code']})": c['id'] for c in courses}
            selected_course_name = st.selectbox("Select Course", list(course_options.keys()))
            selected_course_id = course_options[selected_course_name]
            
            # Fetch enrollments
            enroll_response = requests.get(
                f"{API_BASE_URL}/courses/{selected_course_id}/enrollments",
                headers=get_auth_headers()
            )
            
            if enroll_response.status_code == 200:
                enroll_data = enroll_response.json()
                students = enroll_data.get('students', [])
                
                st.subheader(f"📚 {enroll_data.get('course_name', 'Course')}")
                st.write(f"**Course Code:** `{enroll_data.get('course_code', 'N/A')}`")
                st.write(f"**Total Students:** {enroll_data.get('total_students', 0)}")
                st.markdown("---")
                
                if students:
                    # Display students in a table
                    import pandas as pd
                    
                    df = pd.DataFrame([
                        {
                            "Name": s.get('name', 'N/A'),
                            "Email": s.get('email', 'N/A'),
                            "Enrolled": format_datetime(s.get('enrolled_at', ''))
                        }
                        for s in students
                    ])
                    
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Download button
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Student List (CSV)",
                        data=csv,
                        file_name=f"enrollments_{enroll_data.get('course_code', 'course')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No students enrolled yet. Share the course code with students to enroll.")
            
            else:
                st.error("Failed to fetch enrollments.")
        
        else:
            st.error("Failed to fetch courses.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


# ==================== Student Pages ====================


def show_student_enrollment():
    """Show student course enrollment page."""
    st.title("🎓 Enroll in Course")
    st.markdown("Enter the course code provided by your teacher to enroll.")
    st.markdown("---")
    
    with st.form("enrollment_form"):
        st.subheader("Enter Course Code")
        course_code = st.text_input(
            "Course Code",
            placeholder="e.g., CS101, MATH201",
            help="Get this code from your teacher",
            max_chars=10
        ).upper()
        
        submit = st.form_submit_button("✅ Enroll", use_container_width=True)
        
        if submit:
            if not course_code:
                st.error("Please enter a course code.")
            else:
                with st.spinner("Enrolling..."):
                    try:
                        response = requests.post(
                            f"{API_BASE_URL}/student/enroll",
                            headers=get_auth_headers(),
                            json={"course_code": course_code}
                        )
                        
                        if response.status_code == 201 or response.status_code == 200:
                            data = response.json()
                            st.success(f"✅ {data.get('message', 'Enrolled successfully!')}")
                            st.balloons()
                            st.info(f"**Course:** {data.get('course_name', 'N/A')}")
                            st.info(f"**Course Code:** {data.get('course_code', 'N/A')}")
                            
                            # Show link to courses
                            st.markdown("---")
                            if st.button("📚 Go to My Courses"):
                                st.session_state['nav_page'] = "📚 My Courses"
                                st.rerun()
                        else:
                            error_msg = response.json().get('detail', 'Enrollment failed')
                            st.error(f"❌ {error_msg}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")


def show_student_courses():
    """Show student's enrolled courses and lectures."""
    st.title("📚 My Courses")
    st.markdown("View your enrolled courses and access lectures.")
    st.markdown("---")
    
    try:
        # Fetch student's courses
        response = requests.get(
            f"{API_BASE_URL}/student/my-courses",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            courses = response.json()
            
            if not courses:
                st.info("📝 You're not enrolled in any courses yet.")
                if st.button("🎓 Enroll in a Course"):
                    st.session_state['nav_page'] = "🎓 Enroll in Course"
                    st.rerun()
                return
            
            # Display courses
            st.subheader(f"Your Courses ({len(courses)} total)")
            
            for course in courses:
                with st.expander(f"📘 {course.get('display_name', 'Course')}", expanded=False):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Course:** {course.get('course_name', 'N/A')}")
                        st.write(f"**Teacher:** {course.get('teacher_name', 'N/A')}")
                        st.write(f"**Code:** `{course.get('course_code', 'N/A')}`")
                        if course.get('course_description'):
                            st.write(f"**Description:** {course['course_description']}")
                    
                    with col2:
                        st.metric("Lectures", course.get('published_lectures', 0))
                        st.caption(f"Enrolled: {format_datetime(course.get('enrolled_at', ''))}")
                    
                    st.markdown("---")
                    
                    # Fetch and display lectures
                    if st.button(f"📖 View Lectures", key=f"view_lectures_{course['course_id']}"):
                        st.session_state['selected_course'] = course
                        st.session_state['show_lectures'] = True
                    
                    if st.session_state.get('selected_course', {}).get('course_id') == course['course_id'] and st.session_state.get('show_lectures'):
                        show_student_lectures(course['course_id'])
            
        else:
            st.error("Failed to fetch courses.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


def show_student_lectures(course_id):
    """Show lectures for a specific course."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/student/courses/{course_id}/lectures",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            course_info = data.get('course_info', {})
            lectures = data.get('lectures', [])
            
            st.markdown("### 📖 Lectures")
            
            if not lectures:
                st.info("No lectures available yet.")
                return
            
            for lecture in lectures:
                with st.container():
                    st.markdown(f"#### {lecture.get('title', 'Untitled')}")
                    
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        if lecture.get('description'):
                            st.write(lecture['description'])
                        if lecture.get('chapter'):
                            st.caption(f"📚 Chapter: {lecture['chapter']}")
                    
                    with col2:
                        has_rag = lecture.get('has_embeddings', False)
                        if has_rag:
                            st.success("✅ AI Chat Ready")
                        else:
                            st.warning("⚠️ Chat Disabled")
                    
                    with col3:
                        if st.button("🔍 Open", key=f"open_lecture_{lecture['lecture_id']}"):
                            st.session_state['selected_lecture'] = lecture
                            st.session_state['show_lecture_detail'] = True
                    
                    # Show quick enable button if RAG not available
                    if not has_rag:
                        if st.button(
                            "🚀 Enable AI Chat", 
                            key=f"enable_chat_{lecture['lecture_id']}",
                            use_container_width=True
                        ):
                            with st.spinner("Generating embeddings..."):
                                try:
                                    embed_response = requests.post(
                                        f"{API_BASE_URL}/student/lectures/{lecture['lecture_id']}/generate-embeddings",
                                        headers=get_auth_headers()
                                    )
                                    
                                    if embed_response.status_code == 200:
                                        result = embed_response.json()
                                        st.success("✅ AI Chat enabled!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to enable chat")
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
                    
                    st.markdown("---")
            
            # Show lecture detail if selected
            if st.session_state.get('show_lecture_detail') and st.session_state.get('selected_lecture'):
                show_lecture_detail(st.session_state['selected_lecture'])
        
        else:
            st.error("Failed to fetch lectures.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


def show_lecture_detail(lecture):
    """Show detailed view of a lecture with summary, chat, flashcards, and quiz."""
    st.markdown("---")
    st.markdown(f"## 📄 {lecture.get('title', 'Lecture')}")
    
    # Tabs for summary, flashcards, chat, and quiz
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Summary", "🗂️ Flashcards", "💬 Chat", "📊 Quiz"])
    
    with tab1:
        show_lecture_summary(lecture['lecture_id'])
    
    with tab2:
        show_lecture_flashcards(lecture['lecture_id'], lecture.get('title', 'Lecture'))
    
    with tab3:
        show_lecture_chat(lecture['lecture_id'], lecture.get('title', 'Lecture'))
    
    with tab4:
        show_lecture_quiz(lecture['lecture_id'], lecture.get('title', 'Lecture'))


def show_lecture_flashcards(lecture_id, lecture_title):
    """Show flashcards for quick review and study."""
    st.subheader("🗂️ Flashcards")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/student/lectures/{lecture_id}/flashcards",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            flashcards = data.get('flashcards', [])
            
            if not flashcards:
                st.info("No flashcards available yet.")
                return
            
            # Show stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Cards", data.get('total_flashcards', 0))
            with col2:
                difficulties = data.get('by_difficulty', {})
                st.write("**By Difficulty:**")
                for diff, count in difficulties.items():
                    st.caption(f"{diff}: {count}")
            with col3:
                topics = data.get('by_topic', {})
                st.write("**Topics:**")
                for topic, count in list(topics.items())[:3]:
                    st.caption(f"{topic}: {count}")
            
            st.markdown("---")
            
            # Filter by difficulty
            filter_diff = st.selectbox(
                "Filter by difficulty",
                ["All", "EASY", "MEDIUM", "HARD"],
                key=f"diff_filter_{lecture_id}"
            )
            
            # Filter flashcards
            if filter_diff != "All":
                flashcards = [f for f in flashcards if f['difficulty'] == filter_diff]
            
            if not flashcards:
                st.info(f"No {filter_diff} flashcards available.")
                return
            
            st.info(f"💡 **Tip:** Click on a card to flip it and see the answer!")
            
            # Initialize session state for flipped cards
            if f'flipped_cards_{lecture_id}' not in st.session_state:
                st.session_state[f'flipped_cards_{lecture_id}'] = set()
            
            # Display flashcards in a grid
            for i in range(0, len(flashcards), 2):
                col1, col2 = st.columns(2)
                
                for col, card_idx in [(col1, i), (col2, i+1)]:
                    if card_idx < len(flashcards):
                        card = flashcards[card_idx]
                        card_id = f"{lecture_id}_{card['id']}"
                        
                        with col:
                            # Determine if card is flipped
                            is_flipped = card_id in st.session_state[f'flipped_cards_{lecture_id}']
                            
                            # Card container
                            with st.container():
                                # Difficulty badge
                                diff_color = {
                                    "EASY": "🟢",
                                    "MEDIUM": "🟡",
                                    "HARD": "🔴"
                                }.get(card['difficulty'], "⚪")
                                
                                st.caption(f"{diff_color} {card['difficulty']} | {card['topic']}")
                                
                                # Show question or answer based on flip state
                                if not is_flipped:
                                    st.markdown(f"**Q:** {card['question']}")
                                    if st.button("🔄 Show Answer", key=f"flip_{card_id}", use_container_width=True):
                                        st.session_state[f'flipped_cards_{lecture_id}'].add(card_id)
                                        st.rerun()
                                else:
                                    st.markdown(f"**A:** {card['answer']}")
                                    if st.button("🔄 Show Question", key=f"unflip_{card_id}", use_container_width=True):
                                        st.session_state[f'flipped_cards_{lecture_id}'].remove(card_id)
                                        st.rerun()
                                
                                st.markdown("---")
            
            # Reset button
            if st.button("🔄 Reset All Cards", use_container_width=True):
                st.session_state[f'flipped_cards_{lecture_id}'] = set()
                st.rerun()
        
        elif response.status_code == 404:
            st.info("📝 **Flashcards are being generated...**")
            st.markdown("Flashcards are created when the lecture is published. This usually takes a minute.")
        else:
            st.error("Failed to load flashcards.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


def show_lecture_summary(lecture_id):
    """Show lecture summary."""
    st.subheader("📝 Lecture Summary")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/student/lectures/{lecture_id}/summary",
            headers=get_auth_headers()
        )
        
        if response.status_code == 200:
            data = response.json()
            summary = data.get('summary', 'No summary available.')
            
            st.markdown(summary)
            
            st.markdown("---")
            st.caption(f"Generated: {format_datetime(data.get('generated_at', ''))}")
            
            if st.button("🔄 Regenerate Summary"):
                with st.spinner("Regenerating summary..."):
                    regen_response = requests.get(
                        f"{API_BASE_URL}/student/lectures/{lecture_id}/summary?regenerate=true",
                        headers=get_auth_headers()
                    )
                    if regen_response.status_code == 200:
                        st.success("Summary regenerated!")
                        st.rerun()
        else:
            st.error("Failed to fetch summary.")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")


def show_lecture_chat(lecture_id, lecture_title):
    """Show lecture chatbot interface."""
    st.subheader("💬 Ask Questions About This Lecture")
    
    # Check if embeddings exist for this lecture
    try:
        # Get lecture info including has_embeddings status
        lecture_response = requests.get(
            f"{API_BASE_URL}/student/courses/{st.session_state.get('selected_course', {}).get('course_id', 'unknown')}/lectures",
            headers=get_auth_headers()
        )
        
        has_embeddings = False
        if lecture_response.status_code == 200:
            data = lecture_response.json()
            lectures = data.get('lectures', [])
            current_lecture = next((l for l in lectures if l['lecture_id'] == lecture_id), None)
            if current_lecture:
                has_embeddings = current_lecture.get('has_embeddings', False)
        
        # Show embedding status and generation button if needed
        if not has_embeddings:
            st.warning("⚠️ **AI Chat is not yet enabled for this lecture**")
            st.info(
                "To chat with the AI about this lecture, you need to enable the RAG (Retrieval-Augmented Generation) feature. "
                "This will analyze the lecture content and prepare it for intelligent Q&A."
            )
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🚀 Enable AI Chat (Generate Embeddings)", use_container_width=True, type="primary"):
                    with st.spinner("🔄 Analyzing lecture content... This may take 30-60 seconds..."):
                        try:
                            embed_response = requests.post(
                                f"{API_BASE_URL}/student/lectures/{lecture_id}/generate-embeddings",
                                headers=get_auth_headers()
                            )
                            
                            if embed_response.status_code == 200:
                                result = embed_response.json()
                                st.success(f"✅ {result.get('message', 'Chat enabled!')}")
                                st.balloons()
                                st.info(f"📊 Created {result.get('chunks_created', 0)} knowledge chunks for intelligent search")
                                st.rerun()
                            else:
                                error_msg = embed_response.json().get('detail', 'Failed to generate embeddings')
                                st.error(f"❌ {error_msg}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            
            st.markdown("---")
            st.caption("💡 **Note:** Embeddings only need to be generated once. After that, you and other students can chat instantly!")
            return
        
        # Show chat is ready
        st.success("✅ AI Chat is enabled for this lecture!")
    
    except Exception as e:
        st.warning(f"Could not check embedding status: {str(e)}")
    
    # Initialize chat history in session state
    if f'chat_messages_{lecture_id}' not in st.session_state:
        st.session_state[f'chat_messages_{lecture_id}'] = []
        
        # Load chat history from API
        try:
            response = requests.get(
                f"{API_BASE_URL}/student/lectures/{lecture_id}/chat-history",
                headers=get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get('messages', [])
                for msg in messages:
                    st.session_state[f'chat_messages_{lecture_id}'].append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
        except:
            pass
    
    # Display chat messages
    for message in st.session_state[f'chat_messages_{lecture_id}']:
        role = message['role']
        if role == 'USER':
            with st.chat_message("user"):
                st.write(message['content'])
        elif role == 'ASSISTANT':
            with st.chat_message("assistant"):
                st.write(message['content'])
        elif role == 'SYSTEM':
            with st.chat_message("assistant", avatar="📊"):
                st.info(message['content'])
    
    # Chat input
    if prompt := st.chat_input("Ask a question about the lecture..."):
        # Add user message
        st.session_state[f'chat_messages_{lecture_id}'].append({
            'role': 'USER',
            'content': prompt
        })
        
        # Display user message
        with st.chat_message("user"):
            st.write(prompt)
        
        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/student/lectures/{lecture_id}/chat",
                        headers=get_auth_headers(),
                        json={"content": prompt}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        answer = data.get('response', 'No response')
                        sources = data.get('sources', [])
                        
                        st.write(answer)
                        
                        if sources:
                            with st.expander("📚 Sources"):
                                for idx, source in enumerate(sources[:3], 1):
                                    st.caption(f"**Source {idx}:** {source.get('preview', '')}")
                        
                        # Add assistant message
                        st.session_state[f'chat_messages_{lecture_id}'].append({
                            'role': 'ASSISTANT',
                            'content': answer
                        })
                    else:
                        error_msg = response.json().get('detail', 'Failed to get response')
                        st.error(f"Error: {error_msg}")
                
                except Exception as e:
                    st.error(f"Error: {str(e)}")


def show_lecture_quiz(lecture_id, lecture_title):
    """Show quiz generation and taking interface."""
    st.subheader("📊 Quiz")
    
    # Check if quiz exists in session
    if f'quiz_{lecture_id}' not in st.session_state:
        # Try to load saved quiz first
        try:
            response = requests.get(
                f"{API_BASE_URL}/student/lectures/{lecture_id}/quiz",
                headers=get_auth_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                st.session_state[f'quiz_{lecture_id}'] = data
                st.session_state[f'quiz_answers_{lecture_id}'] = {}
                st.session_state[f'quiz_type_{lecture_id}'] = 'saved'  # Mark as saved quiz
                st.rerun()
            elif response.status_code == 404:
                # No saved quiz available yet
                st.info("📝 **Quiz is being generated...**")
                st.markdown(
                    "The quiz for this lecture is still being created. "
                    "This usually takes a minute after the lecture is published."
                )
                st.markdown("---")
                st.markdown("**Want to practice now?**")
                
                # Option to generate temporary quiz
                with st.form(f"quiz_gen_form_{lecture_id}"):
                    st.caption("Generate a practice quiz (results won't be saved)")
                    num_questions = st.slider("Number of Questions", 5, 20, 10)
                    difficulty = st.selectbox("Difficulty", ["EASY", "MEDIUM", "HARD"])
                    
                    submit = st.form_submit_button("🎯 Generate Practice Quiz", use_container_width=True)
                    
                    if submit:
                        with st.spinner("Generating practice quiz..."):
                            try:
                                response = requests.post(
                                    f"{API_BASE_URL}/student/lectures/{lecture_id}/generate-quiz",
                                    headers=get_auth_headers(),
                                    json={
                                        "lecture_id": lecture_id,
                                        "num_questions": num_questions,
                                        "difficulty": difficulty,
                                        "question_types": ["MULTIPLE_CHOICE"]
                                    }
                                )
                                
                                if response.status_code == 200:
                                    data = response.json()
                                    st.session_state[f'quiz_{lecture_id}'] = data
                                    st.session_state[f'quiz_answers_{lecture_id}'] = {}
                                    st.session_state[f'quiz_type_{lecture_id}'] = 'temporary'
                                    st.success("Practice quiz generated!")
                                    st.rerun()
                                else:
                                    st.error("Failed to generate quiz.")
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                return
            else:
                st.error("Failed to load quiz.")
                return
        except Exception as e:
            st.error(f"Error loading quiz: {str(e)}")
            return
    
    else:
        # Display quiz
        quiz_data = st.session_state[f'quiz_{lecture_id}']
        questions = quiz_data.get('questions', [])
        quiz_type = st.session_state.get(f'quiz_type_{lecture_id}', 'saved')
        
        if f'quiz_submitted_{lecture_id}' not in st.session_state:
            # Quiz taking interface
            if quiz_type == 'saved':
                st.success("✅ **Official Quiz** - Your results will be recorded")
            else:
                st.info("🎯 **Practice Quiz** - Results won't be saved (for practice only)")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{quiz_data.get('title', 'Quiz')}**")
                st.caption(f"Questions: {len(questions)} | Time Limit: {quiz_data.get('time_limit', 30)} minutes")
            
            with col2:
                # Add regenerate button
                if st.button("🔄 New Practice Quiz", help="Generate a different quiz for practice"):
                    with st.spinner("Generating new practice quiz..."):
                        try:
                            response = requests.post(
                                f"{API_BASE_URL}/student/lectures/{lecture_id}/generate-quiz",
                                headers=get_auth_headers(),
                                json={
                                    "lecture_id": lecture_id,
                                    "num_questions": 10,
                                    "difficulty": "MEDIUM",
                                    "question_types": ["MULTIPLE_CHOICE"]
                                }
                            )
                            
                            if response.status_code == 200:
                                data = response.json()
                                st.session_state[f'quiz_{lecture_id}'] = data
                                st.session_state[f'quiz_answers_{lecture_id}'] = {}
                                st.session_state[f'quiz_type_{lecture_id}'] = 'temporary'
                                st.session_state.pop(f'quiz_submitted_{lecture_id}', None)
                                st.session_state.pop(f'quiz_result_{lecture_id}', None)
                                st.success("New practice quiz generated!")
                                st.rerun()
                            else:
                                st.error("Failed to generate new quiz.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            
            st.markdown("---")
            
            with st.form(f"quiz_form_{lecture_id}"):
                answers = {}
                
                for idx, q in enumerate(questions, 1):
                    st.markdown(f"**Question {idx}:** {q.get('question_text', '')}")
                    
                    options = q.get('options', [])
                    answer = st.radio(
                        f"Select answer for Q{idx}:",
                        options,
                        key=f"q_{idx}_{lecture_id}",
                        label_visibility="collapsed"
                    )
                    answers[f"q_{idx}"] = answer
                    
                    st.markdown("---")
                
                submit_quiz = st.form_submit_button("✅ Submit Quiz", use_container_width=True)
                
                if submit_quiz:
                    with st.spinner("Grading quiz..."):
                        try:
                            # Check if this is a temporary quiz
                            if quiz_type == 'temporary' or quiz_data.get('is_temporary'):
                                # For temporary quizzes, just show results without saving
                                st.warning("⚠️ This is a practice quiz. Results will not be recorded.")
                                st.session_state[f'quiz_result_{lecture_id}'] = {
                                    "is_practice": True,
                                    "message": "Practice quiz - results not saved",
                                    "answers": answers
                                }
                                st.session_state[f'quiz_submitted_{lecture_id}'] = True
                                st.rerun()
                            else:
                                # For saved quizzes, submit to backend
                                # Map answers using question IDs (required by backend)
                                answer_dict = {}
                                for idx, q in enumerate(questions, 1):
                                    # Saved quizzes have 'question_id' field
                                    question_id = q.get('question_id', q.get('id'))
                                    if question_id:
                                        answer_dict[question_id] = answers.get(f"q_{idx}", '')
                                
                                # Debug: Show number of answers being submitted
                                st.info(f"Submitting {len(answer_dict)} answers...")
                                
                                response = requests.post(
                                    f"{API_BASE_URL}/student/assessments/{quiz_data['assessment_id']}/submit",
                                    headers=get_auth_headers(),
                                    json={"answers": answer_dict}
                                )
                                
                                if response.status_code == 200:
                                    result = response.json()
                                    st.session_state[f'quiz_result_{lecture_id}'] = result
                                    st.session_state[f'quiz_submitted_{lecture_id}'] = True
                                    st.rerun()
                                else:
                                    st.error("Failed to submit quiz.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
        
        else:
            # Show quiz results
            result = st.session_state.get(f'quiz_result_{lecture_id}', {})
            
            st.success("✅ Quiz Submitted!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Score", f"{result.get('score', 0)}/{result.get('max_score', 0)}")
            with col2:
                st.metric("Percentage", f"{result.get('percentage', 0):.1f}%")
            with col3:
                status = "✅ Passed" if result.get('passed', False) else "❌ Not Passed"
                st.metric("Status", status)
            
            st.markdown("---")
            
            # Weak areas
            weak_areas = result.get('weak_areas', [])
            if weak_areas:
                st.subheader("📚 Topics to Review")
                for area in weak_areas:
                    st.write(f"• {area}")
                
                st.info("💡 The chatbot now knows your weak areas and can help you with these topics!")
            
            # Detailed results
            with st.expander("📊 Detailed Results"):
                for idx, q_result in enumerate(result.get('question_results', []), 1):
                    is_correct = q_result.get('is_correct', False)
                    icon = "✅" if is_correct else "❌"
                    
                    st.markdown(f"**{icon} Question {idx}:** {q_result.get('question_text', '')}")
                    st.write(f"Your answer: {q_result.get('student_answer', 'N/A')}")
                    st.write(f"Correct answer: {q_result.get('correct_answer', 'N/A')}")
                    
                    if q_result.get('explanation'):
                        st.caption(f"💡 {q_result['explanation']}")
                    
                    st.markdown("---")
            
            # Reset button
            if st.button("🔄 Take Another Quiz"):
                st.session_state.pop(f'quiz_{lecture_id}', None)
                st.session_state.pop(f'quiz_submitted_{lecture_id}', None)
                st.session_state.pop(f'quiz_result_{lecture_id}', None)
                st.rerun()


def show_student_chat_history():
    """Show all chat conversations for student."""
    st.title("💬 Chat History")
    st.markdown("View your previous conversations with lecture chatbots.")
    st.markdown("---")
    
    st.info("📝 Chat history is maintained per lecture. Go to a specific lecture to view and continue your conversation.")


# ==================== Entry Point ====================

if __name__ == "__main__":
    main()
