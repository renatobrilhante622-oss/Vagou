import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'api.dart';
import 'automation_panel.dart';
import 'ui.dart';

class CandidateProfile extends StatefulWidget {
  const CandidateProfile({super.key, required this.api, required this.user, required this.onChanged});
  final Api api;
  final Map<String, dynamic> user;
  final Future<void> Function() onChanged;
  @override
  State<CandidateProfile> createState() => _CandidateProfileState();
}

class _CandidateProfileState extends State<CandidateProfile> {
  final _profileKey = GlobalKey<FormState>();
  late final TextEditingController _name, _phone, _skills;
  bool _premium = false, _busy = false;

  @override
  void initState() {
    super.initState();
    final user = widget.user;
    _name = TextEditingController(text: '${user['name'] ?? ''}');
    _phone = TextEditingController(text: '${user['phone'] ?? ''}');
    _skills = TextEditingController(text: (user['skills'] as List? ?? []).join(', '));
    _premium = user['is_premium'] == true;
  }

  @override
  void dispose() {
    for (final controller in [_name, _phone, _skills]) { controller.dispose(); }
    super.dispose();
  }

  List<String> _terms(String value) => value.split(',').map((v) => v.trim()).where((v) => v.isNotEmpty).toSet().toList();
  Future<void> _refreshAccess() async {
    setState(() => _busy = true);
    try {
      final result = Map<String, dynamic>.from(await widget.api.request('GET', '/candidate/entitlements') as Map);
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
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
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
    final completed = [_name.text.trim().isNotEmpty, _skills.text.trim().isNotEmpty, user['has_resume'] == true].where((v) => v).length;
    final premium = _premium || user['is_premium'] == true;
    return ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [CircleAvatar(radius: 32, backgroundColor: Brand.teal.withValues(alpha: .12), child: Text(_name.text.trim().isEmpty ? 'V' : _name.text.trim().substring(0, 1).toUpperCase(), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Brand.teal))), const SizedBox(width: 16), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${user['name']}', style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 4), Text('${user['email']}', style: Theme.of(context).textTheme.bodySmall)]))]),
        const SizedBox(height: 24),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text('Perfil profissional'), Text('${(completed * 100 / 3).round()}%', style: const TextStyle(fontWeight: FontWeight.w800))]),
        const SizedBox(height: 10), LinearProgressIndicator(value: completed / 3, minHeight: 8, borderRadius: BorderRadius.circular(8)),
        const SizedBox(height: 10), const Text('Mantenha seus dados, competências e currículo atualizados.'),
      ])),
      const SectionTitle(title: 'Dados pessoais', subtitle: 'Informações profissionais para apresentar sua trajetória.'),
      Panel(child: Form(key: _profileKey, child: Column(children: [
        TextFormField(controller: _name, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Nome completo', prefixIcon: Icon(Icons.person_outline)), validator: (value) => (value?.trim().length ?? 0) < 2 ? 'Informe seu nome completo.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _phone, enabled: !_busy, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefone com DDD', hintText: '+5511999999999', prefixIcon: Icon(Icons.phone_outlined)), validator: (value) => value != null && value.isNotEmpty && !RegExp(r'^\+55\d{10,11}$').hasMatch(value) ? 'Use +55, DDD e seu número, sem espaços.' : null),
        const SizedBox(height: 16),
        TextFormField(controller: _skills, enabled: !_busy, minLines: 2, maxLines: 4, decoration: const InputDecoration(labelText: 'Suas competências', hintText: 'Python, atendimento, Excel, gestão...', helperText: 'Separe as competências por vírgula.', prefixIcon: Icon(Icons.auto_awesome_outlined))),
        const SizedBox(height: 20), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _busy ? null : () { if (_profileKey.currentState!.validate()) { _perform(() async { await widget.api.request('PUT', '/me/profile', {'name': _name.text.trim(), 'phone': _phone.text.isEmpty ? null : _phone.text, 'skills': _terms(_skills.text)}); }, 'Perfil salvo com sucesso.'); } }, icon: const Icon(Icons.check), label: const Text('Salvar perfil'))),
      ]))),
      Panel(child: Row(children: [Icon(user['has_resume'] == true ? Icons.task_outlined : Icons.upload_file_outlined, size: 34, color: Brand.teal), const SizedBox(width: 14), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(user['has_resume'] == true ? 'Currículo pronto' : 'Apresente sua trajetória', style: Theme.of(context).textTheme.titleMedium), const Text('PDF privado · até 5 MB e 20 páginas')])), IconButton(onPressed: _busy ? null : _upload, tooltip: 'Enviar currículo PDF', icon: const Icon(Icons.file_upload_outlined))])),
      const SectionTitle(title: 'Meu Plano'),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Icon(premium ? Icons.workspace_premium : Icons.workspace_premium_outlined, color: premium ? Brand.coral : Brand.teal), const SizedBox(width: 10), Expanded(child: Text(premium ? 'Premium Ativo' : 'Plano Gratuito', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)))]),
        const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: _busy ? null : _refreshAccess, icon: const Icon(Icons.refresh), label: const Text('Atualizar meu acesso')),
        const SizedBox(height: 8),
        FilledButton.icon(onPressed: () => showAutomationPanel(context, api: widget.api, onChanged: widget.onChanged), icon: const Icon(Icons.bolt), label: const Text('Configurar Robô de Automação')),
      ])),
    ]);
  }
}
