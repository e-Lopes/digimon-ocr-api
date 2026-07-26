# Deploy e operação

Este guia cobre configuração inicial, atualização de código, troca de modelo,
rollback e uso do Hugging Face Spaces como ambiente alternativo.

## Ambientes

```text
DigiStats (GitHub Pages)
        │
        ├── produção → Vercel → Groq
        │
        └── contingência → Hugging Face Space → Groq
```

O Hugging Face substitui a hospedagem da API, não a Groq. Se a Groq inteira
estiver indisponível, Vercel e Hugging Face falharão da mesma forma. Para
contornar uma indisponibilidade do provedor seria necessário integrar um segundo
provedor visual.

## 1. Configurar a Groq

### Criar a chave

1. Entre no console da Groq.
2. Crie uma API key para este projeto.
3. Copie a chave uma única vez.
4. Salve-a como `GROQ_API_KEY` na Vercel ou como Secret no Hugging Face.
5. Nunca coloque a chave no GitHub Pages, em `.env.example` ou no Git.

### Escolher o modelo

O padrão validado em 26 de julho de 2026 é:

```text
qwen/qwen3.6-27b
```

Variáveis recomendadas:

```text
GROQ_MODEL=qwen/qwen3.6-27b
GROQ_FALLBACK_MODELS=
GROQ_MAX_TOKENS=1200
```

O código consulta `/models` da Groq e confirma se o modelo aceita imagem. Se o
preferencial desaparecer, procura os fallbacks configurados e, por último,
outro modelo visual ativo da conta.

### Troca emergencial de modelo

Quando a Groq remover um modelo:

1. Consulte os modelos visuais disponíveis no console Groq.
2. Teste o candidato localmente com `test_image/test.png`.
3. Altere `GROQ_MODEL` na Vercel.
4. Mantenha o modelo anterior fora da lista de fallbacks.
5. Faça redeploy da Vercel.
6. Confirme `/health` e `/process`.
7. Atualize `DEFAULT_MODEL` em `api/index.py` em um commit posterior.

Trocar primeiro a variável permite restaurar o serviço sem esperar uma mudança
de código, desde que o novo modelo aceite os parâmetros atuais.

## 2. Deploy na Vercel

### Configuração inicial pelo GitHub

1. Envie a pasta `digimon-ocr-api` para um repositório GitHub.
2. Na Vercel, escolha **Add New → Project**.
3. Importe o repositório.
4. Se a API estiver dentro de um monorepo, defina **Root Directory** como
   `digimon-ocr-api`.
5. Use **Framework Preset: Other**.
6. Não é necessário configurar Build Command para esta função Python.
7. Adicione as variáveis de ambiente antes do primeiro deploy.
8. Clique em **Deploy**.

O `vercel.json` encaminha as rotas para `api/index.py` e configura duração máxima
de 60 segundos.

### Variáveis na Vercel

Em **Project → Settings → Environment Variables**, crie:

| Nome | Tipo | Ambientes | Valor |
|---|---|---|---|
| `GROQ_API_KEY` | Secret | Production e Preview | chave Groq |
| `GROQ_MODEL` | Plain/Encrypted | Production e Preview | modelo preferencial |
| `GROQ_FALLBACK_MODELS` | Plain/Encrypted | Production e Preview | lista separada por vírgula |
| `GROQ_MAX_TOKENS` | Plain | Production e Preview | `1200` |

Depois de alterar uma variável, faça um novo deployment. Uma função que já foi
construída não passa a usar automaticamente a revisão nova do ambiente.

### Atualizar o código

Antes do push:

```powershell
cd digimon-ocr-api
python -m pip install -r requirements.txt
python -m py_compile api\index.py main.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -X POST http://127.0.0.1:8000/process `
  -F "file=@../test_image/test.png;type=image/png"
```

Depois:

```powershell
git status
git diff
git add api/index.py main.py README.md TROUBLESHOOTING.md DEPLOYMENT.md requirements.txt Dockerfile .env.example
git commit -m "Update Groq vision model and deployment docs"
git push
```

Se a Vercel estiver conectada à branch enviada, o push cria um novo deployment.
Confira a tela **Deployments** e aguarde o status **Ready**.

### Validar produção

```powershell
curl.exe --ssl-no-revoke -sS `
  https://digimon-ocr-api.vercel.app/health

curl.exe --ssl-no-revoke -sS `
  -X POST https://digimon-ocr-api.vercel.app/process `
  -F "file=@../test_image/test.png;type=image/png"
```

Não considere o deploy concluído apenas porque a Vercel mostra `Ready`. Confirme:

- `status` igual a `ok`;
- `model_available` igual a `true`;
- `selected_model` igual ao modelo esperado;
- cinco jogadores na imagem de referência;
- ausência da propriedade `error`.

### Redeploy manual

Use um redeploy quando houver alteração apenas nas variáveis ou quando a
integração Git não iniciar automaticamente:

1. Abra **Project → Deployments**.
2. Localize o deployment mais recente da branch correta.
3. Abra o menu do deployment.
4. Selecione **Redeploy**.
5. Evite reutilizar cache quando estiver investigando dependências antigas.
6. Execute novamente os testes de produção.

### Rollback

Se um deployment novo falhar:

1. Abra **Deployments**.
2. Selecione o último deployment que passou no teste de referência.
3. Use a ação de promover/reatribuir esse deployment para produção.
4. Verifique se as variáveis de ambiente necessárias ainda existem.
5. Teste `/health` e `/process`.

Um rollback do código não restaura automaticamente um modelo que foi removido
pela Groq. Nesse caso, corrija também `GROQ_MODEL`.

## 3. Atualizar o DigiStats

O PWA deve usar a URL ativa da API:

```javascript
const OCR_API_URL = "https://digimon-ocr-api.vercel.app";
```

O cliente precisa ler o corpo antes de concluir que não há jogadores:

```javascript
const response = await fetch(`${OCR_API_URL}/process`, {
  method: "POST",
  body: formData,
});
const data = await response.json();

if (!response.ok || data.error) {
  throw new Error(data.error || `OCR HTTP ${response.status}`);
}
```

Quando trocar para o Hugging Face, altere somente `OCR_API_URL` ou mantenha as
duas URLs em uma configuração com fallback controlado.

## 4. Hugging Face Spaces como plano B

### O que esse plano resolve

O Space ajuda quando o problema está na Vercel: timeout específico, deployment,
roteamento ou indisponibilidade da plataforma. Ele não resolve:

- chave Groq inválida;
- modelo Groq removido;
- rate limit da Groq;
- indisponibilidade geral da Groq.

### Criar o Space

1. No Hugging Face, escolha **New Space**.
2. Selecione **Docker** como SDK.
3. Escolha uma visibilidade adequada.
4. Envie o conteúdo de `digimon-ocr-api` para o repositório do Space.
5. Em **Settings → Variables and secrets**, crie `GROQ_API_KEY` como Secret.
6. Adicione `GROQ_MODEL`, `GROQ_FALLBACK_MODELS` e `GROQ_MAX_TOKENS` como
   Variables.
7. Aguarde o build do Dockerfile.
8. Abra a URL pública do Space e teste `/health`.

O README contém `sdk: docker` e `app_port: 7860`. O Dockerfile executa com um
usuário não-root de UID 1000 e expõe a porta 7860, formato esperado para Docker
Spaces.

### Atualizar o Space

O Space é reconstruído quando recebe um novo commit. Há duas estratégias:

- manter um espelho do repositório da API no Hugging Face;
- enviar manualmente somente versões aprovadas, usando-o como ambiente estável
  de contingência.

Para evitar divergência, use o mesmo commit e as mesmas variáveis da Vercel.
Registre no README operacional qual SHA está em cada ambiente.

### Ativar o plano B

1. Confirme que `/health` do Space está saudável.
2. Envie a imagem de referência ao `/process` do Space.
3. Altere `OCR_API_URL` no DigiStats para a URL `.hf.space`.
4. Publique o DigiStats no GitHub Pages.
5. Monitore latência e cold start.

Não implemente fallback automático no browser sem limites. Se a Vercel responder
lentamente e o cliente enviar a mesma imagem também ao Space, a Groq poderá
receber chamadas duplicadas e consumir cota em dobro.

## 5. Estratégia de recuperação

| Falha | Ação principal | Plano B |
|---|---|---|
| Modelo Groq removido | Trocar `GROQ_MODEL` | Outro modelo Groq validado |
| Rate limit Groq | Reduzir chamadas/aguardar | Segundo provedor, se integrado |
| Vercel fora do ar | Verificar deployment | Ativar Hugging Face Space |
| Deploy com bug | Rollback Vercel | Space no último commit estável |
| CORS/frontend | Corrigir DigiStats | Testar diretamente por curl |
| Imagem não reconhecida | `/debug` e prompt | Correção manual no DigiStats |

## 6. Registro mínimo de releases

Para cada publicação, anote:

```text
Data e hora:
Commit SHA:
Ambiente:
GROQ_MODEL:
GROQ_MAX_TOKENS:
Resultado de /health:
Resultado do print de referência:
Deployment URL:
Responsável:
```

Esse registro torna mais fácil comparar uma versão funcional com a atual.

## Referências oficiais

- Vercel Functions: https://vercel.com/docs/functions
- Vercel environment variables: https://vercel.com/docs/environment-variables
- Vercel deployments: https://vercel.com/docs/deployments
- Groq models: https://console.groq.com/docs/models
- Groq rate limits: https://console.groq.com/docs/rate-limits
- Hugging Face Docker Spaces: https://huggingface.co/docs/hub/spaces-sdks-docker
- Hugging Face secrets: https://huggingface.co/docs/hub/spaces-overview#managing-secrets-and-environment-variables
