/* ------------------------------------------------------------------
   All settings for the site live in this one file.
   Edit here; no other file needs to change to connect the backend.
------------------------------------------------------------------- */
window.APP_CONFIG = {
  /* ---------- Site text ---------- */
  SITE_NAME: "MobiPhysio",
  DESCRIPTION_SHORT: "MobiPhysio scores physiotherapy exercises from an ordinary single-camera video. It detects 2D body keypoints with YOLO26, lifts them to 3D with KTPFormer, and turns the motion into LSTM/GRU features that a trained regressor converts into an assessment score for nine exercises. The project compares how well 2D and 3D pose estimation perform for this kind of evaluation.",
  FOOTER_LEFT: "A Comparative Performance Analysis of 2D and 3D Pose Estimation for Monocular Camera-Based Physiotherapy Exercise Evaluation",
  // Footer contact block (right side): name, university, email (mailto link) and repository link
  HERO_SUBHEADING: "Upload an exercise video. MobiPhysio returns an assessment score.",
  CONTACT_NAME: "Hassan Ahmed Shawon",
  CONTACT_AFFILIATION: "East West University", // shown under the name in the footer
  CONTACT_EMAIL: "hassan.a.shawon@gmail.com",
  REPOSITORY_URL: "https://github.com/Ahmed-Shawon/MobiPhysio3D",
  HERO_MEDIA: "assets/demos/hero.mp4", // shown in the hero; a placeholder box appears if the file is missing

  /* ---------- Backend connection ---------- */
  // true  = no backend needed; the site returns MOCK_RESULT (a banner makes this visible)
  // false = real requests go to the FastAPI server below
  USE_MOCK: false,

  // "" (empty) when FastAPI serves this frontend itself (same origin).
  // Otherwise the server address, e.g. "http://localhost:8000" or "https://my-api.example.com"
  API_BASE_URL: "",

  ENDPOINTS: {
    analyze: "/api/analyze",          // POST multipart/form-data
    status: "/api/status/{job_id}"    // GET, only used when MODE is "poll"
  },

  // Names of the form fields FastAPI receives
  FIELD_NAMES: { video: "video", exercise: "exercise_id" },

  // "sync" = POST waits and returns the result directly (simplest)
  // "poll" = POST returns a job id; the site asks ENDPOINTS.status until it is finished
  //          (use this if inference is slow and the host cuts long requests)
  MODE: "poll",
  POLL_INTERVAL_MS: 2000,
  REQUEST_TIMEOUT_MS: 10 * 60 * 1000,

  // Extra headers sent with every request, e.g. { "X-API-Key": "..." }
  EXTRA_HEADERS: {},

  // Names of the keys in the backend's JSON response
  RESPONSE: {
    score: "score",                    // number
    skeleton: "skeleton_url",          // URL or path to the skeleton GIF / video
    skeletonBase64: "skeleton_base64", // alternative: base64 GIF instead of a URL
    details: "details",                // optional object; every key becomes a row in the Details table
    jobId: "job_id",                   // poll mode
    status: "status",                  // poll mode
    error: "detail"                    // FastAPI's default error key
  },
  POLL_DONE: ["done", "completed", "finished", "success"],
  POLL_FAILED: ["failed", "error"],

  /* ---------- Score display ---------- */
  SCORE_MAX: 100,     // e.g. 100 → shows "out of 100" and a bar; null hides both
  SCORE_DECIMALS: 2,
  // Optional labels, e.g. [{ min: 0, label: "Needs work" }, { min: 50, label: "Fair" }, { min: 80, label: "Good" }]
  RATING_BANDS: [],

  // Backend detail rows NOT shown in the Details table (case-insensitive)
  HIDDEN_DETAILS: ["Model", "Expected error"],

  /* ---------- Upload rules ---------- */
  UPLOAD: {
    ACCEPT: ".mp4,.mov,.webm,.mkv",   // or ".mp4,.avi,.mov"
    MAX_SIZE_MB: Infinity
  },

  /* ---------- Result used when USE_MOCK is true ---------- */
  MOCK_RESULT: { score: 0, skeleton_url: "", details: { note: "Mock data — backend not connected" } },

  /* ---------- The 9 exercises ----------
     id          → sent to the backend as exercise_id (keep it stable, no spaces)
     demo        → GIF/image or MP4/WebM video in assets/demos/ (placeholder shown if missing)
     tips        → recording tips listed on the upload page
     area        → body area; used for the filter pills and the card label
     pose        → "2D" or "3D": the pose model used for this exercise           */
  EXERCISES: [
    { id: "E01", name: "Abduction", area: "Shoulder", pose: "3D", description: "Moving the limb away from the midline of the body.", demo: "assets/demos/E01_Abduction.mp4", tips: [] },
    { id: "E02", name: "Adduction", area: "Shoulder", pose: "3D", description: "Moving the limb back toward the midline of the body.", demo: "assets/demos/E02_Adduction.mp4", tips: [] },
    { id: "E03", name: "Lateral Rotation", area: "Shoulder", pose: "3D", description: "Rotating the limb outward, away from the midline.", demo: "assets/demos/E03_LateralRotation.mp4", tips: [] },
    { id: "E04", name: "Medial Rotation", area: "Shoulder", pose: "3D", description: "Rotating the limb inward, toward the midline.", demo: "assets/demos/E04_MedialRotation.mp4", tips: [] },
    { id: "E05", name: "Circumduction", area: "Shoulder", pose: "3D", description: "Moving the limb in a circular, cone-shaped path.", demo: "assets/demos/E05_Circumduction.mp4", tips: [] },
    { id: "E06", name: "Wrist Extension", area: "Wrist", pose: "2D", description: "Bending the wrist backward so the back of the hand moves toward the forearm.", demo: "assets/demos/E06_WristExtension.mp4", tips: [] },
    { id: "E07", name: "Hip Joint Flexion", area: "Hip", pose: "3D", description: "Raising the thigh forward toward the torso.", demo: "assets/demos/E07_HipJointFlexion.mp4", tips: [] },
    { id: "E08", name: "Lumbar Flexion", area: "Spine", pose: "3D", description: "Bending the lower back forward.", demo: "assets/demos/E08_LumberFlexion.mp4", tips: [] },
    { id: "E09", name: "Back Extension", area: "Spine", pose: "3D", description: "Arching the back backward from an upright position.", demo: "assets/demos/E09_BackExtension.mp4", tips: [] }
  ],
  // Tips shown for every exercise, before the exercise's own tips
  COMMON_TIPS: ["Full body visible in frame", "Single person, steady camera"]
};
