# Central de comando e dossiê do candidato

As migrações `0011` e `0012` acrescentam funções administrativas, auditoria,
notificações criptografadas, dados profissionais e validade declarada dos anúncios.
Execute `alembic upgrade head` antes de iniciar os novos processos.

## Acesso e equipe

O proprietário `rbrilhante001@gmail.com` recebe `super_admin` e PRO vitalício após
confirmar seu e-mail e autenticar-se. Nenhuma senha ou conta é criada pela migração.
O cadastro público aceita somente candidato ou recrutador. A conta proprietária
não pode perder suas permissões pelo painel. Exclusão voluntária da conta continua
respeitando a rota de exclusão e os direitos do titular.

Super Admin pode atribuir funções e administrar planos e contas. Moderadores podem
revisar anúncios, publicar comunicados de vagas reais e verificar empresas; não
podem conceder planos, banir usuários ou atribuir cargos. Mudanças de função,
verificação e bloqueio invalidam sessões existentes. Suspender uma conta também
desativa suas automações e arquiva os anúncios que ela publicou.

A Central de Comando usa `/v1/admin/dashboard`, `/jobs`, `/companies`, `/users`,
`/audit`, `/sync` e `/cleanup`. Publicação, edição, aprovação, rejeição, destaque,
arquivamento e alterações de contas deixam registros com ator, data e motivo.
Rejeições exigem motivo e geram aviso ao recrutador na fila transacional SMTP.
Empresas verificadas recebem aprovação automática com auditoria do autor.

## Vitrine e Radar

`/v1/internal-jobs` entrega anúncios internos ativos e aprovados, com selo de
empresa verificada e prioridade para destaques. Não cria anúncios fictícios:
a equipe publica uma vaga real pelo painel ou aprova o cadastro de uma empresa.
`/v1/radar` exige PRO. A rota legada `/v1/matches` mantém seu contrato para clientes
existentes. Pesquisa por links não conta como anúncio, match ou envio.

Compatibilidade de cargo, região brasileira e modalidade pode alcançar 75–98%,
mesmo quando o anúncio não declara salário, contrato ou competências estruturadas.
Ausência desses dados permanece explícita; não comprova domínio de habilidades.
Conflitos explícitos de filtros e cargos adjacentes continuam exigindo avaliação.
Uma candidatura registrada não equivale a aceite por um ATS externo ou leitura de
um e-mail. Somente o aceite do SMTP altera o estado de entrega correspondente.

Coletores incluem portais brasileiros e feeds públicos de recrutamento com e-mail
anunciado. Leituras são limitadas, sem contornar bloqueios e sem adivinhar contatos,
empregadores ou cidades. Feeds genéricos só geram anúncios quando há metadados
estruturados verificáveis. A disponibilidade depende dos publicadores; falhas
aparecem na saúde dos coletores após sincronização global. Vagas expiradas usam a
validade declarada pelo publicador; a limpeza preserva candidaturas e auditorias.

## Dados pessoais e currículo

Cadastro e perfil aceitam nascimento em DD/MM/AAAA ou ISO, telefone brasileiro com
máscara, CPF opcional, senioridade, LinkedIn HTTPS e pretensão salarial. CPF e
telefone ficam criptografados; CPF não integra o painel do recrutador nem e-mails.
O candidato pode atualizar ou remover seu CPF no próprio perfil.

Candidaturas e automação exigem currículo PDF. Recrutadores responsáveis podem
baixá-lo pela rota autenticada e consultar nascimento/idade, contato, localidade,
competências, senioridade, resumo e LinkedIn. Encaminhamentos SMTP autorizados
incluem o currículo PDF e esses dados profissionais. A fila exige consentimento,
conta ativa e acesso PRO vigente, com deduplicação, tentativas limitadas e recibo
separado do registro da candidatura. Segredos SMTP permanecem somente no arquivo
local ignorado; nunca devem ser adicionados ao repositório.

O aplicativo envia `ngrok-skip-browser-warning: true` em JSON, upload e download,
preserva o endereço configurado e mantém SDK 36/minSdk 24 e permissões Android.
