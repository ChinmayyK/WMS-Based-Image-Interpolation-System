.PHONY: setup setup-backend setup-frontend run run-backend run-frontend

setup: setup-backend setup-frontend

setup-backend:
	cd backend && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

setup-frontend:
	cd frontend && npm install

run:
	@echo "Run backend and frontend separately or use Docker if added later."

run-backend:
	cd backend && ./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	cd frontend && npm run dev
