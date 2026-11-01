import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'api.dart';
import 'forms.dart';
import 'admin.dart';
import 'automation_panel.dart';
import 'ui.dart';
import 'profile.dart';

class CandidateProfile extends StatefulWidget {
  const CandidateProfile(
      {super.key,
      required this.api,
      required this.user,
      required this.onChanged});
  final Api api;
  final Map<String, dynamic> user;
  final Future<void> Function() onChanged;
  @override
  State<CandidateProfile> createState() => _CandidateProfileState();
}

class _CandidateProfileState extends State<CandidateProfile> {
  final _profileKey = GlobalKey<FormState>();
  late final TextEditingController _name, _phone, _skills;
  final _details = {
    for (final key in [
      'birth_date',
      'cpf',
      'seniority',
      'linkedin_url',
      'professional_summary',
      'candidate_city',
      'candidate_state',
      'desired_salary'
    ])
      key: TextEditingController()
  };
  bool _premium = false, _busy = false;

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    _name = TextEditingController(text: '${user['name'] ?? ''}');
    _phone = TextEditingController(
        text: formatBrazilPhone('${user['phone'] ?? ''}'));
    for (final entry in _details.entries) {
      entry.value.text = entry.key == 'birth_date'
          ? birthDateDisplay(user[entry.key])
          : '${user[entry.key] ?? ''}';
    }
    _skills =
        TextEditingController(text: (user['skills'] as List? ?? []).join(', '));
    _premium = user['is_premium'] == true;
  }

  @override
  void dispose() {
    for (final controller in [_name, _phone, _skills, ..._details.values]) {
      controller.dispose();
    }
    super.dispose();
  }

  List<String> _terms(String value) => value
      .split(',')
      .map((v) => v.trim())
      .where((v) => v.isNotEmpty)
      .toSet()
      .toList();
  Future<void> _refreshAccess() async {
    setState(() => _busy = true);
    try {
      final result = Map<String, dynamic>.from(
          await widget.api.request('GET', '/candidate/entitlements') as Map);
      if (mounted) setState(() => _premium = result['is_premium'] == true);
      await widget.onChanged();
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _perform(Future<void> Function() work, String message) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await work();
      await widget.onChanged();
      if (mounted)
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      if (mounted) friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _upload() async {
    try {
      final result = await FilePicker.platform.pickFiles(
          type: FileType.custom, allowedExtensions: ['pdf'], withData: true);
      if (!mounted || result == null) return;
      final bytes = result.files.single.bytes;
      if (bytes == null || bytes.length > 5 * 1024 * 1024) {
        throw const ApiException('Escolha um currículo PDF com até 5 MB.');
      }
      await _perform(
          () => widget.api.upload(bytes), 'Seu currículo foi atualizado.');
    } catch (error) {
      if (mounted) friendlyError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.user;
    final preferences =
        Map<String, dynamic>.from(user['preferences'] as Map? ?? const {});
    final skills = _terms(_skills.text);
    final target =
        List<String>.from(preferences['titles'] as List? ?? const []);
    final locations =
        List<String>.from(preferences['locations'] as List? ?? const []);
    final courses = List<String>.from(
        preferences['completed_course_ids'] as List? ?? const []);
    final completion = [
      _name.text.trim().isNotEmpty,
      user['email_verified'] == true,
      (brazilPhonePayload(_phone.text) != null),
      skills.isNotEmpty,
      user['has_resume'] == true,
      target.isNotEmpty,
    ].where((value) => value).length;
    final profileStrength = (completion * 100 / 6).round();
    final premium = _premium || user['is_premium'] == true;
    return ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        children: [
          if (user['is_admin'] == true)
            Panel(
                child: ListTile(
                    leading: const Icon(Icons.admin_panel_settings),
                    title: const Text('🛡️ Admin'),
                    subtitle: const Text('Central de Comando'),
                    onTap: () => openAdmin(context, widget.api, user))),
          ExecutiveDossier(
              name: '${user['name']}',
              email: '${user['email']}',
              premium: premium,
              verified: user['email_verified'] == true,
              completion: profileStrength),
          const SectionTitle(title: 'Resumo executivo'),
          Panel(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                _summaryRow(Icons.work_outline, 'Cargo-alvo',
                    target.isEmpty ? 'Não informado' : target.join(', ')),
                _summaryRow(Icons.location_on_outlined, 'Cidade/UF',
                    locations.isEmpty ? 'Não informada' : locations.join(', ')),
                _summaryRow(
                    Icons.payments_outlined,
                    'Pretensão mínima',
                    (num.tryParse('${preferences['min_salary'] ?? 0}') ?? 0) > 0
                        ? formatBrlCurrency(preferences['min_salary'])
                        : 'Não informada'),
              ])),
          const SectionTitle(
              title: 'Dados pessoais',
              subtitle:
                  'Informações profissionais para apresentar sua trajetória.'),
          Panel(
              child: Form(
                  key: _profileKey,
                  child: Column(children: [
                    TextFormField(
                        controller: _name,
                        enabled: !_busy,
                        textCapitalization: TextCapitalization.words,
                        decoration: const InputDecoration(
                            labelText: 'Nome completo',
                            prefixIcon: Icon(Icons.person_outline)),
                        validator: (value) => (value?.trim().length ?? 0) < 2
                            ? 'Informe seu nome completo.'
                            : null),
                    const SizedBox(height: 16),
                    TextFormField(
                        controller: _phone,
                        inputFormatters: [BrazilPhoneFormatter()],
                        enabled: !_busy,
                        keyboardType: TextInputType.phone,
                        decoration: const InputDecoration(
                            labelText: 'Telefone com DDD',
                            hintText: '+5511999999999',
                            prefixIcon: Icon(Icons.phone_outlined)),
                        validator: (value) => value != null &&
                                brazilPhonePayload(value) != null &&
                                !RegExp(r'^\+55\d{10,11}$')
                                    .hasMatch(brazilPhonePayload(value) ?? '')
                            ? 'Use +55, DDD e seu número, sem espaços.'
                            : null),
                    const SizedBox(height: 16),
                    TextFormField(
                        controller: _skills,
                        enabled: !_busy,
                        minLines: 2,
                        maxLines: 4,
                        decoration: const InputDecoration(
                            labelText: 'Suas competências',
                            hintText: 'Python, atendimento, Excel, gestão...',
                            helperText: 'Separe as competências por vírgula.',
                            prefixIcon: Icon(Icons.auto_awesome_outlined))),
                    const SizedBox(height: 14),
                    CandidateDetailsFields(
                        controllers: _details, enabled: !_busy),
                    if (skills.isNotEmpty)
                      Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Wrap(spacing: 8, runSpacing: 4, children: [
                            for (final skill in skills)
                              Chip(
                                  visualDensity: VisualDensity.compact,
                                  label: Text(skill))
                          ])),
                    const SizedBox(height: 20),
                    SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                            onPressed: _busy
                                ? null
                                : () {
                                    if (_profileKey.currentState!.validate()) {
                                      _perform(() async {
                                        await widget.api
                                            .request('PUT', '/me/profile', {
                                          'name': _name.text.trim(),
                                          'phone':
                                              brazilPhonePayload(_phone.text),
                                          ...candidateDetailsPayload(_details),
                                          'skills': _terms(_skills.text)
                                        });
                                      }, 'Perfil salvo com sucesso.');
                                    }
                                  },
                            icon: const Icon(Icons.check),
                            label: const Text('Salvar perfil'))),
                  ]))),
          Panel(
              child: Row(children: [
            Icon(
                user['has_resume'] == true
                    ? Icons.task_outlined
                    : Icons.upload_file_outlined,
                size: 34,
                color: Brand.teal),
            const SizedBox(width: 14),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(
                      user['has_resume'] == true
                          ? 'Currículo pronto'
                          : 'Apresente sua trajetória',
                      style: Theme.of(context).textTheme.titleMedium),
                  const Text('PDF privado · até 5 MB e 20 páginas')
                ])),
            IconButton(
                onPressed: _busy ? null : _upload,
                tooltip: 'Enviar currículo PDF',
                icon: const Icon(Icons.file_upload_outlined))
          ])),
          const SectionTitle(title: 'Experiência e formação'),
          Panel(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                const Text('Cursos declarados',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                if (courses.isEmpty)
                  const Text(
                      'Nenhum curso informado. Os cursos concluídos são autodeclarados.'),
                if (courses.isNotEmpty)
                  Wrap(spacing: 8, children: [
                    for (final course in courses)
                      Chip(
                          avatar: const Icon(Icons.school_outlined, size: 16),
                          label: Text(course))
                  ]),
                const SizedBox(height: 8),
                const Text(
                    'Experiências profissionais podem ser apresentadas no currículo PDF.'),
              ])),
          const ExecutiveHero(
              title: 'Vagou! Pro',
              subtitle:
                  'Critérios salvos, decisões transparentes e automação sob seu controle.',
              eyebrow: 'SEU PLANO DE CARREIRA',
              trailing:
                  Icon(Icons.workspace_premium, color: Color(0xFFFBBF24))),
          const SectionTitle(title: 'Meu Plano'),
          Panel(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Row(children: [
                  Icon(
                      premium
                          ? Icons.workspace_premium
                          : Icons.workspace_premium_outlined,
                      color: premium ? Brand.coral : Brand.teal),
                  const SizedBox(width: 10),
                  Expanded(
                      child: Text(premium ? 'Premium Ativo' : 'Plano Gratuito',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w800)))
                ]),
                const SizedBox(height: 8),
                const Text(
                    'Vagou! Pro · buscas regionais, análise de compatibilidade e encaminhamento assistido.'),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                    onPressed: _busy ? null : _refreshAccess,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Atualizar meu acesso')),
                const SizedBox(height: 8),
                FilledButton.icon(
                    onPressed: () => showAutomationPanel(context,
                        api: widget.api, onChanged: widget.onChanged),
                    icon: const Icon(Icons.bolt),
                    label: const Text('Configurar Robô de Automação')),
              ])),
        ]);
  }

  Widget _summaryRow(IconData icon, String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          Icon(icon, color: Brand.teal),
          const SizedBox(width: 10),
          Expanded(child: Text(label)),
          const SizedBox(width: 8),
          Flexible(
              child: Text(value,
                  textAlign: TextAlign.end,
                  style: const TextStyle(fontWeight: FontWeight.w700))),
        ]),
      );
}
