#!/bin/bash
set -e

echo "Setting up WMS-Based Image Interpolation System..."

echo "1. Setting up Backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

echo "2. Setting up Frontend..."
cd frontend
npm install
cd ..

echo "Setup Complete!"
