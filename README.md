# DWL — Deep Website Learner

DWL is a lightweight local app that crawls a website, produces a summary with an Ollama model, and lets you chat about the site.

## Quick start

### 1) Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend expects Ollama at `http://localhost:11434` and uses the `llama3.1:8b` model by default. Override with:

```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=llama3.1:8b
```

### 2) Start the frontend

```bash
cd frontend
python -m http.server 5173
```

Open `http://localhost:5173` and start exploring a website.

## Notes

- The crawler keeps to the same domain, pulls from `/sitemap.xml` when present, and caps pages/characters (see `MAX_PAGES`, `MAX_CHARS`, `MAX_DEPTH`).
- For large sites, the first summary uses a representative slice. Follow-up questions trigger a focused crawl using keyword-matched links to fetch a few more relevant pages.
- Responses are structured with headings to mirror a ChatGPT-style layout and make key details easier to scan.
