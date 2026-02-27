---
title: Digimon OCR API
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
short_description: OCR de ranking do Digimon TCG+ com FastAPI e Groq Vision
---

# Digimon OCR API

API para extrair dados de ranking de torneios do aplicativo Digimon TCG+ a partir de imagens (prints), retornando JSON estruturado.

## O que esta API faz

- Recebe uma imagem via upload.
- Envia a imagem para um modelo multimodal no Groq.
- Extrai:
  - `store_name`
  - `tournament_datetime`
  - `tournament_date` (normalizada em `YYYY-MM-DD`, quando possivel)
  - lista de `players` (rank, nome, member_id, pontos, OMW)
- Filtra jogadores invalidos (aceita apenas `member_id` com 10 digitos ou `GUEST` + digitos).

## Stack

- Python 3.12
- FastAPI
- Uvicorn
- Groq SDK
- Docker (para deploy no Hugging Face Spaces)

## Estrutura do projeto

- `main.py`: API FastAPI e logica de OCR/normalizacao
- `requirements.txt`: dependencias
- `Dockerfile`: imagem e comando de execucao
- `index.html`, `script.js`, `style.css`: interface web simples para upload em lote

## Variaveis de ambiente

- `GROQ_API_KEY` (obrigatoria)

Sem essa variavel, a aplicacao falha no startup.

## Como rodar localmente

1. Instale as dependencias:

```bash
pip install -r requirements.txt
```

2. Defina a chave da Groq:

```bash
export GROQ_API_KEY="sua_chave_aqui"
```

No Windows PowerShell:

```powershell
$env:GROQ_API_KEY="sua_chave_aqui"
```

3. Rode a API:

```bash
uvicorn main:app --host 0.0.0.0 --port 7860
```

## Endpoints

### `POST /process`

Processa a imagem e retorna os dados estruturados.

`multipart/form-data`:
- campo: `file`

Exemplo com `curl`:

```bash
curl -X POST "http://localhost:7860/process" \
  -F "file=@print_torneio.jpg"
```

Resposta esperada:

```json
{
  "store_name": "Meruru Curitiba",
  "tournament_datetime": "Fri. February 20, 2026 07:00 PM~",
  "tournament_date": "2026-02-20",
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

Em caso de erro:

```json
{
  "store_name": "",
  "tournament_datetime": "",
  "tournament_date": "",
  "players": [],
  "error": "mensagem de erro",
  "raw": "resposta bruta do modelo"
}
```

### `POST /debug`

Retorna apenas o texto bruto do modelo (util para ajuste de prompt e depuracao).

### `GET /health`

Healthcheck para monitoramento do servico.

Exemplo de resposta:

```json
{
  "status": "ok",
  "model": "meta-llama/llama-4-scout-17b-16e-instruct",
  "groq_api_key_configured": true
}
```

## Deploy no Hugging Face Spaces

Este repositorio ja esta pronto para Spaces com `sdk: docker`.

Passos:

1. Crie um Space (Docker).
2. Suba estes arquivos.
3. Em `Settings > Variables and secrets`, adicione:
   - `GROQ_API_KEY`
4. O Space iniciara com:

```bash
uvicorn main:app --host 0.0.0.0 --port 7860
```

## Observacoes

- OCR por LLM pode variar conforme qualidade do print (corte, blur, reflexo, zoom).
- Se quiser usar a interface web localmente, ajuste `API_BASE_URL` em `script.js`.

## Pronto para producao (checklist rapido)

1. Configurar `GROQ_API_KEY` no Space.
2. Confirmar endpoint `GET /health` retornando `status: ok`.
3. No frontend, usar retry para primeira chamada (cold start).
4. Monitorar logs de runtime para timeouts da chamada ao modelo.
