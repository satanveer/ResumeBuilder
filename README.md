# RoleFit Local

Deterministic local application that tailors an existing resume to a Job Description.

Pipeline:

Upload Resume → Parse → Match to JD → Controlled Rewrite → Inject into LaTeX → Compile PDF

## Stack

Backend:
- Python 3.11
- Flask
- Jinja2
- sentence-transformers
- Ollama (`qwen2.5:3b`)
- pdflatex
- pdfplumber

Frontend:
- React + TypeScript (Vite)
- TailwindCSS
- shadcn/ui style primitives
- TanStack Query

No database is used. Session state is stored as JSON files in `backend/sessions`.

## Project Structure

- `backend/app.py`
- `backend/services/parser.py`
- `backend/services/matcher.py`
- `backend/services/llm.py`
- `backend/services/renderer.py`
- `backend/templates/resume_template.tex`
- `backend/sessions/`
- `backend/outputs/`
- `frontend/`

## API Contract

- `POST /parse-resume`
- `POST /analyze-jd`
- `POST /match/<session_id>`
- `POST /generate/<session_id>`
- `GET /export/<session_id>`

## Run

### 1) Start Ollama model

```bash
ollama run qwen2.5:3b
```

### 2) Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Backend runs on `http://localhost:5001`.

### 3) Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`.

If your backend is running on a non-default port, set:

```bash
VITE_API_BASE_URL=http://localhost:5001
```

This is already configured in `frontend/.env`.

## Notes

- LaTeX formatting is deterministic and rendered by Jinja2 template only.
- LLM rewrites only matched bullet text.
- Session retention keeps latest 20 sessions; older session artifacts are pruned.
