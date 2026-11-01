# Interface executiva e encaminhamento de candidaturas

A revisão mantém rotas, autenticação, consentimentos, limites de plano, SDK36 e os métodos das classes State. O perfil é apresentado por CandidateProfile, com o novo componente ExecutiveDossier em profile.dart.

| Arquivo | Estrutura entregue |
| --- | --- |
| ui.dart / main.dart | Marca vetorial VagouBrandMark, compatibilidade BrandMark, componentes executivos, tema claro/escuro e splash |
| home.dart | AppBar com identidade Premium e NavigationBar flutuante com estados ativos |
| auth.dart / onboarding.dart | Hero de boas-vindas, escolha de perfil, formulário acessível, CTA em gradiente e introdução responsiva |
| jobs.dart / opportunity_details.dart | Busca compacta, chips, banner Premium, identidade da empresa, score, resumo expansível, contato e link oficial |
| automation_panel.dart | Cockpit escuro com critérios e ação principal, quatro KPIs, resultados automáticos, possíveis e canais separados |
| reporting.dart | Visão executiva, contadores, distribuição, histórico, snapshots ricos e deduplicação |
| recruiter.dart | Dashboard ATS, KPIs, publicação em três seções, pipeline de candidatos e contato rápido |
| candidate.dart / profile.dart | Dossiê com capa, identidade, progresso, competências, currículo privado e assinatura |
| res/drawable e res/mipmap | Ícones Android vetoriais, versão adaptativa e fundo Indigo/Royal |

Os coletores normalizam HTML e espaçamento antes de persistir o anúncio, extraem somente contatos públicos de recrutamento identificáveis e mantêm a URL oficial. A extração de competências usa requisitos publicados, não o perfil do candidato.

Uma vaga real com score >=70 gera Application uma única vez, dentro do limite autorizado. Registro, intenção de e-mail e relatório são gravados transacionalmente; o worker publica o disparo após commit. O relatório inclui descrição e contato quando disponíveis. Scores40–69 permanecem como avaliação individual, com descrição, motivos e canal direto. Filas/retries SMTP, revogação de consentimento, criptografia e proteção contra repetição permanecem ativos.

Registro na plataforma, aceite SMTP e inscrição em portal externo são estados distintos. A disponibilidade de anúncios e de e-mail de recrutamento depende da publicação; os coletores não fabricam vagas, contatos ou remunerações.

Validação: PostgreSQL/Redis descartáveis com suíte completa, mocks somente no transporte SMTP, análise Flutter e testes de widgets em320/360/430px. O CI Backend isola seu processo de API dos coletores públicos. Credenciais reais e arquivos .env/settings.json permanecem fora dos commits.
