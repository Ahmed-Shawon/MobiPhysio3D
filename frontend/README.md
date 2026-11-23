# MobiPhysio website

Plain HTML, CSS and JavaScript. No build step, no framework.

```
frontend/
  index.html          Home: description + 9 exercise cards
  exercise.html       Upload page and results (exercise.html?id=E01)
  css/style.css       All styles; colours and fonts are variables at the top
  js/config.js        ALL settings: site text, exercises, backend connection
  js/api.js           The only file that talks to the backend
  js/home.js          Builds the cards
  js/exercise.js      Upload, progress, results
  assets/demos/       Hero video and one demo video per exercise
```

## Running

Normally the backend serves this site: start the backend (see the main README) and open
http://localhost:8000.

## Try it without a backend

Set `USE_MOCK: true` in `js/config.js`; the site then returns mock results (a banner shows this).

```
cd frontend
python -m http.server 5500
```

Open http://localhost:5500

## Hosting options

| Setup | `API_BASE_URL` | Notes |
|---|---|---|
| FastAPI serves the site too (default) | `""` | Open http://localhost:8000. No CORS needed. |
| Site and API on different addresses | the API address | CORS must allow the site. |

## API contract

Request: `POST /api/analyze`, `multipart/form-data`

| Field | Value |
|---|---|
| `video` | the video file |
| `exercise_id` | e.g. `E01` |

Response (JSON):

```json
{
  "score": 87.5,
  "skeleton_url": "/outputs/abc123.gif",
  "details": { "model": "GRU + 2D", "frames": 240 }
}
```

- `skeleton_url` may be a full URL or a path on the API server. A base64 GIF in `skeleton_base64` also works.
- `details` is optional. Every key becomes a row in the Details table.
- Errors: any non-2xx response with `{"detail": "message"}` is shown to the user.

Every name above (endpoint, form fields, response keys) can be changed in `js/config.js`
without touching other files.

## Poll mode (default)

With `MODE: "poll"` in `js/config.js` (must match `MODE` in `backend/settings.py`):

- `POST /api/analyze` returns `{"job_id": "..."}` immediately.
- The site calls `GET /api/status/{job_id}` every 2 seconds until it returns
  `{"status": "done", "score": ..., "skeleton_url": ..., "details": {...}}`
  (or `{"status": "failed", "detail": "message"}`).
