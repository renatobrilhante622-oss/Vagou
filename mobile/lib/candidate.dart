import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';

double? parseSalaryBr(String input) {
  var text = input.trim().replaceAll('R\
  const CandidateProfile({super.key, required this.api, required this.user, required this.onChanged});
  final Api api;
  final Map<String, dynamic> user;
  final VoidCallback onChanged;
  @override
  State<CandidateProfile> createState() => _CandidateProfileState();
}

class _CandidateProfileState extends State<CandidateProfile> {
  final _profileKey = GlobalKey<FormState>();
  final _preferencesKey = GlobalKey<FormState>();
  late final TextEditingController _name, _phone, _skills, _titles, _salary, _city, _limit;
  String _state = 'SP';
  int _interval = 60;
  Set<String> _modalities = {'remote'};
  bool _automatic = false, _busy = false;
  static const _states = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'];

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    final preferences = Map<String, dynamic>.from(user['preferences'] as Map? ?? {});
    final locations = List<String>.from(preferences['locations'] as List? ?? []);
    final place = locations.isEmpty ? <String>[] : locations.first.split(' / ');
    if (place.length > 1 && _states.contains(place.last)) _state = place.last;
    _name = TextEditingController(text: '${user['name'] ?? ''}');
    _phone = TextEditingController(text: '${user['phone'] ?? ''}');
    _skills = TextEditingController(text: (user['skills'] as List? ?? []).join(', '));
    _titles = TextEditingController(text: (preferences['titles'] as List? ?? []).join(', '));
    _salary = TextEditingController(text: '${preferences['min_salary'] ?? 0}');
    _city = TextEditingController(text: place.isEmpty ? '' : place.first);
    _limit = TextEditingController(text: '${preferences['automation_max_applications_per_run'] ?? 20}');
    _modalities = Set<String>.from(preferences['modalities'] as List? ?? ['remote']);
    _automatic = user['automation_enabled'] == true;
    final savedInterval = preferences['automation_interval_minutes'];
    _interval = [15, 30, 60, 360, 1440].contains(savedInterval) ? savedInterval as int : 60;
  }

  @override
  void dispose() {
    for (final controller in [_name, _phone, _skills, _titles, _salary, _city, _limit]) { controller.dispose(); }
    super.dispose();
  }

  List<String> _terms(String value) => value.split(',').map((v) => v.trim()).where((v) => v.isNotEmpty).toSet().toList();
  bool get _needsCity => _modalities.contains('onsite') || _modalities.contains('hybrid');
  Future<void> _perform(Future<void> Function() work, String message) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await work();
      if (!mounted) return;
      widget.onChanged();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      if (mounted) friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _upload() async {
    try {
      final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['pdf'], withData: true);
      if (!mounted || result == null) return;
      final bytes = result.files.single.bytes;
      if (bytes == null || bytes.length > 5 * 1024 * 1024) {
        throw const ApiException('Escolha um currículo PDF com até 5 MB.');
      }
      await _perform(() => widget.api.upload(bytes), 'Seu currículo foi atualizado.');
    } catch (error) {
      if (mounted) friendlyError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.user;
    final completed = [(_name.text.trim().isNotEmpty), (_skills.text.trim().isNotEmpty), user['has_resume'] == true, _titles.text.trim().isNotEmpty].where((v) => v).length;
    final premium = user['is_premium'] == true;
    return ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [CircleAvatar(radius: 32, backgroundColor: Brand.teal.withValues(alpha: .12), child: Text(_name.text.trim().isEmpty ? 'V' : _name.text.trim().substring(0, 1).toUpperCase(), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Brand.teal))), const SizedBox(width: 16), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${user['name']}', style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 4), Text('${user['email']}', style: Theme.of(context).textTheme.bodySmall), const SizedBox(height: 6), Text(premium ? 'Vagou! Premium' : 'Perfil profissional', style: const TextStyle(color: Brand.teal, fontWeight: FontWeight.w700))]))]),
        const SizedBox(height: 24),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text('Seu próximo passo começa aqui'), Text('${completed * 25}%', style: const TextStyle(fontWeight: FontWeight.w800))]),
        const SizedBox(height: 10), LinearProgressIndicator(value: completed / 4, minHeight: 8, borderRadius: BorderRadius.circular(8)),
        const SizedBox(height: 10), const Text('Complete seus dados, competências, currículo e objetivos para receber recomendações mais relevantes.'),
      ])),
      const SizedBox(height: 20), const SectionTitle(title: 'Seu perfil', subtitle: 'Informações profissionais que ajudam a apresentar você.'),
      Panel(child: Form(key: _profileKey, child: Column(children: [
        TextFormField(controller: _name, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Nome completo', prefixIcon: Icon(Icons.person_outline)), validator: (value) => (value?.trim().length ?? 0) < 2 ? 'Informe seu nome completo.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _phone, enabled: !_busy, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefone com DDD', hintText: '+5511999999999', prefixIcon: Icon(Icons.phone_outlined)), validator: (value) => value != null && value.isNotEmpty && !RegExp(r'^\+55\d{10,11}$').hasMatch(value) ? 'Use +55, DDD e seu número, sem espaços.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _skills, enabled: !_busy, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Suas competências', hintText: 'Python, atendimento, Excel, gestão...', helperText: 'Separe as competências por vírgula.', prefixIcon: Icon(Icons.auto_awesome_outlined))),
        const SizedBox(height: 20), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _busy ? null : () { if (_profileKey.currentState!.validate()) { _perform(() async { await widget.api.request('PUT', '/me/profile', {'name': _name.text.trim(), 'phone': _phone.text.isEmpty ? null : _phone.text, 'skills': _terms(_skills.text)}); }, 'Perfil salvo com sucesso.'); } }, icon: const Icon(Icons.check), label: const Text('Salvar perfil'))),
      ]))),
      const SizedBox(height: 20),
      Panel(child: Row(children: [Icon(user['has_resume'] == true ? Icons.task_outlined : Icons.upload_file_outlined, size: 34, color: Brand.teal), const SizedBox(width: 14), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(user['has_resume'] == true ? 'Currículo pronto' : 'Apresente sua trajetória', style: Theme.of(context).textTheme.titleMedium), const Text('PDF privado · até 5 MB e 20 páginas')])), IconButton(onPressed: _busy ? null : _upload, tooltip: 'Enviar currículo PDF', icon: const Icon(Icons.file_upload_outlined))])),
      const SizedBox(height: 20), const SectionTitle(title: 'Seu próximo trabalho', subtitle: 'Escolha como e onde você quer trabalhar.'),
      Panel(child: Form(key: _preferencesKey, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextFormField(controller: _titles, enabled: !_busy, decoration: const InputDecoration(labelText: 'Cargos ou áreas de interesse', hintText: 'Analista, Python, atendimento', prefixIcon: Icon(Icons.work_outline))),
        const SizedBox(height: 16),
        TextFormField(controller: _salary, enabled: !_busy, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Salário mínimo desejado', prefixText: 'R\$ ', prefixIcon: Icon(Icons.payments_outlined)), validator: (value) { final number = parseSalaryBr(value ?? ''); return number == null || number > 1000000 ? 'Informe um salário válido até R\$ 1.000.000.' : null; }),
        const SizedBox(height: 20), const Text('Modalidade', style: TextStyle(fontWeight: FontWeight.w700)), const SizedBox(height: 8),
        Wrap(spacing: 8, children: [for (final entry in {'remote':'Remoto','hybrid':'Híbrido','onsite':'Presencial'}.entries) FilterChip(label: Text(entry.value), selected: _modalities.contains(entry.key), onSelected: _busy ? null : (selected) => setState(() { if (selected) { _modalities.add(entry.key); } else { _modalities.remove(entry.key); } }))]),
        if (_needsCity) ...[
          const SizedBox(height: 16), Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: TextFormField(controller: _city, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Cidade', prefixIcon: Icon(Icons.location_city)), validator: (value) => _needsCity && (value?.trim().length ?? 0) < 2 ? 'Informe a cidade.' : null)), const SizedBox(width: 12), SizedBox(width: 100, child: DropdownButtonFormField<String>(initialValue: _state, decoration: const InputDecoration(labelText: 'UF'), items: [for (final state in _states) DropdownMenuItem(value: state, child: Text(state))], onChanged: _busy ? null : (value) => setState(() => _state = value!)))]),
          const SizedBox(height: 8), const Text('A cidade é aplicada às vagas presenciais e híbridas. Vagas remotas continuam disponíveis em qualquer local.'),
        ],
        const SizedBox(height: 20),
        Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: Brand.teal.withValues(alpha: .08), borderRadius: BorderRadius.circular(16)), child: Column(children: [Row(children: [const Icon(Icons.bolt, color: Brand.teal), const SizedBox(width: 8), Expanded(child: Text(premium ? 'Sua busca no piloto automático' : 'Vagou! Premium', style: const TextStyle(fontWeight: FontWeight.w800)))]), const SizedBox(height: 8), const Text('Envio automático para vagas internas aprovadas. Oportunidades externas exigem sua ação no site oficial; os resultados aparecem em Relatórios.'), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Autorizar candidaturas automáticas'), subtitle: Text(premium ? 'Usa seu perfil, currículo e critérios atuais.' : 'Disponível para assinaturas Premium ativas.'), value: premium && _automatic, onChanged: _busy || !premium ? null : (value) => setState(() => _automatic = value))])),
        if (!premium) TextButton.icon(onPressed: _busy ? null : () => showDialog<void>(context: context, builder: (dialog) => AlertDialog(title: const Text('Envio Automático Premium'), content: const Text('Com Premium ativo, configure cargo, cidade, salário, frequência e limite de envios. A ativação da assinatura depende da confirmação do serviço de pagamento; a versão gratuita não executa envios automáticos.'), actions: [FilledButton(onPressed: () => Navigator.pop(dialog), child: const Text('Entendi'))])), icon: const Icon(Icons.workspace_premium_outlined), label: const Text('Conheça os recursos Premium')),
        if (!premium) TextButton.icon(onPressed: _busy ? null : () => showDialog<void>(context: context, builder: (dialog) => AlertDialog(title: const Text('Envio Automático Premium'), content: const Text('Com Premium ativo, configure cargo, cidade, salário, frequência e limite de envios. A ativação da assinatura depende da confirmação do serviço de pagamento; a versão gratuita não executa envios automáticos.'), actions: [FilledButton(onPressed: () => Navigator.pop(dialog), child: const Text('Entendi'))])), icon: const Icon(Icons.workspace_premium_outlined), label: const Text('Conheça os recursos Premium')),
        if (premium) ...[const SizedBox(height: 16), DropdownButtonFormField<int>(initialValue: _interval, decoration: const InputDecoration(labelText: 'Frequência da busca automática', prefixIcon: Icon(Icons.schedule)), items: const [DropdownMenuItem(value: 15, child: Text('A cada 15 minutos')), DropdownMenuItem(value: 30, child: Text('A cada 30 minutos')), DropdownMenuItem(value: 60, child: Text('A cada hora')), DropdownMenuItem(value: 360, child: Text('A cada 6 horas')), DropdownMenuItem(value: 1440, child: Text('Uma vez por dia'))], onChanged: _busy ? null : (value) => setState(() => _interval = value ?? 60)), const SizedBox(height: 16), TextFormField(controller: _limit, enabled: !_busy, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Limite de candidaturas por ciclo', helperText: 'Defina entre 1 e 100 envios por ciclo de busca.'), validator: (value) { final limit = int.tryParse(value ?? ''); return limit == null || limit < 1 || limit > 100 ? 'Escolha um limite entre 1 e 100.' : null; })],
        const SizedBox(height: 20), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _busy ? null : () { if (_preferencesKey.currentState!.validate()) { _perform(() async { await widget.api.request('PUT', '/me/preferences', {'titles': _terms(_titles.text), 'min_salary': parseSalaryBr(_salary.text) ?? 0, 'modalities': _modalities.toList(), 'locations': _needsCity ? ['${_city.text.trim()} / $_state'] : [], 'automation_enabled': premium && _automatic, 'automation_max_applications_per_run': int.tryParse(_limit.text) ?? 20, 'automation_interval_minutes': _interval}); if (premium && _automatic) { try { await widget.api.request('POST', '/automation/run'); } on ApiException catch (error) { if (error.status != 503) rethrow; } } }, 'Preferências atualizadas. Acompanhe o envio em Relatórios.'); } }, icon: const Icon(Icons.tune), label: const Text('Salvar preferências'))),
        if (_busy) const Padding(padding: EdgeInsets.only(top: 16), child: LinearProgressIndicator()),
      ]))),
    ]);
  }
}
, '').replaceAll(' ', '');
  if (text.contains(',')) text = text.replaceAll('.', '').replaceAll(',', '.');
  final number = double.tryParse(text);
  return number != null && number.isFinite && number >= 0 ? number : null;
}

double? parseSalaryBr(String input) {
  var text = input.trim().replaceAll(r'R$', '').replaceAll(' ', '');
  if (text.contains(',')) text = text.replaceAll('.', '').replaceAll(',', '.');
  final number = double.tryParse(text);
  return number != null && number.isFinite && number >= 0 ? number : null;
}

class CandidateProfile extends StatefulWidget {
  const CandidateProfile({super.key, required this.api, required this.user, required this.onChanged});
  final Api api;
  final Map<String, dynamic> user;
  final VoidCallback onChanged;
  @override
  State<CandidateProfile> createState() => _CandidateProfileState();
}

class _CandidateProfileState extends State<CandidateProfile> {
  final _profileKey = GlobalKey<FormState>();
  final _preferencesKey = GlobalKey<FormState>();
  late final TextEditingController _name, _phone, _skills, _titles, _salary, _city, _limit;
  String _state = 'SP';
  int _interval = 60;
  Set<String> _modalities = {'remote'};
  bool _automatic = false, _busy = false;
  static const _states = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'];

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    final preferences = Map<String, dynamic>.from(user['preferences'] as Map? ?? {});
    final locations = List<String>.from(preferences['locations'] as List? ?? []);
    final place = locations.isEmpty ? <String>[] : locations.first.split(' / ');
    if (place.length > 1 && _states.contains(place.last)) _state = place.last;
    _name = TextEditingController(text: '${user['name'] ?? ''}');
    _phone = TextEditingController(text: '${user['phone'] ?? ''}');
    _skills = TextEditingController(text: (user['skills'] as List? ?? []).join(', '));
    _titles = TextEditingController(text: (preferences['titles'] as List? ?? []).join(', '));
    _salary = TextEditingController(text: '${preferences['min_salary'] ?? 0}');
    _city = TextEditingController(text: place.isEmpty ? '' : place.first);
    _limit = TextEditingController(text: '${preferences['automation_max_applications_per_run'] ?? 20}');
    _modalities = Set<String>.from(preferences['modalities'] as List? ?? ['remote']);
    _automatic = user['automation_enabled'] == true;
    final savedInterval = preferences['automation_interval_minutes'];
    _interval = [15, 30, 60, 360, 1440].contains(savedInterval) ? savedInterval as int : 60;
  }

  @override
  void dispose() {
    for (final controller in [_name, _phone, _skills, _titles, _salary, _city, _limit]) { controller.dispose(); }
    super.dispose();
  }

  List<String> _terms(String value) => value.split(',').map((v) => v.trim()).where((v) => v.isNotEmpty).toSet().toList();
  bool get _needsCity => _modalities.contains('onsite') || _modalities.contains('hybrid');
  Future<void> _perform(Future<void> Function() work, String message) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await work();
      if (!mounted) return;
      widget.onChanged();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      if (mounted) friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _upload() async {
    try {
      final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['pdf'], withData: true);
      if (!mounted || result == null) return;
      final bytes = result.files.single.bytes;
      if (bytes == null || bytes.length > 5 * 1024 * 1024) {
        throw const ApiException('Escolha um currículo PDF com até 5 MB.');
      }
      await _perform(() => widget.api.upload(bytes), 'Seu currículo foi atualizado.');
    } catch (error) {
      if (mounted) friendlyError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.user;
    final completed = [(_name.text.trim().isNotEmpty), (_skills.text.trim().isNotEmpty), user['has_resume'] == true, _titles.text.trim().isNotEmpty].where((v) => v).length;
    final premium = user['is_premium'] == true;
    return ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [CircleAvatar(radius: 32, backgroundColor: Brand.teal.withValues(alpha: .12), child: Text(_name.text.trim().isEmpty ? 'V' : _name.text.trim().substring(0, 1).toUpperCase(), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Brand.teal))), const SizedBox(width: 16), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${user['name']}', style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 4), Text('${user['email']}', style: Theme.of(context).textTheme.bodySmall), const SizedBox(height: 6), Text(premium ? 'Vagou! Premium' : 'Perfil profissional', style: const TextStyle(color: Brand.teal, fontWeight: FontWeight.w700))]))]),
        const SizedBox(height: 24),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text('Seu próximo passo começa aqui'), Text('${completed * 25}%', style: const TextStyle(fontWeight: FontWeight.w800))]),
        const SizedBox(height: 10), LinearProgressIndicator(value: completed / 4, minHeight: 8, borderRadius: BorderRadius.circular(8)),
        const SizedBox(height: 10), const Text('Complete seus dados, competências, currículo e objetivos para receber recomendações mais relevantes.'),
      ])),
      const SizedBox(height: 20), const SectionTitle(title: 'Seu perfil', subtitle: 'Informações profissionais que ajudam a apresentar você.'),
      Panel(child: Form(key: _profileKey, child: Column(children: [
        TextFormField(controller: _name, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Nome completo', prefixIcon: Icon(Icons.person_outline)), validator: (value) => (value?.trim().length ?? 0) < 2 ? 'Informe seu nome completo.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _phone, enabled: !_busy, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefone com DDD', hintText: '+5511999999999', prefixIcon: Icon(Icons.phone_outlined)), validator: (value) => value != null && value.isNotEmpty && !RegExp(r'^\+55\d{10,11}$').hasMatch(value) ? 'Use +55, DDD e seu número, sem espaços.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _skills, enabled: !_busy, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Suas competências', hintText: 'Python, atendimento, Excel, gestão...', helperText: 'Separe as competências por vírgula.', prefixIcon: Icon(Icons.auto_awesome_outlined))),
        const SizedBox(height: 20), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _busy ? null : () { if (_profileKey.currentState!.validate()) { _perform(() async { await widget.api.request('PUT', '/me/profile', {'name': _name.text.trim(), 'phone': _phone.text.isEmpty ? null : _phone.text, 'skills': _terms(_skills.text)}); }, 'Perfil salvo com sucesso.'); } }, icon: const Icon(Icons.check), label: const Text('Salvar perfil'))),
      ]))),
      const SizedBox(height: 20),
      Panel(child: Row(children: [Icon(user['has_resume'] == true ? Icons.task_outlined : Icons.upload_file_outlined, size: 34, color: Brand.teal), const SizedBox(width: 14), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(user['has_resume'] == true ? 'Currículo pronto' : 'Apresente sua trajetória', style: Theme.of(context).textTheme.titleMedium), const Text('PDF privado · até 5 MB e 20 páginas')])), IconButton(onPressed: _busy ? null : _upload, tooltip: 'Enviar currículo PDF', icon: const Icon(Icons.file_upload_outlined))])),
      const SizedBox(height: 20), const SectionTitle(title: 'Seu próximo trabalho', subtitle: 'Escolha como e onde você quer trabalhar.'),
      Panel(child: Form(key: _preferencesKey, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        TextFormField(controller: _titles, enabled: !_busy, decoration: const InputDecoration(labelText: 'Cargos ou áreas de interesse', hintText: 'Analista, Python, atendimento', prefixIcon: Icon(Icons.work_outline))),
        const SizedBox(height: 16),
        TextFormField(controller: _salary, enabled: !_busy, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Salário mínimo desejado', prefixText: 'R\$ ', prefixIcon: Icon(Icons.payments_outlined)), validator: (value) { final number = parseSalaryBr(value ?? ''); return number == null || number > 1000000 ? 'Informe um salário válido até R\$ 1.000.000.' : null; }),
        const SizedBox(height: 20), const Text('Modalidade', style: TextStyle(fontWeight: FontWeight.w700)), const SizedBox(height: 8),
        Wrap(spacing: 8, children: [for (final entry in {'remote':'Remoto','hybrid':'Híbrido','onsite':'Presencial'}.entries) FilterChip(label: Text(entry.value), selected: _modalities.contains(entry.key), onSelected: _busy ? null : (selected) => setState(() { if (selected) { _modalities.add(entry.key); } else { _modalities.remove(entry.key); } }))]),
        if (_needsCity) ...[
          const SizedBox(height: 16), Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: TextFormField(controller: _city, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Cidade', prefixIcon: Icon(Icons.location_city)), validator: (value) => _needsCity && (value?.trim().length ?? 0) < 2 ? 'Informe a cidade.' : null)), const SizedBox(width: 12), SizedBox(width: 100, child: DropdownButtonFormField<String>(initialValue: _state, decoration: const InputDecoration(labelText: 'UF'), items: [for (final state in _states) DropdownMenuItem(value: state, child: Text(state))], onChanged: _busy ? null : (value) => setState(() => _state = value!)))]),
          const SizedBox(height: 8), const Text('A cidade é aplicada às vagas presenciais e híbridas. Vagas remotas continuam disponíveis em qualquer local.'),
        ],
        const SizedBox(height: 20),
        Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: Brand.teal.withValues(alpha: .08), borderRadius: BorderRadius.circular(16)), child: Column(children: [Row(children: [const Icon(Icons.bolt, color: Brand.teal), const SizedBox(width: 8), Expanded(child: Text(premium ? 'Sua busca no piloto automático' : 'Vagou! Premium', style: const TextStyle(fontWeight: FontWeight.w800)))]), const SizedBox(height: 8), const Text('Envio automático para vagas internas aprovadas. Oportunidades externas exigem sua ação no site oficial; os resultados aparecem em Relatórios.'), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Autorizar candidaturas automáticas'), subtitle: Text(premium ? 'Usa seu perfil, currículo e critérios atuais.' : 'Disponível para assinaturas Premium ativas.'), value: premium && _automatic, onChanged: _busy || !premium ? null : (value) => setState(() => _automatic = value))])),
        if (premium) ...[const SizedBox(height: 16), DropdownButtonFormField<int>(initialValue: _interval, decoration: const InputDecoration(labelText: 'Frequência da busca automática', prefixIcon: Icon(Icons.schedule)), items: const [DropdownMenuItem(value: 15, child: Text('A cada 15 minutos')), DropdownMenuItem(value: 30, child: Text('A cada 30 minutos')), DropdownMenuItem(value: 60, child: Text('A cada hora')), DropdownMenuItem(value: 360, child: Text('A cada 6 horas')), DropdownMenuItem(value: 1440, child: Text('Uma vez por dia'))], onChanged: _busy ? null : (value) => setState(() => _interval = value ?? 60)), const SizedBox(height: 16), TextFormField(controller: _limit, enabled: !_busy, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Limite de candidaturas por ciclo', helperText: 'Defina entre 1 e 100 envios por ciclo de busca.'), validator: (value) { final limit = int.tryParse(value ?? ''); return limit == null || limit < 1 || limit > 100 ? 'Escolha um limite entre 1 e 100.' : null; })],
        const SizedBox(height: 20), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _busy ? null : () { if (_preferencesKey.currentState!.validate()) { _perform(() async { await widget.api.request('PUT', '/me/preferences', {'titles': _terms(_titles.text), 'min_salary': parseSalaryBr(_salary.text) ?? 0, 'modalities': _modalities.toList(), 'locations': _needsCity ? ['${_city.text.trim()} / $_state'] : [], 'automation_enabled': premium && _automatic, 'automation_max_applications_per_run': int.tryParse(_limit.text) ?? 20, 'automation_interval_minutes': _interval}); if (premium && _automatic) { try { await widget.api.request('POST', '/automation/run'); } on ApiException catch (error) { if (error.status != 503) rethrow; } } }, 'Preferências atualizadas. Acompanhe o envio em Relatórios.'); } }, icon: const Icon(Icons.tune), label: const Text('Salvar preferências'))),
        if (_busy) const Padding(padding: EdgeInsets.only(top: 16), child: LinearProgressIndicator()),
      ]))),
    ]);
  }
}
