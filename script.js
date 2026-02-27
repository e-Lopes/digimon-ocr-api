const API_BASE_URL = "https://e-lopes-digimon-ocr-api.hf.space";

let playersMap = new Map();

document.getElementById('imageInput').addEventListener('change', function () {
    const count = this.files.length;
    document.getElementById('fileCount').innerText =
        count === 0 ? 'Nenhum arquivo selecionado' :
        count === 1 ? this.files[0].name :
        `${count} arquivos selecionados`;
});

async function processarImagens() {
    const fileInput = document.getElementById('imageInput');
    const statusEl  = document.getElementById('status');
    const btn       = document.getElementById('btnProcessar');

    if (fileInput.files.length === 0) {
        statusEl.innerText = "⚠️ Selecione pelo menos um arquivo.";
        statusEl.style.color = "orange";
        return;
    }

    btn.disabled = true;
    let totalNovos = 0;
    const files = Array.from(fileInput.files);

    for (let i = 0; i < files.length; i++) {
        statusEl.innerText = `⏳ Processando ${i + 1}/${files.length}: ${files[i].name}`;
        statusEl.style.color = "blue";

        try {
            const formData = new FormData();
            formData.append("file", files[i]);

            const response = await fetch(`${API_BASE_URL}/process`, {
                method: "POST",
                body: formData,
                signal: AbortSignal.timeout(120000)
            });

            if (!response.ok) continue;

            const data = await response.json();
            if (data.error) { console.warn("Erro da API:", data.error); continue; }

            (data.players || []).forEach(player => {
                if (!playersMap.has(player.member_id)) {
                    playersMap.set(player.member_id, player);
                    totalNovos++;
                }
            });

        } catch (err) {
            if (err.name === "TimeoutError") {
                statusEl.innerText = "⏳ API ainda iniciando, aguarde e tente novamente...";
                statusEl.style.color = "orange";
            } else {
                console.error(err);
            }
        }
    }

    renderTabela();

    if (totalNovos > 0) {
        statusEl.innerText = `✅ +${totalNovos} adicionados. Total: ${playersMap.size} jogadores`;
        statusEl.style.color = "green";
    } else if (playersMap.size > 0) {
        statusEl.innerText = `ℹ️ Nenhum ID novo. Total: ${playersMap.size} jogadores`;
        statusEl.style.color = "#888";
    } else {
        statusEl.innerText = "⚠️ Nenhum jogador encontrado. Verifique o print.";
        statusEl.style.color = "orange";
    }

    btn.disabled = false;
    fileInput.value = "";
    document.getElementById('fileCount').innerText = "Nenhum arquivo selecionado";
}

function renderTabela() {
    const tbody = document.querySelector('#resultsTable tbody');
    tbody.innerHTML = "";
    let rank = 1;
    playersMap.forEach(player => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${rank}º</strong></td>
            <td class="player-name">${esc(player.name) || '—'}</td>
            <td><span class="id-badge">${esc(player.member_id)}</span></td>
            <td>${player.points ? esc(player.points) + ' pts' : '—'}</td>
            <td>${player.omw   ? esc(player.omw)    + '%'  : '—'}</td>
        `;
        tbody.appendChild(tr);
        rank++;
    });
}

function exportarCSV() {
    if (playersMap.size === 0) { alert("Nenhum dado para exportar."); return; }
    let csv = "Rank,Nome,Member ID,Win Points,OMW%\n";
    let rank = 1;
    playersMap.forEach(p => {
        csv += `${rank},"${p.name || ""}",${p.member_id},${p.points || ""},${p.omw || ""}\n`;
        rank++;
    });
    const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" })),
        download: "resultado_torneio.csv"
    });
    a.click();
}

function limparTabela() {
    if (confirm("Resetar lista do torneio?")) {
        playersMap.clear();
        document.querySelector('#resultsTable tbody').innerHTML = "";
        document.getElementById('status').innerText = "Tabela limpa.";
        document.getElementById('status').style.color = "#333";
    }
}

function esc(str) {
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}