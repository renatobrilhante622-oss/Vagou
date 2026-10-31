import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'preferences.dart';
import 'ui.dart';

Future<void> showAutomationPanel(BuildContext context, {
  required Api api,
  required Future<void> Function() onChanged,
}) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  showDragHandle: true,
  builder: (_) => _AutomationPanel(api: api, onChanged: onChanged),
);

class _AutomationPanel extends StatefulWidget {
  const _AutomationPanel({required this.api, required this.onChanged});
  final Api api;
  final Future<void> Function() onChanged;
  @override
  State<_AutomationPanel> createState() => _AutomationPanelState();
}

class _AutomationPanelState extends State<_AutomationPanel> {
  Map<String, dynamic> _user = {};
  Map<String, dynamic> _latestRun = {};
  Map<String, dynamic> _progress = {};
  List<dynamic> _runs = [], _events = [];
  String? _activeRunId;
  String _runStatus = '';
  Timer? _pollTimer;
  bool _loading = true, _busy = false;

  bool get _premium => _user['is_premium'] == true;
  Map<String, dynamic> get _preferences => Map<String, dynamic>.from(_user['preferences'] as Map? ?? const {});

  @override
  void initState() { super.initState(); _load(); }

  @override
  void dispose() { _pollTimer?.cancel(); super.dispose(); }

  Future<void> _load({bool reportErrors = false}) async {
    try {
      final user = Map<String, dynamic>.from(await widget.api.request('GET', '/me') as Map);
      List<dynamic> runs = [];
      if (user['is_premium'] == true) {
        try { runs = List<dynamic>.from((await widget.api.request('GET', '/automation/runs?limit=10'))['items'] as List? ?? const []); }
        on ApiException catch (error) { if (error.status != 403) rethrow; }
      }
      if (!mounted) return;
      setState(() { _user = user; _runs = runs; _latestRun = runs.isEmpty ? {} : Map<String, dynamic>.from(runs.first as Map); });
      Map? running;
      for (final item in runs) {
        final candidate = item as Map;
        if (['queued', 'running'].contains(candidate['status'])) { running = candidate; break; }
      }
      if (running != null) {
        _activeRunId = '${running['id']}';
        await _poll();
      } else {
        _activeRunId = null;
        _pollTimer?.cancel();
        await _loadEvents();
      }
    } catch (error) {
      if (reportErrors && mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadEvents() async {
    final id = _latestRun['id']?.toString();
    if (id == null || !_premium) { _events = []; return; }
    try {
      final result = await widget.api.request('GET', '/automation/runs/$id/events?limit=50');
      if (mounted) setState(() => _events = List<dynamic>.from(result['items'] as List? ?? const []));
    } catch (_) { }
  }

  Future<void> _poll() async {
    final id = _activeRunId;
    if (id == null) return;
    try {
      final result = Map<String, dynamic>.from(await widget.api.request('GET', '/automation/runs/$id/status') as Map);
      if (!mounted) return;
      final status = '${result['status'] ?? 'queued'}';
      setState(() {
        _runStatus = status;
        _latestRun = result;
        _progress = Map<String, dynamic>.from(result['progress'] as Map? ?? const {});
      });
      if (status == 'complete' || status == 'failed') {
        _activeRunId = null;
        _pollTimer?.cancel();
        await _loadEvents();
        await _loadRuns();
        return;
      }
      _pollTimer ??= Timer.periodic(const Duration(seconds: 1), (_) => _poll());
    } catch (error) {
      if (mounted && _pollTimer == null) await friendlyError(context, error);
    }
  }

  Future<void> _loadRuns() async {
    try {
      final response = await widget.api.request('GET', '/automation/runs?limit=10');
      if (mounted) setState(() {
        _runs = List<dynamic>.from(response['items'] as List? ?? const []);
        if (_runs.isNotEmpty) _latestRun = Map<String, dynamic>.from(_runs.first as Map);
      });
      await _loadEvents();
    } catch (_) { }
  }

  Future<void> _refreshAccess() async {
    setState(() => _busy = true);
    try {
      final entitlements = Map<String, dynamic>.from(await widget.api.request('GET', '/candidate/entitlements') as Map);
      if (mounted) setState(() => _user = {..._user, ...entitlements});
      await _load();
      await widget.onChanged();
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggle(bool enabled) async {
    setState(() => _busy = true);
    try {
      await widget.api.request('PUT', '/me/preferences', {'automation_enabled': enabled});
      await _load();
      await widget.onChanged();
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() async {
    setState(() => _busy = true);
    try {
      final response = await widget.api.request('POST', '/automation/run');
      _activeRunId = response['run_id']?.toString();
      _runStatus = 'queued';
      _progress = {};
      await _poll();
      if (_activeRunId != null) _pollTimer ??= Timer.periodic(const Duration(seconds: 1), (_) => _poll());
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _editPreferences() async {
    await showPreferencesSheet(context, api: widget.api, preferences: _preferences, onSaved: () async {
      await _load();
      await widget.onChanged();
    });
  }

  String _criteria() {
    final titles = List<String>.from(_preferences['titles'] as List? ?? const []);
    final locations = List<String>.from(_preferences['locations'] as List? ?? const []);
    final modalities = List<String>.from(_preferences['modalities'] as List? ?? const []);
    final position = titles.isEmpty ? 'todos os cargos' : titles.join(', ');
    final region = locations.isEmpty ? 'qualquer região' : locations.join(', ');
    final mode = modalities.isEmpty ? 'todas as modalidades' : modalities.map((item) => const {'remote': 'remoto', 'hybrid': 'híbrido', 'onsite': 'presencial'}[item] ?? item).join(', ');
    final minimum = num.tryParse('${_preferences['min_salary'] ?? 0}') ?? 0;
    final salary = minimum > 0 ? 'piso R\$ ${minimum.toStringAsFixed(0)}' : 'sem piso salarial';
    final contracts = List<String>.from(_preferences['contract_types'] as List? ?? const []);
    final contract = contracts.isEmpty ? 'todos os contratos' : contracts.map((item) => contractLabels[item] ?? item).join(', ');
    final keywords = List<String>.from(_preferences['keywords'] as List? ?? const []);
    final terms = keywords.isEmpty ? 'sem palavras-chave' : keywords.join(', ');
    return 'Buscando por: $position em $region · $mode · $salary · $contract · $terms';
  }

  int _count(String key) => ((_progress[key] ?? _latestRun[key]) as num? ?? 0).toInt();

  @override
  Widget build(BuildContext context) {
    if (_loading) return const SizedBox(height: 320, child: Center(child: CircularProgressIndicator()));
    final active = _activeRunId != null || _runStatus == 'running' || _runStatus == 'queued';
    return Padding(padding: const EdgeInsets.fromLTRB(20, 8, 20, 24), child: ListView(shrinkWrap: true, children: [
      const SectionTitle(title: 'Robô de Candidaturas', subtitle: 'A automação só envia candidaturas para vagas internas aprovadas. Vagas externas ficam para sua avaliação.'),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Icon(_premium ? Icons.bolt : Icons.lock_outline, color: Brand.coral), const SizedBox(width: 10), Expanded(child: Text(_premium ? 'Premium Ativo' : 'Plano Gratuito', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800))), if (_busy) const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))]),
        const SizedBox(height: 8),
        SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Ativar envio automático'), subtitle: Text(_premium ? 'O robô seguirá estes critérios em segundo plano.' : 'Atualize o acesso para ativar a automação.'), value: _premium && _user['automation_enabled'] == true, onChanged: _busy || !_premium ? null : _toggle),
        if (!_premium) OutlinedButton.icon(onPressed: _busy ? null : _refreshAccess, icon: const Icon(Icons.refresh), label: const Text('Atualizar meu acesso')),
      ])),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Critérios ativos', style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8), Text(_criteria()),
        const SizedBox(height: 12), Align(alignment: Alignment.centerLeft, child: TextButton.icon(onPressed: _editPreferences, icon: const Icon(Icons.tune), label: const Text('Editar Preferências'))),
      ])),
      if (_premium) FilledButton.icon(onPressed: _busy || active || _user['has_resume'] != true || _user['automation_enabled'] != true ? null : _start,
        icon: active ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.radar),
        label: Text(active ? 'Varredura em andamento' : 'Iniciar Varredura e Envio Agora')),
      if (_premium && _user['has_resume'] != true) const Padding(padding: EdgeInsets.only(top: 8), child: Text('Envie seu currículo no Perfil para liberar candidaturas automáticas.')),
      if (_premium && _user['automation_enabled'] != true) const Padding(padding: EdgeInsets.only(top: 8), child: Text('Ative o envio automático para iniciar uma varredura.')),
      if (active || _latestRun.isNotEmpty) ...[
        const SizedBox(height: 18), const SectionTitle(title: 'Progresso da execução'),
        Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(statusLabel(active ? (_runStatus.isEmpty ? 'running' : _runStatus) : '${_latestRun['status'] ?? 'complete'}'), style: const TextStyle(fontWeight: FontWeight.w800)),
          if (active) ...[const SizedBox(height: 10), const LinearProgressIndicator()],
          const SizedBox(height: 12),
          Text('${_count('scanned_jobs')} analisadas · ${_count('filtered_jobs')} descartadas · ${_count('eligible_jobs')} compatíveis · ${_count('submitted_applications')} candidaturas · ${_count('manual_review_jobs')} para sua avaliação'),
        ])),
      ],
      if (_premium) ...[
        const SectionTitle(title: 'Histórico e atividade'),
        if (_events.isEmpty) const Panel(child: Text('Os resultados e motivos de descarte aparecerão aqui após a primeira varredura.')),
        for (final event in _events.take(20)) Panel(child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(event['status'] == 'submitted' ? Icons.check_circle_outline : event['status'] == 'filtered' ? Icons.filter_alt_off_outlined : Icons.info_outline, color: event['status'] == 'submitted' ? Brand.teal : Brand.coral), const SizedBox(width: 10), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${event['job_title'] ?? 'Oportunidade'}', style: const TextStyle(fontWeight: FontWeight.w700)), Text('${statusLabel('${event['status']}')} · ${event['detail'] ?? ''}'), Text(formatDate(event['created_at']), style: Theme.of(context).textTheme.bodySmall)]))])),
        if (_runs.length > 1) Text('Há ${_runs.length} execuções recentes; o histórico completo também fica em Relatórios.'),
      ],
    ]));
  }
}