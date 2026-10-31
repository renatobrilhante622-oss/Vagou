# Vagou!

Base de API de empregabilidade para o mercado brasileiro e cliente Flutter de referência. Não há afirmação de prontidão comercial: esta entrega precisa das validações de integração, auditoria e configurações operacionais descritas abaixo antes de produção.

## Organização

```text
backend/
  app/
    main.py          # inicialização, rate limiting Redis e health checks
    config.py        # variáveis validadas, segredos obrigatórios
    db.py            # sessões assíncronas PostgreSQL
    models.py        # usuários, vagas, candidaturas e restrições
    schemas.py       # contratos Pydantic v2
    security.py      # scrypt, JWT, autorização, Fernet
    matching.py      # regras determinísticas e filtros
    services.py      # candidatura idempotente e armazenamento
    api.py           # rotas REST v1
    worker.py        # Celery e agendamento premium
    courses.py       # referências oficiais e regras de certificação
  alembic/           # migração inicial explícita
  tests/             # testes unitários e contrato integrado
  .env.example
  requirements.txt
  Dockerfile
mobile/
  lib/api.dart       # transporte HTTPS e Android Keystore via secure storage
  lib/main.dart      # cadastro/login, feed, relatório, cursos, perfil e exclusão
  pubspec.yaml
compose.yaml
```

A aplicação não depende de portais externos: vagas são publicadas por recrutadores e candidaturas ficam disponíveis ao recrutador responsável no próprio Vagou!. Não existe envio de e-mail ou integração com ATS implícita. PDF não é usado para inferir competências; competências são declaradas pelo candidato. O score representa cobertura dessas competências, não probabilidade de contratação.

## Execução local com Docker

Requer Docker Compose, acesso aos registros oficiais e portas locais disponíveis. Não usar os exemplos de credenciais em produção.

1. Copie `backend/.env.example` para `backend/.env` sem sobrescrever configurações existentes.
2. Gere `JWT_SECRET` usando `python -c "import secrets; print(secrets.token_urlsafe(48))"` e `DATA_KEY` usando `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` em um Python com as dependências instaladas. Guarde em um gerenciador de segredos; não versionar.
3. Defina `POSTGRES_PASSWORD` no ambiente do Compose. Em `backend/.env`, defina `DATABASE_URL=postgresql+asyncpg://vagou:SENHA_URL_ENCODED@postgres:5432/vagou` e `REDIS_URL=redis://redis:6379/0`. Faça percent-encoding da senha na URL. O Compose lê a senha do banco no ambiente do comando, não de `backend/.env`.
4. Execute `docker compose up --build -d`. A migração precisa terminar antes da API e workers. Apenas um processo beat deve estar ativo.
5. Valide com `curl --fail http://127.0.0.1:8000/health/ready`; consulte `/docs` e `/openapi.json` para contratos completos. O endereço local é para desenvolvimento, não para configurar o aplicativo distribuído.
6. Execute `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt` e `VAGOU_TEST_URL=http://127.0.0.1:8000 .venv/bin/python -m unittest discover -s tests -v`. Os testes usam exclusivamente contas próprias descartáveis. Não rodar testes contra produção.
7. Pare com `docker compose down`. Não usar `down -v` se precisar preservar dados.

Sem Docker: configure PostgreSQL 16, Redis 7 e as URLs locais; na pasta `backend`, instale as dependências, exporte as variáveis do `.env` de forma segura, rode `alembic upgrade head`, `uvicorn app.main:app`, `celery -A app.worker:celery worker --concurrency=2` e, em um único processo separado, `celery -A app.worker:celery beat --schedule=/tmp/vagou-beat`. Arquivos `.env` são carregados pela aplicação, não são comandos shell.

As versões em requirements são intervalos compatíveis, não um lock reproduzível. Gerar lock com hashes, revisar CVEs e fixar imagens por digest em CI antes de release. Não foi possível resolver um lock confiável nesta máquina sem acesso ao registro.

## Contratos principais

Prefixo `/v1`; autorização `Authorization: Bearer <access_token>`. UUIDs identificam recursos. Respostas de erro usam `detail`. Cadastro não aceita `is_premium`: somente uma integração de cobrança confiável deve conceder esse direito. Não há endpoint público de promoção a Premium nem cobrança implementada.

| Método | Caminho | Acesso / finalidade |
|---|---|---|
| POST | /auth/register | público, candidato ou recrutador |
| POST | /auth/login | público, token de 15 minutos |
| POST | /auth/logout | revoga todas as sessões do usuário |
| GET, DELETE | /me | perfil; exclusão com senha recente |
| PUT | /me/profile | candidato, competências e telefone |
| PUT | /me/preferences | candidato, filtros e consentimento de automação |
| PUT, GET | /me/resume | candidato, PDF privado de até 5 MiB e 20 páginas |
| POST, GET | /jobs | recrutador cria; listagem pública paginada |
| GET, DELETE | /jobs/{id} | detalhe público; proprietário encerra |
| GET | /matches | candidato, score, categoria e lacunas |
| POST | /jobs/{id}/applications | candidato, envio idempotente |
| GET | /applications | histórico paginado; recrutador vê só suas vagas |
| PATCH | /applications/{id} | recrutador proprietário atualiza status |
| GET | /applications/{id}/resume | recrutador proprietário baixa currículo |
| GET | /dashboard | candidato, métricas consolidadas |
| GET | /courses?skill=python | catálogo oficial por competência |

### Cadastro

```json
{
  "email": "ana@example.com",
  "password": "UmaSenhaLongaEUnica!2026",
  "name": "Ana Silva",
  "role": "candidate",
  "privacy_version": "2026-01",
  "consent": true
}
```

### Login

```json
{"email":"ana@example.com","password":"UmaSenhaLongaEUnica!2026"}
```

Resposta (token abaixo representado simbolicamente, nunca um segredo real):

```json
{"access_token":"<JWT assinado>","token_type":"bearer","expires_in":900}
```

Não há refresh token nesta versão: após expiração, novo login é necessário. O logout incrementa a versão do token no banco e invalida todas as sessões; exclusão invalida tokens pela ausência do usuário.

### Perfil e critérios

`PUT /me/profile`:

```json
{"name":"Ana Silva","phone":"+5511999999999","skills":["python","sql","docker"]}
```

`PUT /me/preferences`:

```json
{
  "titles": ["Python", "Backend"],
  "min_salary": 5000,
  "modalities": ["remote", "hybrid"],
  "locations": ["São Paulo"],
  "automation_enabled": true
}
```

Ativar automação exige `is_premium=true`. A flag é administrada no banco por um processo de cobrança confiável; não conceder direitos pelo cliente. Sem Premium, o exemplo acima retorna 403. A automação exige currículo e autorização explícita, verifica elegibilidade a cada ciclo e só aplica em score >75. Filtros com listas vazias aceitam qualquer valor. Localização é ignorada para remoto. Salário compara a remuneração máxima anunciada com o mínimo do candidato; não promete que a contratação pagará aquele máximo.

### Match

```json
{
  "match_score": 75,
  "category": "observation",
  "missing_skills": ["redis"]
}
```

Score = competências exigidas atendidas / competências exigidas únicas × 100, arredondado. Normaliza caixa e acentos, preserva distinção entre Java e JavaScript. Não inventa equivalências. Alto: 76–100; observação: 50–75; descartada: 0–49. Requisitos vazios geram 0. Os contratos de vaga impedem lista vazia. O feed mobile oculta descartadas; API retorna categoria para transparência. `/matches` pagina vagas examinadas antes do filtro; continuar pelo `next_offset`, inclusive em páginas vazias. Para catálogo grande, materializar matches por versão de perfil/vaga e adotar paginação por cursor; o worker atual faz varredura paginada a cada minuto e não é uma solução de escala ilimitada.

### Dashboard

`GET /dashboard` não recebe corpo. Exemplo ilustrativo de resposta:

```json
{
  "total_applications": 42,
  "manual": 12,
  "automatic": 30,
  "observation_jobs": 8,
  "average_match_score": 86.5,
  "by_status": {"submitted":30,"reviewing":8,"interview":3,"hired":1},
  "generated_at":"2026-10-31T00:00:00Z"
}
```

A média é das candidaturas registradas, não do feed. Observação conta vagas ativas elegíveis para os filtros atuais. Status corrente e origem estão no histórico; não há log de cada transição nem histórico de ciclos sem candidatura.

### Exclusão

`DELETE /me` com `{"password":"senha atual"}` retorna 204. Remove PDF ativo, usuário, candidaturas e, para recrutador, vagas/candidaturas associadas por cascade. O acesso do recrutador ao currículo é revogado com a exclusão do candidato. A implementação usa o currículo atual, não uma cópia histórica por candidatura. Falha de armazenamento interrompe a exclusão; o cliente pode repetir a operação.

## Android / Flutter

O código é um cliente de referência com telas essenciais de candidato; recrutadores usam os contratos REST (painel mobile de gestão não implementado). Requer Flutter estável com Dart >=3.5 e SDK Android. Na pasta `mobile`, execute `flutter create --platforms=android --project-name vagou .`, revise os arquivos gerados, `flutter pub get`, `flutter analyze` e `flutter build apk --release --dart-define=API_BASE_URL=https://api.seu-dominio-real`. Informe a URL HTTPS real, sem barra final. Nenhum APK foi compilado neste ambiente, que não tem Flutter/Android SDK.

No manifesto Android gerado, declare apenas `android.permission.INTERNET` e `android:usesCleartextTraffic="false"`. Desative backup (`android:allowBackup="false"`) ou exclua explicitamente o armazenamento seguro nas regras de backup. Use o seletor de documentos do sistema; não solicitar permissão ampla de arquivos, SMS, contatos, localização ou acessibilidade. Configure applicationId próprio, assinatura em cofre/Play App Signing, ícones, versões e target SDK exigido na data da publicação. Não versionar keystore ou senhas de assinatura.

As telas cobrem login/cadastro, feed com candidatura e paginação, critérios Premium, perfil, upload PDF, cursos externos, relatórios, logout e exclusão. Material 3 acompanha tema do dispositivo. Erros, carregamento e nova autenticação são explícitos. O APK, assinatura e formulários da Play Console são etapas de release separadas.

## Segurança, LGPD e limites para produção

- Expor somente via gateway HTTPS/TLS; rede privada entre API, Redis e PostgreSQL. Configurar TLS também no banco/Redis fora de redes locais isoladas. Não habilitar confiança em headers de proxy de fontes arbitrárias. O Dockerfile desativa proxy headers; com gateway confiável, configurar lista explícita de IPs permitidos.
- Senhas usam scrypt com salt individual e comparação constante. JWT tem emissor, audiência, expiração e versão revogável. Redis impõe limites compartilhados; falha de Redis retorna 503 em vez de remover a proteção. No gateway limitar corpo a 6 MiB e configurar timeouts/conexões. O endpoint de upload limita leitura, mas o parser multipart pode consumir recursos antes da validação.
- Telefone e PDFs usam Fernet autenticado. Banco, e-mail, nome e volumes precisam de criptografia de disco/backups pelo provedor. A chave deve ficar em KMS/cofre separado dos dados; perda da chave impede recuperação. Rotação de chaves requer recriptografia operacional, não está automatizada.
- PDF é privado, baixado como anexo, com limite, parsing e rejeição de ações de catálogo/formulários/anexos. Isso **não é antivírus nem sanitização completa**: integrar scanner de malware/CDR em processo isolado, quarentena e bloqueio de download até aprovação antes de produção. Bibliotecas de parsing exigem atualizações e limites de CPU/memória.
- Arquivos são escritos atomicamente com permissões restritas. Banco e filesystem não compartilham transação: uma falha entre gravação e commit pode deixar arquivo órfão. Antes de produção, implementar outbox/reconciliação para remoção de órfãos e exclusão verificável em armazenamento durável privado. `/tmp` é apenas padrão de desenvolvimento; Compose usa volume persistente na API.
- Política de privacidade deve informar controlador, contato do encarregado, finalidade/base legal por tratamento, compartilhamento com recrutadores, direitos do titular e retenção. Consentimento de automação é separado. O aceite versionado não substitui análise jurídica das bases legais.
- Publicar página web de exclusão acessível fora do APK e cadastrar URL na Play Console; endpoint REST sozinho não satisfaz toda a experiência exigida. Definir expiração de backups e impedir restauração de dados excluídos com registro de exclusão/reaplicação. Preencher Data Safety com os fluxos reais. Não anunciar conformidade certificada com base apenas neste código.
- Antes de venda: verificação de e-mail, recuperação de senha com token de uso único, cobrança e webhooks assinados para Premium, verificação de recrutadores/antifraude, auditoria de eventos sem PII, observabilidade, testes de concorrência/carga, acessibilidade e revisão de segurança. O serviço atual permite cadastro de recrutador sem verificação empresarial.
- Cursos são referências oficiais de catálogo, sem scraping ou promessa de disponibilidade. Microsoft Learn oferece conquistas gratuitas, mas certificação profissional pode exigir exame pago; SENAI varia por região. Confirmar curso, gratuidade e certificado antes de exibir o selo “gratuito com certificado”. Links não foram verificados por rede nesta sessão.

## Estado de validação desta entrega

Testes unitários do motor são executáveis com a biblioteca padrão. A suíte integrada exige dependências e stack real; sem sua execução não é possível afirmar que banco, migrações, worker e endpoints funcionam em conjunto. A compilação Python valida apenas sintaxe. O proxy da máquina atual recusa conexões; SQLAlchemy, Alembic, Celery, pypdf e Flutter não estavam disponíveis. Veja o relatório final da tarefa para resultados efetivamente executados.