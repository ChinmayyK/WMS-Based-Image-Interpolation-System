Write-Host "Starting Backend API..."
Start-Process powershell -ArgumentList "-NoExit -Command `"cd backend; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`""
Write-Host "Started Backend."

Write-Host "Starting Frontend App..."
Start-Process powershell -ArgumentList "-NoExit -Command `"cd frontend; npm run dev`""
Write-Host "Started Frontend App."

Write-Host "Systems are running in separate windows! Close those windows to stop them."
