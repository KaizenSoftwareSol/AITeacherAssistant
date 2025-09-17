#!/usr/bin/env python3
"""
Simple test script to verify AI Teacher setup
"""

import sys
import os

def test_imports():
    """Test if all required modules can be imported"""
    try:
        import fastapi
        import sqlmodel
        import pydantic
        import uvicorn
        print("✅ Core dependencies imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_project_structure():
    """Test if project structure is correct"""
    required_files = [
        "main.py",
        "settings.py",
        "dependencies.py",
        "logger.py",
        "requirements.txt",
        "pyproject.toml"
    ]
    
    required_dirs = [
        "ai",
        "auth", 
        "user",
        "utils",
        "static",
        "logs",
        "streamlit_app"
    ]
    
    missing_files = []
    missing_dirs = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    for dir in required_dirs:
        if not os.path.exists(dir):
            missing_dirs.append(dir)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    if missing_dirs:
        print(f"❌ Missing directories: {missing_dirs}")
        return False
    
    print("✅ Project structure is correct")
    return True

def main():
    """Run all tests"""
    print("🧪 Testing AI Teacher setup...")
    print("=" * 50)
    
    tests = [
        ("Project Structure", test_project_structure),
        ("Dependencies", test_imports),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Testing {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} test failed")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! AI Teacher is ready to use.")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Set up environment variables: cp env.example .env")
        print("3. Run the application: python run.py")
    else:
        print("❌ Some tests failed. Please check the setup.")
        sys.exit(1)

if __name__ == "__main__":
    main()

