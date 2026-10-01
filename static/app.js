const fileInput = document.querySelector("#fileInput");
const dropzone = document.querySelector("#dropzone");
const fileCard = document.querySelector("#fileCard");
const preview = document.querySelector("#preview");
const resultPreview = document.querySelector("#resultPreview");
const fileName = document.querySelector("#fileName");
const fileSize = document.querySelector("#fileSize");
const analyzeBtn = document.querySelector("#analyzeBtn");
const removeBtn = document.querySelector("#removeBtn");
const homeView = document.querySelector("#homeView");
const loadingView = document.querySelector("#loadingView");
const resultView = document.querySelector("#resultView");
const toast = document.querySelector("#toast");
const progressBar = document.querySelector("#progressBar");
const loadingText = document.querySelector("#loadingText");

let selectedFile = null;
let previewUrl = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3200);
}

function formatBytes(bytes) {
  const sizes = ["B","KB","MB","GB"];
  if (!bytes) return "0 B";
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
}

function resetApp() {
  selectedFile = null;
  fileInput.value = "";
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  preview.src = "";
  resultPreview.src = "";
  fileCard.classList.add("hidden");
  dropzone.classList.remove("hidden");
  analyzeBtn.disabled = true;
  resultView.classList.add("hidden");
  loadingView.classList.add("hidden");
  homeView.classList.remove("hidden");
  progressBar.style.width = "12%";
  window.scrollTo({top:0, behavior:"smooth"});
}

function handleFile(file) {
  if (!file) return;
  if (file.type.startsWith("video/")) {
    showToast("Video input is not available right now.");
    fileInput.value = "";
    return;
  }
  if (!file.type.startsWith("image/")) {
    showToast("Please upload an image file.");
    fileInput.value = "";
    return;
  }
  if (file.size > 12 * 1024 * 1024) {
    showToast("Image is too large. Maximum size is 12 MB.");
    return;
  }

  selectedFile = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
  resultPreview.src = previewUrl;
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  dropzone.classList.add("hidden");
  fileCard.classList.remove("hidden");
  analyzeBtn.disabled = false;
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
fileInput.addEventListener("change", e => handleFile(e.target.files[0]));
["dragenter","dragover"].forEach(eventName => dropzone.addEventListener(eventName, e => {
  e.preventDefault(); dropzone.classList.add("drag");
}));
["dragleave","drop"].forEach(eventName => dropzone.addEventListener(eventName, e => {
  e.preventDefault(); dropzone.classList.remove("drag");
}));
dropzone.addEventListener("drop", e => handleFile(e.dataTransfer.files[0]));
removeBtn.addEventListener("click", resetApp);

function animateLoading() {
  const phases = [
    ["Running detector one…", 24],
    ["Running detector two…", 50],
    ["Combining confidence signals…", 76],
    ["Preparing result…", 92]
  ];
  phases.forEach(([text, width], i) => {
    setTimeout(() => {
      loadingText.textContent = text;
      progressBar.style.width = `${width}%`;
    }, 600 * i);
  });
}

analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  homeView.classList.add("hidden");
  loadingView.classList.remove("hidden");
  animateLoading();

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const response = await fetch("/api/analyze", { method:"POST", body:form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Analysis failed");

    renderResult(data);
    progressBar.style.width = "100%";
    setTimeout(() => {
      loadingView.classList.add("hidden");
      resultView.classList.remove("hidden");
      window.scrollTo({top:0, behavior:"smooth"});
    }, 350);
  } catch (err) {
    loadingView.classList.add("hidden");
    homeView.classList.remove("hidden");
    showToast(err.message || "Analysis failed. Please try again.");
  }
});

function renderResult(data) {
  // Show the detector's actual score instead of rounding to a whole number.
  const rawPct = Number.isFinite(Number(data.ai_percentage))
    ? Number(data.ai_percentage)
    : Number(data.ai_probability || 0) * 100;

  const pct = Math.max(0, Math.min(100, rawPct));
  const displayPct = `${pct.toFixed(1)}%`;

  document.querySelector("#scoreText").textContent = displayPct;
  document.querySelector("#confidenceText").textContent = displayPct;
  document.querySelector("#verdictText").textContent = data.verdict;
  document.querySelector("#reasonText").textContent = data.explanation;
  document.querySelector("#scoreRing").style.background =
    `conic-gradient(#b9c6ff ${pct * 3.6}deg,#1a203b ${pct * 3.6}deg)`;

  const matches = data.similar_images || [];
  searchStatus.textContent = data.web_search_enabled ? (matches.length ? `${matches.length} found` : "No matches") : "Not configured";

  if (matches.length) {
      matches.forEach(item => {
      const card = document.createElement("article");
      card.className = "match";
      card.innerHTML = `
        <img src="${item.thumbnail || item.image_url || ""}" alt="Possible visually similar image" loading="lazy" />
        <div>
          <a href="${item.source_url}" target="_blank" rel="noopener noreferrer">${item.title || "View source"}</a>
          <small>${item.source || "Public web"}</small>
        </div>
      `;
      matchesGrid.appendChild(card);
    });
  } else {
    noMatches.classList.remove("hidden");
    noMatches.textContent = data.web_search_enabled
      ? "No reliable visually similar public-web matches were returned by the configured search provider."
      : "Open-web similarity search is not configured yet.";
  }
}

document.querySelector("#backBtn").addEventListener("click", resetApp);
document.querySelector("#scanAnotherBtn").addEventListener("click", resetApp);
