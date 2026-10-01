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

  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3500);
}

function formatBytes(bytes) {
  const sizes = ["B", "KB", "MB", "GB"];

  if (!bytes) {
    return "0 B";
  }

  const i = Math.floor(Math.log(bytes) / Math.log(1024));

  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
}

function resetApp() {
  selectedFile = null;
  fileInput.value = "";

  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
  }

  previewUrl = null;

  preview.src = "";
  resultPreview.src = "";

  fileCard.classList.add("hidden");
  dropzone.classList.remove("hidden");

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyze image";

  resultView.classList.add("hidden");
  loadingView.classList.add("hidden");
  homeView.classList.remove("hidden");

  progressBar.style.width = "12%";
  loadingText.textContent = "Inspecting visual signals…";

  window.scrollTo({
    top: 0,
    behavior: "smooth"
  });
}

function handleFile(file) {
  if (!file) {
    return;
  }

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
    fileInput.value = "";
    return;
  }

  selectedFile = file;

  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
  }

  previewUrl = URL.createObjectURL(file);

  preview.src = previewUrl;
  resultPreview.src = previewUrl;

  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);

  dropzone.classList.add("hidden");
  fileCard.classList.remove("hidden");

  analyzeBtn.disabled = false;
}

dropzone.addEventListener("click", () => {
  fileInput.click();
});

dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", (event) => {
  handleFile(event.target.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("drag");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag");
  });
});

dropzone.addEventListener("drop", (event) => {
  handleFile(event.dataTransfer.files[0]);
});

removeBtn.addEventListener("click", resetApp);

function animateLoading() {
  const phases = [
    ["Running detector one…", 24],
    ["Running detector two…", 50],
    ["Combining confidence signals…", 76],
    ["Preparing result…", 92]
  ];

  phases.forEach(([text, width], index) => {
    setTimeout(() => {
      loadingText.textContent = text;
      progressBar.style.width = `${width}%`;
    }, 650 * index);
  });
}

analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) {
    return;
  }

  analyzeBtn.disabled = true;

  homeView.classList.add("hidden");
  loadingView.classList.remove("hidden");
  resultView.classList.add("hidden");

  animateLoading();

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: form
    });

    let data;

    try {
      data = await response.json();
    } catch {
      throw new Error("The server returned an invalid response.");
    }

    if (!response.ok) {
      throw new Error(data.detail || "Analysis failed.");
    }

    renderResult(data);

    progressBar.style.width = "100%";

    setTimeout(() => {
      loadingView.classList.add("hidden");
      resultView.classList.remove("hidden");

      window.scrollTo({
        top: 0,
        behavior: "smooth"
      });
    }, 350);

  } catch (error) {
    loadingView.classList.add("hidden");
    homeView.classList.remove("hidden");
    analyzeBtn.disabled = false;

    showToast(
      error.message || "Analysis failed. Please try again."
    );
  }
});

function renderResult(data) {
  const serverPercentage = Number(data.ai_percentage);

  const rawPct = Number.isFinite(serverPercentage)
    ? serverPercentage
    : Number(data.ai_probability || 0) * 100;

  const pct = Math.max(0, Math.min(100, rawPct));

  const displayPct = `${pct.toFixed(1)}%`;

  const scoreText = document.querySelector("#scoreText");
  const confidenceText = document.querySelector("#confidenceText");
  const verdictText = document.querySelector("#verdictText");
  const reasonText = document.querySelector("#reasonText");
  const scoreRing = document.querySelector("#scoreRing");

  scoreText.textContent = displayPct;
  confidenceText.textContent = displayPct;
  verdictText.textContent = data.verdict || "Analysis complete";

  reasonText.textContent =
    data.explanation || "The image analysis has been completed.";

  scoreRing.style.background =
    `conic-gradient(
      #b9c6ff ${pct * 3.6}deg,
      #1a203b ${pct * 3.6}deg
    )`;
}

document.querySelector("#backBtn").addEventListener("click", resetApp);

document
  .querySelector("#scanAnotherBtn")
  .addEventListener("click", resetApp);