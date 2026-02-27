const API_BASE_URL = "https://e-lopes-digimon-ocr-api.hf.space";

// Map: member_id → player object (source of truth for dedup)
let playersMap = new Map();

// ---------------------------------------------------------------------------
// Process one or more files sequentially
// ---------------------------------------------------------------------------
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
        const file = files[i];
        statusEl.innerText = `⏳ Processando print ${i + 1} de ${files.length}: ${file.name}`;
        statusEl.style.color = "blue";

        try {
            const formData = new FormData();
            formData.append("file", file);

            const response = await fetch(`${API_BASE_URL}/process`, {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                console.warn(`Erro HTTP ${response.status} no arquivo ${file.name}`);
                continue;
            }

            const data = await response.json();

            if (data.players && data.players.length > 0) {
                data.players.forEach(player => {
                    if (!playersMap.has(player.member_id)) {
                        playersMap.set(player.member_id, player);
                        totalNovos++;
                    }
                    // Se já existe mas veio sem rank e agora tem, atualiza
                    else if (!playersMap.get(player.member_id).rank && player.rank) {
                        playersMap.set(player.member_id, player);
                    }
                });
            }
        } catch (err) {
            console.error(`Erro ao processar ${file.name}:`, err);
        }
    }

    renderTabela();

    if (totalNovos > 0) {
        statusEl.innerText = `✅ +${totalNovos} jogadores adicionados. Total: ${playersMap.size}`;
        statusEl.style.color = "green";
    } else if (playersMap.size > 0) {
        statusEl.innerText = `ℹ️ Nenhum jogador novo. Todos os ${playersMap.size} já estavam na tabela.`;
        statusEl.style.color = "#888";
    } else {
        statusEl.innerText = "⚠️ Nenhum jogador encontrado. Tente um print mais próximo da tabela.";
        statusEl.style.color = "orange";
    }

    btn.disabled = false;
    fileInput.value = "";
}

// ---------------------------------------------------------------------------
// Render: sort by rank then by insertion order
// ---------------------------------------------------------------------------
function renderTabela() {
    const tbody = document.querySelector('#resultsTable tbody');
    tbody.innerHTML = "";

    // Sort: known rank first (ascending), unknown rank at the end
    const sorted = Array.from(playersMap.values()).sort((a, b) => {
        const ra = a.rank ?? 9999;
        const rb = b.rank ?? 9999;
        return ra - rb;
    });

    sorted.forEach((player, idx) => {
        const rank = player.rank ?? (idx + 1);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${rank}º</strong></td>
            <td>
                <div class="player-info">
                    <strong>${escHtml(player.name)}</strong>
                    <span class="id-badge">ID: ${escHtml(player.member_id)}</span>
                </div>
            </td>
            <td>${escHtml(player.points)} pts</td>
            <td>${player.omw ? escHtml(player.omw) + '%' : '—'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------
function exportarCSV() {
    if (playersMap.size === 0) {
        alert("Nenhum dado para exportar.");
        return;
    }

    const sorted = Array.from(playersMap.values()).sort((a, b) =>
        (a.rank ?? 9999) - (b.rank ?? 9999)
    );

    const header = "Rank,Nome,Member ID,Win Points,OMW%\n";
    const rows = sorted.map((p, i) =>
        `${p.rank ?? i + 1},"${p.name}",${p.member_id},${p.points},${p.omw || ""}`
    ).join("\n");

    const blob = new Blob([header + rows], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "resultado_torneio.csv";
    a.click();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function escHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function limparTabela() {
    if (confirm("Deseja resetar a lista do torneio?")) {
        playersMap.clear();
        document.querySelector('#resultsTable tbody').innerHTML = "";
        document.getElementById('status').innerText = "Tabela limpa.";
        document.getElementById('status').style.color = "#333";
    }
}