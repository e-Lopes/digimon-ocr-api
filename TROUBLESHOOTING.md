# Troubleshooting — Digimon OCR API

Este guia ajuda a identificar em qual camada está a falha:

```text
DigiStats/navegador → rede/CORS → Vercel → FastAPI → Groq → modelo → parser
```

## Diagnóstico rápido

| Sintoma | Camada mais provável | Primeira verificação |
|---|---|---|
| Site ou endpoint não abre | DNS/Vercel | Abrir `/health` |
| `/health` retorna 404 | Deploy/roteamento Vercel | Conferir `vercel.json` e deployment ativo |
| `/health` retorna 500 | Importação/runtime Vercel | Logs da função |
| `/health` mostra `degraded` | Groq, chave ou modelo | Ler `model_error` |
| Funciona no `curl`, falha no DigiStats | Browser/CORS/frontend | Network e Console do navegador |
| `players: []` com `error` | Groq ou processamento | Ler `error_code` e `error` |
| `players: []` sem `error` | Imagem, prompt ou validação | Usar `/debug` e conferir IDs |
| Vercel mostra 504 | Timeout | Duração da função e latência Groq |
| Groq mostra 401 | Credencial | Recriar/verificar `GROQ_API_KEY` |
| Groq mostra 404 | Modelo removido | `/health`, modelos disponíveis e redeploy |
| Groq mostra 413 | Tokens/requisição Groq | Reduzir `GROQ_MAX_TOKENS` ou imagem |
| Groq mostra 429 | Cota RPM/TPM | Aguardar, reduzir chamadas ou rever plano |

## Passo 1 — verificar a Vercel e a Groq ao mesmo tempo

Abra:

```text
https://digimon-ocr-api.vercel.app/health
```

Resposta saudável:

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

### Como interpretar

`groq_api_key_configured: false` significa problema de configuração na Vercel,
antes mesmo do OCR. Configure a chave em **Settings → Environment Variables** e
faça redeploy.

`groq_api_key_configured: true` com `model_available: false` significa que a
variável existe, mas a consulta à Groq falhou. `model_error` diferencia chave
inválida, rede, conta ou ausência de modelos visuais.

`configured_model` diferente de `selected_model` significa que o fallback foi
ativado. A API pode continuar funcionando, mas o novo modelo deve ser validado.

## Passo 2 — testar sem o DigiStats

No PowerShell:

```powershell
curl.exe --ssl-no-revoke -sS `
  https://digimon-ocr-api.vercel.app/health
```

Envie a imagem de referência:

```powershell
curl.exe --ssl-no-revoke -sS `
  -X POST https://digimon-ocr-api.vercel.app/process `
  -F "file=@../test_image/test.png;type=image/png"
```

Se esse comando funcionar e o DigiStats não, o problema está no frontend,
CORS, timeout do browser ou manipulação da resposta — não no OCR.

## Passo 3 — interpretar o JSON antes dos logs

A API mantém HTTP 200 em erros de OCR por compatibilidade com o cliente atual.
Por isso, sempre verifique:

```javascript
if (data.error) {
  console.error(data.error_code, data.error);
}
```

Uma tabela vazia pode ter duas causas muito diferentes:

```json
{"players": [], "error": "..."}
```

Houve falha técnica.

```json
{"players": []}
```

A chamada terminou, mas nenhum jogador com ID válido foi extraído.

## Passo 4 — ler os logs da Vercel

Um log como:

```text
POST 200 /process
HTTP Request: POST https://api.groq.com/openai/v1/chat/completions 404 Not Found
```

significa:

- a Vercel recebeu e executou `/process`;
- a função FastAPI não caiu;
- a chamada interna à Groq falhou;
- o problema é o modelo/conta Groq, não o roteamento Vercel;
- o `200` externo ocorre porque a API encapsulou o erro em JSON.

Erros `404 /favicon.ico`, `404 /favicon.png` e `404 /robots.txt` são requisições
automáticas do navegador ou de crawlers. Eles não interferem no OCR.

## Casos comuns

### Modelo removido ou sem acesso

Sinais:

```text
404 Not Found
model_not_found
The model ... does not exist or you do not have access to it
```

Procedimento:

1. Abra `/health`.
2. Veja `configured_model`, `selected_model` e `model_error`.
3. Consulte os modelos disponíveis na conta Groq.
4. Defina o novo ID em `GROQ_MODEL` na Vercel.
5. Se houver alternativas aprovadas, coloque-as em
   `GROQ_FALLBACK_MODELS`, separadas por vírgula.
6. Faça redeploy.
7. Repita `/health` e o print de referência.

O código consulta as modalidades dos modelos e tenta substituir um modelo
removido. Isso reduz indisponibilidade, mas não garante que um modelo novo tenha
a mesma precisão; o teste visual continua obrigatório.

### Limite de tokens — Groq 413

Uma imagem consome tokens de entrada. `max_tokens` reserva tokens de saída e
também entra no cálculo da cota TPM. Portanto, uma resposta curta ainda pode
ser rejeitada se o máximo solicitado for muito alto.

Use inicialmente:

```text
GROQ_MAX_TOKENS=1200
```

Se prints com muitos jogadores forem truncados, aumente gradualmente e confira
a cota da conta. Não volte diretamente para 8192.

### Rate limit — Groq 429

Verifique no erro se o limite é RPM, TPM ou diário.

- O DigiStats já deve enviar imagens sequencialmente, não todas em paralelo.
- Evite uma segunda chamada ao modelo para a mesma imagem.
- Implemente espera progressiva apenas para 429 e falhas temporárias.
- Não repita indefinidamente: isso aumenta o congestionamento e o custo.

### Chave inválida — Groq 401

1. Confirme que `GROQ_API_KEY` está configurada para o ambiente correto
   (Production, Preview ou Development).
2. Não imprima a chave nos logs.
3. Se houver dúvida sobre exposição, revogue e gere outra.
4. Faça redeploy depois da alteração.

### Timeout — Vercel 504

1. Veja se a Groq chegou a receber a chamada.
2. Confira a duração na linha do log Vercel.
3. Confirme `maxDuration` em `vercel.json`.
4. Reduza tamanho da imagem e evite chamadas duplicadas.
5. Diferencie um timeout ocasional de uma falha consistente do modelo.

### Imagem grande — Vercel ou Groq 413

Há dois 413 possíveis:

- Resposta gerada pela Vercel antes de executar a função: corpo do upload
  excedeu o limite da plataforma.
- Resposta mencionando modelo, tokens ou TPM: rejeição da Groq.

No primeiro caso, redimensione/comprima a imagem no DigiStats antes do upload.
No segundo, reduza `GROQ_MAX_TOKENS`, resolução ou número de chamadas.

### Funciona no curl, mas não no GitHub Pages

Abra DevTools → Network e verifique:

- URL exata de `/process`;
- método `POST`;
- campo multipart chamado `file`;
- status e corpo da resposta;
- mensagens de CORS;
- timeout configurado pelo frontend.

O backend atualmente permite todas as origens. Se isso for restringido no
futuro, inclua explicitamente o domínio `https://<usuario>.github.io`.

### A API responde sem jogadores e sem erro

Possibilidades:

- o print não contém a tabela;
- a tabela está cortada ou ilegível;
- o modelo retornou IDs com quantidade errada de dígitos;
- todos os jogadores foram removidos pela validação;
- a resposta foi válida, mas o prompt não identificou as linhas.

Use `POST /debug` e confira o texto bruto. Compare `member_id` com a regra:

```text
10 dígitos, ou GUEST seguido de dígitos
```

## Imagem de referência

O arquivo `../test_image/test.png` deve retornar cinco jogadores:

| Rank | Nome | Member ID | Pontos | OMW |
|---:|---|---|---:|---:|
| 1 | Philippe | 0000411943 | 9 | 48.1 |
| 2 | Krysto | 0000906712 | 6 | 66.7 |
| 3 | João Muller | 0000473932 | 4 | 62.9 |
| 4 | Cóbra | 0000859691 | 4 | 44.4 |
| 5 | Melro | 0000918076 | 3 | 83.4 |

Nomes próprios e acentos são os campos mais sujeitos a pequenas divergências.
IDs, pontos e OMW devem coincidir exatamente.

## Checklist de incidente

Copie e preencha ao investigar:

```text
Horário e fuso:
URL do deployment:
Deployment/commit:
Resposta de /health:
Status HTTP de /process:
error_code:
error:
configured_model:
selected_model:
Tamanho e tipo da imagem:
Funciona localmente?:
Funciona via curl?:
Funciona no DigiStats?:
Trecho relevante do log Vercel:
```

## Monitoramento recomendado

- Chamar `/health` periodicamente.
- Executar o print de referência após cada deploy.
- Criar um teste agendado semanal no GitHub Actions.
- Alertar quando `status` for `degraded` ou quando o modelo selecionado mudar.
- Monitorar consumo e rate limits no painel Groq.

Essa combinação detecta remoção de modelo antes que o problema seja percebido
pelos usuários do DigiStats.
