const jobId = window.CSV_CUPS_JOB_ID;
const STATUS_LABELS = {
    queued: "En cua",
    processing: "Processant",
    completed: "Completat",
    failed: "Fallit",
    splitting: "Dividint",
    partial_failed: "Parcial amb errors",
};

if (jobId) {
    const statusNode = document.getElementById("job-status");
    const errorNode = document.getElementById("job-error");
    const actionFeedbackNode = document.getElementById("job-action-feedback");
    const debugPanel = document.getElementById("debug-job-panel");
    const uploadBar = document.getElementById("upload-bar");
    const uploadText = document.getElementById("upload-text");
    const processingBar = document.getElementById("processing-bar");
    const processingText = document.getElementById("processing-text");
    const processedRowsNode = document.getElementById("processed-rows");
    const createdRowsNode = document.getElementById("created-rows");
    const updatedRowsNode = document.getElementById("updated-rows");
    const errorRowsNode = document.getElementById("error-rows");
    const rowsPerSecondNode = document.getElementById("rows-per-second");
    const etaNode = document.getElementById("eta");
    const chart = document.getElementById("speed-chart");
    const requeueButton = document.getElementById("requeue-job-button");
    const retryFailedChunksButton = document.getElementById("retry-failed-chunks-button");
    const forceRequeueButton = document.getElementById("force-requeue-job-button");
    const cleanupArtifactsButton = document.getElementById("cleanup-artifacts-button");
    const totalChunksNode = document.getElementById("total-chunks");
    const queuedChunksNode = document.getElementById("queued-chunks");
    const processingChunksNode = document.getElementById("processing-chunks");
    const completedChunksNode = document.getElementById("completed-chunks");
    const failedChunksNode = document.getElementById("failed-chunks");
    const splitProgressPanel = document.getElementById("split-progress-panel");
    const splitProgressBar = document.getElementById("split-progress-bar");
    const splitProgressText = document.getElementById("split-progress-text");
    const splitProgressMeta = document.getElementById("split-progress-meta");
    const chunksTableBody = document.getElementById("chunks-table-body");
    const chunksPrevButton = document.getElementById("chunks-prev-button");
    const chunksNextButton = document.getElementById("chunks-next-button");
    const chunksPageInfo = document.getElementById("chunks-page-info");
    const speedPoints = [];
    const searchParams = new URLSearchParams(window.location.search);
    const chunksPageSize = 100;
    let refreshTimer = null;
    let requeueInFlight = false;
    let debugMode = searchParams.get("debug") === "1";
    let currentJob = null;
    let currentChunksPage = 1;
    let currentChunksTotalPages = 1;

    const refresh = async () => {
        const response = await fetch(`/api/jobs/${jobId}`);
        if (!response.ok) {
            return;
        }

        const job = await response.json();
        currentJob = job;
        renderJob(job);
        await refreshChunks();
        if (job.status === "queued" || job.status === "processing" || job.status === "splitting") {
            refreshTimer = window.setTimeout(refresh, 1500);
        }
    };

    const renderJob = (job) => {
        statusNode.textContent = STATUS_LABELS[job.status] || job.status;
        statusNode.className = `badge badge-${job.status}`;

        if (job.error_message) {
            errorNode.textContent = job.error_message;
            errorNode.classList.remove("hidden");
        } else {
            errorNode.classList.add("hidden");
        }

        const uploadPercent = percentage(job.uploaded_bytes, job.total_bytes);
        const processingPercent = percentage(job.processed_bytes, job.total_bytes);

        uploadBar.style.width = `${uploadPercent}%`;
        processingBar.style.width = `${processingPercent}%`;
        uploadText.textContent = `${uploadPercent.toFixed(1)}% pujat (${formatBytes(job.uploaded_bytes)} / ${formatBytes(job.total_bytes)})`;
        processingText.textContent = `${processingPercent.toFixed(1)}% processat (${formatBytes(job.processed_bytes)} / ${formatBytes(job.total_bytes)})`;

        processedRowsNode.textContent = formatNumber(job.processed_rows);
        createdRowsNode.textContent = formatNumber(job.created_rows);
        updatedRowsNode.textContent = formatNumber(job.updated_rows);
        errorRowsNode.textContent = formatNumber(job.error_rows);
        rowsPerSecondNode.textContent = formatNumber(job.rows_per_second);
        etaNode.textContent = estimateEta(job);

        totalChunksNode.textContent = formatNumber(job.total_chunks);
        queuedChunksNode.textContent = formatNumber(job.queued_chunks);
        processingChunksNode.textContent = formatNumber(job.processing_chunks);
        completedChunksNode.textContent = formatNumber(job.completed_chunks);
        failedChunksNode.textContent = formatNumber(job.failed_chunks);
        renderSplitProgress(job);

        renderRequeueButton(job);
        renderRetryFailedChunksButton(job);
        renderDebugPanel(job);

        speedPoints.push(job.rows_per_second || 0);
        if (speedPoints.length > 40) {
            speedPoints.shift();
        }
        drawChart(chart, speedPoints);
    };

    const refreshChunks = async () => {
        if (!chunksTableBody) {
            return;
        }
        const response = await fetch(`/api/jobs/${jobId}/chunks?page=${currentChunksPage}&page_size=${chunksPageSize}`);
        if (!response.ok) {
            return;
        }
        const payload = await response.json();
        currentChunksPage = payload.page;
        currentChunksTotalPages = payload.total_pages;
        renderChunks(payload.items, payload.total);
        renderChunkPagination(payload);
    };

    const renderSplitProgress = (job) => {
        if (!splitProgressPanel || !splitProgressBar || !splitProgressText || !splitProgressMeta) {
            return;
        }

        const shouldShow = job.status === "splitting" || job.split_created_chunks > 0;
        if (!shouldShow) {
            splitProgressPanel.classList.add("hidden");
            return;
        }

        splitProgressPanel.classList.remove("hidden");
        const percent = Number(job.split_progress_percent || 0);
        splitProgressBar.style.width = `${percent}%`;
        splitProgressText.textContent = `${percent.toFixed(1)}% dividit`;
        splitProgressMeta.textContent = `${formatBytes(job.split_processed_bytes)} / ${formatBytes(job.total_bytes)} llegits · ${formatNumber(job.split_created_chunks)} chunks creats`;
    };

    const renderChunks = (chunks, total) => {
        if (!chunks.length) {
            chunksTableBody.innerHTML = total > 0
                ? "<tr><td colspan=\"8\">No hi ha chunks en aquesta pàgina.</td></tr>"
                : "<tr><td colspan=\"8\">Esperant chunks...</td></tr>";
            return;
        }

        chunksTableBody.innerHTML = chunks.map((chunk) => `
            <tr>
                <td>#${chunk.chunk_index}</td>
                <td><span class="badge badge-${chunk.status}">${STATUS_LABELS[chunk.status] || chunk.status}</span></td>
                <td>${formatNumber(chunk.total_rows)}</td>
                <td>${formatNumber(chunk.processed_rows)}</td>
                <td>${formatNumber(chunk.created_rows)}</td>
                <td>${formatNumber(chunk.updated_rows)}</td>
                <td>${formatNumber(chunk.error_rows)}</td>
                <td>${escapeHtml(chunk.error_message || "-")}</td>
            </tr>
        `).join("");
    };

    const renderChunkPagination = (payload) => {
        if (!chunksPageInfo || !chunksPrevButton || !chunksNextButton) {
            return;
        }
        chunksPageInfo.textContent = `Pàgina ${payload.page} de ${payload.total_pages} · ${formatNumber(payload.total)} chunks`;
        chunksPrevButton.disabled = requeueInFlight || payload.page <= 1;
        chunksNextButton.disabled = requeueInFlight || payload.page >= payload.total_pages;
    };

    const renderRequeueButton = (job) => {
        if (job.can_requeue) {
            requeueButton.classList.remove("hidden");
        } else {
            requeueButton.classList.add("hidden");
        }
        requeueButton.disabled = requeueInFlight;
    };

    const renderRetryFailedChunksButton = (job) => {
        if (job.can_retry_failed_chunks) {
            retryFailedChunksButton.classList.remove("hidden");
        } else {
            retryFailedChunksButton.classList.add("hidden");
        }
        retryFailedChunksButton.disabled = requeueInFlight;
    };

    const canForceRequeue = (job) => job && job.status !== "completed";

    const renderDebugPanel = (job) => {
        if (debugMode) {
            debugPanel.classList.remove("hidden");
        } else {
            debugPanel.classList.add("hidden");
        }

        if (debugMode && canForceRequeue(job)) {
            forceRequeueButton.classList.remove("hidden");
        } else {
            forceRequeueButton.classList.add("hidden");
        }
        if (debugMode) {
            cleanupArtifactsButton.classList.remove("hidden");
        } else {
            cleanupArtifactsButton.classList.add("hidden");
        }
        forceRequeueButton.disabled = requeueInFlight;
        cleanupArtifactsButton.disabled = requeueInFlight;
        if (chunksPrevButton && chunksNextButton) {
            chunksPrevButton.disabled = requeueInFlight || currentChunksPage <= 1;
            chunksNextButton.disabled = requeueInFlight || currentChunksPage >= currentChunksTotalPages;
        }
    };

    const showActionFeedback = (message, type) => {
        actionFeedbackNode.textContent = message;
        actionFeedbackNode.className = `notice ${type}`;
    };

    const enableDebugMode = () => {
        if (debugMode) {
            return;
        }
        debugMode = true;
        if (currentJob) {
            renderDebugPanel(currentJob);
        }
        showActionFeedback("Accions de depuracio activades.", "success");
    };

    const executeRequeue = async (force) => {
        if (requeueInFlight) {
            return;
        }
        if (force) {
            const confirmed = window.confirm(
                "Aixo reiniciara la importacio des de zero, esborrant els chunks actuals encara que estigui dividint o processant. Vols continuar?"
            );
            if (!confirmed) {
                return;
            }
        }

        requeueInFlight = true;
        requeueButton.disabled = true;
        retryFailedChunksButton.disabled = true;
        forceRequeueButton.disabled = true;
        cleanupArtifactsButton.disabled = true;
        showActionFeedback(force ? "Forcant importacio..." : "Tornant a posar l'import en cua...", "success");

        try {
            const suffix = force ? "?force=1" : "";
            const response = await fetch(`/api/jobs/${jobId}/requeue${suffix}`, { method: "POST" });
            if (!response.ok) {
                const payload = await safeJson(response);
                throw new Error(payload.detail || "No s'ha pogut tornar a posar l'import en cua.");
            }
            if (refreshTimer) {
                window.clearTimeout(refreshTimer);
                refreshTimer = null;
            }
            showActionFeedback(force ? "Importació reiniciada correctament." : "Import tornat a la cua correctament.", "success");
            await refresh();
        } catch (error) {
            showActionFeedback(error.message || "No s'ha pogut tornar a posar l'import en cua.", "error");
        } finally {
            requeueInFlight = false;
            if (currentJob) {
                renderRequeueButton(currentJob);
                renderRetryFailedChunksButton(currentJob);
                renderDebugPanel(currentJob);
            }
        }
    };

    const executeRetryFailedChunks = async () => {
        if (requeueInFlight) {
            return;
        }
        requeueInFlight = true;
        requeueButton.disabled = true;
        retryFailedChunksButton.disabled = true;
        forceRequeueButton.disabled = true;
        cleanupArtifactsButton.disabled = true;
        showActionFeedback("Reintentant chunks fallits...", "success");

        try {
            const response = await fetch(`/api/jobs/${jobId}/retry-failed-chunks`, { method: "POST" });
            if (!response.ok) {
                const payload = await safeJson(response);
                throw new Error(payload.detail || "No s'han pogut reintentar els chunks fallits.");
            }
            if (refreshTimer) {
                window.clearTimeout(refreshTimer);
                refreshTimer = null;
            }
            showActionFeedback("Chunks fallits tornats a la cua correctament.", "success");
            await refresh();
        } catch (error) {
            showActionFeedback(error.message || "No s'han pogut reintentar els chunks fallits.", "error");
        } finally {
            requeueInFlight = false;
            if (currentJob) {
                renderRequeueButton(currentJob);
                renderRetryFailedChunksButton(currentJob);
                renderDebugPanel(currentJob);
            }
        }
    };

    requeueButton.addEventListener("click", async () => {
        await executeRequeue(false);
    });

    retryFailedChunksButton.addEventListener("click", async () => {
        await executeRetryFailedChunks();
    });

    forceRequeueButton.addEventListener("click", async () => {
        await executeRequeue(true);
    });

    cleanupArtifactsButton.addEventListener("click", async () => {
        if (requeueInFlight) {
            return;
        }

        const isCompleted = currentJob && currentJob.status === "completed";
        const confirmed = window.confirm(
            isCompleted
                ? "Aixo esborrara els chunks i el fitxer original d'aquest import. Vols continuar?"
                : "Aixo esborrara els chunks i el fitxer original encara que l'import no hagi acabat. Pot deixar el job fallit i sense possibilitat de reprocessar. Vols continuar?"
        );
        if (!confirmed) {
            return;
        }

        requeueInFlight = true;
        requeueButton.disabled = true;
        retryFailedChunksButton.disabled = true;
        forceRequeueButton.disabled = true;
        cleanupArtifactsButton.disabled = true;
        showActionFeedback("Esborrant fitxers i chunks...", "success");

        try {
            const response = await fetch(`/api/jobs/${jobId}/cleanup-artifacts`, { method: "POST" });
            if (!response.ok) {
                const payload = await safeJson(response);
                throw new Error(payload.detail || "No s'han pogut esborrar els artefactes de l'import.");
            }
            if (refreshTimer) {
                window.clearTimeout(refreshTimer);
                refreshTimer = null;
            }
            showActionFeedback("Artefactes esborrats correctament.", "success");
            await refresh();
        } catch (error) {
            showActionFeedback(error.message || "No s'han pogut esborrar els artefactes de l'import.", "error");
        } finally {
            requeueInFlight = false;
            if (currentJob) {
                renderRequeueButton(currentJob);
                renderRetryFailedChunksButton(currentJob);
                renderDebugPanel(currentJob);
            }
        }
    });

    if (chunksPrevButton) {
        chunksPrevButton.addEventListener("click", async () => {
            if (requeueInFlight || currentChunksPage <= 1) {
                return;
            }
            currentChunksPage -= 1;
            await refreshChunks();
        });
    }

    if (chunksNextButton) {
        chunksNextButton.addEventListener("click", async () => {
            if (requeueInFlight || currentChunksPage >= currentChunksTotalPages) {
                return;
            }
            currentChunksPage += 1;
            await refreshChunks();
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.shiftKey && event.key.toLowerCase() === "d") {
            enableDebugMode();
        }
    });

    refresh();
}

function percentage(part, total) {
    if (!total) {
        return 0;
    }
    return Math.min((part / total) * 100, 100);
}

function formatBytes(bytes) {
    if (!bytes) {
        return "0 B";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / (1024 ** exponent);
    return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[exponent]}`;
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function estimateEta(job) {
    if (!job.rows_per_second || !job.total_bytes || !job.processed_bytes) {
        return "-";
    }
    const remainingBytes = Math.max(job.total_bytes - job.processed_bytes, 0);
    const bytesPerRow = job.processed_rows > 0 ? job.processed_bytes / job.processed_rows : 0;
    if (!bytesPerRow) {
        return "-";
    }
    const remainingRows = remainingBytes / bytesPerRow;
    const seconds = remainingRows / job.rows_per_second;
    if (!Number.isFinite(seconds)) {
        return "-";
    }
    return humanDuration(seconds);
}

function humanDuration(seconds) {
    const rounded = Math.max(Math.round(seconds), 0);
    const hours = Math.floor(rounded / 3600);
    const minutes = Math.floor((rounded % 3600) / 60);
    const secs = rounded % 60;
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
}

function drawChart(canvas, points) {
    if (!canvas || !canvas.getContext) {
        return;
    }
    const context = canvas.getContext("2d");
    const width = canvas.clientWidth || 800;
    const height = canvas.height;
    canvas.width = width;
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "#0b57d0";
    context.lineWidth = 2;
    context.beginPath();

    const max = Math.max(...points, 1);
    points.forEach((point, index) => {
        const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
        const y = height - (point / max) * (height - 20) - 10;
        if (index === 0) {
            context.moveTo(x, y);
        } else {
            context.lineTo(x, y);
        }
    });
    context.stroke();
}

async function safeJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return {};
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
