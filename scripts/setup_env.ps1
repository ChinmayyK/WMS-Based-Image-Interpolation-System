Write-Host "Setting up backend..."
cd backend
python -m pip install -r requirements.txt
cd ..

Write-Host "Setting up frontend..."
cd frontend
npm install
cd ..

Write-Host "Setup complete."
