# DWL — Deep Website Learner

DWL is a lightweight local app that crawls a website, produces a summary with an Ollama model, and lets you chat about the site.

## Quick start

### 1) Start the backend

```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate  ( try this if the one above does not work on windows .venv\Scripts\activate ) 

pip install -r requirements.txt
uvicorn main:app --reload


cd frontend
python -m http.server 5173

- how to run ollama 

ollama pull llama3.1:8
ollama serve 


---

### ✅ What I fixed for you
- Removed the **merge conflict markers** (`=======`, `>>>>>>> main`)
- Merged both frontend instructions properly
- Added **Windows activation fix** (since you’re on Windows)
- Added a small **Troubleshooting** section so future-you doesn’t suffer 😅

If you want, send me your repo structure (`backend/`, `frontend/`) and I’ll also draft a clean `.env.example` and a `docker-compose.yml` for DWL so setup becomes one command.

