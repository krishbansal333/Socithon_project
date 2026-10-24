# Naaravali — EcoLoop AI

**Smart campus waste management for a cleaner tomorrow.**

Naaravali is a hackathon MVP for smarter waste segregation, collection reporting, recycling discovery, and impact monitoring. This repository contains a React frontend and a FastAPI backend with SQLite demo data.

> **Important prototype note:** When `HF_INFERENCE_URL` and `HF_TOKEN` are not configured, image scanning runs in clearly marked **Demo mode**. It uses the filename and basic image-color heuristics to produce a demonstration category; it is not a validated waste-classification model and must not be presented as measured AI accuracy. For a real deployment, configure an image classifier trained/evaluated for the target waste categories and report its evaluation metrics.

## Included

- Dashboard with demo waste metrics, recent activity, and bin status
- Waste photo scan workflow with disposal guidance
- Overflow-bin reporting
- Collection queue and a simple nearest-neighbour route suggestion
- Recycler marketplace listings and pickup-request form
- Impact metrics page
- SQLite persistence for reports, scans, and pickup updates
- Optional Hugging Face-compatible inference endpoint configuration

## Project structure

```text
Naaravali-EcoLoopAI/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── render.yaml
├── .gitignore
└── README.md
```

## Run locally

### 1. Start the backend

Use Python 3.10+ (Python 3.11 recommended).

```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: <http://localhost:8000/docs>

### 2. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open <http://localhost:5173>.

The Vite dev server proxies `/api` requests to `http://localhost:8000`. The frontend also uses `VITE_API_BASE_URL` when configured.

## Optional image inference

Set these in `backend/.env`:

```env
HF_INFERENCE_URL=https://router.huggingface.co/hf-inference/models/YOUR_IMAGE_CLASSIFICATION_MODEL
HF_TOKEN=your_hugging_face_token
```

Use a model/endpoint that accepts a base64 image in the JSON `inputs` field and supports candidate labels, or adapt the request in `classify_with_provider()` in `backend/main.py` to your provider's API contract. The app normalizes the returned class label to one of: `recyclable`, `organic`, `hazardous`, `residual`. If the provider is not configured or fails, the backend falls back to marked demo mode.

Do not commit `.env` or API tokens. Keep provider credentials on the backend only.

## Deploy to Render

The included `render.yaml` defines two services:

1. `naaravali-api` — Python/FastAPI backend
2. `naaravali-web` — static React frontend

Push this repository to GitHub, then in Render choose **New + → Blueprint** and select the repository. Review the services and environment variables before deployment. Set `VITE_API_BASE_URL` for the static site to the deployed API URL ending in `/api` (for example, `https://YOUR-API.onrender.com/api`). Depending on your Render account and YAML support, you may need to enter this static-site environment variable in the dashboard and trigger a redeploy so Vite can bake it into the frontend build.

For durable production data, configure a persistent disk or replace SQLite with managed PostgreSQL. The included SQLite database is appropriate for a small demo; ephemeral hosting filesystems may reset on redeploy/restart.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard` | Dashboard summary |
| GET | `/api/bins` | Bin status list |
| POST | `/api/bins/{bin_id}/report` | Report a full/overflowing bin |
| GET | `/api/pickups` | Collection queue |
| POST | `/api/pickups/{pickup_id}/complete` | Mark a pickup complete |
| POST | `/api/collection/optimize` | Build a simple suggested collection route |
| POST | `/api/scan` | Classify an uploaded image or return demo-mode result |
| GET | `/api/recyclers` | Recycler listings |
| POST | `/api/recyclers/{recycler_id}/request` | Create a pickup request |
| GET | `/api/impact` | Impact indicators |
| GET | `/api/activity` | Recent activity |

## Demo checklist

1. Open the dashboard and point out the bin status and waste metrics (seeded demo data).
2. Open **AI Waste Scan**, upload a waste photo, and explain the output. If it says `DEMO MODE`, explicitly say it is a prototype heuristic rather than a validated vision model.
3. Open **Bins & Collection** and report an overflow issue.
4. Generate a suggested route and mark a pickup completed.
5. Open **Recycling Hub** and submit a pickup request.
6. Open **Impact** and describe which indicators should be measured during a real campus pilot.

## Team

- Krish Bansal
- Manthan Soni
- Tejas A

Team name: **Naaravali**

## Responsible-use notes

- All initial records are sample/demo records, not measured IIT Roorkee data.
- Impact figures in the interface are clearly labelled as demo estimates/illustrative metrics.
- Do not present the route optimizer as a production routing system: it uses straight-line distances and seeded coordinates, not road-network travel times.
- Obtain consent and permissions before collecting campus images or deploying any bins/sensors.

## License

MIT — see `LICENSE`.

## GitHub upload

From the project root:

```bash
git init
git add .
git commit -m "Build Naaravali EcoLoop AI MVP"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/naaravali-ecoloop-ai.git
git push -u origin main
```

Create the empty repository on GitHub first, and replace `YOUR-USERNAME` with your GitHub username. If you prefer the website, unzip this project, open your new GitHub repository, choose **Add file → Upload files**, and drag the project files into it.
