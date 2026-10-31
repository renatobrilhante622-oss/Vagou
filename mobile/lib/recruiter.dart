import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
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
  late Future<dynamic> data;
  @override
  void initState() { super.initState(); reload(); }
  void reload() { data = widget.api.request('GET', '/recruiter/jobs'); }
  Future<void> create() async {
    final created = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => JobEditor(api: widget.api, companyName: widget.user['company_name'] ?? widget.user['name'])));
    if (created == true && mounted) setState(reload);
  }
  Future<void> close(String id) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(title: const Text('Encerrar esta vaga?'), content: const Text('Ela deixará de receber novas candidaturas.'), actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Encerrar'))]));
    if (confirmed != true) return;
    try { await widget.api.request('DELETE', '/jobs/$id'); if (mounted) setState(reload); }
    catch (e) { if (mounted) await friendlyError(context, e); }
  }
  @override
  Widget build(BuildContext context) => FutureBuilder<dynamic>(future: data, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return EmptyState(icon: Icons.cloud_off_outlined, title: 'Vamos recuperar suas vagas', message: 'Não foi possível consultar as oportunidades publicadas.', onRetry: () => setState(reload));
    final dynamic result = snapshot.data;
    final List jobs = result is List ? result : (result['items'] as List? ?? []);
    return RefreshIndicator(onRefresh: () async { setState(reload); await data; }, child: ListView(padding: const EdgeInsets.all(20), physics: const AlwaysScrollableScrollPhysics(), children: [
      const SectionTitle(title: 'Talentos começam por uma boa oportunidade', subtitle: 'Publique com clareza e acompanhe a aprovação das suas vagas.'),
      FilledButton.icon(onPressed: create, icon: const Icon(Icons.add), label: const Text('Criar nova vaga')),
      const SizedBox(height: 20), Panel(child: Row(children: [const Icon(Icons.verified_user_outlined, color: Brand.teal), const SizedBox(width: 12), Expanded(child: Text('Todas as vagas passam por moderação antes de aparecer no feed.', style: Theme.of(context).textTheme.bodyMedium))])),
      if (jobs.isEmpty) const EmptyState(icon: Icons.work_outline, title: 'Sua próxima contratação começa aqui', message: 'Crie sua primeira vaga para se conectar aos candidatos.'),
      for (final job in jobs) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Expanded(child: Text(job['title'], style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold))), Icon(job['active'] == true ? Icons.work_outline : Icons.archive_outlined, color: Brand.teal)]),
        const SizedBox(height: 10), Text('${modalityLabel(job['modality'])} · ${job['location']}'),
        const SizedBox(height: 10), Chip(avatar: Icon(job['moderation_status'] == 'approved' ? Icons.check_circle_outline : Icons.schedule, size: 18), label: Text(job['active'] == false ? 'Encerrada' : statusLabel(job['moderation_status'] ?? 'pending'))),
        Text('Publicada em ${formatDate(job['created_at'])}'),
        if (job['moderation_status'] == 'rejected') Padding(padding: const EdgeInsets.only(top: 8), child: Text(job['moderation_note']?.toString().trim().isNotEmpty == true ? job['moderation_note'].toString() : 'Esta publicação não foi aprovada. Consulte o atendimento antes de republicar.')),
        if (job['active'] == true) Align(alignment: Alignment.centerRight, child: TextButton(onPressed: () => close(job['id'].toString()), child: const Text('Encerrar vaga'))),
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
  final title = TextEditingController(), description = TextEditingController(), min = TextEditingController(), max = TextEditingController(), city = TextEditingController(), state = TextEditingController(), skills = TextEditingController();
  String modality = 'remote';
  bool busy = false;
  @override
  void dispose() { for (final c in [title, description, min, max, city, state, skills]) { c.dispose(); } super.dispose(); }
  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() => busy = true);
    try {
      await widget.api.request('POST', '/jobs', {
        'title': title.text.trim(), 'company': widget.companyName, 'description': description.text.trim(),
        'salary_min': double.parse(min.text.replaceAll(',', '.')), 'salary_max': double.parse(max.text.replaceAll(',', '.')),
        'modality': modality, 'location': modality == 'remote' ? 'Brasil' : '${city.text.trim()} / ${state.text.trim().toUpperCase()}',
        'keywords': skills.text.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Vaga recebida! Ela será exibida após aprovação.')));
      Navigator.pop(context, true);
    } catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => busy = false); }
  }
  Widget field(TextEditingController c, String label, {int lines = 1, TextInputType? type, String? Function(String?)? validator}) => Padding(padding: const EdgeInsets.only(bottom: 16), child: TextFormField(controller: c, enabled: !busy, maxLines: lines, keyboardType: type, decoration: InputDecoration(labelText: label), validator: validator ?? (v) => (v?.trim().isEmpty ?? true) ? 'Preencha este campo.' : null));
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Nova oportunidade')), body: Form(key: form, child: ListView(padding: const EdgeInsets.all(24), children: [
    const SectionTitle(title: 'Descreva a próxima conexão', subtitle: 'Informações objetivas ajudam a encontrar as pessoas certas.'),
    field(title, 'Título do cargo'), field(description, 'Descrição, responsabilidades e requisitos', lines: 6, validator: (v) => (v?.trim().length ?? 0) < 30 ? 'Descreva a vaga com pelo menos 30 caracteres.' : null),
    field(min, 'Salário mínimo (R\$)', type: const TextInputType.numberWithOptions(decimal: true), validator: (v) => (double.tryParse((v ?? '').replaceAll(',', '.')) ?? -1) < 0 ? 'Informe um valor válido.' : null),
    field(max, 'Salário máximo (R\$)', type: const TextInputType.numberWithOptions(decimal: true), validator: (v) { final value = double.tryParse((v ?? '').replaceAll(',', '.')); final low = double.tryParse(min.text.replaceAll(',', '.')) ?? 0; return value == null || value < low ? 'O máximo deve ser maior ou igual ao mínimo.' : null; }),
    DropdownButtonFormField<String>(initialValue: modality, decoration: const InputDecoration(labelText: 'Modalidade'), items: const [DropdownMenuItem(value: 'remote', child: Text('Remoto')), DropdownMenuItem(value: 'hybrid', child: Text('Híbrido')), DropdownMenuItem(value: 'onsite', child: Text('Presencial'))], onChanged: busy ? null : (v) => setState(() => modality = v!)), const SizedBox(height: 16),
    if (modality != 'remote') ...[field(city, 'Cidade'), field(state, 'Estado (UF)', validator: (v) => RegExp(r'^[A-Za-z]{2}$').hasMatch(v?.trim() ?? '') ? null : 'Informe a sigla do estado.')],
    field(skills, 'Competências separadas por vírgula'),
    const Text('Sua vaga passará por moderação antes de entrar no feed público.'), const SizedBox(height: 20),
    FilledButton.icon(onPressed: busy ? null : save, icon: busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.send_outlined), label: const Text('Enviar para aprovação')),
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
  @override
  void initState() { super.initState(); reload(); }
  void reload() { data = widget.api.request('GET', '/applications?limit=100'); }
  Future<void> update(String id, String value) async {
    setState(() => changing = id);
    try { await widget.api.request('PATCH', '/applications/$id', {'status': value}); if (mounted) setState(reload); }
    catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => changing = null); }
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
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Currículo salvo no local escolhido.')));
      }
    } catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => downloading = null); }
  }
  @override
  Widget build(BuildContext context) => FutureBuilder<dynamic>(future: data, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return EmptyState(icon: Icons.cloud_off, title: 'Não conseguimos consultar agora', message: 'Tente novamente para acompanhar seus candidatos.', onRetry: () => setState(reload));
    final rows = snapshot.data as List;
    return RefreshIndicator(onRefresh: () async { setState(reload); await data; }, child: ListView(padding: const EdgeInsets.all(20), physics: const AlwaysScrollableScrollPhysics(), children: [
      const SectionTitle(title: 'Cada candidatura é uma possibilidade', subtitle: 'Acompanhe os candidatos e mantenha o status atualizado.'),
      if (rows.isEmpty) const EmptyState(icon: Icons.people_outline, title: 'Suas conexões aparecerão aqui', message: 'Depois da aprovação das vagas, as candidaturas ficarão disponíveis nesta área.'),
      for (final row in rows) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(row['candidate_name'] ?? 'Candidato', style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 6),
        Text(row['job_title'] ?? 'Oportunidade', style: Theme.of(context).textTheme.titleMedium), const SizedBox(height: 8),
        Text('Compatibilidade: ${row['match_score']}% · ${row['source'] == 'automatic' ? 'Automática' : 'Manual'}'),
        const SizedBox(height: 6), Text(formatDate(row['created_at'])), const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: downloading != null ? null : () => saveResume(row['id'].toString()), icon: downloading == row['id'] ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.download_outlined), label: const Text('Salvar currículo PDF')), const SizedBox(height: 12),
        DropdownButtonFormField<String>(initialValue: row['status'], decoration: const InputDecoration(labelText: 'Etapa do processo'), items: [for (final value in ['submitted', 'reviewing', 'interview', 'rejected', 'hired']) DropdownMenuItem(value: value, child: Text(statusLabel(value)))], onChanged: changing == row['id'] ? null : (v) { if (v != null && v != 'submitted') update(row['id'], v); }),
      ])),
      if (rows.length == 100) const Text('Exibindo as 100 candidaturas mais recentes.'),
    ]));
  });
}

class CompanyProfile extends StatelessWidget {
  final Map<String, dynamic> user;
  const CompanyProfile({super.key, required this.user});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(20), children: [
    const SectionTitle(title: 'Sua empresa no Vagou!', subtitle: 'Transparência para criar relações profissionais de confiança.'),
    Panel(child: Column(children: [const CircleAvatar(radius: 38, backgroundColor: Brand.teal, child: Icon(Icons.business_rounded, size: 38, color: Colors.white)), const SizedBox(height: 18), Text(user['company_name'] ?? user['name'], style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center), const SizedBox(height: 8), const Chip(avatar: Icon(Icons.mark_email_read_outlined, size: 18), label: Text('E-mail confirmado'))])),
    Panel(child: Column(children: [ListTile(leading: const Icon(Icons.badge_outlined), title: const Text('CNPJ'), subtitle: Text(user['company_cnpj'] ?? 'Não informado')), ListTile(leading: const Icon(Icons.person_outline), title: const Text('Responsável'), subtitle: Text(user['name'] ?? '')), ListTile(leading: const Icon(Icons.email_outlined), title: const Text('Contato corporativo'), subtitle: Text(user['company_contact_email'] ?? user['email']))])),
    const Panel(child: Text('Confirmar o e-mail não equivale a uma certificação empresarial. As publicações passam por revisão antes de aparecer para os candidatos.')),
  ]);
}
