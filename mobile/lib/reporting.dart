import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';

class ReportsView extends StatefulWidget {
  const ReportsView({super.key, required this.api});
  final Api api;
  @override
  State<ReportsView> createState() => _ReportsViewState();
}

class _ReportsViewState extends State<ReportsView> {
  late Future<Map<String, dynamic>> _data;
  List<dynamic> _applications = [];
  int _offset = 0;
  bool _hasMore = false, _loadingMore = false;
  @override
  void initState() { super.initState(); _reload(); }
  void _reload() { _data = _load(); }
  Future<Map<String, dynamic>> _load() async {
    final report = Map<String, dynamic>.from(await widget.api.request('GET', '/dashboard') as Map);
    final applications = await widget.api.request('GET', '/applications?limit=20');
    final notifications = await widget.api.request('GET', '/notifications?limit=10');
    report['notifications'] = notifications;
    dynamic runs;
    try { runs = await widget.api.request('GET', '/automation/runs?limit=10'); }
    on ApiException catch (error) { if (error.status != 403 && error.status != 404) { report['automation_unavailable'] = true; } }
    if (mounted) {
      _applications = List<dynamic>.from(applications as List);
      _offset = _applications.length;
      _hasMore = _applications.length == 20;
    }
    report['runs'] = runs is Map ? runs['items'] ?? [] : [];
    return report;
  }
  Future<void> _more() async {
    if (_loadingMore) return;
    setState(() => _loadingMore = true);
    try {
      final result = List<dynamic>.from(await widget.api.request('GET', '/applications?offset=$_offset&limit=20') as List);
      if (mounted) setState(() { _applications.addAll(result); _offset += result.length; _hasMore = result.length == 20; });
    } catch (error) { if (mounted) friendlyError(context, error); }
    finally { if (mounted) setState(() => _loadingMore = false); }
  }
  Future<void> _job(Map row) async {
    final link = (row['job_url'] ?? row['source_url'])?.toString();
    final uri = link == null ? null : Uri.tryParse(link);
    if (uri != null && ['http', 'https'].contains(uri.scheme)) {
      try { await externalLink('${row['job_url'] ?? row['source_url']}'); }
      catch (error) { if (mounted) friendlyError(context, error); }
      return;
    }
    try {
      final job = await widget.api.request('GET', '/jobs/${row['job_id']}');
      if (!mounted) return;
      await showModalBottomSheet<void>(context: context, showDragHandle: true, isScrollControlled: true, builder: (context) => SafeArea(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${job['title']}', style: Theme.of(context).textTheme.headlineSmall), const SizedBox(height: 8), Text('${job['company']} • ${job['location']}'), const SizedBox(height: 20), Text('${job['description']}')]))));
    } catch (error) { if (mounted) friendlyError(context, error); }
  }
  Future<void> _events(Map run) async {
    try {
      final data = await widget.api.request('GET', '/automation/runs/${run['id']}/events?limit=50');
      if (!mounted) return;
      await showModalBottomSheet<void>(context: context, showDragHandle: true, isScrollControlled: true, useSafeArea: true, builder: (context) => _RunEvents(api: widget.api, initial: Map<String, dynamic>.from(data as Map), runId: '${run['id']}', onJob: _job));
    } catch (error) { if (mounted) friendlyError(context, error); }
  }
  @override
  Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(future: _data, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return EmptyState(icon: Icons.insights_outlined, title: 'Sua evolução profissional', message: 'Não foi possível carregar seus relatórios.', onRetry: () => setState(_reload));
    final data = snapshot.data!;
    final manual = (data['manual'] as num? ?? 0).toDouble();
    final automatic = (data['automatic'] as num? ?? 0).toDouble();
    final total = (data['total_applications'] as num? ?? 0).toInt();
    final statuses = Map<String, dynamic>.from(data['by_status'] as Map? ?? {});
    final metrics = [
      ('Enviadas', '$total', Icons.send_outlined),
      ('Manuais', '${manual.toInt()}', Icons.touch_app_outlined),
      ('Automáticas', '${automatic.toInt()}', Icons.bolt_outlined),
      ('Em observação', '${data['observation_jobs'] ?? 0}', Icons.visibility_outlined),
    ];
    return RefreshIndicator(onRefresh: () async { setState(_reload); await _data; }, child: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
      const SectionTitle(title: 'Sua carreira em movimento', subtitle: 'Cada candidatura é um passo. Acompanhe sua jornada com clareza.'),
      LayoutBuilder(builder: (context, constraints) => Wrap(spacing: 12, runSpacing: 0, children: [for (final metric in metrics) SizedBox(width: (constraints.maxWidth - 12) / 2, child: Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(metric.$3, color: Brand.teal), const SizedBox(height: 14), Text(metric.$2, style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900)), Text(metric.$1)])))])),
      Panel(child: Row(children: [SizedBox(width: 110, height: 110, child: Semantics(label: '$total candidaturas: ${manual.toInt()} manuais e ${automatic.toInt()} automáticas', child: CustomPaint(painter: _DistributionPainter(manual, automatic), child: Center(child: Text('$total', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)))))), const SizedBox(width: 20), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('Candidaturas por origem', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)), const SizedBox(height: 14), _legend('Manuais', Brand.teal), const SizedBox(height: 8), _legend('Automáticas', Brand.coral)]))])),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(children: [const Icon(Icons.auto_awesome_outlined, color: Brand.teal), const SizedBox(width: 10), const Expanded(child: Text('Compatibilidade média', style: TextStyle(fontWeight: FontWeight.w700))), Text('${data['average_match_score'] ?? 0}%', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900))]), const SizedBox(height: 14), LinearProgressIndicator(value: ((data['average_match_score'] as num? ?? 0).toDouble() / 100).clamp(0.0, 1.0).toDouble(), minHeight: 9, borderRadius: BorderRadius.circular(8)), const SizedBox(height: 10), const Text('Média das candidaturas registradas, com base nas competências declaradas.') ])),
      if (statuses.isNotEmpty) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const SectionTitle(title: 'Etapas da sua jornada'), for (final entry in statuses.entries) Padding(padding: const EdgeInsets.only(bottom: 16), child: Column(children: [Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(statusLabel(entry.key)), Text('${entry.value}', style: const TextStyle(fontWeight: FontWeight.w800))]), const SizedBox(height: 8), LinearProgressIndicator(value: total == 0 ? 0 : ((entry.value as num).toDouble() / total).clamp(0.0, 1.0).toDouble(), minHeight: 7, borderRadius: BorderRadius.circular(6))]))])),
      const SectionTitle(title: 'Atualizações das suas candidaturas', subtitle: 'Mudanças registradas pelos recrutadores. Arraste para atualizar; não são notificações push.'),
      if ((data['notifications'] as List? ?? []).isEmpty) const Panel(child: Text('Quando um recrutador atualizar uma candidatura, a novidade aparecerá aqui.')),
      for (final note in (data['notifications'] as List? ?? []))
        Panel(child: Row(children: [const Icon(Icons.notifications_active_outlined, color: Brand.teal), const SizedBox(width: 12), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${note['job_title']}', style: const TextStyle(fontWeight: FontWeight.w700)),
          Text(statusLabel('${note['status']}')), Text(formatDate(note['updated_at']), style: Theme.of(context).textTheme.bodySmall),
        ]))])),
      const SectionTitle(title: 'Histórico de candidaturas', subtitle: 'Status, data e acesso à oportunidade em um só lugar.'),
      if (_applications.isEmpty) const Panel(child: Text('Suas candidaturas aparecerão aqui. Explore as vagas e encontre seu próximo passo.')),
      for (final row in _applications) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(children: [Expanded(child: Text('${row['job_title']}', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800))), Icon(row['source'] == 'automatic' ? Icons.bolt : Icons.touch_app_outlined, color: Brand.teal)]), const SizedBox(height: 10), Wrap(spacing: 8, runSpacing: 6, children: [Chip(label: Text(statusLabel('${row['status']}')), visualDensity: VisualDensity.compact), Chip(label: Text('${row['match_score']}% de compatibilidade'), visualDensity: VisualDensity.compact)]), const SizedBox(height: 6), Text(formatDate(row['created_at']), style: Theme.of(context).textTheme.bodySmall), TextButton.icon(onPressed: () => _job(row as Map), icon: const Icon(Icons.arrow_forward), label: const Text('Ver oportunidade'))])),
      if (_hasMore) OutlinedButton(onPressed: _loadingMore ? null : _more, child: Text(_loadingMore ? 'Carregando...' : 'Ver candidaturas anteriores')),
      const SizedBox(height: 16), const SectionTitle(title: 'Relatórios de automação', subtitle: 'Transparência sobre cada busca e seus resultados.'),
      if (data['automation_unavailable'] == true) const Panel(child: Text('Os detalhes de automação estão temporariamente indisponíveis. Suas candidaturas continuam disponíveis acima.')),
      if ((data['runs'] as List).isEmpty) const Panel(child: Text('Os ciclos de busca Premium aparecerão aqui após a automação ser autorizada nas suas preferências.')),
      for (final run in data['runs']) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(children: [const Icon(Icons.radar, color: Brand.teal), const SizedBox(width: 10), Expanded(child: Text(statusLabel('${run['status']}'), style: const TextStyle(fontWeight: FontWeight.w800))), Text('${run['submitted_applications'] ?? 0} envios')]), const SizedBox(height: 10), Text(formatDate(run['started_at'])), const SizedBox(height: 6), Text('${run['scanned_jobs'] ?? 0} vagas analisadas · ${run['eligible_jobs'] ?? 0} elegíveis · ${run['manual_review_jobs'] ?? 0} para sua avaliação'), if ((run['omitted_events'] as num? ?? 0) > 0) Text('Há ${run['omitted_events']} eventos adicionais resumidos neste ciclo.'), TextButton.icon(onPressed: () => _events(run as Map), icon: const Icon(Icons.receipt_long_outlined), label: const Text('Ver detalhes do ciclo'))])),
    ]));
  });
  Widget _legend(String label, Color color) => Row(children: [Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)), const SizedBox(width: 8), Text(label)]);
}

class _DistributionPainter extends CustomPainter {
  final double manual, automatic;
  _DistributionPainter(this.manual, this.automatic);
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final ring = rect.deflate(9);
    final paint = Paint()..style = PaintingStyle.stroke..strokeWidth = 12..strokeCap = StrokeCap.round;
    canvas.drawArc(ring, 0, math.pi * 2, false, paint..color = Brand.teal.withValues(alpha: .12));
    if (manual + automatic <= 0) return;
    final sweep = manual / (manual + automatic) * math.pi * 2;
    canvas.drawArc(ring, -math.pi / 2, sweep, false, paint..color = Brand.teal);
    if (automatic > 0) canvas.drawArc(ring, -math.pi / 2 + sweep, math.pi * 2 - sweep, false, paint..color = Brand.coral);
  }
  @override
  bool shouldRepaint(covariant _DistributionPainter oldDelegate) => oldDelegate.manual != manual || oldDelegate.automatic != automatic;
}

class _RunEvents extends StatefulWidget {
  const _RunEvents({required this.api, required this.initial, required this.runId, required this.onJob});
  final Api api;
  final Map<String, dynamic> initial;
  final String runId;
  final Future<void> Function(Map row) onJob;
  @override
  State<_RunEvents> createState() => _RunEventsState();
}
class _RunEventsState extends State<_RunEvents> {
  late List<dynamic> _events;
  dynamic _next;
  bool _busy = false;
  @override
  void initState() { super.initState(); _events = List<dynamic>.from(widget.initial['items'] as List? ?? []); _next = widget.initial['next_offset']; }
  Future<void> _more() async {
    setState(() => _busy = true);
    try {
      final result = await widget.api.request('GET', '/automation/runs/${widget.runId}/events?offset=$_next&limit=50');
      if (mounted) setState(() { _events.addAll(result['items'] as List); _next = result['next_offset']; });
    } catch (error) { if (mounted) friendlyError(context, error); }
    finally { if (mounted) setState(() => _busy = false); }
  }
  @override
  Widget build(BuildContext context) => FractionallySizedBox(heightFactor: .85, child: ListView(padding: const EdgeInsets.all(24), children: [
    const SectionTitle(title: 'Detalhes da busca'),
    if (((widget.initial['run'] as Map?)?['omitted_events'] as num? ?? 0) > 0) const Padding(padding: EdgeInsets.only(bottom: 16), child: Text('Este ciclo contém muitos resultados. O histórico detalhado é limitado; os totais completos aparecem no resumo.')),
    if (_events.isEmpty) const Text('Não há eventos de candidatura neste ciclo.'),
    for (final event in _events) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${event['job_title'] ?? 'Oportunidade'}', style: Theme.of(context).textTheme.titleMedium), const SizedBox(height: 8), Text(statusLabel('${event['status']}'), style: const TextStyle(fontWeight: FontWeight.w800, color: Brand.teal)), const SizedBox(height: 8), Text('${event['detail'] ?? ''}'), Text(formatDate(event['created_at']), style: Theme.of(context).textTheme.bodySmall), if (event['job_url'] != null || event['job_id'] != null) TextButton.icon(onPressed: () => widget.onJob(event as Map), icon: const Icon(Icons.open_in_new), label: const Text('Ver oportunidade'))])),
    if (_next != null) OutlinedButton(onPressed: _busy ? null : _more, child: Text(_busy ? 'Carregando...' : 'Mais eventos')),
  ]));
}
