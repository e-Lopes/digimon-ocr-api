---
title: Digimon OCR API
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: OCR de ranking do Digimon TCG+ com FastAPI e Groq Vision
---

# Digimon OCR API

API que transforma prints do aplicativo Bandai TCG+ em JSON estruturado para o
DigiStats. O DigiStats pode permanecer como PWA estática no GitHub Pages; esta
API fica na Vercel e protege a chave da Groq.

## Arquitetura

```text
Usuário seleciona o print
          │
          ▼
DigiStats — GitHub Pages
          │ POST multipart/form-data
          ▼
Digimon OCR API — Vercel/FastAPI
          │ imagem + prompt
          ▼
Groq — modelo visual
          │ JSON
          ▼
Validação e normalização
          │
          ▼
DigiStats recebe jogadores, loja e data
```

A chave `GROQ_API_KEY` existe somente no backend. Nunca coloque essa chave no
JavaScript publicado pelo GitHub Pages.

## Fluxo de processamento

1. O cliente envia uma imagem no campo `file` para `POST /process`.
2. A API consulta os modelos disponíveis para a chave Groq.
3. Ela prefere `GROQ_MODEL`, cujo padrão atual é `qwen/qwen3.6-27b`.
4. Se esse modelo não estiver disponível, tenta os modelos informados em
   `GROQ_FALLBACK_MODELS`.
5. Se nenhum modelo configurado estiver disponível, seleciona outro modelo
   ativo que aceite imagem e produza texto.
6. A imagem e o prompt são enviados à Groq.
7. A resposta é solicitada em JSON Object Mode, sem raciocínio exposto para o
   Qwen.
8. A API descarta jogadores cujo `member_id` não tenha 10 dígitos e não seja
   `GUEST` seguido de dígitos.
9. A data é normalizada para `YYYY-MM-DD`, quando estiver visível.

A seleção fica em cache durante a vida da função. Se uma chamada retornar 404
por modelo removido, a API atualiza a lista e tenta novamente uma vez.

## Dados extraídos

```json
{
  "store_name": "Meruru Curitiba",
  "tournament_datetime": "Fri. February 20, 2026 07:00 PM~",
  "tournament_date": "2026-02-20",
  "model": "qwen/qwen3.6-27b",
  "players": [
    {
      "rank": 1,
      "name": "Edu",
      "member_id": "0000238403",
      "points": "12",
      "omw": "47.1"
    }
  ]
}
```

Campos que não aparecem no print são retornados como string vazia. A API não
inventa loja ou data ausentes.

## Estrutura do projeto

| Caminho | Responsabilidade |
|---|---|
| `api/index.py` | Única implementação da API, usada pela Vercel e pelo Docker |
| `main.py` | Entrada compatível com Uvicorn; apenas reexporta `api.index:app` |
| `vercel.json` | Roteamento e duração da função Vercel |
| `Dockerfile` | Imagem para Hugging Face Spaces ou outro host Docker |
| `requirements.txt` | Dependências Python |
| `index.html`, `script.js`, `style.css` | Interface manual de teste |
| `TROUBLESHOOTING.md` | Diagnóstico de Vercel, Groq, CORS, timeout e OCR |
| `DEPLOYMENT.md` | Configuração, deploy, atualização, rollback e plano B |

Manter a lógica somente em `api/index.py` evita que Vercel e Docker usem
modelos ou prompts diferentes.

## Variáveis de ambiente

| Variável | Obrigatória | Padrão | Uso |
|---|---:|---|---|
| `GROQ_API_KEY` | Sim | — | Chave secreta da Groq |
| `GROQ_MODEL` | Não | `qwen/qwen3.6-27b` | Modelo visual preferencial |
| `GROQ_FALLBACK_MODELS` | Não | vazio | IDs alternativos separados por vírgula |
| `GROQ_MAX_TOKENS` | Não | `1200` | Máximo de tokens da resposta |

Exemplo:

```text
GROQ_MODEL=qwen/qwen3.6-27b
GROQ_FALLBACK_MODELS=modelo-visual-2,modelo-visual-3
GROQ_MAX_TOKENS=1200
```

Não aumente `GROQ_MAX_TOKENS` sem verificar a cota TPM da conta. Um valor de
8192 fez a requisição ultrapassar o limite da Groq mesmo quando a resposta real
era curta.

## Execução local

Requisitos: Python 3.12 recomendado e uma chave Groq ativa.

```powershell
cd digimon-ocr-api
python -m pip install -r requirements.txt
```

Crie `.env` somente no ambiente local:

```text
GROQ_API_KEY=gsk_sua_chave
GROQ_MODEL=qwen/qwen3.6-27b
```

Inicie a API:

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Verifique:

```powershell
curl.exe http://localhost:8000/health
curl.exe -X POST http://localhost:8000/process -F "file=@../test_image/test.png;type=image/png"
```

Documentação interativa local:

```text
http://localhost:8000/docs
```

## Endpoints

### `GET /health`

Verifica chave, seleção e disponibilidade real do modelo.

```json
{
  "status": "ok",
  "configured_model": "qwen/qwen3.6-27b",
  "selected_model": "qwen/qwen3.6-27b",
  "model_available": true,
  "model_error": "",
  "groq_api_key_configured": true
}
```

Interpretação:

- `status: ok`: a API conseguiu consultar a Groq e selecionar um modelo visual.
- `status: degraded`: chave, rede ou seleção de modelo falhou.
- `configured_model`: preferência definida no ambiente.
- `selected_model`: modelo realmente utilizado, que pode ser um fallback.
- `model_error`: causa da falha quando o status é `degraded`.

### `POST /process`

Recebe `multipart/form-data` com uma imagem no campo `file`.

```powershell
curl.exe -X POST https://digimon-ocr-api.vercel.app/process `
  -F "file=@../test_image/test.png;type=image/png"
```

Por compatibilidade com o cliente atual, erros de processamento ainda são
devolvidos em um corpo JSON com `players: []`. O cliente deve verificar
`data.error`, mesmo quando o HTTP externo aparece como 200:

```json
{
  "store_name": "",
  "tournament_datetime": "",
  "tournament_date": "",
  "players": [],
  "model": "qwen/qwen3.6-27b",
  "error_code": "groq_rate_limit",
  "error": "mensagem original",
  "raw": "sem resposta"
}
```

Possíveis `error_code`:

| Código | Significado |
|---|---|
| `groq_authentication_error` | Chave ausente, inválida ou revogada |
| `groq_model_not_found` | Modelo removido ou não acessível |
| `groq_request_too_large` | Tokens ou imagem excederam um limite |
| `groq_rate_limit` | Cota RPM/TPM atingida |
| `invalid_model_json` | O modelo não produziu JSON processável |
| `ocr_processing_error` | Outra falha no pipeline |

### `POST /debug`

Executa a mesma chamada visual e devolve a resposta bruta. Use apenas para
investigar prompt ou resposta do modelo; `/process` é o endpoint de produção.

## Integração com o DigiStats

O cliente deve diferenciar erro HTTP, erro declarado pela API e uma extração
válida sem jogadores:

```javascript
const formData = new FormData();
formData.append("file", imageFile);

const response = await fetch(
  "https://digimon-ocr-api.vercel.app/process",
  { method: "POST", body: formData }
);

const data = await response.json();

if (!response.ok) {
  throw new Error(`OCR HTTP ${response.status}`);
}
if (data.error) {
  throw new Error(`${data.error_code}: ${data.error}`);
}

const players = data.players;
```

Não interprete automaticamente `players: []` como “o print não tem jogadores”
sem verificar antes a propriedade `error`.

## Deploy na Vercel

1. Importe o repositório na Vercel.
2. Em **Settings → Environment Variables**, configure `GROQ_API_KEY`.
3. Opcionalmente configure `GROQ_MODEL`, `GROQ_FALLBACK_MODELS` e
   `GROQ_MAX_TOKENS`.
4. Faça um novo deploy. Mudanças de variável devem ser seguidas de redeploy
   para garantir uma nova função com o ambiente atualizado.
5. Abra `/health` e confirme `status: ok` e `model_available: true`.
6. Envie uma imagem conhecida para `/process`.
7. Confirme no JSON qual valor foi retornado em `model`.

O `vercel.json` encaminha todas as rotas para `api/index.py` e permite até 60
segundos por execução.

## Deploy com Docker/Hugging Face

O container inicia:

```text
uvicorn main:app --host 0.0.0.0 --port 7860
```

Como `main.py` reexporta a mesma aplicação da Vercel, os dois ambientes usam o
mesmo modelo, prompt, parser e validação.

## Checklist depois de qualquer deploy

- [ ] `/health` retorna `status: ok`.
- [ ] `groq_api_key_configured` é `true`.
- [ ] `model_available` é `true`.
- [ ] `selected_model` é conhecido e esperado.
- [ ] O print de referência retorna os cinco jogadores esperados.
- [ ] O DigiStats mostra o erro da API em vez de apenas uma tabela vazia.
- [ ] A chave Groq não aparece no JavaScript, no Git ou nos logs.

## Limitações conhecidas

- OCR por modelo visual pode errar acentos e nomes próprios.
- Campos que estão fora do recorte não podem ser extraídos.
- Um modelo escolhido automaticamente deve ser validado com a imagem de
  referência antes de ser considerado aprovado.
- A função Vercel possui limites de duração e tamanho de requisição.
- O endpoint é público. Para uso amplo, adicione limitação por IP/usuário e
  monitore consumo da Groq.

## Quando algo parar de funcionar

Comece por `GET /health`, depois teste `POST /process` fora do navegador e só
então examine os logs. O procedimento completo está em
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

Para criar ou atualizar os ambientes de produção, consulte
[DEPLOYMENT.md](DEPLOYMENT.md).
