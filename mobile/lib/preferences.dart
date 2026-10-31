import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';

const contractLabels = {
  'clt': 'CLT', 'pj': 'PJ', 'internship': 'Estágio',
  'temporary': 'Temporário', 'apprentice': 'Aprendiz', 'other': 'Outro',
};

Future<void> showPreferencesSheet(BuildContext context, {
  required Api api,
  required Map<String, dynamic> preferences,
  required Future<void> Function() onSaved,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  showDragHandle: true,
  builder: (_) => _PreferencesSheet(api: api, preferences: preferences, onSaved: onSaved),
);

class _PreferencesSheet extends StatefulWidget {
  const _PreferencesSheet({required this.api, required this.preferences, required this.onSaved});
  final Api api;
  final Map<String, dynamic> preferences;
  final Future<void> Function() onSaved;
  @override
  State<_PreferencesSheet> createState() => _PreferencesSheetState();
}

class _PreferencesSheetState extends State<_PreferencesSheet> {
  late final TextEditingController _titles, _city, _keywords, _salary;
  late String _state;
  late Set<String> _modalities, _contracts;
  bool _busy = false;
  static const _states = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'];

  @override
  void initState() {
    super.initState();
    final prefs = widget.preferences;
    final locations = List<String>.from(prefs['locations'] as List? ?? const []);
    final place = locations.isEmpty ? <String>[] : locations.first.split(RegExp(r'\s*[/,]\s*'));
    _state = place.length > 1 && _states.contains(place.last.toUpperCase()) ? place.last.toUpperCase() : '';
    _titles = TextEditingController(text: (prefs['titles'] as List? ?? const []).join(', '));
    _city = TextEditingController(text: place.isEmpty ? '' : place.first);
    _keywords = TextEditingController(text: (prefs['keywords'] as List? ?? const []).join(', '));
    _salary = TextEditingController(text: '${prefs['min_salary'] ?? ''}');
    _modalities = Set<String>.from(prefs['modalities'] as List? ?? const []);
    _contracts = Set<String>.from(prefs['contract_types'] as List? ?? const []);
  }

  @override
  void dispose() {
    for (final controller in [_titles, _city, _keywords, _salary]) { controller.dispose(); }
    super.dispose();
  }

  List<String> _terms(String value) => value.split(',').map((item) => item.trim()).where((item) => item.isNotEmpty).toSet().toList();

  double? _salaryValue() {
    var value = _salary.text.trim().replaceAll(r'R$', '').replaceAll(' ', '');
    if (value.isEmpty) return 0;
    if (value.contains(',')) value = value.replaceAll('.', '').replaceAll(',', '.');
    final parsed = double.tryParse(value);
    return parsed != null && parsed.isFinite && parsed >= 0 && parsed <= 1000000 ? parsed : null;
  }

  Future<void> _save() async {
    final salary = _salaryValue();
    if (salary == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Informe um salário válido ou deixe o campo vazio.')));
      return;
    }
    setState(() => _busy = true);
    final city = _city.text.trim();
    final location = city.isEmpty ? <String>[] : ['${city}${_state.isEmpty ? '' : ' / $_state'}'];
    try {
      await widget.api.request('PUT', '/me/preferences', {
        'titles': _terms(_titles.text),
        'keywords': _terms(_keywords.text),
        'min_salary': salary,
        'modalities': _modalities.toList(),
        'locations': location,
        'contract_types': _contracts.toList(),
      });
      await widget.onSaved();
      if (mounted) Navigator.pop(context);
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(20, 8, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
    child: ListView(shrinkWrap: true, children: [
      const SectionTitle(title: 'Filtros e Preferências', subtitle: 'A lista de vagas e o robô usam estes critérios.'),
      TextField(controller: _titles, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Cargo ou área desejada', hintText: 'Analista, Python, atendimento', prefixIcon: Icon(Icons.work_outline))),
      const SizedBox(height: 12),
      Row(children: [
        Expanded(child: TextField(controller: _city, enabled: !_busy, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Cidade', prefixIcon: Icon(Icons.location_city_outlined)))),
        const SizedBox(width: 10),
        SizedBox(width: 108, child: DropdownButtonFormField<String>(initialValue: _state.isEmpty ? '' : _state, decoration: const InputDecoration(labelText: 'UF'), items: [const DropdownMenuItem(value: '', child: Text('Todas')), for (final state in _states) DropdownMenuItem(value: state, child: Text(state))], onChanged: _busy ? null : (value) => setState(() => _state = value ?? ''))),
      ]),
      const SizedBox(height: 16),
      const Text('Modalidade', style: TextStyle(fontWeight: FontWeight.w700)),
      Wrap(spacing: 8, children: [for (final entry in const {'onsite': 'Presencial', 'hybrid': 'Híbrido', 'remote': 'Remoto'}.entries) FilterChip(label: Text(entry.value), selected: _modalities.contains(entry.key), onSelected: _busy ? null : (selected) => setState(() => selected ? _modalities.add(entry.key) : _modalities.remove(entry.key)))]),
      Text(_modalities.isEmpty ? 'Sem seleção: considerar todas as modalidades.' : 'Vagas remotas continuam disponíveis em qualquer região.'),
      const SizedBox(height: 16),
      TextField(controller: _salary, enabled: !_busy, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Salário mínimo', hintText: 'Opcional', prefixText: 'R\$ ', prefixIcon: Icon(Icons.payments_outlined))),
      const SizedBox(height: 16),
      const Text('Tipo de contrato', style: TextStyle(fontWeight: FontWeight.w700)),
      Wrap(spacing: 8, children: [for (final entry in contractLabels.entries) FilterChip(label: Text(entry.value), selected: _contracts.contains(entry.key), onSelected: _busy ? null : (selected) => setState(() => selected ? _contracts.add(entry.key) : _contracts.remove(entry.key))]),
      TextField(controller: _keywords, enabled: !_busy, decoration: const InputDecoration(labelText: 'Palavras-chave', hintText: 'Python, SQL, atendimento', helperText: 'Separe por vírgula; basta uma palavra aparecer na vaga.', prefixIcon: Icon(Icons.key_outlined))),
      const SizedBox(height: 20),
      FilledButton.icon(onPressed: _busy ? null : _save, icon: _busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.check), label: const Text('Salvar preferências')),
    ]),
  );
}