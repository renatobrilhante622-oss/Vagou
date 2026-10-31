# Operação do Vagou!

## Atualização de uma instalação existente

Preserve `JWT_SECRET`, `DATA_KEY`, `DATABASE_URL`, `REDIS_URL`, volumes e o endereço local do app. Esta atualização não muda o Compose nem publica portas novas. Faça backup do banco/volume de currículos e execute, na configuração já utilizada:

```bash
docker compose build api worker beat migrate
docker compose run --rm migrate
docker compose up -d api worker beat
```

A migração vai de `0001` a `0003`. A `0002` exige confirmação de e-mail também das contas antigas: no próximo login, solicitar novo código e confirmar. Vagas anteriores à migração permanecem aprovadas; toda vaga nova entra em moderação. Recrutadores antigos têm campos empresariais nulos preservados, sem criar CNPJ fictício. Novos cadastros empresariais exigem CNPJ válido, razão social, e-mail e telefone. A validação de CNPJ verifica formato/dígitos (inclusive alfanumérico), não consulta a situação cadastral na Receita Federal.

A migração de downgrade para antes de `0002` elimina vagas externas que não cabem no esquema antigo. Não faça downgrade com dados de produção sem um plano de restauração.

## Gmail SMTP sem domínio próprio

1. Na conta Google que enviará os códigos, ative a verificação em duas etapas.
2. Crie uma **senha de app** quando esse recurso estiver disponível para a conta. Não use a senha normal do Google.
3. Configure somente no `backend/.env` já usado pelo Compose ou no gerenciador de segredos do servidor:

| Variável | Configuração |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_SECURITY` | `starttls` |
| `SMTP_USERNAME` | Endereço completo da conta remetente |
| `SMTP_PASSWORD` | Senha de app gerada no Google |
| `SMTP_FROM` | O mesmo endereço autorizado como remetente |
| `SMTP_TIMEOUT_SECONDS` | `15` |

`SMTP_USER` é aceito como alternativa a `SMTP_USERNAME`; se `SMTP_FROM` estiver vazio, será usado o usuário autenticado. Espaços de agrupamento na senha de app Gmail são removidos. Após alterações, recrie API/worker/beat para recarregar a configuração.

Não cole senhas no chat, GitHub, logs ou arquivos versionados. A senha de app é usada pelo processo SMTP; não é um token de proxy HTTP. A rede do servidor precisa permitir SMTP com TLS para `smtp.gmail.com:587`. Não há alteração automática de firewall ou rede nesta implementação. A conta Gmail está sujeita às cotas/restrições do provedor; a equipe deve acompanhar falhas de entrega. Se a conta não disponibilizar senhas de app, será necessário outro serviço SMTP compatível autenticado e com TLS.

Recrie API, worker e beat após alterar as variáveis para aplicar a configuração. O Compose já carrega `backend/.env` nesses serviços; não é preciso editar sua estrutura.

### Confirmar envio real

- Cadastre uma conta de teste pelo aplicativo. A API persiste uma outbox criptografada e responde `delivery_status=pending` quando SMTP está configurado; isso **não é um recibo de entrega**.
- Um único Celery beat agenda `vagou.deliver_verification_mail` a cada 15 segundos. Mantenha worker e beat ativos.
- Confira a chegada na caixa de entrada/spam e use o código de seis dígitos em até dez minutos. O login permanece bloqueado até confirmar.
- O código tem no máximo cinco tentativas. Reenvios têm intervalo mínimo de 60 segundos, substituem o código anterior e recebem resposta neutra para evitar enumeração de contas.
- Sem SMTP, o cadastro retorna `configuration_required`. Depois de configurar, solicite novo código. Não há código universal, confirmação automática, OTP em respostas públicas ou bypass de produção.
- SMTP aplica TLS com validação de certificado e retries limitados. Após entrega/falha final/cancelamento, o payload do código é limpo. As falhas não registram senhas ou código nos logs.

O envio do Gmail **não foi testado com uma conta real nesta sessão**, pois as credenciais ainda não foram configuradas. Os testes unitários de transporte usam mocks para verificar autenticação, TLS e propagação de falhas; não equivalem a uma entrega real.

## Moderação

Defina `MODERATOR_EMAILS` como uma lista JSON de e-mails da equipe autorizada. As contas precisam existir e confirmar o próprio e-mail. Não coloque endereços de terceiros sem autorização.

- `GET /v1/recruiter/jobs`: o contratante consulta suas vagas, inclusive pendentes e reprovadas, com motivo.
- `GET /v1/moderation/jobs`: fila privada de vagas pendentes.
- `PATCH /v1/moderation/jobs/{id}` com `{"status":"approved","note":"Revisão concluída"}` aprova.
- Para reprovar, use `status=rejected` e informe motivo não vazio.
- Nenhum moderador aprova a própria vaga. A lista pública, detalhes, recomendações e worker consideram somente vagas ativas aprovadas. Os campos privados de moderação não são publicados no feed.

A operação de moderação pode ser feita pela API autenticada/Swagger por uma conta autorizada. O aplicativo da empresa mostra os estados de aprovação; ele não concede poderes de moderação ao contratante.

## Fontes externas e automação Premium

A importação externa é desativada por padrão. Configure apenas canais cuja API e termos permitam essa integração:

- `JOB_SOURCE_URLS`: lista JSON de endpoints HTTPS, sem credenciais na URL.
- `JOB_SOURCE_ALLOWED_HOSTS`: lista JSON dos hostnames exatos autorizados.
- `JOB_SOURCE_AUTO_APPROVE=false`: mantém anúncios importados na moderação. Só habilitar aprovação automática para fonte previamente confiável e autorizada.
- Limites: `JOB_SOURCE_MAX_BYTES=2097152`, `JOB_SOURCE_MAX_JOBS=200` por leitura.

O conector aceita envelope JSON `jobs` com campos `id`, `url`/`source_url`, `title`, `company_name`/`company`, `description`, `tags`/`keywords`, `modality`, `location`/`candidate_required_location`, `salary_min` e `salary_max`. O formato cobre feeds no estilo Remotive e parceiros equivalentes. Requisitos obrigatórios ausentes descartam o registro; HTML vira texto; não se infere salário BRL de texto em moeda estrangeira. Sem salário numérico estruturado o valor é desconhecido (zero no armazenamento) e não atende a um filtro salarial positivo. Não configurar automaticamente uma fonte significa não alegar acesso/permissão que o usuário ainda não forneceu.

As fontes exigem HTTPS e allowlist administrativa, não seguem redirects e têm timeout/tamanho limitados. A rede deve continuar aplicando proteção de egress contra resolução de destinos privados; não conceder edição dessa allowlist a candidatos.

O beat verifica fontes a cada 15 minutos e candidaturas elegíveis a cada minuto, mas cada candidato tem intervalo próprio entre 15 minutos e um dia (padrão uma hora). São necessários conta confirmada, Premium, currículo e autorização explícita. O teto real é o menor entre a preferência do candidato e `AUTOMATION_MAX_APPLICATIONS_PER_RUN` (padrão 20).

- **Vaga interna aprovada:** a candidatura é entregue ao recrutador dentro do Vagou!, com unicidade por candidato/vaga e registro `submitted`.
- **Vaga externa:** o canal oficial precisa ser aberto pelo candidato. O evento é `requires_manual`; não se conta um link aberto como envio. A implementação não envia formulários a LinkedIn, Gupy ou outros portais sem APIs e permissões desses provedores.

`GET /v1/automation/runs` entrega resumos privados paginados; `/runs/{id}/events` entrega eventos paginados, status, data e link. Cada ciclo armazena até 200 eventos detalhados e informa `omitted_events`; os totais contam todos os resultados examinados. Defina rotina operacional de retenção/expurgo de relatórios conforme a política de privacidade e volume real. Remoção de conta elimina seus relatórios em cascata.

## Android e download do APK

Preservados: endpoint atual `https://nest-gents-sudden.ngrok-free.dev` (workflow e padrão do cliente), acesso local opcional `http://192.168.18.128:8000`, `compileSdk=36`, `targetSdk=36`, `minSdk=24`, AGP 8.9.1, Gradle 8.11.1, Java 17, HTTP local autorizado e permissão Internet. O cliente usa o endpoint HTTPS atual por padrão. Se configurado para HTTP local, permite apenas a origem local indicada; nessa opção, o aparelho precisa alcançar a rede local. Não há túnel nem mudança de infraestrutura implícitos.

O workflow usa Flutter 3.35.7, instala explicitamente API36 e `platform-tools` sem o pacote obsoleto `tools`, completa apenas arquivos Android ausentes e verifica os SDKs efetivos. Em seguida executa formatação, análise, testes Flutter e compilação. Recursos de ícone/splash próprios ficam versionados e não são sobrescritos pelo scaffold temporário.

- Em commits da `main`: `Actions → Build Android APK → execução → Artifacts → vagou-release-apk`. O GitHub empacota esse download como ZIP mesmo contendo um único APK; `compression-level: 0` evita compressão desnecessária.
- Em tags `v*`: após build bem-sucedido, o job `publish-apk` publica `app-release.apk` como asset de uma GitHub Release, permitindo download direto do APK. O token tem escrita apenas nesse job. Crie a tag somente quando desejar publicar a versão. Se a release já existir, revise a execução e publique o asset conscientemente; o comando não sobrescreve releases antigas automaticamente.

O APK interno mantém a assinatura de debug usada no template anterior. Para Google Play é obrigatória assinatura de produção/Play App Signing e configuração de release própria; isso não é inventado nesta atualização. A análise e os testes Flutter podem ser executados nesta máquina com o SDK fixado; a compilação Android completa é confirmada pelo workflow.

## Testes

Na pasta `backend`, após instalar `requirements.txt` e migrar um banco descartável:

```bash
python -m unittest discover -s tests -v
```

Sem `VAGOU_TEST_URL`, os testes integrados são explicitamente ignorados. O CI backend usa PostgreSQL/Redis descartáveis e `MODERATOR_EMAILS=["moderator-ci@example.com"]`. Os testes leem a outbox apenas desse banco de testes para confirmar OTP, sem endpoint de bypass e sem imprimir o código. Não use a suíte contra produção.

No mobile:

```bash
flutter pub get
flutter analyze
flutter test
```

A aprovação de testes locais puros ou sintaxe não comprova o funcionamento integrado de PostgreSQL, Celery, SMTP ou APK. Confira sempre os resultados reais do CI e faça um teste de entrega Gmail com sua conta configurada.

## Correção SMTP e diagnóstico local de confirmação

A configuração privada de SMTP deve ficar em `backend/.env.smtp.local`, ignorado pelo Git e excluído do contexto Docker. A senha não pertence ao arquivo rastreado `backend/.env`. Use `backend/.env.smtp.example` como modelo; não copie credenciais para o repositório. `SMTP_USER` tem prioridade sobre o alias legado `SMTP_USERNAME`. O remetente explícito em `SMTP_FROM` é preservado; se vazio, será usado o usuário autenticado. No Gmail, um remetente diferente da conta autenticada precisa estar autorizado como alias em “Enviar e-mail como”; o Google pode reescrever ou rejeitar remetentes não autorizados.

O backend resolve seus arquivos dotenv a partir da pasta do próprio backend, independente do diretório de execução. `VAGOU_ENV_FILE` permite selecionar outro arquivo; os testes usam `/dev/null` para não ler credenciais privadas. Para passar o arquivo privado aos contêineres sem alterar as redes, portas ou variáveis existentes do banco:

```bash
docker compose -f compose.yaml -f compose.smtp.yaml up -d --build api worker beat
```

O arquivo privado precisa existir na máquina que executa esse comando. Arquivos privados criados no ambiente de desenvolvimento em nuvem não são enviados ao GitHub nem ao seu computador. `.dockerignore` impede que arquivos dotenv reais sejam incorporados às imagens. O overlay injeta as variáveis somente em tempo de execução.

Os logs indicam fases de conexão, STARTTLS, autenticação, envio e aceite SMTP, e classificam falhas pelo tipo e código numérico do provedor. Eles não incluem senha, destinatário, conteúdo da mensagem nem resposta bruta do Google. Aceite SMTP não comprova chegada à caixa de entrada.

A conta e seu desafio de confirmação são gravados antes da tentativa de envio. A tentativa imediata tem orçamento de cinco segundos (`VERIFICATION_DELIVERY_TIMEOUT_SECONDS`, máximo dez); lentidão não mantém o cadastro aberto indefinidamente. A outbox continua permitindo retries. Um timeout pode resultar em entrega duplicada do mesmo código, mas apenas o desafio atual pode ser confirmado uma vez.

### Fallback solicitado para testes

Somente em desenvolvimento/testes, defina no arquivo privado:

```dotenv
APP_ENV=development
DEBUG_VERIFICATION_CODES=true
```

Se a entrega imediata falhar ou o SMTP não estiver configurado, o processo da **API**, depois do commit do cadastro, escreve `DEBUG VERIFICATION CODE: ` seguido dos seis dígitos nos logs. Consulte `docker compose -f compose.yaml -f compose.smtp.yaml logs api` em um terminal privado. O mesmo vale para um reenvio efetivamente agendado. A conta permanece pendente até confirmar o código; não há bypass de autenticação.

Esse recurso é falso por padrão e permanece inativo com `APP_ENV=production`, mesmo que o flag esteja ligado. Ao terminar os testes, use `APP_ENV=production` e `DEBUG_VERIFICATION_CODES=false` e recrie os serviços. Evite compartilhar logs de teste, pois eles passam a conter códigos de acesso. Nenhum código real deve ser publicado em issues ou no Git.

## Plano Premium e automação: acesso efetivo

`GET /v1/me` mantém `is_premium` e acrescenta `entitlements`:

```json
{"is_premium":false,"entitlements":{"plan":"test","can_automate":true,"is_test_access":true,"reason":"available"}}
```

Esse exemplo só é possível para uma conta verificada autorizada em ambiente de desenvolvimento/teste. A UI usa `can_automate` da API, atualiza a conta ao retornar ao app/abrir perfil ou relatórios e permite atualizar manualmente sem perder formulários em edição. O plano não é uma permissão congelada no JWT: API e worker consultam o estado atual no servidor.

### Contas de teste

No arquivo privado de configuração do servidor, use `APP_ENV=development` ou `APP_ENV=test` e `PREMIUM_TEST_EMAILS` como lista JSON dos endereços explicitamente autorizados. A lista padrão é vazia. Reinicie API e worker ao mudar configuração. Em `APP_ENV=production`, a lista de teste é ignorada. Não existe concessão automática a todas as contas e não se aceita `is_premium` enviado pelo cliente.

### Assinaturas e concessão pelo operador

O campo `is_premium` existente continua sendo a fonte de assinatura ativa. Enquanto não houver integração de cobrança, um operador autorizado com acesso ao servidor pode conceder ou revogar explicitamente o plano:

```bash
docker compose exec api python -m app.manage_premium --email candidato@example.com --grant
docker compose exec api python -m app.manage_premium --email candidato@example.com --revoke
```

Use o e-mail real da conta desejada; os endereços acima são exemplos. O comando exige conta existente de candidato, é idempotente e não cria conta fictícia. Revogar também desativa o consentimento de automação para novos ciclos. Conceder o plano não ativa consentimento e não elimina a confirmação de e-mail. Isso não processa pagamentos nem comprova uma assinatura em provedor externo. Nenhum endpoint público permite autopromoção.

### Fluxo do envio automático

1. Confirme o e-mail, envie currículo, declare competências e salve cargo, modalidade, cidade/UF quando presencial/híbrido e faixa salarial. A automação exige autorização explícita.
2. O salário máximo desejado é opcional (`max_salary=null` remove esse filtro). A faixa da vaga deve sobrepor a faixa desejada. A localização aceita cidade/UF com barra, vírgula ou hífen separado; UF e acentos são normalizados. Remoto continua ignorando cidade.
3. O botão **Iniciar busca agora** usa `POST /v1/automation/run`, sem payload de candidato ou permissões. A API agenda exclusivamente o usuário autenticado com `force=true`; não inicia todos os usuários. Solicitações repetidas em 30 segundos são deduplicadas. Erros de pré-requisitos são 409 com código orientativo, não falso erro de cadastro duplicado.
4. A execução imediata ultrapassa apenas o intervalo agendado, nunca confirmação, Premium, consentimento, currículo, aprovação da vaga, filtros ou limites de candidatura. O beat continua respeitando a frequência escolhida.
5. O worker percorre todas as páginas de vagas ativas aprovadas e aplica a compatibilidade alta (>75%). Atingir o teto interrompe apenas novos envios, não a análise das páginas seguintes. Há prefetch das candidaturas existentes por página e unicidade por candidato/vaga.
6. Os eventos distinguem envio, candidatura já existente, vaga externa manual, currículo/critério ausente e `limit_reached` (vaga compatível adiada pelo teto). A UI mostra os motivos no histórico; até 200 eventos detalhados por ciclo, com totais e `omitted_events` explícitos. Vagas pendentes/reprovadas/encerradas não recebem envios.

Aplique `alembic upgrade head` (agora até `0006`) antes de reiniciar a API/worker. O teste integrado inicia um worker Celery real e comprova o trajeto HTTP → Redis → Celery → PostgreSQL; testes de paginação usam mais de 200 vagas. Isso não representa envio automático a portais externos sem uma API autorizada: esses anúncios continuam exigindo ação manual no canal oficial.
