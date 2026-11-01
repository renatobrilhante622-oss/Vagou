# Operação do Vagou!

## Atualização de uma instalação existente

Preserve `JWT_SECRET`, `DATA_KEY`, `DATABASE_URL`, `REDIS_URL`, volumes e o endereço local do app. Esta atualização não muda o Compose nem publica portas novas. Faça backup do banco/volume de currículos e execute, na configuração já utilizada:

```bash
docker compose build api worker beat migrate
docker compose run --rm migrate
docker compose up -d api worker beat
```

A migração vai de `0001` a `0010`; as últimas versões adicionam contrato opcional às vagas e evidências/contagens explicáveis de automação. A `0009` adiciona contato opcional da vaga, canal/status de entrega, consentimento da rodada e outbox transacional criptografada. A `0010` adiciona cidade/UF/país estruturados e snapshots ricos dos anúncios nos relatórios, com campos opcionais para preservar dados antigos. A `0002` exige confirmação de e-mail também das contas antigas: no próximo login, solicitar novo código e confirmar. Vagas anteriores à migração permanecem aprovadas; toda vaga nova entra em moderação. Recrutadores antigos têm campos empresariais nulos preservados, sem criar CNPJ fictício. Novos cadastros empresariais exigem CNPJ válido, razão social, e-mail e telefone. A validação de CNPJ verifica formato/dígitos (inclusive alfanumérico), não consulta a situação cadastral na Receita Federal.

A migração de downgrade para antes de `0002` elimina vagas externas que não cabem no esquema antigo. Não faça downgrade com dados de produção sem um plano de restauração.

## Gmail SMTP sem domínio próprio

1. Na conta Google que enviará os códigos, ative a verificação em duas etapas.
2. Crie uma **senha de app** quando esse recurso estiver disponível para a conta. Não use a senha normal do Google.
3. Configure no arquivo privado ignorado `backend/.env.smtp.local` ou no gerenciador de segredos do servidor:

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

Recrie API, worker e beat após alterar as variáveis para aplicar a configuração. Use o overlay `compose.smtp.yaml` para injetar o arquivo privado nesses serviços.

### Confirmar envio real

- Cadastre uma conta de teste pelo aplicativo. A API persiste uma outbox criptografada e responde `delivery_status=pending` quando SMTP está configurado; isso **não é um recibo de entrega**.
- Um único Celery beat agenda `vagou.deliver_verification_mail` a cada 15 segundos. Mantenha worker e beat ativos.
- Confira a chegada na caixa de entrada/spam e use o código de seis dígitos em até dez minutos. O login permanece bloqueado até confirmar.
- O código tem no máximo cinco tentativas. Reenvios têm intervalo mínimo de 60 segundos, substituem o código anterior e recebem resposta neutra para evitar enumeração de contas.
- Sem SMTP, o cadastro retorna `configuration_required`. Depois de configurar, solicite novo código. Não há código universal, confirmação automática, OTP em respostas públicas ou bypass de produção.
- SMTP aplica TLS com validação de certificado e retries limitados. Após entrega/falha final/cancelamento, o payload do código é limpo. As falhas não registram senhas ou código nos logs.

Os testes de transporte usam mocks para verificar autenticação, TLS e propagação de falhas; não equivalem a uma entrega real. Os testes integrados verificam persistência, criptografia, anexos e retentativas no PostgreSQL, substituindo somente a conexão SMTP. A confirmação de recebimento no Gmail exige uma rodada autorizada no ambiente configurado.

## Moderação

Defina `MODERATOR_EMAILS` como uma lista JSON de e-mails da equipe autorizada. As contas precisam existir e confirmar o próprio e-mail. Não coloque endereços de terceiros sem autorização.

- `GET /v1/recruiter/jobs`: o contratante consulta suas vagas, inclusive pendentes e reprovadas, com motivo.
- `GET /v1/moderation/jobs`: fila privada de vagas pendentes.
- `PATCH /v1/moderation/jobs/{id}` com `{"status":"approved","note":"Revisão concluída"}` aprova.
- Para reprovar, use `status=rejected` e informe motivo não vazio.
- Nenhum moderador aprova a própria vaga. A lista pública, detalhes, recomendações e worker consideram somente vagas ativas aprovadas. Os campos privados de moderação não são publicados no feed.

A operação de moderação pode ser feita pela API autenticada/Swagger por uma conta autorizada. O aplicativo da empresa mostra os estados de aprovação; ele não concede poderes de moderação ao contratante.

## Fontes externas e automação Premium

A importação pública é controlada por `ENABLE_PUBLIC_COLLECTORS` (ativada por padrão). Configure fontes adicionais apenas quando sua API e termos permitirem essa integração:

- `JOB_SOURCE_URLS`: lista JSON de endpoints HTTPS, sem credenciais na URL.
- `JOB_SOURCE_ALLOWED_HOSTS`: lista JSON dos hostnames exatos autorizados.
- `JOB_SOURCE_AUTO_APPROVE=false`: mantém anúncios importados na moderação. Só habilitar aprovação automática para fonte previamente confiável e autorizada.
- Limites: `JOB_SOURCE_MAX_BYTES=2097152`, `JOB_SOURCE_MAX_JOBS=200` por leitura.

O conector aceita JSON `jobs`, RSS/Atom e JSON-LD `schema.org/JobPosting` em hosts allowlisted. Os provedores padrão consultam páginas públicas de Gupy Brasil, LinkedIn Brasil, Indeed Brasil, InfoJobs, Vagas.com.br, Catho, Programathor e Trabalha Brasil. A Gupy utiliza o documento público estruturado da busca `https://portal.gupy.io/job-search/term=suporte&city=Bras%C3%ADlia`, sem o endpoint que retornava 404. Nos demais portais, o indexador lê somente anúncios públicos estruturados e links oficiais dentro dos hosts fixos. Não executa JavaScript, resolve CAPTCHA, contorna autenticação ou bloqueios. Remotive, Arbeitnow e feeds internacionais saíram dos coletores padrão. Feeds administrativos seguem `JOB_SOURCE_AUTO_APPROVE` e também passam pelo filtro Brasil.

Toda vaga precisa de localização brasileira verificável: país BR, Cidade/UF brasileira ou abrangência Remoto Brasil. País estrangeiro explícito prevalece sobre um nome de cidade coincidente; Worldwide/América Latina sem confirmação Brasil não é suficiente. Antes de servir o catálogo e varrer candidaturas, anúncios estrangeiros ou sem localização confirmável são desativados; suas candidaturas e auditorias permanecem no banco. Cidade/UF/país de anúncios brasileiros antigos são normalizados quando há evidência no anúncio. A varredura conta somente vagas brasileiras da região escolhida ou remotas no Brasil.

Cargo, empresa, descrição, modalidade, contrato, salário e contato mantêm os fatos publicados. Valores ausentes continuam ausentes: salário desconhecido aparece como não informado, contrato não é presumido CLT e não se inventam empresas, contatos ou remunerações. O parser aceita contatos explícitos de recrutamento e e-mails anunciados com contexto de RH/currículo, excluindo scripts e contatos legais/suporte. `company_name`, `external_url`, `recruiter_email` e `modality_label` são aliases de leitura; os campos originais e modalidades REST `remote`, `hybrid`, `onsite` continuam válidos.

O fallback mantém o índice local de anúncios brasileiros verificados e oferece links de pesquisa oficiais dinâmicos nos oito portais, usando cargo/palavras-chave e Cidade/UF. São eventos `search_channel`, contados em `search_channels_count`, sem anúncio inventado nem percentual de match. Oscilações de fonte ficam nos logs técnicos; os cards não mostram alertas de fonte quebrada quando o candidato pode seguir pelo índice e pelas pesquisas. Nenhuma integração garante que sempre haverá vagas compatíveis ou candidaturas: se não existir anúncio verificável, os números continuam honestos e as buscas permanecem disponíveis.

As fontes exigem HTTPS e têm timeout, concorrência e tamanho limitados. Feeds administrativos exigem allowlist exata e não seguem redirects. Páginas dos portais aceitam somente um redirect canônico dentro dos hosts fixos do mesmo provedor. A rede deve continuar aplicando proteção de egress contra resolução de destinos privados; não conceder edição dessa allowlist a candidatos.

Uma varredura iniciada pelo candidato reconsulta feeds configurados em `JOB_SOURCE_URLS`, em paralelo, com hosts exatos em `JOB_SOURCE_ALLOWED_HOSTS`; erros por fonte não cancelam as demais. Feeds não aprovados ficam pendentes. O sistema não raspa portais fechados. Só encaminha currículo ao contato explícito validado da vaga ou ao recrutador proprietário com e-mail confirmado, mediante autorização do candidato.

`PREMIUM_TEST_EMAILS` é uma lista separada por vírgula ou ponto e vírgula. A configuração padrão inclui `rbrilhante001@gmail.com`; qualquer conta listada recebe acesso Premium independente de `APP_ENV`, inclusive em produção. Configure essa allowlist somente com contas de teste autorizadas e remova acessos que não devam permanecer ativos. A API mostra o entitlement em `GET /v1/candidate/entitlements`; a execução imediata usa `POST /v1/automation/run`, que retorna `run_id`, acompanhado por `GET /v1/automation/runs/{run_id}/status`.

O beat verifica fontes a cada 15 minutos e candidaturas elegíveis a cada minuto, mas cada candidato tem intervalo próprio entre 15 minutos e um dia (padrão uma hora). São necessários conta confirmada, Premium, currículo e autorização explícita. O teto real é o menor entre a preferência do candidato e `AUTOMATION_MAX_APPLICATIONS_PER_RUN` (padrão 20).

- **Vaga interna aprovada:** a candidatura é entregue ao recrutador dentro do Vagou!, com unicidade por candidato/vaga e registro `submitted`.
- **Vaga externa com contato:** a candidatura é registrada em `requires_manual`, com `delivery_status=queued` e `destination_channel=email`. Após aceite SMTP, passa a `submitted` e `delivery_status=sent`. Isso confirma o encaminhamento por e-mail, sem afirmar inscrição no ATS externo ou leitura pelo recrutador.
- **Vaga externa sem contato:** a candidatura fica registrada em `requires_manual`, com link oficial para conclusão pelo candidato. Não se conta um link aberto como envio. A implementação não envia formulários a portais sem APIs e permissões desses provedores.

`POST /v1/automation/run` aceita `{"consent_granted":true}`; clientes antigos podem omitir o corpo quando já existe autorização salva em `automation_enabled`. Uma recusa explícita bloqueia a execução. Matches com score a partir de70 geram registros, respeitando o teto configurado e a unicidade; scores40–69 ficam em possíveis matches. Cargo/skills PT-BR e inglês são normalizados com aliases. Suporte N1/N2/N3, Service Desk, Técnico de Informática, Infraestrutura/Redes e Auxiliar de TI são reconhecidos como cargos próximos; níveis e funções diferentes continuam em revisão individual. Remoto Brasil atende a uma cidade brasileira. Restrições incompatíveis, salário desconhecido com piso exigido e competências apenas inferidas impedem envio automático. Competências explicitamente publicadas na seção de requisitos podem ser extraídas lexicalmente, sem copiar o perfil do candidato para fabricar aderência. A varredura continua examinando as páginas seguintes mesmo após atingir o limite de candidaturas; o feed também percorre páginas regionais para evitar uma primeira página vazia causada por anúncios de outras cidades.

`submitted_applications` e seu alias `applications_submitted` contam registros criados na rodada, exibidos como **Registradas**. Canal e status de entrega distinguem registro, fila e aceite SMTP. Eventos incluem `source_name`, `external_url`, `match_score`, `match_reasons`, `company_name`, `location`, `destination_channel` e os novos campos de descrição, contato, Cidade/UF, modalidade, contrato e salário. O snapshot preserva até3000 caracteres de descrição; quando o anúncio ainda existe, a API entrega sua descrição completa. Cards e relatórios mostram resumo expansível, e-mail copiável/com ação de contato e link oficial. Motivos repetidos são removidos sem apagar o histórico. A criação da candidatura, o relatório e a intenção de envio são confirmados na mesma transação; falhas SMTP não desfazem o registro.

O worker agenda `vagou.deliver_application_mail` após o commit; o beat também verifica a outbox a cada15 segundos. O relatório executivo do candidato inclui candidaturas registradas, possíveis matches e links clicáveis. Configure `PUBLIC_API_URL` com a origem HTTPS pública para links de vagas internas em e-mails; anúncios externos preservam a URL oficial. A outbox deduplica por candidatura/rodada, usa Message-ID estável, limita a cinco tentativas e elimina payloads privados após entrega/falha final/cancelamento. A entrega SMTP tem semântica de pelo menos uma vez: uma perda de conexão após aceite pode gerar repetição. Revogar autorização, excluir a conta ou invalidar o currículo cancela o envio pendente.

`GET /v1/automation/runs` entrega resumos privados paginados; `/runs/{id}/status` informa estado e progresso; `/runs/{id}/events` entrega eventos paginados, status, score, razões, fonte e link. Os eventos podem ser filtrados por `status=possible_match`. Cada ciclo armazena até 200 eventos detalhados e informa `omitted_events`; os totais distinguem anúncios coletados, vagas externas aprovadas/varridas, possíveis matches e descartes. Defina rotina operacional de retenção/expurgo de relatórios conforme a política de privacidade e volume real. Remoção de conta elimina seus relatórios em cascata.

## Android e download do APK

Preservados: endpoint atual `https://nest-gents-sudden.ngrok-free.dev` (workflow e padrão do cliente), acesso local opcional `http://192.168.18.128:8000`, `compileSdk=36`, `targetSdk=36`, `minSdk=24`, AGP 8.9.1, Gradle 8.11.1, Java 17, HTTP local autorizado e permissão Internet. O cliente usa o endpoint HTTPS atual por padrão. Se configurado para HTTP local, permite apenas a origem local indicada; nessa opção, o aparelho precisa alcançar a rede local. Não há túnel nem mudança de infraestrutura implícitos.

O workflow usa Flutter 3.35.7, instala explicitamente API36 e `platform-tools` sem o pacote obsoleto `tools`, completa apenas arquivos Android ausentes e verifica os SDKs efetivos. Em seguida executa formatação, análise, testes Flutter e compilação. Recursos de ícone/splash próprios ficam versionados e não são sobrescritos pelo scaffold temporário.

- Em commits da `main`: `Actions → Build Android APK → execução → Artifacts → vagou-release-apk`. O GitHub empacota esse download como ZIP mesmo contendo um único APK; `compression-level: 0` evita compressão desnecessária.
- Em tags `v*`: após build bem-sucedido, o job `publish-apk` publica `app-release.apk` como asset de uma GitHub Release, permitindo download direto do APK. O token tem escrita apenas nesse job. Crie a tag somente quando desejar publicar a versão. Se a release já existir, revise a execução e publique o asset conscientemente; o comando não sobrescreve releases antigas automaticamente.

O APK interno mantém a assinatura de debug usada no template anterior. Para Google Play é obrigatória assinatura de produção/Play App Signing e configuração de release própria. A análise e os testes locais usam Flutter3.35.7; a geração final do APK é validada pelo workflow Android com SDK36.

## Testes

Na pasta `backend`, após instalar `requirements.txt` e migrar um banco descartável:

```bash
python -m pytest -q
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
docker compose --env-file backend/.env.smtp.local -f compose.yaml -f compose.smtp.yaml up -d --build api worker beat
docker compose exec api alembic upgrade head
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
