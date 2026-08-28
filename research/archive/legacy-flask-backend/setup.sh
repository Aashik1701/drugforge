#!/bin/bash

# DrugForge AI - Development Setup Script
# This script sets up the development environment for both frontend and backend

echo "🚀 Setting up DrugForge AI Development Environment"
echo "================================================="

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Node.js
if command_exists node; then
    echo "✅ Node.js $(node --version) found"
else
    echo "❌ Node.js not found. Please install Node.js 16+ from https://nodejs.org/"
    exit 1
fi

# Check Python
if command_exists python3; then
    echo "✅ Python $(python3 --version) found"
elif command_exists python; then
    echo "✅ Python $(python --version) found"
else
    echo "❌ Python not found. Please install Python 3.8+ from https://python.org/"
    exit 1
fi

# Setup Frontend
echo ""
echo "📦 Setting up Frontend Dependencies..."
if [ -f "package.json" ]; then
    npm install
    if [ $? -eq 0 ]; then
        echo "✅ Frontend dependencies installed successfully"
    else
        echo "❌ Failed to install frontend dependencies"
        exit 1
    fi
else
    echo "❌ package.json not found. Are you in the correct directory?"
    exit 1
fi

# Setup Backend
echo ""
echo "🐍 Setting up Backend Dependencies..."
cd backendML

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv || python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate || source venv/Scripts/activate

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo "✅ Backend dependencies installed successfully"
    else
        echo "❌ Failed to install backend dependencies"
        exit 1
    fi
else
    echo "❌ requirements.txt not found in backendML directory"
    exit 1
fi

# Return to root directory
cd ..

echo ""
echo "🎉 Setup Complete!"
echo "==================="
echo ""
echo "To start the development servers:"
echo ""
echo "1. Frontend (in terminal 1):"
echo "   npm start"
echo ""
echo "2. Backend (in terminal 2):"
echo "   cd backendML"
echo "   source venv/bin/activate  # On Windows: venv\\Scripts\\activate"
echo "   python app.py"
echo ""
echo "3. Access the application:"
echo "   Frontend: http://localhost:3000"
echo "   Backend API: http://localhost:5001"
echo "   Health Check: http://localhost:5001/health"
echo ""
echo "Happy coding! 🧬✨"
