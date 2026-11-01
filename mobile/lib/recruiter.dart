import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';
import 'jobs.dart';
import 'ui.dart';

class RecruiterView extends StatefulWidget {
  final Api api;
  final Map<String, dynamic> user;
  const RecruiterView({super.key, required this.api, required this.user});
  @override
  State<RecruiterView> createState() => _RecruiterViewState();
}

class _RecruiterViewState extends State<RecruiterView> {
  late Future<Map<String, dynamic>> data;
  @override
  void initState() {
    super.initState();
    reload();
  }

  void reload() {
    data = Future.wait<dynamic>([
      widget.api.request('GET', '/recruiter/jobs'),
      widget.api.request('GET', '/recruiter/dashboard'),
    ]).then((values) => {
          'jobs': values[0] as List,
          'dashboard': Map<String, dynamic>.from(values[1] as Map)
        });
  }

  Future<void> create() async {
    final created = await Navigator.push<bool>(
        context,
        MaterialPageRoute(
            builder: (_) => JobEditor(
                api: widget.api,
                companyName:
                    widget.user['company_name'] ?? widget.user['name'])));
    if (created == true && mounted) setState(reload);
  }

  Future<void> close(String id) async {
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: const Text('Encerrar esta vaga?'),
                content:
                    const Text('Ela deixará de receber novas candidaturas.'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancelar')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Encerrar'))
                ]));
    if (confirmed != true) return;
    try {
      await widget.api.request('DELETE', '/jobs/$id');
      if (mounted) setState(reload);
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    }
  }

  Future<void> contact(String email) async {
    final uri = Uri(scheme: 'mailto', path: email);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
        mounted) {
      await friendlyError(context,
          const ApiException('Não foi possível abrir o aplicativo de e-mail.'));
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(
      future: data,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done)
          return const Center(child: CircularProgressIndicator());
        if (snapshot.hasError)
          return EmptyState(
              icon: Icons.cloud_off_outlined,
              title: 'Vamos recuperar suas vagas',
              message:
                  'Não foi possível consultar as oportunidades publicadas.',
              onRetry: () => setState(reload));
        final result = snapshot.data!;
        final List jobs = result['jobs'] as List;
        final dashboard = Map<String, dynamic>.from(result['dashboard'] as Map);
        final applicationsByJob = Map<String, dynamic>.from(
            dashboard['applications_by_job'] as Map? ?? const {});
        return RefreshIndicator(
            onRefresh: () async {
              setState(reload);
              await data;
            },
            child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
                physics: const AlwaysScrollableScrollPhysics(),
                children: [
                  const ExecutiveHero(
                      title: 'Central de Recrutamento',
                      subtitle:
                          'Vagas, candidaturas e conversões em um só lugar.',
                      eyebrow: 'TALENT ACQUISITION · ATS',
                      trailing: Icon(Icons.hub_outlined,
                          color: Color(0xFF93C5FD), size: 36)),
                  LayoutBuilder(builder: (context, constraints) {
                    final width = (constraints.maxWidth - 12) / 2;
                    final metrics = [
                      (
                        'Vagas ativas',
                        '${dashboard['active_jobs'] ?? 0}',
                        Icons.work_outline,
                        Brand.teal
                      ),
                      (
                        'Candidaturas',
                        '${dashboard['total_applications'] ?? 0}',
                        Icons.people_outline,
                        Brand.navy
                      ),
                      (
                        'Match forte',
                        '${dashboard['strong_candidates'] ?? 0}',
                        Icons.auto_awesome_outlined,
                        Brand.coral
                      ),
                      (
                        'Conversão',
                        '${dashboard['conversion_rate'] ?? 0}%',
                        Icons.trending_up,
                        const Color(0xFFB88A28)
                      ),
                    ];
                    return Wrap(spacing: 12, runSpacing: 0, children: [
                      for (final metric in metrics)
                        SizedBox(
                            width: width,
                            child: ExecutiveMetric(
                                label: metric.$1,
                                value: metric.$2,
                                icon: metric.$3)),
                    ]);
                  }),
                  Panel(
                      child: Wrap(spacing: 8, runSpacing: 8, children: [
                    Chip(
                        avatar: const Icon(Icons.schedule_outlined, size: 16),
                        label: Text(
                            'Em análise: ${jobs.where((j) => j['active'] == true && j['moderation_status'] == 'pending').length}')),
                    Chip(
                        avatar: const Icon(Icons.verified_outlined, size: 16),
                        label: Text(
                            'Aprovadas: ${jobs.where((j) => j['active'] == true && j['moderation_status'] == 'approved').length}')),
                    Chip(
                        avatar: const Icon(Icons.error_outline, size: 16),
                        label: Text(
                            'Reprovadas: ${jobs.where((j) => j['active'] == true && j['moderation_status'] == 'rejected').length}')),
                    Chip(
                        avatar: const Icon(Icons.archive_outlined, size: 16),
                        label: Text(
                            'Encerradas: ${jobs.where((j) => j['active'] == false).length}')),
                  ])),
                  FilledButton.icon(
                      onPressed: create,
                      icon: const Icon(Icons.add),
                      label: const Text('Publicar oportunidade')),
                  const SizedBox(height: 8),
                  const Text(
                      'Vagas aguardando aprovação não recebem candidaturas.'),
                  if (jobs.isEmpty)
                    const EmptyState(
                        icon: Icons.work_outline,
                        title: 'Sua próxima contratação começa aqui',
                        message:
                            'Crie sua primeira vaga para se conectar aos candidatos.'),
                  for (final job in jobs)
                    Panel(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                          Row(children: [
                            CompanyAvatar(company: '${job['company']}'),
                            const SizedBox(width: 12),
                            Expanded(
                                child: Text(job['title'],
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleLarge
                                        ?.copyWith(
                                            fontWeight: FontWeight.bold))),
                            Chip(
                                avatar: Icon(
                                    job['moderation_status'] == 'approved'
                                        ? Icons.check_circle_outline
                                        : Icons.schedule,
                                    size: 18),
                                label: Text(job['active'] == false
                                    ? 'Encerrada'
                                    : statusLabel(
                                        job['moderation_status'] ?? 'pending')))
                          ]),
                          const SizedBox(height: 8),
                          Text(
                              '${job['company']} · ${modalityLabel(job['modality'])} · ${job['location']}'),
                          const SizedBox(height: 6),
                          Text(job['contract_type'] == null
                              ? 'Contrato não informado'
                              : 'Contrato: ${job['contract_type']}'),
                          Text(formatSalaryRange(
                              job['salary_min'], job['salary_max'])),
                          const SizedBox(height: 6),
                          Text(
                              '${applicationsByJob['${job['id']}'] ?? 0} candidaturas recebidas'),
                          Text('Publicada em ${formatDate(job['created_at'])}'),
                          if (job['moderation_status'] == 'rejected')
                            Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(job['moderation_note']
                                            ?.toString()
                                            .trim()
                                            .isNotEmpty ==
                                        true
                                    ? job['moderation_note'].toString()
                                    : 'Esta publicação não foi aprovada. Consulte o atendimento antes de republicar.')),
                          Wrap(spacing: 8, children: [
                            OutlinedButton.icon(
                                onPressed: () => Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                        builder: (_) => RecruiterApplications(
                                            api: widget.api))),
                                icon: const Icon(Icons.people_outline),
                                label: const Text('Ver candidatos')),
                            if (job['active'] == true)
                              TextButton.icon(
                                  onPressed: () => close(job['id'].toString()),
                                  icon: const Icon(Icons.archive_outlined),
                                  label: const Text('Encerrar')),
                          ]),
                        ])),
                ]));
      });
}

class JobEditor extends StatefulWidget {
  final Api api;
  final String companyName;
  const JobEditor({super.key, required this.api, required this.companyName});
  @override
  State<JobEditor> createState() => _JobEditorState();
}

class _JobEditorState extends State<JobEditor> {
  final form = GlobalKey<FormState>();
  final title = TextEditingController(),
      description = TextEditingController(),
      min = TextEditingController(),
      max = TextEditingController(),
      city = TextEditingController(),
      state = TextEditingController(),
      skills = TextEditingController();
  String modality = 'remote', contractType = 'clt';
  bool busy = false;
  @override
  void dispose() {
    for (final c in [title, description, min, max, city, state, skills]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() => busy = true);
    try {
      await widget.api.request('POST', '/jobs', {
        'title': title.text.trim(),
        'company': widget.companyName,
        'description': description.text.trim(),
        'salary_min': double.parse(min.text.replaceAll(',', '.')),
        'salary_max': double.parse(max.text.replaceAll(',', '.')),
        'modality': modality,
        'contract_type': contractType,
        'location': modality == 'remote'
            ? 'Brasil'
            : '${city.text.trim()} / ${state.text.trim().toUpperCase()}',
        'country': 'BR',
        if (modality != 'remote') 'city': city.text.trim(),
        if (modality != 'remote') 'state': state.text.trim().toUpperCase(),
        'keywords': skills.text
            .split(',')
            .map((e) => e.trim())
            .where((e) => e.isNotEmpty)
            .toList(),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Vaga recebida! Ela será exibida após aprovação.')));
      Navigator.pop(context, true);
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget field(TextEditingController c, String label,
          {int lines = 1,
          TextInputType? type,
          String? Function(String?)? validator}) =>
      Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: TextFormField(
              controller: c,
              enabled: !busy,
              maxLines: lines,
              keyboardType: type,
              decoration: InputDecoration(
                  labelText: label,
                  prefixIcon: Icon(c == title
                      ? Icons.work_outline
                      : c == description
                          ? Icons.description_outlined
                          : c == min || c == max
                              ? Icons.payments_outlined
                              : c == city || c == state
                                  ? Icons.location_on_outlined
                                  : Icons.auto_awesome_outlined)),
              validator: validator ??
                  (v) => (v?.trim().isEmpty ?? true)
                      ? 'Preencha este campo.'
                      : null));
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Nova oportunidade')),
      body: Form(
          key: form,
          child: ListView(padding: const EdgeInsets.all(24), children: [
            const SectionTitle(
                title: 'Descreva a próxima conexão',
                subtitle:
                    'Informações objetivas ajudam a encontrar as pessoas certas.'),
            const SectionTitle(
                title: '01 · Identidade da oportunidade',
                subtitle: 'Cargo, contexto e responsabilidades'),
            field(title, 'Título do cargo'),
            field(description, 'Descrição, responsabilidades e requisitos',
                lines: 6,
                validator: (v) => (v?.trim().length ?? 0) < 30
                    ? 'Descreva a vaga com pelo menos 30 caracteres.'
                    : null),
            const SectionTitle(
                title: '02 · Condições de contratação',
                subtitle: 'Remuneração e modelo de trabalho'),
            field(min, 'Salário mínimo (R\$)',
                type: const TextInputType.numberWithOptions(decimal: true),
                validator: (v) =>
                    (double.tryParse((v ?? '').replaceAll(',', '.')) ?? -1) < 0
                        ? 'Informe um valor válido.'
                        : null),
            field(max, 'Salário máximo (R\$)',
                type: const TextInputType.numberWithOptions(decimal: true),
                validator: (v) {
              final value = double.tryParse((v ?? '').replaceAll(',', '.'));
              final low = double.tryParse(min.text.replaceAll(',', '.')) ?? 0;
              return value == null || value < low
                  ? 'O máximo deve ser maior ou igual ao mínimo.'
                  : null;
            }),
            DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: modality,
                decoration: const InputDecoration(labelText: 'Modalidade'),
                items: const [
                  DropdownMenuItem(value: 'remote', child: Text('Remoto')),
                  DropdownMenuItem(value: 'hybrid', child: Text('Híbrido')),
                  DropdownMenuItem(value: 'onsite', child: Text('Presencial'))
                ],
                onChanged: busy ? null : (v) => setState(() => modality = v!)),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: contractType,
                decoration:
                    const InputDecoration(labelText: 'Tipo de contrato'),
                items: const [
                  DropdownMenuItem(value: 'clt', child: Text('CLT')),
                  DropdownMenuItem(value: 'pj', child: Text('PJ')),
                  DropdownMenuItem(value: 'internship', child: Text('Estágio')),
                  DropdownMenuItem(
                      value: 'temporary', child: Text('Temporário')),
                  DropdownMenuItem(
                      value: 'apprentice', child: Text('Aprendiz')),
                  DropdownMenuItem(value: 'other', child: Text('Outro'))
                ],
                onChanged:
                    busy ? null : (v) => setState(() => contractType = v!)),
            const SizedBox(height: 16),
            if (modality != 'remote') ...[
              field(city, 'Cidade'),
              field(state, 'Estado (UF)',
                  validator: (v) =>
                      RegExp(r'^[A-Za-z]{2}$').hasMatch(v?.trim() ?? '')
                          ? null
                          : 'Informe a sigla do estado.')
            ],
            const SectionTitle(
                title: '03 · Perfil ideal',
                subtitle: 'Competências publicadas com transparência'),
            field(skills, 'Competências separadas por vírgula'),
            const Text(
                'Sua vaga passará por moderação antes de entrar no feed público.'),
            const SizedBox(height: 20),
            FilledButton.icon(
                onPressed: busy ? null : save,
                icon: busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.send_outlined),
                label: const Text('Enviar para aprovação')),
          ])));
}

class RecruiterApplications extends StatefulWidget {
  final Api api;
  const RecruiterApplications({super.key, required this.api});
  @override
  State<RecruiterApplications> createState() => _RecruiterApplicationsState();
}

class _RecruiterApplicationsState extends State<RecruiterApplications> {
  late Future<dynamic> data;
  String? changing, downloading;
  final locationFilter = TextEditingController(),
      salaryFilter = TextEditingController();
  int minMatch = 0;
  String workStyle = '', courseFilter = '';
  @override
  void initState() {
    super.initState();
    reload();
  }

  @override
  void dispose() {
    locationFilter.dispose();
    salaryFilter.dispose();
    super.dispose();
  }

  void reload() {
    final query = <String, String>{'limit': '100', 'min_match': '$minMatch'};
    if (locationFilter.text.trim().isNotEmpty)
      query['location'] = locationFilter.text.trim();
    if (salaryFilter.text.trim().isNotEmpty) {
      final ceiling =
          double.tryParse(salaryFilter.text.trim().replaceAll(',', '.'));
      if (ceiling != null && ceiling >= 0) query['salary_ceiling'] = '$ceiling';
    }
    if (workStyle.isNotEmpty) query['work_style'] = workStyle;
    if (courseFilter.isNotEmpty) query['completed_course_id'] = courseFilter;
    data = widget.api
        .request(
            'GET', '/recruiter/applicants?${Uri(queryParameters: query).query}')
        .then((result) => (result as Map)['items'] as List);
  }

  Future<void> update(String id, String value) async {
    setState(() => changing = id);
    try {
      await widget.api.request('PATCH', '/applications/$id', {'status': value});
      if (mounted) setState(reload);
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => changing = null);
    }
  }

  Future<void> saveResume(String id) async {
    if (downloading != null) return;
    setState(() => downloading = id);
    try {
      final bytes = await widget.api.downloadPdf('/applications/$id/resume');
      if (!mounted) return;
      final saved = await FilePicker.platform.saveFile(
        dialogTitle: 'Salvar currículo do candidato',
        fileName: 'curriculo.pdf',
        type: FileType.custom,
        allowedExtensions: ['pdf'],
        bytes: bytes,
      );
      if (saved != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Currículo salvo no local escolhido.')));
      }
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => downloading = null);
    }
  }

  Future<void> _openContact(Uri uri) async {
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw const ApiException(
            'Não foi possível abrir o aplicativo de contato. Você pode copiar os dados exibidos.');
      }
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    }
  }

  Future<void> _contact(Map<String, dynamic> candidate) async {
    final email = candidate['candidate_email']?.toString().trim() ?? '';
    final phone = candidate['candidate_phone']?.toString().trim() ?? '';
    final skills =
        List<String>.from(candidate['candidate_skills'] as List? ?? const []);
    final locations = List<String>.from(
        candidate['preferred_locations'] as List? ?? const []);
    final summary =
        (candidate['resume_summary'] ?? candidate['candidate_summary'])
            ?.toString()
            .trim();
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (sheetContext) => ConstrainedBox(
        constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(sheetContext).height * .85),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionTitle(
                    title: 'Contato do candidato',
                    subtitle: 'Dados compartilhados nesta candidatura.'),
                Text(candidate['candidate_name']?.toString() ?? 'Candidato',
                    style: Theme.of(sheetContext).textTheme.titleLarge),
                const SizedBox(height: 16),
                const Text('E-mail',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                SelectableText(email.isEmpty ? 'Não informado' : email),
                if (email.isNotEmpty)
                  TextButton.icon(
                      onPressed: () =>
                          _openContact(Uri(scheme: 'mailto', path: email)),
                      icon: const Icon(Icons.mail_outline),
                      label: const Text('Enviar e-mail')),
                const SizedBox(height: 12),
                const Text('Telefone',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                SelectableText(phone.isEmpty ? 'Não informado' : phone),
                if (phone.isNotEmpty)
                  TextButton.icon(
                      onPressed: () => _openContact(Uri(
                          scheme: 'tel',
                          path: phone.replaceAll(RegExp(r'[^+0-9]'), ''))),
                      icon: const Icon(Icons.phone_outlined),
                      label: const Text('Ligar para candidato')),
                if (phone.isNotEmpty)
                  TextButton.icon(
                      onPressed: () => _openContact(Uri.https('wa.me',
                          '/${phone.replaceAll(RegExp(r'[^0-9]'), '')}')),
                      icon: const Icon(Icons.chat_outlined),
                      label: const Text('Abrir WhatsApp')),
                if (candidate['candidate_birth_date'] != null)
                  Text(
                      'Nascimento: ${candidate['candidate_birth_date']} · ${candidate['candidate_age'] ?? '—'} anos'),
                if (candidate['candidate_city'] != null)
                  Text(
                      'Cidade/UF: ${candidate['candidate_city']} / ${candidate['candidate_state'] ?? ''}'),
                if (candidate['candidate_seniority'] != null)
                  Text('Senioridade: ${candidate['candidate_seniority']}'),
                if (candidate['candidate_linkedin'] != null)
                  TextButton(
                      onPressed: () => _openContact(Uri.parse(
                          candidate['candidate_linkedin'].toString())),
                      child: const Text('Abrir LinkedIn')),
                const SizedBox(height: 18),
                Text('Resumo do currículo',
                    style: Theme.of(sheetContext)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                Text(summary?.isNotEmpty == true
                    ? summary!
                    : skills.isEmpty
                        ? 'O candidato ainda não declarou competências no perfil.'
                        : 'Competências declaradas: ${skills.join(' · ')}'),
                if (locations.isNotEmpty)
                  Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child:
                          Text('Localidade desejada: ${locations.join(', ')}')),
                if (candidate['salary_expectation'] != null)
                  Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                          'Pretensão salarial: ${formatBrlCurrency(candidate['salary_expectation'])}')),
                if (candidate['id'] != null)
                  Padding(
                      padding: const EdgeInsets.only(top: 18),
                      child: OutlinedButton.icon(
                          onPressed: () {
                            Navigator.pop(sheetContext);
                            saveResume(candidate['id'].toString());
                          },
                          icon: const Icon(Icons.download_outlined),
                          label: const Text('Salvar currículo PDF'))),
              ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<dynamic>(
      future: data,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done)
          return const Center(child: CircularProgressIndicator());
        if (snapshot.hasError)
          return EmptyState(
              icon: Icons.cloud_off,
              title: 'Não conseguimos consultar agora',
              message: 'Tente novamente para acompanhar seus candidatos.',
              onRetry: () => setState(reload));
        final rows = snapshot.data as List;
        return RefreshIndicator(
            onRefresh: () async {
              setState(reload);
              await data;
            },
            child: ListView(
                padding: const EdgeInsets.all(20),
                physics: const AlwaysScrollableScrollPhysics(),
                children: [
                  const ExecutiveHero(
                      title: 'Cada candidatura é uma possibilidade',
                      subtitle:
                          'Filtre apenas pessoas inscritas em vagas da sua empresa.',
                      eyebrow: 'PIPELINE DE TALENTOS'),
                  Panel(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        const Text('Filtros de recrutamento',
                            style: TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 8),
                        const Text(
                            'Compatibilidade técnica e preferências profissionais declaradas. Não use atributos pessoais ou sensíveis para seleção.'),
                        const SizedBox(height: 12),
                        TextField(
                            controller: locationFilter,
                            decoration: const InputDecoration(
                                labelText: 'Cidade/UF declarada',
                                prefixIcon: Icon(Icons.location_on_outlined))),
                        const SizedBox(height: 12),
                        TextField(
                            controller: salaryFilter,
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: const InputDecoration(
                                labelText: 'Pretensão até R\$ (opcional)',
                                prefixIcon: Icon(Icons.payments_outlined))),
                        const SizedBox(height: 12),
                        DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: workStyle,
                            decoration: const InputDecoration(
                                labelText: 'Estilo de trabalho compatível'),
                            items: const [
                              DropdownMenuItem(value: '', child: Text('Todos')),
                              DropdownMenuItem(
                                  value: 'remote', child: Text('Remoto')),
                              DropdownMenuItem(
                                  value: 'hybrid', child: Text('Híbrido')),
                              DropdownMenuItem(
                                  value: 'onsite', child: Text('Presencial')),
                            ],
                            onChanged: (value) =>
                                setState(() => workStyle = value ?? '')),
                        const SizedBox(height: 12),
                        DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: courseFilter,
                            decoration: const InputDecoration(
                                labelText: 'Curso concluído (declarado)'),
                            items: const [
                              DropdownMenuItem(
                                  value: '', child: Text('Qualquer curso')),
                              DropdownMenuItem(
                                  value: 'bradesco-python',
                                  child: Text('Python · Fundação Bradesco')),
                              DropdownMenuItem(
                                  value: 'senai',
                                  child: Text('Qualificação · SENAI')),
                              DropdownMenuItem(
                                  value: 'sebrae',
                                  child: Text('Gestão · Sebrae')),
                              DropdownMenuItem(
                                  value: 'microsoft',
                                  child: Text('Microsoft Learn')),
                              DropdownMenuItem(
                                  value: 'cisco',
                                  child: Text('Python · Cisco')),
                            ],
                            onChanged: (value) =>
                                setState(() => courseFilter = value ?? '')),
                        const SizedBox(height: 12),
                        Text('Compatibilidade técnica mínima: $minMatch%'),
                        Slider(
                            value: minMatch.toDouble(),
                            min: 0,
                            max: 100,
                            divisions: 10,
                            label: '$minMatch%',
                            onChanged: (value) =>
                                setState(() => minMatch = value.round())),
                        SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                                onPressed: () => setState(reload),
                                icon: const Icon(Icons.filter_alt_outlined),
                                label: const Text('Aplicar filtros'))),
                      ])),
                  if (rows.isEmpty)
                    const EmptyState(
                        icon: Icons.people_outline,
                        title: 'Suas conexões aparecerão aqui',
                        message:
                            'Depois da aprovação das vagas, as candidaturas ficarão disponíveis nesta área.'),
                  for (final row in rows)
                    Panel(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                          Row(children: [
                            CompanyAvatar(
                                company:
                                    '${row['candidate_name'] ?? 'Candidato'}'),
                            const SizedBox(width: 12),
                            Expanded(
                                child: Text(
                                    row['candidate_name'] ?? 'Candidato',
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium
                                        ?.copyWith(
                                            fontWeight: FontWeight.w700)))
                          ]),
                          const SizedBox(height: 12),
                          Text(row['job_title'] ?? 'Oportunidade',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 8),
                          Wrap(spacing: 8, runSpacing: 4, children: [
                            Chip(
                                avatar:
                                    const Icon(Icons.auto_awesome, size: 16),
                                label: Text('${row['match_score']}% Match')),
                            Chip(
                                label: Text(row['status'] == 'submitted'
                                    ? 'Nova candidatura'
                                    : statusLabel('${row['status']}')))
                          ]),
                          Text(
                              'Modalidade: ${row['work_style_fit'] == 'aligned' ? 'alinhada' : row['work_style_fit'] == 'different' ? 'diferente' : 'não informada'}'),
                          const SizedBox(height: 4),
                          Text(
                              'Localidade: ${(row['preferred_locations'] as List? ?? []).join(', ')} · Pretensão: ${row['salary_expectation'] == null ? 'não informada' : formatBrlCurrency(row['salary_expectation'])}'),
                          const SizedBox(height: 8),
                          if ((row['candidate_skills'] as List? ?? [])
                              .isNotEmpty)
                            Wrap(spacing: 6, runSpacing: 2, children: [
                              for (final skill
                                  in (row['candidate_skills'] as List).take(8))
                                Chip(
                                    visualDensity: VisualDensity.compact,
                                    label: Text('$skill'))
                            ]),
                          if (row['candidate_email'] != null)
                            TextButton.icon(
                                onPressed: () => _contact(
                                    Map<String, dynamic>.from(row as Map)),
                                icon: const Icon(Icons.mail_outline),
                                label: Text('${row['candidate_email']}',
                                    overflow: TextOverflow.ellipsis)),
                          if (row['candidate_email'] == null)
                            TextButton.icon(
                                onPressed: () => _contact(
                                    Map<String, dynamic>.from(row as Map)),
                                icon: const Icon(Icons.contact_page_outlined),
                                label: const Text('Contato rápido')),
                          if (row['candidate_phone'] != null)
                            SelectableText(
                                'Telefone: ${row['candidate_phone']}'),
                          const SizedBox(height: 4),
                          Text(
                              'Cursos informados: ${(row['completed_course_ids'] as List? ?? []).isEmpty ? 'nenhum' : (row['completed_course_ids'] as List).join(', ')} (autodeclarados)'),
                          const SizedBox(height: 6),
                          Text(formatDate(row['created_at'])),
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                              onPressed: downloading != null
                                  ? null
                                  : () => saveResume(row['id'].toString()),
                              icon: downloading == row['id']
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2))
                                  : const Icon(Icons.download_outlined),
                              label: const Text('Salvar currículo PDF')),
                          const SizedBox(height: 12),
                          Wrap(spacing: 8, runSpacing: 4, children: [
                            OutlinedButton(
                                onPressed: changing == row['id']
                                    ? null
                                    : () => update(
                                        row['id'].toString(), 'reviewing'),
                                child: const Text('Em análise')),
                            OutlinedButton(
                                onPressed: changing == row['id']
                                    ? null
                                    : () => update(
                                        row['id'].toString(), 'interview'),
                                child: const Text('Aprovar p/ entrevista')),
                            TextButton(
                                onPressed: changing == row['id']
                                    ? null
                                    : () => update(
                                        row['id'].toString(), 'rejected'),
                                child: const Text('Descartar')),
                          ]),
                        ])),
                  if (rows.length == 100)
                    const Text(
                        'Exibindo até 100 candidaturas por consulta. Refine os filtros para localizar outros perfis.'),
                ]));
      });
}

class CompanyProfile extends StatelessWidget {
  final Map<String, dynamic> user;
  const CompanyProfile({super.key, required this.user});
  @override
  Widget build(BuildContext context) =>
      ListView(padding: const EdgeInsets.all(20), children: [
        const SectionTitle(
            title: 'Sua empresa no Vagou!',
            subtitle:
                'Transparência para criar relações profissionais de confiança.'),
        Panel(
            child: Column(children: [
          const CircleAvatar(
              radius: 38,
              backgroundColor: Brand.teal,
              child:
                  Icon(Icons.business_rounded, size: 38, color: Colors.white)),
          const SizedBox(height: 18),
          Text(user['company_name'] ?? user['name'],
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center),
          const SizedBox(height: 8),
          const Chip(
              avatar: Icon(Icons.mark_email_read_outlined, size: 18),
              label: Text('E-mail confirmado'))
        ])),
        Panel(
            child: Column(children: [
          ListTile(
              leading: const Icon(Icons.badge_outlined),
              title: const Text('CNPJ'),
              subtitle: Text(user['company_cnpj'] ?? 'Não informado')),
          ListTile(
              leading: const Icon(Icons.person_outline),
              title: const Text('Responsável'),
              subtitle: Text(user['name'] ?? '')),
          ListTile(
              leading: const Icon(Icons.email_outlined),
              title: const Text('Contato corporativo'),
              subtitle: Text(user['company_contact_email'] ?? user['email']))
        ])),
        const Panel(
            child: Text(
                'Confirmar o e-mail não equivale a uma certificação empresarial. As publicações passam por revisão antes de aparecer para os candidatos.')),
      ]);
}
