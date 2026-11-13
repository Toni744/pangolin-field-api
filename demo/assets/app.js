const signinPanel = document.querySelector("#signin-panel");
const dashboard = document.querySelector("#dashboard");
const message = document.querySelector("#app-message");
const signinButton = document.querySelector("#signin-button");
const signoutButton = document.querySelector("#signout-button");
const uploadForm = document.querySelector("#upload-form");
const uploadButton = document.querySelector("#upload-button");
const fileInput = document.querySelector("#sample-file");
const fileName = document.querySelector("#file-name");
const sampleButton = document.querySelector("#sample-button");
const accountName = document.querySelector("#account-name");
const avatar = document.querySelector("#avatar");
const emptyState = document.querySelector("#empty-state");
const jobState = document.querySelector("#job-state");
const jobStatus = document.querySelector("#job-status");
const jobTime = document.querySelector("#job-time");
const jobName = document.querySelector("#job-name");
const jobId = document.querySelector("#job-id");
const qcResults = document.querySelector("#qc-results");
const jobError = document.querySelector("#job-error");
const sampleList = document.querySelector("#sample-list");
const libraryEmpty = document.querySelector("#library-empty");
const refreshSamplesButton = document.querySelector("#refresh-samples");

const syntheticFastq = [
  "@PANGOLIN-DEMO-1",
  "ACGTACGT",
  "+",
  "IIIIIIII",
  "@PANGOLIN-DEMO-2",
  "TTGCAAAA",
  "+",
  "HHHHHHHH",
].join("\n") + "\n";

let configuration;
let authClient;
let activeFile;
let pollTimer;

function showMessage(text) {
  message.textContent = text;
  message.hidden = false;
}

function clearMessage() {
  message.textContent = "";
  message.hidden = true;
}

function setBusy(isBusy) {
  uploadButton.disabled = isBusy;
  uploadButton.firstChild.textContent = isBusy ? "Submitting sample…" : "Upload & queue analysis ";
}

function setAccount(account) {
  const signedIn = Boolean(account);
  signinPanel.hidden = signedIn;
  dashboard.hidden = !signedIn;
  signoutButton.hidden = !signedIn;
  if (!signedIn) {
    accountName.textContent = "";
    return;
  }
  const displayName = account.name || account.username;
  accountName.textContent = displayName;
  avatar.textContent = displayName.slice(0, 1).toUpperCase();
}

function currentAccount() {
  return authClient.getActiveAccount() || authClient.getAllAccounts()[0] || null;
}

async function acquireAccessToken() {
  const account = currentAccount();
  if (!account) {
    throw new Error("Sign in before uploading a sample.");
  }
  authClient.setActiveAccount(account);
  const request = { scopes: [configuration.apiScope], account };
  try {
    const result = await authClient.acquireTokenSilent(request);
    return result.accessToken;
  } catch (error) {
    if (error instanceof msal.InteractionRequiredAuthError) {
      await authClient.acquireTokenRedirect({
        ...request,
        extraQueryParameters: { p: configuration.userFlow },
      });
      return "";
    }
    throw error;
  }
}

function renderJob(sample, status) {
  emptyState.hidden = true;
  jobState.hidden = false;
  jobStatus.textContent = status.status;
  jobStatus.dataset.status = status.status;
  jobTime.textContent = new Date(sample.observed_at || Date.now()).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  jobName.textContent = sample.filename;
  jobId.textContent = sample.sample_id;

  for (const step of document.querySelectorAll(".pipeline-step")) {
    step.classList.remove("done", "active");
  }
  document.querySelector('[data-step="stored"]').classList.add("done");
  if (status.status === "queued") {
    document.querySelector('[data-step="queued"]').classList.add("active");
  } else {
    document.querySelector('[data-step="queued"]').classList.add("done");
  }
  if (status.status === "processing") {
    document.querySelector('[data-step="completed"]').classList.add("active");
  } else if (status.status === "completed") {
    document.querySelector('[data-step="completed"]').classList.add("done");
  }

  qcResults.hidden = status.status !== "completed" || !status.qc;
  qcResults.replaceChildren();
  if (status.qc) {
    const metrics = [
      ["READS", status.qc.read_count],
      ["BASES", status.qc.base_count],
      ["GC CONTENT", `${(status.qc.gc_fraction * 100).toFixed(1)}%`],
      ["MEAN QUALITY", `Q${status.qc.mean_phred_quality.toFixed(1)}`],
    ];
    for (const [label, value] of metrics) {
      const metric = document.createElement("div");
      metric.className = "metric";
      const title = document.createElement("span");
      title.textContent = label;
      const result = document.createElement("strong");
      result.textContent = value;
      metric.append(title, result);
      qcResults.append(metric);
    }
  }

  jobError.hidden = !status.error;
  jobError.textContent = status.error ? `This sample could not be processed (${status.error}).` : "";
}

function createDownloadButton(label, sampleId, kind) {
  const button = document.createElement("button");
  button.className = "download-button";
  button.type = "button";
  button.textContent = label;
  button.dataset.sampleId = sampleId;
  button.dataset.downloadKind = kind;
  return button;
}

function renderSampleLibrary(samples) {
  sampleList.replaceChildren();
  libraryEmpty.hidden = samples.length > 0;
  for (const sample of samples) {
    const row = document.createElement("article");
    row.className = "sample-row";

    const details = document.createElement("div");
    details.className = "sample-details";
    const name = document.createElement("strong");
    name.textContent = sample.filename;
    const metadata = document.createElement("span");
    metadata.textContent = `${sample.site_code} · ${new Date(sample.observed_at).toLocaleString()}`;
    details.append(name, metadata);

    const status = document.createElement("span");
    status.className = "library-status";
    status.dataset.status = sample.status;
    status.textContent = sample.status;

    const actions = document.createElement("div");
    actions.className = "sample-actions";
    if (sample.status === "completed") {
      actions.append(
        createDownloadButton("FASTQ", sample.sample_id, "data"),
        createDownloadButton("QC report", sample.sample_id, "report"),
      );
    } else if (sample.status === "failed" && sample.error) {
      status.title = sample.error;
    }

    row.append(details, status, actions);
    sampleList.append(row);
  }
}

async function downloadSample(button) {
  const token = await acquireAccessToken();
  if (!token) {
    return;
  }
  const sampleId = encodeURIComponent(button.dataset.sampleId);
  const kind = button.dataset.downloadKind;
  const response = await fetch(`/samples/${sampleId}/${kind}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "The sample could not be downloaded.");
  }
  const filename = /filename="([^"]+)"/i.exec(
    response.headers.get("Content-Disposition") || "",
  )?.[1] || `${sampleId}-${kind}`;
  const downloadUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
}

async function refreshSamples() {
  window.clearTimeout(pollTimer);
  if (!currentAccount()) {
    return;
  }
  try {
    const token = await acquireAccessToken();
    if (!token) {
      return;
    }
    const response = await fetch("/samples?limit=50", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Could not retrieve your samples.");
    }
    const samples = result.samples || [];
    renderSampleLibrary(samples);

    const savedSample = sessionStorage.getItem("pangolin.sample");
    const activeSampleId = savedSample ? JSON.parse(savedSample).sample_id : null;
    const activeSample = samples.find((sample) => sample.sample_id === activeSampleId);
    if (activeSample) {
      renderJob(activeSample, activeSample);
    }
    if (samples.some((sample) => ["queued", "processing"].includes(sample.status))) {
      pollTimer = window.setTimeout(refreshSamples, 1800);
    }
  } catch (error) {
    showMessage(error.message || "Your sample library could not be refreshed.");
  } finally {
    refreshSamplesButton.disabled = false;
  }
}

async function initialize() {
  try {
    const configResponse = await fetch("/demo/config.json");
    configuration = await configResponse.json();
    if (!configResponse.ok) {
      throw new Error(configuration.detail || "The demo sign-in configuration is unavailable.");
    }
    if (!window.msal) {
      throw new Error("The Microsoft sign-in library did not load. Check the browser's network connection.");
    }

    const metadataResponse = await fetch(configuration.authorityMetadataUrl);
    if (!metadataResponse.ok) {
      throw new Error("Could not load the External ID sign-in configuration.");
    }
    const authorityMetadata = await metadataResponse.json();
    authClient = new msal.PublicClientApplication({
      auth: {
        clientId: configuration.clientId,
        authority: configuration.authority,
        authorityMetadata: JSON.stringify(authorityMetadata),
        knownAuthorities: [new URL(configuration.authority).hostname],
        redirectUri: `${window.location.origin}/`,
        postLogoutRedirectUri: `${window.location.origin}/`,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    await authClient.initialize();
    const redirectResult = await authClient.handleRedirectPromise();
    if (redirectResult?.account) {
      authClient.setActiveAccount(redirectResult.account);
    }
    setAccount(currentAccount());
    if (currentAccount()) {
      await refreshSamples();
    }
  } catch (error) {
    showMessage(error.message || "The demo could not be initialized.");
  }
}

signinButton.addEventListener("click", async () => {
  clearMessage();
  try {
    await authClient.loginRedirect({
      scopes: [configuration.apiScope],
      extraQueryParameters: { p: configuration.userFlow },
    });
  } catch (error) {
    showMessage(error.message || "Sign-in could not be started.");
  }
});

signoutButton.addEventListener("click", async () => {
  const account = currentAccount();
  if (account) {
    window.clearTimeout(pollTimer);
    sessionStorage.removeItem("pangolin.sample");
    try {
      await authClient.logoutRedirect({
        account,
        postLogoutRedirectUri: `${window.location.origin}/`,
      });
    } catch (error) {
      showMessage(error.message || "Sign-out could not be completed.");
    }
  }
});

refreshSamplesButton.addEventListener("click", async () => {
  clearMessage();
  refreshSamplesButton.disabled = true;
  await refreshSamples();
});

sampleList.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }
  const button = event.target.closest("button[data-download-kind]");
  if (!button) {
    return;
  }
  clearMessage();
  button.disabled = true;
  try {
    await downloadSample(button);
  } catch (error) {
    showMessage(error.message || "The sample could not be downloaded.");
  } finally {
    button.disabled = false;
  }
});

fileInput.addEventListener("change", () => {
  activeFile = fileInput.files?.[0] || null;
  fileName.textContent = activeFile ? activeFile.name : "Choose a FASTQ file";
});

sampleButton.addEventListener("click", () => {
  activeFile = new File([syntheticFastq], "pangolin-demo.fastq", { type: "text/plain" });
  fileName.textContent = activeFile.name;
  clearMessage();
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  if (!activeFile) {
    showMessage("Choose a FASTQ file or load the synthetic demo sample.");
    return;
  }
  setBusy(true);
  try {
    const token = await acquireAccessToken();
    if (!token) {
      return;
    }
    const formData = new FormData();
    const sampleId = crypto.randomUUID();
    formData.append("sample_id", sampleId);
    formData.append("site_code", document.querySelector("#site-code").value);
    formData.append("observed_at", new Date().toISOString());
    formData.append("file", activeFile, activeFile.name);

    const response = await fetch("/samples", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const receipt = await response.json();
    if (!response.ok) {
      throw new Error(receipt.detail || "The sample could not be uploaded.");
    }
    sessionStorage.setItem(
      "pangolin.sample",
      JSON.stringify({ sample_id: receipt.sample_id, filename: activeFile.name }),
    );
    renderJob(
      { sample_id: receipt.sample_id, filename: activeFile.name },
      { status: "queued", qc: null, error: null },
    );
    await refreshSamples();
  } catch (error) {
    showMessage(error.message || "The sample could not be uploaded.");
  } finally {
    setBusy(false);
  }
});

initialize();
