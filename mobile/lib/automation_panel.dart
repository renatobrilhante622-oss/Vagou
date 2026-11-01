import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'preferences.dart';
import 'opportunity_details.dart';
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
      if (status == 'complete' || status == 'failed' || status == 'cancelled') {
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
      final response = await widget.api.request('POST', '/automation/run', {'consent_granted': _user['automation_enabled'] == true});
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
    final salary = minimum > 0 ? 'piso ${formatBrlCurrency(minimum)}' : 'sem piso salarial';
    final contracts = List<String>.from(_preferences['contract_types'] as List? ?? const []);
    final contract = contracts.isEmpty ? 'todos os contratos' : contracts.map((item) => contractLabels[item] ?? item).join(', ');
    final keywords = List<String>.from(_preferences['keywords'] as List? ?? const []);
    final terms = keywords.isEmpty ? 'sem palavras-chave' : keywords.join(', ');
    return 'Buscando por: $position em $region · $mode · $salary · $contract · $terms';
  }

  int _count(String key) => ((_progress[key] ?? _latestRun[key]) as num? ?? 0).toInt();

  Future<void> _openEvent(Map event) async {
    final link = (event['external_url'] ?? event['job_url'])?.toString();
    final uri = link == null ? null : Uri.tryParse(link);
    if (uri != null && ['http', 'https'].contains(uri.scheme)) {
      try { await externalLink(link!); }
      catch (error) { if (mounted) await friendlyError(context, error); }
      return;
    }
    final id = event['job_id']?.toString();
    if (id == null) return;
    try {
      final job = await widget.api.request('GET', '/jobs/$id');
      if (!mounted) return;
      await showModalBottomSheet<void>(context: context, showDragHandle: true,
        isScrollControlled: true, builder: (context) => SafeArea(child: SingleChildScrollView(
          padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start, children: [
              OpportunityDetails(row: Map<String, dynamic>.from(job as Map), initiallyExpanded: true),
            ]))));
    } catch (error) { if (mounted) await friendlyError(context, error); }
  }

  Widget _eventCard(Map event) {
    return Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      OpportunityDetails(row: event),
      if (event['destination_channel'] != null) Text('Canal de destino: ${const {'smtp': 'contato de recrutamento por e-mail', 'email': 'contato de recrutamento por e-mail', 'platform': 'recrutador no Vagou!', 'portal': 'portal oficial', 'portal_link': 'portal oficial', 'portal_search': 'pesquisa no portal', 'candidate_review': 'avaliação individual', 'existing_application': 'candidatura existente'}[event['destination_channel']] ?? 'consulte a vaga'}'),
      if (event['delivery_status'] != null) Text(const {'pending': 'Notificação aguardando envio.', 'queued': 'Notificação na fila de envio.', 'sent': 'Mensagem aceita pelo servidor de e-mail.', 'smtp_accepted': 'Mensagem aceita pelo servidor de e-mail.', 'retrying': 'O envio da notificação será tentado novamente.', 'failed': 'A notificação não foi entregue; confira o relatório.', 'cancelled': 'Envio da notificação cancelado.', 'not_requested': 'Registro disponível no Vagou!.', 'requires_manual': 'Conclua a candidatura no portal oficial.'}[event['delivery_status']] ?? 'Consulte o relatório para acompanhar a notificação.'),
      if (opportunityValue(event, const ['external_url', 'job_url']).isEmpty || opportunityValue(event, const ['external_url', 'job_url']).startsWith('/'))
        TextButton.icon(onPressed: () => _openEvent(event), icon: const Icon(Icons.open_in_new), label: const Text('Candidatar-se / Abrir Vaga')),
    ]));
  }

  Widget _statusBadge(String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(color: Colors.white.withValues(alpha: .12), borderRadius: BorderRadius.circular(20), border: Border.all(color: const Color(0xFFE7C36A).withValues(alpha: .5))),
    child: Text(label, style: const TextStyle(color: Color(0xFFE7C36A), fontSize: 11, fontWeight: FontWeight.w800)),
  );

  @override
  Widget build(BuildContext context) {
    if (_loading) return const SizedBox(height: 320, child: Center(child: CircularProgressIndicator()));
    final active = _activeRunId != null || _runStatus == 'running' || _runStatus == 'queued';
    return Padding(padding: const EdgeInsets.fromLTRB(20, 4, 20, 20), child: ListView(shrinkWrap: true, children: [
      Container(margin: const EdgeInsets.only(bottom: 16), padding: const EdgeInsets.all(20), decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Brand.navy, Color(0xFF1E4864)], begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(18),
      ), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Container(width: 42, height: 42, decoration: BoxDecoration(color: Brand.coral.withValues(alpha: .18), borderRadius: BorderRadius.circular(12)), child: const Icon(Icons.radar, color: Color(0xFFE7C36A))), const SizedBox(width: 12), Expanded(child: Text('Central de Automação', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700))), if (_busy) const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 4, children: [
          _statusBadge(_premium ? 'VAGOU! PRO' : 'PLANO GRATUITO'),
          if (_premium && _user['automation_enabled'] == true) _statusBadge('ROBÔ ATIVO 24/7'),
          if (active) _statusBadge('BUSCA EM ANDAMENTO'),
        ]),
        const SizedBox(height: 8),
        const Text('A automação registra candidaturas compatíveis e encaminha o currículo quando houver contato de recrutamento. Alguns portais exigem concluir o processo no site oficial.', style: TextStyle(color: Colors.white70)),
      ])),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Icon(_premium ? Icons.workspace_premium : Icons.lock_outline, color: Brand.coral), const SizedBox(width: 10), Expanded(child: Text(_premium ? 'Premium Ativo' : 'Plano Gratuito', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800))), if (_busy) const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))]),
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
        Padding(padding: const EdgeInsets.only(bottom: 12), child: Row(children: [
          Expanded(child: Text(statusLabel(active ? (_runStatus.isEmpty ? 'running' : _runStatus) : '${_latestRun['status'] ?? 'complete'}'), style: const TextStyle(fontWeight: FontWeight.w800))),
          if (active) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        ])),
        if (active) const Padding(padding: EdgeInsets.only(bottom: 12), child: LinearProgressIndicator(minHeight: 5)),
        LayoutBuilder(builder: (context, constraints) {
          final metrics = [
            ('Coletadas', _count('collected_jobs'), Icons.travel_explore),
            ('Varridas', _count('scanned_jobs'), Icons.radar),
            ('Possíveis', _count('possible_match_jobs'), Icons.auto_awesome_outlined),
            ('Registradas', _count('submitted_applications'), Icons.send_outlined),
          ];
          return Wrap(spacing: 8, runSpacing: 0, children: [for (final metric in metrics)
            SizedBox(width: (constraints.maxWidth - 8) / 2, child: Container(
              margin: const EdgeInsets.only(bottom: 8), padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: Theme.of(context).colorScheme.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: Theme.of(context).colorScheme.outlineVariant)),
              child: Row(children: [Icon(metric.$3, color: Brand.teal), const SizedBox(width: 8), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${metric.$2}', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900)), Text(metric.$1, maxLines: 1, overflow: TextOverflow.ellipsis)]))]),
            )),
          ]);
        }),
        Padding(padding: const EdgeInsets.only(bottom: 12), child: Text('${_count('external_jobs_scanned')} externas analisadas · ${_count('filtered_jobs')} descartadas', style: Theme.of(context).textTheme.bodySmall)),
      ],
      if (_premium) ...[
        const SectionTitle(title: 'Vagas enviadas / encaminhadas'),
        for (final event in _events.where((item) => ['submitted', 'requires_manual'].contains(item['status'])).take(20)) _eventCard(Map<String, dynamic>.from(event as Map)),
        if (!_events.any((item) => ['submitted', 'requires_manual'].contains(item['status']))) const Panel(child: Text('Vagas enviadas ou encaminhadas aparecerão aqui.')),
        const SectionTitle(title: 'Possíveis Matches (Próximas ao seu perfil)'),
        for (final event in _events.where((item) => item['status'] == 'possible_match').take(20)) _eventCard(Map<String, dynamic>.from(event as Map)),
        if (!_events.any((item) => item['status'] == 'possible_match')) const Panel(child: Text('Nenhuma vaga próxima ao perfil nesta execução.')),
        if (_events.any((item) => item['status'] == 'search_channel')) ...[
          const SectionTitle(title: 'Explorar canais regionais', subtitle: 'Links de busca com seus critérios. Não são anúncios confirmados nem candidaturas enviadas.'),
          for (final event in _events.where((item) => item['status'] == 'search_channel')) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${event['source_name'] ?? 'Portal de vagas'}', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8), Text('${event['location'] ?? 'Região dos seus critérios'}'),
            Text('${event['detail'] ?? 'Explore vagas diretamente no canal oficial.'}'),
            TextButton.icon(onPressed: () => _openEvent(Map<String, dynamic>.from(event as Map)), icon: const Icon(Icons.open_in_new), label: const Text('Abrir busca no portal')),
          ])),
        ],
        const SectionTitle(title: 'Vagas descartadas'),
        for (final event in _events.where((item) => item['status'] == 'filtered').take(20)) _eventCard(Map<String, dynamic>.from(event as Map)),
        if (_runs.length > 1) Text('Há ${_runs.length} execuções recentes; o histórico completo também fica em Relatórios.'),
      ],
    ]));
  }
}
