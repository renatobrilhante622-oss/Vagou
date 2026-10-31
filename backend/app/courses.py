"""Official learning references with honest certification conditions.

Catalog availability and current pricing/certificate rules must be checked on
the official page. Learning achievements do not imply a paid professional exam.
"""
COURSES = [
    {
        'id': 'bradesco-python', 'provider': 'Fundação Bradesco',
        'title': 'Linguagem de Programação Python – Básico',
        'url': 'https://www.ev.org.br/cursos/linguagem-de-programacao-python-basico',
        'skills': ['python', 'programacao'],
        'summary': 'Uma porta de entrada para desenvolver raciocínio lógico e escrever programas em Python, pelo catálogo da Escola Virtual.',
        'syllabus': ['Variáveis, tipos, operadores e entrada de dados','Condições, repetição e resolução de problemas','Funções e organização de pequenos scripts'],
        'workload': '18 horas (informação da Fundação Bradesco). Confira a oferta vigente no site oficial.',
        'objectives': ['Entender variáveis, operadores e estruturas de controle.', 'Praticar lógica aplicada à resolução de problemas.', 'Construir uma base para estudos de automação e análise de dados.'],
        'career_impact': 'Ajuda a construir repertório inicial para vagas de tecnologia e tarefas de automação. A prática em projetos complementa o curso.',
        'resume_value': 'Após concluir, registre a formação complementar com instituição, conteúdo e carga horária comprovada. Inclua também um pequeno projeto próprio.',
        'certificate': 'Curso livre; emissão de certificado depende de conclusão e aprovação conforme regras vigentes da Escola Virtual.',
    },
    {
        'id': 'senai', 'provider': 'SENAI', 'title': 'Cursos online e qualificação profissional',
        'url': 'https://www.mundosenai.com.br/cursos/', 'skills': ['industria', 'seguranca', 'logistica'],
        'summary': 'Catálogo oficial para localizar oportunidades de qualificação em áreas industriais, logística e segurança, conforme disponibilidade regional.',
        'syllabus': ['Fundamentos da área industrial escolhida','Segurança, procedimentos e aplicação no ambiente de trabalho','Atividades práticas e avaliação conforme a unidade e a turma'],
        'workload': 'Carga horária varia conforme o curso, unidade e turma escolhidos.',
        'objectives': ['Identificar uma formação alinhada à sua área de atuação.', 'Desenvolver fundamentos técnicos aplicáveis ao ambiente de trabalho.', 'Consultar pré-requisitos, modalidade e oferta da unidade responsável.'],
        'career_impact': 'Pode apoiar a transição para funções operacionais e técnicas. A aderência depende da formação escolhida e dos requisitos da vaga.',
        'resume_value': 'Informe o nome exato do curso e da unidade SENAI. Destaque competências efetivamente praticadas e comprovadas.',
        'certificate': 'O catálogo inclui ofertas com condições diferentes. Confirme gratuidade e certificado na página da turma antes de se inscrever.',
    },
    {
        'id': 'sebrae', 'provider': 'Sebrae', 'title': 'Cursos online de gestão e negócios',
        'url': 'https://sebrae.com.br/sites/PortalSebrae/cursosonline', 'skills': ['gestao', 'vendas', 'marketing'],
        'summary': 'Formações do Sebrae para aperfeiçoar conhecimentos em gestão, atendimento, vendas e desenvolvimento de pequenos negócios.',
        'syllabus': ['Planejamento e indicadores básicos de gestão','Atendimento, jornada do cliente e vendas','Organização financeira e divulgação de pequenos negócios'],
        'workload': 'Carga horária depende do curso escolhido no catálogo do Sebrae.',
        'objectives': ['Reconhecer processos básicos de gestão de negócios.', 'Desenvolver competências de atendimento e vendas.', 'Aplicar conceitos de planejamento em situações profissionais reais.'],
        'career_impact': 'Complementa perfis de áreas comerciais, administrativas e de empreendedorismo com uma visão prática de negócios.',
        'resume_value': 'Selecione formações relacionadas ao cargo desejado e descreva como aplicou o conhecimento, sem declarar experiência que ainda não possui.',
        'certificate': 'Há cursos online gratuitos com certificado conforme a oferta e seus critérios de conclusão. Confira as regras no site oficial.',
    },
    {
        'id': 'microsoft', 'provider': 'Microsoft Learn', 'title': 'Trilhas de aprendizagem Microsoft Learn',
        'url': 'https://learn.microsoft.com/pt-br/training/', 'skills': ['azure', 'c#', 'sql', 'python'],
        'summary': 'Módulos e roteiros oficiais para estudar tecnologias Microsoft, nuvem, desenvolvimento e dados no seu ritmo.',
        'syllabus': ['Fundamentos de tecnologia e preparação do ambiente','Laboratórios guiados e documentação de serviços','Exercícios por módulo e validação das competências estudadas'],
        'workload': 'Cada módulo e trilha possui duração estimada própria no Microsoft Learn.',
        'objectives': ['Selecionar uma trilha alinhada às competências que faltam no perfil.', 'Estudar conceitos técnicos com documentação e exercícios oficiais.', 'Organizar uma sequência de aprendizado contínuo.'],
        'career_impact': 'Ajuda a estruturar a evolução técnica para projetos que usam o ecossistema Microsoft. Laboratórios e projetos próprios reforçam o aprendizado.',
        'resume_value': 'Diferencie módulos concluídos, conquistas do Learn e certificações oficiais. Só declare certificação profissional após aprovação no exame correspondente.',
        'certificate': 'O treinamento é gratuito e oferece conquistas. Certificações profissionais podem exigir exames pagos; não há garantia de certificado gratuito para toda trilha.',
    },
    {
        'id': 'cisco', 'provider': 'Cisco Networking Academy', 'title': 'Python Essentials 1',
        'url': 'https://www.netacad.com/courses/python-essentials-1', 'skills': ['redes', 'python', 'cybersecurity'],
        'summary': 'Referência oficial da Networking Academy para estudar fundamentos de programação Python e raciocínio computacional.',
        'syllabus': ['Sintaxe, expressões e tipos de dados em Python','Fluxo de controle, coleções e funções','Tratamento de erros e exercícios de programação'],
        'workload': '30 horas estimadas (Cisco Networking Academy). Confirme a modalidade e a turma no site oficial.',
        'objectives': ['Aprender conceitos básicos de sintaxe e tipos de dados.', 'Praticar estruturas de controle e funções.', 'Desenvolver autonomia para continuar em trilhas de programação e tecnologia.'],
        'career_impact': 'Contribui para a base de programação útil em automação, redes e estudos posteriores de segurança. Não substitui experiência prática.',
        'resume_value': 'Registre a conclusão e a credencial realmente emitida. Associe o curso a exemplos de código ou projetos de estudo.',
        'certificate': 'Confira a oferta vigente: cursos elegíveis podem emitir badge ou certificado de conclusão. Isso não equivale automaticamente a certificação profissional por exame.',
    },
]
