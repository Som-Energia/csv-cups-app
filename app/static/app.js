const uploadForm = document.getElementById("upload-form");

if (uploadForm) {
    const progressBar = document.getElementById("upload-progress-bar");
    const progressText = document.getElementById("upload-progress-text");
    const feedback = document.getElementById("upload-feedback");

    uploadForm.addEventListener("submit", (event) => {
        event.preventDefault();

        const formData = new FormData(uploadForm);
        const file = formData.get("file");
        if (!file || !file.name) {
            feedback.textContent = "Tria un fitxer CSV o ZIP.";
            feedback.classList.remove("hidden");
            return;
        }

        feedback.classList.add("hidden");
        progressText.textContent = "Pujant fitxer al servidor...";
        progressBar.style.width = "0%";

        const request = new XMLHttpRequest();
        request.open("POST", "/api/uploads");

        request.upload.addEventListener("progress", (progressEvent) => {
            if (!progressEvent.lengthComputable) {
                progressText.textContent = "Pujant fitxer...";
                return;
            }

            const percent = (progressEvent.loaded / progressEvent.total) * 100;
            progressBar.style.width = `${percent.toFixed(1)}%`;
            progressText.textContent = `Progrés de pujada: ${percent.toFixed(1)}% (${formatBytes(progressEvent.loaded)} / ${formatBytes(progressEvent.total)})`;
        });

        request.addEventListener("load", () => {
            if (request.status >= 200 && request.status < 300) {
                const response = JSON.parse(request.responseText);
                progressBar.style.width = "100%";
                progressText.textContent = "Pujada completada. Redirigint a l'estat de l'import...";
                window.location.href = `/jobs/${response.job_id}`;
                return;
            }

            let message = "La pujada ha fallat.";
            try {
                const response = JSON.parse(request.responseText);
                message = response.detail || message;
            } catch (error) {
                message = "La pujada ha fallat.";
            }
            feedback.textContent = message;
            feedback.classList.remove("hidden");
        });

        request.addEventListener("error", () => {
            feedback.textContent = "Error de xarxa mentre es pujava el fitxer.";
            feedback.classList.remove("hidden");
        });

        request.send(formData);
    });
}

const recordTabs = document.querySelector("[data-record-tabs]");

const loadDeferredPanel = (panel) => {
    if (!panel || panel.dataset.loaded === "true" || panel.dataset.loading === "true") {
        return;
    }
    panel.dataset.loading = "true";
    fetch(panel.dataset.partialUrl, {
        headers: {
            "X-Requested-With": "fetch",
        },
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error(`Request failed with status ${response.status}`);
            }
            return response.text();
        })
        .then((html) => {
            panel.innerHTML = html;
            panel.setAttribute("aria-busy", "false");
            panel.dataset.loaded = "true";
        })
        .catch(() => {
            panel.innerHTML = `
                <section class="panel empty-state">
                    <h3>No s'han pogut carregar les dades</h3>
                    <p class="muted">Torna-ho a provar d'aquí una estona o recarrega la pàgina.</p>
                </section>
            `;
            panel.setAttribute("aria-busy", "false");
        })
        .finally(() => {
            delete panel.dataset.loading;
        });
};

if (recordTabs) {
    const tabLinks = Array.from(recordTabs.querySelectorAll(".tab-link[data-tab-target]"));
    const panels = Array.from(document.querySelectorAll("[data-record-tab-panel]"));

    const setActiveTab = (tabName) => {
        tabLinks.forEach((link) => {
            const isActive = link.dataset.tabTarget === tabName;
            link.classList.toggle("active", isActive);
            link.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        panels.forEach((panel) => {
            const isActive = panel.dataset.recordTabPanel === tabName;
            panel.hidden = !isActive;
            if (isActive) {
                const deferredPanel = panel.querySelector("[data-deferred-panel][data-partial-url]");
                loadDeferredPanel(deferredPanel);
            }
        });
    };

    tabLinks.forEach((link) => {
        if (link.classList.contains("disabled")) {
            return;
        }
        link.addEventListener("click", (event) => {
            event.preventDefault();
            setActiveTab(link.dataset.tabTarget);
            window.history.replaceState({}, "", link.href);
        });
    });

    const activePanel = panels.find((panel) => !panel.hidden);
    if (activePanel) {
        const deferredPanel = activePanel.querySelector("[data-deferred-panel][data-partial-url]");
        loadDeferredPanel(deferredPanel);
    }
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
