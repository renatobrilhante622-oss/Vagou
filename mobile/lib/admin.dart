import 'dart:convert';
import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';
import 'opportunity_details.dart';

Future<void> openAdmin(BuildContext context, Api api, Map user) =>
    Navigator.push(context,
        MaterialPageRoute(builder: (_) => AdminScreen(api: api, user: user)));

class AdminScreen extends StatefulWidget {
  final Api api;
  final Map user;
  const AdminScreen({super.key, required this.api, required this.user});
  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  final search = TextEditingController();
  int tab = 0;
  String filter = 'pending';
  String? companyId;
  bool busy = false;
  late Future<dynamic> data;
  bool get manager => widget.user['role'] == 'super_admin';
  @override
  void initState() {
    super.initState();
    reload();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  void reload() {
    final q = Uri.encodeQueryComponent(search.text.trim());
    final paths = [
      '/admin/dashboard',
      '/admin/jobs?limit=50${filter == 'external' ? '&external=true' : filter == 'all' ? '' : '&status=$filter'}${companyId == null ? '' : '&recruiter_id=$companyId'}',
      '/admin/companies?q=$q',
      '/admin/users?q=$q',
      '/admin/audit'
    ];
    data = tab == 3 && !manager
        ? Future.value([])
        : widget.api
            .request('GET', paths[tab])
            .timeout(const Duration(seconds: 15));
  }

  Future<String?> note(String title, {bool required = false}) async {
    final controller = TextEditingController();
    final value = await showDialog<String>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, refresh) => AlertDialog(
                    title: Text(title),
                    content: TextField(
                        controller: controller,
                        maxLines: 3,
                        onChanged: (_) => refresh(() {}),
                        decoration: InputDecoration(
                            labelText: required
                                ? 'Motivo obrigatório'
                                : 'Observação para auditoria')),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Cancelar')),
                      FilledButton(
                          onPressed: required && controller.text.trim().isEmpty
                              ? null
                              : () => Navigator.pop(
                                  context, controller.text.trim()),
                          child: const Text('Confirmar'))
                    ])));
    controller.dispose();
    return value;
  }

  Future<void> act(String method, String path, [Map? payload]) async {
    setState(() => busy = true);
    try {
      await widget.api.request(method, path, payload);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Ação registrada com auditoria.')));
      setState(reload);
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> jobAction(Map job, String action) async {
    final reason = await note(
        action == 'reject' ? 'Rejeitar publicação' : 'Confirmar ação na vaga',
        required: action == 'reject');
    if (reason != null)
      await act('POST', '/admin/jobs/${job['id']}/actions',
          {'action': action, 'note': reason});
  }

  Future<void> editor([Map? job]) async {
    final saved = await Navigator.push<bool>(
        context,
        MaterialPageRoute(
            builder: (_) => AdminJobEditor(api: widget.api, job: job)));
    if (mounted && saved == true) setState(reload);
  }

  Widget metrics(Map value) => LayoutBuilder(
      builder: (context, constraints) => Wrap(spacing: 12, children: [
            for (final item in const [
              ('candidates', 'Candidatos', Icons.people),
              ('active_pro', 'PRO Ativos', Icons.workspace_premium),
              ('companies', 'Empresas', Icons.business),
              ('internal_jobs', 'Vagas Internas', Icons.work),
              ('external_jobs', 'Vagas Externas', Icons.travel_explore),
              ('pending_moderation', 'Fila Pendente', Icons.fact_check),
              ('automation_runs', 'Varreduras', Icons.radar),
              ('applications', 'Candidaturas', Icons.send)
            ])
              SizedBox(
                  width: (constraints.maxWidth - 12) / 2,
                  child: ExecutiveMetric(
                      label: item.$2,
                      value: '${value[item.$1] ?? 0}',
                      icon: item.$3))
          ]));
  Widget companyCard(Map row) => Panel(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${row['company_name'] ?? row['name']}',
            style: Theme.of(context).textTheme.titleMedium),
        SelectableText('CNPJ: ${row['company_cnpj'] ?? 'Não informado'}'),
        SelectableText('${row['company_contact_email'] ?? row['email']}'),
        SelectableText('${row['phone'] ?? 'Telefone não informado'}'),
        Wrap(spacing: 8, children: [
          Chip(
              label: Text(row['company_verified'] == true
                  ? 'Empresa Verificada'
                  : 'KYB pendente')),
          Chip(label: Text(row['is_active'] == true ? 'Ativa' : 'Suspensa'))
        ]),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton(
              onPressed: busy
                  ? null
                  : () => act('PATCH', '/admin/users/${row['id']}',
                      {'company_verified': row['company_verified'] != true}),
              child: Text(row['company_verified'] == true
                  ? 'Revogar verificação'
                  : 'Verificar/Aprovar Empresa')),
          if (manager)
            TextButton(
                onPressed: busy
                    ? null
                    : () => act('PATCH', '/admin/users/${row['id']}',
                        {'is_active': row['is_active'] != true}),
                child: Text(row['is_active'] == true
                    ? 'Suspender Recrutador'
                    : 'Reativar Recrutador')),
          TextButton(
              onPressed: () {
                setState(() {
                  companyId = '${row['id']}';
                  filter = 'all';
                  tab = 1;
                  reload();
                });
              },
              child: const Text('Revisar vagas da empresa'))
        ]),
      ]));
  Widget userCard(Map row) {
    final owner = '${row['email']}'.toLowerCase() == 'rbrilhante001@gmail.com';
    return Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('${row['name']}', style: Theme.of(context).textTheme.titleMedium),
      SelectableText('${row['email']}'),
      Wrap(spacing: 8, children: [
        Chip(label: Text('${row['role']}')),
        Chip(
            label: Text(owner
                ? 'PRO Vitalício'
                : row['is_premium'] == true
                    ? 'PRO'
                    : 'Grátis')),
        Chip(label: Text(row['is_active'] == true ? 'Ativa' : 'Desativada'))
      ]),
      if (!owner) ...[
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton(
              onPressed: busy
                  ? null
                  : () => act('PATCH', '/admin/users/${row['id']}',
                      {'is_premium': row['is_premium'] != true}),
              child: Text(
                  row['is_premium'] == true ? 'Revogar PRO' : 'Conceder PRO')),
          TextButton(
              onPressed: busy || row['email_verified'] == true
                  ? null
                  : () => act('PATCH', '/admin/users/${row['id']}',
                      {'email_verified': true}),
              child: const Text('Verificar Conta Manualmente')),
          TextButton(
              onPressed: busy
                  ? null
                  : () => act('PATCH', '/admin/users/${row['id']}',
                      {'is_active': row['is_active'] != true}),
              child: Text(row['is_active'] == true
                  ? 'Desativar Conta'
                  : 'Reativar Conta'))
        ]),
        DropdownButtonFormField<String>(
            isExpanded: true,
            initialValue: '${row['role']}',
            decoration: const InputDecoration(labelText: 'Papel na plataforma'),
            items: [
              for (final role in const [
                ('candidate', 'Candidato'),
                ('recruiter', 'Recrutador'),
                ('moderator', 'Moderador'),
                ('super_admin', 'Super Admin')
              ])
                DropdownMenuItem(value: role.$1, child: Text(role.$2))
            ],
            onChanged: busy
                ? null
                : (role) =>
                    act('PATCH', '/admin/users/${row['id']}', {'role': role})),
      ] else
        const Text('Conta proprietária protegida contra revogação.'),
    ]));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Central de Comando Admin')),
      body: Column(children: [
        SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.all(12),
            child: SegmentedButton<int>(
                segments: const [
                  ButtonSegment(value: 0, label: Text('Dashboard')),
                  ButtonSegment(value: 1, label: Text('Moderação')),
                  ButtonSegment(value: 2, label: Text('Empresas')),
                  ButtonSegment(value: 3, label: Text('Usuários e Equipe')),
                  ButtonSegment(value: 4, label: Text('Auditoria'))
                ],
                selected: {
                  tab
                },
                onSelectionChanged: (value) => setState(() {
                      tab = value.first;
                      reload();
                    }))),
        if (tab == 2 || tab == 3)
          Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: TextField(
                  controller: search,
                  onSubmitted: (_) => setState(reload),
                  decoration: InputDecoration(
                      labelText: 'Buscar por nome, e-mail ou CNPJ',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: IconButton(
                          onPressed: () => setState(reload),
                          icon: const Icon(Icons.arrow_forward))))),
        if (tab == 1)
          Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Wrap(spacing: 8, runSpacing: 8, children: [
                for (final item in const [
                  ('pending', 'Pendentes'),
                  ('approved', 'Aprovadas'),
                  ('rejected', 'Rejeitadas'),
                  ('external', 'Externas'),
                  ('all', 'Todas')
                ])
                  ChoiceChip(
                      label: Text(item.$2),
                      selected: filter == item.$1,
                      onSelected: (_) => setState(() {
                            filter = item.$1;
                            companyId = null;
                            reload();
                          })),
                OutlinedButton.icon(
                    onPressed: () => editor(),
                    icon: const Icon(Icons.add),
                    label: const Text('Publicar Vaga Oficial Vagou!'))
              ])),
        if (busy) const LinearProgressIndicator(),
        Expanded(
            child: FutureBuilder<dynamic>(
                future: data,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done)
                    return const Center(child: CircularProgressIndicator());
                  if (snapshot.hasError)
                    return EmptyState(
                        icon: Icons.shield_outlined,
                        title: 'Não foi possível carregar a central',
                        message: snapshot.error is ApiException
                            ? (snapshot.error as ApiException).message
                            : 'Tente novamente.',
                        onRetry: () => setState(reload));
                  final value = snapshot.data;
                  return RefreshIndicator(
                      onRefresh: () async {
                        setState(reload);
                        await data;
                      },
                      child: ListView(
                          padding: const EdgeInsets.all(16),
                          children: [
                            if (tab == 0) ...[
                              const ExecutiveHero(
                                  title: 'Operação em tempo real',
                                  subtitle:
                                      'Controle de publicações, contas e automações com rastreabilidade.',
                                  eyebrow: 'SUPER VAGOU! · ADMIN'),
                              metrics(value as Map),
                              Panel(
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                    const SectionTitle(
                                        title: 'Saúde dos Coletores'),
                                    Text(value['last_sync'] == null
                                        ? 'Sem sincronização manual registrada.'
                                        : 'Última atualização: ${formatDate(value['last_sync']['at'])}'),
                                    if (value['last_sync'] != null)
                                      Wrap(
                                          spacing: 6,
                                          runSpacing: 4,
                                          children: [
                                            for (final provider in ((value[
                                                                    'last_sync']
                                                                ['result']
                                                            ['source_health']
                                                        as Map?) ??
                                                    {})
                                                .entries)
                                              Chip(
                                                  avatar: Icon(
                                                      provider.value[
                                                                  'status'] ==
                                                              'ok'
                                                          ? Icons
                                                              .check_circle_outline
                                                          : Icons
                                                              .cloud_off_outlined,
                                                      size: 16),
                                                  label: Text(
                                                      '${provider.key}: ${provider.value['status'] == 'ok' ? '${provider.value['jobs']} vagas' : 'indisponível'}')),
                                          ]),
                                    const SizedBox(height: 12),
                                    Wrap(spacing: 8, runSpacing: 8, children: [
                                      FilledButton.icon(
                                          onPressed: busy
                                              ? null
                                              : () =>
                                                  act('POST', '/admin/sync'),
                                          icon: const Icon(Icons.sync),
                                          label: const Text(
                                              'Forçar Sincronização Global de Portais')),
                                      OutlinedButton(
                                          onPressed: busy
                                              ? null
                                              : () =>
                                                  act('POST', '/admin/cleanup'),
                                          child: const Text(
                                              'Limpar Vagas Expiradas/Inválidas'))
                                    ])
                                  ])),
                            ],
                            if (tab == 1) ...[
                              if ((value as List).isEmpty)
                                const Panel(
                                    child:
                                        Text('Nenhum anúncio neste filtro.')),
                              for (final job in value)
                                Panel(
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                      OpportunityDetails(
                                          row: Map<String, dynamic>.from(
                                              job as Map),
                                          initiallyExpanded: true),
                                      Text(
                                          'Status: ${job['moderation_status']}'),
                                      if (job['moderation_notes'] != null)
                                        Text(
                                            'Revisão: ${job['moderation_notes']}'),
                                      Wrap(
                                          spacing: 8,
                                          runSpacing: 8,
                                          children: [
                                            FilledButton(
                                                onPressed: busy
                                                    ? null
                                                    : () => jobAction(
                                                        job, 'approve'),
                                                child: const Text(
                                                    'Aprovar Publicação')),
                                            OutlinedButton(
                                                onPressed: busy
                                                    ? null
                                                    : () => jobAction(
                                                        job, 'reject'),
                                                child: const Text('Rejeitar')),
                                            TextButton(
                                                onPressed: () => editor(job),
                                                child: const Text(
                                                    'Editar informações')),
                                            TextButton(
                                                onPressed: busy
                                                    ? null
                                                    : () => jobAction(
                                                        job,
                                                        job['featured'] == true
                                                            ? 'unfeature'
                                                            : 'feature'),
                                                child: Text(
                                                    job['featured'] == true
                                                        ? 'Remover destaque'
                                                        : 'Destacar Vaga')),
                                            TextButton(
                                                onPressed: busy
                                                    ? null
                                                    : () => jobAction(
                                                        job, 'delete'),
                                                child: const Text(
                                                    'Excluir da vitrine'))
                                          ])
                                    ])),
                            ],
                            if (tab == 2) ...[
                              if ((value as List).isEmpty)
                                const Text('Nenhuma empresa encontrada.'),
                              for (final row in value) companyCard(row as Map)
                            ],
                            if (tab == 3) ...[
                              if (!manager)
                                const Panel(
                                    child: Text(
                                        'Somente Super Admin gerencia contas, planos e equipe.')),
                              if (manager) ...[
                                if ((value as List).isEmpty)
                                  const Text('Nenhum usuário encontrado.'),
                                for (final row in value) userCard(row as Map)
                              ]
                            ],
                            if (tab == 4) ...[
                              Panel(
                                  child: Text(
                                      'Aceite SMTP: ${(value as Map)['smtp_acceptance_rate']}% · ${jsonEncode(value['smtp'])}')),
                              const SectionTitle(
                                  title: 'Execuções globais do robô'),
                              for (final run in value['runs'])
                                Panel(
                                    child: Text(
                                        '${run['status']} · ${run['scanned_jobs']} analisadas · ${run['applications_submitted']} registradas · ${run['error_count']} falhas de fontes/execução\n${formatDate(run['started_at'])}')),
                              const SectionTitle(title: 'Histórico de ações'),
                              for (final action in value['actions'])
                                Panel(
                                    child: Text(
                                        '${action['action']} · ${action['target_type']}\nAtor: ${action['actor_id'] ?? 'Conta removida'}\n${formatDate(action['created_at'])}\n${jsonEncode(action['details'])}')),
                            ],
                          ]));
                })),
      ]));
}

class AdminJobEditor extends StatefulWidget {
  final Api api;
  final Map? job;
  const AdminJobEditor({super.key, required this.api, this.job});
  @override
  State<AdminJobEditor> createState() => _AdminJobEditorState();
}

class _AdminJobEditorState extends State<AdminJobEditor> {
  final form = GlobalKey<FormState>();
  final fields = <String, TextEditingController>{};
  String mode = 'remote', contract = 'clt';
  bool busy = false;
  @override
  void initState() {
    super.initState();
    for (final key in [
      'title',
      'company',
      'description',
      'salary_min',
      'salary_max',
      'location',
      'contact_email',
      'keywords'
    ]) {
      final value = widget.job?[key];
      fields[key] = TextEditingController(
          text: key == 'keywords'
              ? (value as List? ?? []).join(', ')
              : '$value' == 'null'
                  ? (key == 'company'
                      ? 'Vagou!'
                      : key.startsWith('salary')
                          ? '0'
                          : key == 'location'
                              ? 'Brasil'
                              : '')
                  : '$value');
    }
    mode = widget.job?['modality'] ?? 'remote';
    contract = widget.job?['contract_type'] ?? 'clt';
  }

  @override
  void dispose() {
    for (final c in fields.values) c.dispose();
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() => busy = true);
    try {
      final payload = {
        for (final key in ['title', 'company', 'description', 'location'])
          key: fields[key]!.text.trim(),
        'salary_min':
            num.parse(fields['salary_min']!.text.replaceAll(',', '.')),
        'salary_max':
            num.parse(fields['salary_max']!.text.replaceAll(',', '.')),
        'country': 'BR',
        'modality': mode,
        'contract_type': contract,
        'contact_email': fields['contact_email']!.text.trim().isEmpty
            ? null
            : fields['contact_email']!.text.trim(),
        'keywords': fields['keywords']!
            .text
            .split(',')
            .map((v) => v.trim())
            .where((v) => v.isNotEmpty)
            .toList()
      };
      await widget.api.request(
          widget.job == null ? 'POST' : 'PUT',
          widget.job == null
              ? '/admin/jobs'
              : '/admin/jobs/${widget.job!['id']}',
          payload);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(
          title: Text(widget.job == null
              ? 'Publicar Vaga Oficial Vagou!'
              : 'Editar anúncio')),
      body: Form(
          key: form,
          child: ListView(padding: const EdgeInsets.all(20), children: [
            for (final item in const [
              ('title', 'Título do cargo'),
              ('company', 'Empresa'),
              ('description', 'Descrição e requisitos'),
              ('location', 'Cidade/UF ou Brasil'),
              ('salary_min', 'Salário mínimo'),
              ('salary_max', 'Salário máximo'),
              ('keywords', 'Competências (vírgulas)'),
              ('contact_email', 'E-mail do RH (opcional)')
            ])
              Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: TextFormField(
                      controller: fields[item.$1],
                      maxLines: item.$1 == 'description' ? 6 : 1,
                      decoration: InputDecoration(labelText: item.$2),
                      validator: (v) {
                        if (item.$1 == 'contact_email') return null;
                        if (item.$1.startsWith('salary'))
                          return num.tryParse((v ?? '').replaceAll(',', '.')) ==
                                  null
                              ? 'Informe um valor válido.'
                              : null;
                        return (v ?? '').trim().isEmpty
                            ? 'Preencha este campo.'
                            : null;
                      })),
            DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: mode,
                items: const [
                  DropdownMenuItem(
                      value: 'remote', child: Text('Remoto Brasil')),
                  DropdownMenuItem(value: 'hybrid', child: Text('Híbrido')),
                  DropdownMenuItem(value: 'onsite', child: Text('Presencial'))
                ],
                onChanged: (v) => setState(() => mode = v!)),
            const SizedBox(height: 14),
            DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: contract,
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
                onChanged: (v) => setState(() => contract = v!)),
            const SizedBox(height: 20),
            FilledButton(
                onPressed: busy ? null : save,
                child: const Text('Salvar publicação'))
          ])));
}
