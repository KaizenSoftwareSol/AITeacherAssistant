# AI Teacher Assistant - Streamlit Application

A modern web interface for the AI Teacher Assistant platform that enables teachers to manage documents and generate AI-powered lecture materials.

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- Backend API running on `http://localhost:8001`
- Teacher account with valid credentials

### Installation

1. **Ensure dependencies are installed**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the backend API** (in a separate terminal):
   ```bash
   python run.py
   ```

3. **Launch the Streamlit app**:
   ```bash
   streamlit run streamlit_app/app.py
   ```

4. **Access the application**:
   - Open your browser to `http://localhost:8501`
   - Login with your teacher credentials

## 📋 Features

### 🔐 Authentication
- Secure login with email and password
- JWT token-based session management
- Automatic user profile loading
- Persistent session until logout

### 📄 Document Management

#### Upload Documents
- **File Upload**: Support for PDF, PPTX, and DOCX files
- **Website Upload**: Extract content from any public URL
- **Metadata**: Add title and description for each document
- **Real-time Processing**: Track document processing status

#### View Documents
- List all your uploaded documents
- View document details (type, status, size, timestamps)
- Filter by processing status
- Refresh to see latest updates

### 🎯 Lecture Generation

#### Smart Selection
- **Document Selection**: Choose from completed documents
- **Chapter Selection**: Select specific chapters from PDF documents
- **Course Selection**: Dropdown menu of your university's courses
- **Semester Selection**: Dynamically filtered by selected course
- No manual UUID entry required!

#### AI-Powered Generation
- Provide lecture title and description
- **Learning Outcomes**: Define what students should learn (optional)
- **Duplicate Detection**: Automatically checks for existing lectures
- AI generates comprehensive lecture content
- Output in professional PDF format
- Download with one click

#### Duplicate Handling
- Automatic duplicate detection before generation
- Shows existing lecture details if duplicate found
- Two options when duplicate exists:
  - **Download Existing**: Get the already-generated lecture
  - **Delete & Regenerate**: Remove old lecture and create new one

## 📖 Usage Guide

### 1. Login

1. Navigate to `http://localhost:8501`
2. Enter your teacher credentials:
   - **Email**: Your registered email
   - **Password**: Your password
3. Click **Login**

### 2. Upload Documents

#### Upload a File
1. Go to **"📄 Document Management"**
2. Click **"📤 Upload File"** tab
3. Choose your file (PDF, PPTX, or DOCX)
4. Enter a **Title**
5. Optionally add a **Description**
6. Click **"Upload Document"**
7. Wait for processing to complete

#### Upload a Website
1. Go to **"📄 Document Management"**
2. Click **"🌐 Upload Website"** tab
3. Enter the **Website URL**
4. Enter a **Title**
5. Optionally add a **Description**
6. Click **"Upload Website"**
7. Wait for content extraction

### 3. View Your Documents

1. Go to **"📄 Document Management"**
2. Click **"📚 My Documents"** tab
3. View all your documents with details
4. Click **🔄 Refresh** to update the list
5. Expand any document to see full information

### 4. Generate Lectures

1. Go to **"🎯 Lecture Generation"**
2. **Select a Document** from the dropdown
   - Only completed documents are available
3. **Select Chapters** (for PDF documents)
   - Choose specific chapters or use all content
   - See word count for each chapter
4. **Select a Course** from the dropdown
   - Shows all courses in your university
5. **Select a Semester** from the dropdown
   - Automatically filtered for the selected course
6. Enter **Lecture Title**
7. Enter **Lecture Description**
   - Provide context for the AI
   - Specify what topics to cover
   - Mention target audience
8. Enter **Learning Outcomes** (optional)
   - Define what students should learn
   - List specific skills or knowledge
   - Use clear, measurable objectives
9. Click **"🚀 Generate Lecture"**
10. **If duplicate detected**:
    - Review existing lecture details
    - Choose to download existing OR delete and regenerate
11. Wait for AI generation (1-3 minutes)
12. Click **"📥 Download PDF"** to download

### 5. Handle Duplicate Lectures

When you try to generate a lecture that already exists:

1. The system automatically detects duplicates based on:
   - Same title
   - Same course and semester
   - Same learning outcomes
   - Same selected chapters
2. You'll see details of the existing lecture
3. **Option 1: Download Existing**
   - Click "📥 Download Existing Lecture"
   - Get the already-generated PDF
4. **Option 2: Delete & Regenerate**
   - Click "🔄 Delete and Regenerate"
   - Old lecture is deleted
   - New lecture is generated with fresh AI content

## 🎓 Best Practices

### Document Upload
- ✅ Use clear, descriptive titles
- ✅ Add meaningful descriptions
- ✅ Ensure documents are well-formatted
- ✅ Wait for "COMPLETED" status before using for lectures

### Lecture Description
- ✅ Be specific about topics to cover
- ✅ Mention the target audience (e.g., "undergraduate students")
- ✅ Specify desired depth level (introductory, advanced, etc.)
- ✅ Include any specific requirements or focus areas

**Example**:
```
Create a comprehensive lecture on machine learning fundamentals. 
Cover supervised and unsupervised learning with practical examples. 
Target audience: Computer Science undergraduate students. 
Include: definitions, algorithms, real-world applications, and examples.
```

### Learning Outcomes
- ✅ Use action verbs (understand, apply, analyze, create)
- ✅ Be specific and measurable
- ✅ Focus on student capabilities
- ✅ List 3-5 key outcomes

**Example**:
```
By the end of this lecture, students will be able to:
1. Understand and explain supervised vs unsupervised learning
2. Identify appropriate algorithms for different problem types
3. Implement basic machine learning models using Python
4. Evaluate model performance using common metrics
5. Apply machine learning concepts to real-world scenarios
```

### Avoiding Duplicates
- ✅ Check learning outcomes carefully - small changes create new lectures
- ✅ Use consistent naming conventions for similar lectures
- ✅ Review existing lectures before creating new ones
- ✅ Take advantage of duplicate detection to reuse content

## ⚙️ Configuration

### API Base URL

The app connects to the backend at `http://localhost:8001/api/v1` by default.

To change this, modify the `API_BASE_URL` variable in `app.py`:

```python
API_BASE_URL = "http://localhost:8001/api/v1"
```

### Supported File Types

- **PDF** (.pdf) - Best for text-heavy documents
- **PowerPoint** (.pptx) - Presentations and slides
- **Word** (.docx) - Documents and reports
- **Websites** (URLs) - Any public webpage

## 🔧 Troubleshooting

### Cannot Connect to Server
**Problem**: "Cannot connect to the server" error

**Solution**:
1. Check if backend API is running: `python run.py`
2. Verify backend is on port 8001
3. Check the API_BASE_URL in app.py
4. Ensure no firewall is blocking the connection

### Login Fails
**Problem**: "Login failed" or "Incorrect credentials"

**Solution**:
1. Verify email and password are correct
2. Ensure you have a teacher account
3. Check if user account is active
4. Review backend logs for detailed errors

### No Documents Showing
**Problem**: "No documents found" in My Documents tab

**Solution**:
1. Click the **🔄 Refresh** button
2. Verify you're logged in as the correct user
3. Check if documents belong to your teacher profile
4. Ensure documents were uploaded successfully
5. Open browser DevTools (F12) to check API responses

### No Courses/Semesters Available
**Problem**: "No courses found" or "No semesters found"

**Solution**:
1. Ensure courses exist in your university's database
2. Verify semesters are created for your courses
3. Contact your administrator to create courses/semesters
4. Check that your teacher profile has correct university_id

### Document Upload Fails
**Problem**: Upload fails or takes too long

**Solution**:
1. Check file size (very large files may take longer)
2. Verify file format is supported (PDF, PPTX, DOCX)
3. Ensure Supabase storage is configured correctly
4. Check backend logs for detailed errors
5. Try with a smaller file first

### Lecture Generation Fails
**Problem**: Generation fails or times out

**Solution**:
1. Verify document status is "COMPLETED"
2. Check OpenAI API key is configured in backend
3. Ensure course_id and semester_id are valid
4. Try with a shorter/simpler document
5. Review backend logs for detailed errors

### Duplicate Detection Issues
**Problem**: Duplicate not detected or wrong lecture shown

**Solution**:
1. Duplicates match on: title, course, semester, learning outcomes
2. Description is NOT compared (intentionally)
3. Check that learning outcomes match exactly
4. Selected chapters must match for duplicate detection
5. Case and whitespace matter in comparisons

### Session Expired
**Problem**: Suddenly logged out or "Unauthorized" errors

**Solution**:
1. JWT tokens expire after 30 minutes
2. Simply login again
3. Session state is cleared on logout
4. Browser refresh may clear session

## 🏗️ Technical Details

### Architecture
- **Frontend**: Streamlit (Python web framework)
- **Backend**: FastAPI REST API
- **Authentication**: JWT Bearer tokens
- **Storage**: Supabase (documents and files)
- **AI**: OpenAI GPT-4 for lecture generation

### API Endpoints Used
- `POST /api/v1/auth/login` - User authentication
- `GET /api/v1/auth/me` - Get user profile
- `POST /api/v1/documents/upload/file` - Upload file
- `POST /api/v1/documents/upload/website` - Upload website
- `GET /api/v1/documents/` - List documents
- `GET /api/v1/documents/{id}/chapters` - Get document chapters
- `GET /api/v1/courses/` - List courses
- `GET /api/v1/courses/{id}/semesters` - List semesters
- `POST /api/v1/lectures/check-duplicate` - Check for duplicate lectures
- `POST /api/v1/lectures/generate` - Generate lecture
- `DELETE /api/v1/lectures/{id}` - Delete lecture
- `GET /api/v1/lectures/{id}/download` - Download lecture

### Session Management
- Access tokens stored in `st.session_state`
- Tokens included in all API requests via Authorization header
- Session persists until logout or browser close
- Automatic re-authentication required after token expiry

### Performance
- **Login**: < 1 second
- **Document List**: < 2 seconds
- **File Upload**: 5-30 seconds (depends on size)
- **Website Upload**: 10-60 seconds (depends on content)
- **Lecture Generation**: 1-3 minutes (AI processing)
- **Download**: Instant (pre-signed URL)

## 📁 File Structure

```
streamlit_app/
├── app.py          # Main Streamlit application
└── README.md       # This file
```

## 🔒 Security

- Never share your access tokens
- Use strong passwords
- Logout when done using shared computers
- Bearer token authentication for all API calls
- HTTPS recommended for production

## 🆘 Getting Help

If you encounter issues:

1. **Check Logs**:
   - Streamlit terminal output
   - Backend API logs
   - Browser console (F12)

2. **Verify Configuration**:
   - Environment variables set correctly
   - Backend API running
   - Supabase connection working

3. **Test API Directly**:
   - Use backend Swagger docs at `http://localhost:8001/docs`
   - Test endpoints manually

4. **Common Issues**:
   - Ensure all prerequisites are met
   - Check that courses and semesters exist
   - Verify document processing is complete
   - Confirm teacher profile is properly set up

## 📝 Notes

- Documents must be in "COMPLETED" status before generating lectures
- Course and semester must exist before lecture generation
- Teacher must be associated with a university
- JWT tokens expire after 30 minutes
- Large documents may take longer to process
- Learning outcomes are included in the AI prompt for better lecture generation
- Duplicate detection helps avoid regenerating the same content
- Chapter selection is only available for PDF documents
- Deleting a lecture removes both database records and PDF files

## 🎉 Tips for Success

1. **Upload Quality Content**: Better source material = better lectures
2. **Be Descriptive**: Detailed lecture descriptions help AI generate better content
3. **Define Clear Learning Outcomes**: Helps AI focus on key objectives
4. **Use Chapter Selection**: Generate focused lectures on specific topics
5. **Check for Duplicates**: Reuse existing lectures when appropriate
6. **Wait for Processing**: Don't rush - let documents process completely
7. **Test First**: Try with a small document before bulk uploads
8. **Save Work**: Download generated lectures immediately
9. **Consistent Naming**: Use clear naming conventions for easy duplicate detection

---

**Happy Teaching! 🎓**

For backend API documentation, see the main project README.md
