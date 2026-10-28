# TerraWatch AI [Non-Coder]

A hackathon-ready satellite image change detection demo.

## Requirements
- Python 3.10+
- Node.js 18+
- VS Code

## 1. Backend setup
Open a terminal in VS Code:

```bash
cd backend
python -m venv .venv
```

Activate the environment:
- Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Then install and run:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at http://127.0.0.1:8000  
API docs: http://127.0.0.1:8000/docs

## 2. Frontend setup
Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually http://localhost:5173).

## Demo tips
- Use two images of the same location and roughly the same framing.
- Start with a clear before/after pair; avoid clouds and major lighting differences.
- The change mask is a visual difference estimate, not proof of damage or cause.
- Use the sample-pair upload controls in the UI only if you add your own sample images; otherwise upload two images manually.

## Current capabilities
- Upload before/after images
- Resize images to a common canvas
- Compare image pixels and threshold differences
- Generate a highlighted change overlay
- Calculate changed-pixel percentage
- Download a JSON incident report

This MVP does not georeference images, estimate real-world area, or classify the cause of changes.
