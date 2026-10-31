# Vagou!

Plataforma de empregabilidade com FastAPI, PostgreSQL, Redis, Celery, Alembic e cliente Flutter Android. Interface em português, Material 3 claro/escuro, onboarding, identidade própria, jornada de candidato e área de empresas.

## Estrutura

```text
backend/
  app/
    main.py                 # inicialização e validação amigável sem ecoar dados sensíveis
    api.py                  # rotas existentes de perfil, PDF, vagas, matches e dashboard
    auth.py                 # cadastro, login, código de e-mail e reenvio
    smtp_transport.py       # Gmail/SMTP com STARTTLS ou SSL
    mailer.py               # outbox criptografada, expiração e retries
    company.py              # dígitos verificadores de CNPJ
    moderation.py           # fila privada, aprovação e vagas do contratante
    automation.py           # relatórios privados de ciclos e eventos
    automation_models.py    # modelos dos relatórios
    job_sources.py          # fontes JSON HTTPS autorizadas, sem scraping de formulários
    worker.py               # tarefas Celery de e-mail, fontes e candidaturas
    models.py / schemas.py  # persistência e contratos Pydantic v2
    security.py / passwords.py / matching.py / services.py / db.py / config.py
    courses.py              # referências oficiais com objetivos e contexto profissional
  alembic/versions/          # migrações 0001 → 0006
  tests/
  .env.example / Dockerfile / requirements.txt
mobile/
  lib/
    main.dart / api.dart / ui.dart / home.dart
    onboarding.dart / auth.dart
    candidate.dart / jobs.dart / reporting.dart / courses.dart / recruiter.dart
  android/                  # configuração SDK36, ícone e splash próprios
  test/
  pubspec.yaml
.github/workflows/          # backend CI e APK Android
compose.yaml                # serviços/portas existentes preservados
docs/OPERATIONS.md           # atualização, Gmail, moderação, fontes e release
```

## Funcionalidades

- Cadastro com código de confirmação de seis dígitos por e-mail; login só após confirmar. Empresas fornecem CNPJ, razão social e contato, sem exigir domínio corporativo próprio.
- Perfil com competências declaradas, telefone criptografado, currículo PDF privado, indicadores de preenchimento e preferências por salário, modalidade e cidade/UF.
- Matching determinístico: alto acima de75%, observação50–75%, descartado abaixo de50%; não representa probabilidade de contratação e não infere competências de PDFs.
- Vagas novas moderadas antes de publicação. Empresas acompanham fila/status e candidaturas das próprias vagas.
- Automação Premium opcional, com frequência/teto configuráveis, somente em vagas internas aprovadas; fontes externas autorizadas geram recomendações com ação manual no portal oficial.
- Dashboard visual, histórico paginado, eventos detalhados de automação e cursos com modais de resumo, objetivos, impacto e CTA oficial. As regras de certificados variam por oferta; treinamento gratuito não equivale necessariamente a certificação profissional gratuita.
- Exclusão autenticada de conta, currículo e registros associados; JWT revogável, scrypt, controles de acesso e rate limiting Redis.

## Instalação e atualização

Leia [o guia operacional](docs/OPERATIONS.md) antes de atualizar uma instalação existente. Preserve as chaves, URLs e volumes atuais. A confirmação de e-mail passa a ser exigida também das contas antigas; use o fluxo de reenvio após configurar SMTP.

Para uma instalação nova, copie `backend/.env.example` para `backend/.env`, instale `backend/requirements.txt` em um ambiente Python3.12 e gere suas chaves:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use os valores gerados em `JWT_SECRET` e `DATA_KEY` no ambiente privado, sem versionar. Configure `POSTGRES_PASSWORD` no ambiente do Compose e a senha correspondente, com percent-encoding, na `DATABASE_URL` de `backend/.env`. Dentro do Compose, os hosts são `postgres:5432` e `redis:6379`; não altere uma configuração existente que já funciona. Configure Gmail SMTP conforme o guia e execute:

```bash
docker compose up --build -d
curl --fail http://127.0.0.1:8000/health/ready
```

A documentação OpenAPI está em `/docs`. Dependências usam intervalos compatíveis, não lock com hashes; revisar e fixar dependências/imagens antes de release comercial.

## Contratos principais

Todos os caminhos abaixo usam prefixo `/v1`. Autorização: `Authorization: Bearer <access_token>`. As rotas existentes foram preservadas; a confirmação e a moderação acrescentam requisitos de acesso.

| Método | Rota | Uso |
|---|---|---|
| POST | `/auth/register` | Cadastro candidato/empresa, agenda código |
| POST | `/auth/verify-email` | Confirma código único de seis dígitos |
| POST | `/auth/resend-verification` | Reenvio limitado, resposta neutra |
| POST | `/auth/login`, `/auth/logout` | JWT de15min e revogação de sessões |
| GET, DELETE | `/me` | Perfil próprio / exclusão com senha |
| PUT | `/me/profile`, `/me/preferences` | Perfil e critérios/consentimento |
| GET, PUT | `/me/resume` | PDF privado de até5MiB/20páginas |
| GET, POST | `/jobs` | Feed aprovado / empresa cria anúncio pendente |
| GET, DELETE | `/jobs/{id}` | Detalhe aprovado / proprietário encerra |
| GET | `/matches` | Compatibilidade e lacunas, paginado |
| POST | `/jobs/{id}/applications` | Candidatura interna idempotente; externo exige ação manual |
| GET, PATCH | `/applications`, `/applications/{id}` | Histórico próprio / empresa atualiza status |
| GET | `/applications/{id}/resume` | Empresa responsável acessa currículo atual |
| GET | `/dashboard` | Contagens, média e status consolidados |
| GET | `/courses` | Catálogo oficial por competência opcional |
| GET | `/recruiter/jobs` | Vagas do proprietário, inclusive moderação |
| GET, PATCH | `/moderation/jobs`, `/moderation/jobs/{id}` | Fila e decisão por equipe autorizada |
| GET | `/automation/runs`, `/automation/runs/{id}/events` | Relatórios Premium privados |

### Cadastro e confirmação

```json
{"email":"ana@example.com","password":"SenhaLongaEUnica!2026","name":"Ana Silva","role":"candidate","privacy_version":"2026-01","consent":true}
```

Para `role=recruiter`, acrescente `company_cnpj`, `company_name`, `company_contact_email` e `company_phone` no formato `+55DDDnumero`. Não envie `is_premium`: a assinatura deve ser administrada por um processo confiável de cobrança. A integração de cobrança não foi incluída.

`POST /auth/verify-email`:

```json
{"email":"ana@example.com","code":"123456"}
```

O código acima é apenas exemplo de formato, não uma credencial ou código universal. A API só aceita o código efetivamente enviado e não o retorna nas respostas. Depois de confirmar, `POST /auth/login` recebe e-mail/senha e retorna `access_token`, `token_type=bearer`, `expires_in=900`. Não há refresh token: a sessão expirada exige novo login.

### Preferências

```json
{"titles":["Python","Backend"],"min_salary":5000,"modalities":["remote","hybrid"],"locations":["São Paulo / SP"],"automation_enabled":true,"automation_max_applications_per_run":20,"automation_interval_minutes":60}
```

Automação exige Premium, confirmação e currículo. Presencial/híbrido exige cidade/estado. Remoto ignora localização; listas vazias de filtros aceitam qualquer valor. O salário compara a máxima anunciada com o mínimo desejado, sem garantir remuneração contratada. `/matches` pagina vagas examinadas antes do filtro; continue pelo `next_offset`, inclusive em páginas vazias.

### Dashboard

`GET /dashboard` não recebe corpo. Exemplo ilustrativo:

```json
{"total_applications":42,"manual":12,"automatic":30,"observation_jobs":8,"average_match_score":86.5,"by_status":{"submitted":30,"reviewing":8,"interview":3,"hired":1}}
```

A média é das candidaturas registradas. Vagas em observação usam os critérios atuais. O timestamp `generated_at` também é retornado. `DELETE /me` recebe a senha atual em JSON e remove a conta, o PDF ativo e os registros em cascata. Currículos não são copiados por candidatura: o recrutador acessa a versão atual enquanto houver autorização.

## Android

Endpoint atual preservado do remoto: `https://nest-gents-sudden.ngrok-free.dev`. O acesso local `http://192.168.18.128:8000` continua permitido quando configurado explicitamente. SDK36/36/24, Java17, Gradle8.11.1 e AGP8.9.1 permanecem fixados. O workflow entrega um artifact com um APK; em tags `v*`, publica também um asset `.apk` direto em GitHub Releases. O download de artifacts do Actions é ZIP por regra do serviço. Leia as instruções de publicação/assinatura no guia: APK interno com assinatura de debug não é release pronto para Google Play.

## Segurança e limites de validação

A implementação não constitui certificação LGPD/Google Play nem garantia de prontidão comercial. O operador deve publicar política com controlador/contato, base legal, compartilhamento, retenção, direitos e página web de exclusão. É necessário plano de expurgo de backups, consentimento e operação de moderação. A autenticação confirma o controle do e-mail, não a identidade civil ou a regularidade empresarial.

Produção exige TLS, banco/volumes/backups criptografados, chaves em cofre, rede privada, observabilidade, revisão de segurança e assinatura Android própria. HTTP local foi mantido por requisito do ambiente de desenvolvimento. PDFs são limitados, criptografados e privados, mas parsing não substitui antivírus/CDR: integrar scanner isolado e reconciliação de arquivos órfãos. Banco e filesystem não compartilham transação. Os relatórios exigem política de retenção; o worker faz varredura paginada, ainda sem índice de matching materializado para catálogos muito grandes.

Os testes diferenciam execução real e casos ignorados. Esta máquina permite executar a suíte integrada com PostgreSQL/Redis/Celery e os testes Flutter após instalar as ferramentas; a entrega Gmail real depende da rede SMTP e das credenciais e a geração de APK é verificada no CI. Consulte os resultados da tarefa e o workflow; não trate verificação de sintaxe como prova de funcionamento integrado.
