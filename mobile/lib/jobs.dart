import 'package:flutter/material.dart';
import 'api.dart';
import 'automation_panel.dart';
import 'opportunity_details.dart';
import 'preferences.dart';
import 'ui.dart';

class JobsView extends StatefulWidget {
  final Api api;
  final Future<void> Function() onUserChanged;
  const JobsView({super.key, required this.api, required this.onUserChanged});
  @override
  State<JobsView> createState() => _JobsViewState();
}
class _JobsViewState extends State<JobsView> {
  final List<Map<String, dynamic>> items = [];
  int? next;
  bool loading = true, loadingMore = false;
  String category = 'high';
  Object? error;
  Map<String, dynamic> user = {}, preferences = {};
  Map<String, dynamic> collectorStatus = {};
  final Set<String> pending = {}, applied = {};
  @override
  void initState() { super.initState(); load(); _loadAccount(); }

  Future<void> _loadAccount() async {
    try {
      final result = Map<String, dynamic>.from(await widget.api.request('GET', '/me') as Map);
      if (mounted) setState(() { user = result; preferences = Map<String, dynamic>.from(result['preferences'] as Map? ?? const {}); });
    } catch (_) { }
  }

  Future<void> _editPreferences() async {
    if (user.isEmpty) await _loadAccount();
    if (!mounted) return;
    await showPreferencesSheet(context, api: widget.api, preferences: preferences, onSaved: () async {
      await _loadAccount();
      await load();
      await widget.onUserChanged();
    });
  }

  Future<void> _refreshAfterAutomation() async {
    await _loadAccount();
    await load();
    await widget.onUserChanged();
  }
  Future<void> load({bool more = false}) async {
    setState(() { if (more) { loadingMore = true; } else { loading = true; } error = null; });
    try {
      final result = await widget.api.request('GET', '/matches?offset=${more ? next ?? 0 : 0}&limit=30');
      if (!mounted) return;
      setState(() {
        if (!more) items.clear();
        items.addAll((result['items'] as List).map((e) => Map<String, dynamic>.from(e)));
        next = result['next_offset'] as int?;
        collectorStatus = Map<String, dynamic>.from(result['collector_status'] as Map? ?? const {});
      });
    } catch (e) { if (mounted) setState(() => error = e); }
    finally { if (mounted) setState(() { loading = false; loadingMore = false; }); }
  }
  Future<void> apply(Map<String, dynamic> job) async {
    final id = job['id'].toString();
    if (pending.contains(id)) return;
    // Imported external opportunities require the candidate's manual review.
    if (job['source_url'] != null && job['source_url'].toString().isNotEmpty && job['recruiter_id'] == null) {
      try { await externalLink(job['source_url']); }
      catch (e) { if (mounted) await friendlyError(context, e); }
      return;
    }
    setState(() => pending.add(id));
    try {
      final result = await widget.api.request('POST', '/jobs/$id/applications');
      if (!mounted) return;
      if (result['status'] == 'requires_manual') {
        final link = result['external_url'] ?? result['source_url'] ?? result['job_url'] ?? job['source_url'];
        if (link is String && link.isNotEmpty) { await externalLink(link); }
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Esta vaga exige candidatura no site oficial. Nenhum envio automático foi registrado.')));
        return;
      }
      setState(() => applied.add(id));
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result['created'] == true ? 'Candidatura enviada. Boa sorte no próximo passo!' : 'Sua candidatura já estava registrada.')));
    } catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => pending.remove(id)); }
  }
  Future<void> details(Map<String, dynamic> item) async {
    final job = Map<String, dynamic>.from(item['job']);
    await showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, builder: (context) => SafeArea(child: DraggableScrollableSheet(expand: false, initialChildSize: .78, maxChildSize: .95, minChildSize: .4, builder: (context, controller) => ListView(controller: controller, padding: const EdgeInsets.all(24), children: [
      SectionTitle(title: job['title'], subtitle: '${job['company']} · ${job['location']}'),
      OpportunityDetails(row: {...job, 'match_score': item['match_score'], 'match_reasons': item['match_reasons']}, showHeader: false, initiallyExpanded: true),
      const SizedBox(height: 24), Text('Competências da oportunidade', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 10), Wrap(spacing: 8, children: [for (final skill in job['keywords'] ?? []) Chip(label: Text('$skill'))]),
      if ((item['missing_skills'] as List? ?? []).isNotEmpty) ...[const SizedBox(height: 18), Text('O que pode fortalecer seu perfil', style: Theme.of(context).textTheme.titleMedium), const SizedBox(height: 8), Text((item['missing_skills'] as List).join(' · ')), const SizedBox(height: 8), const Text('Visite a aba Cursos para encontrar trilhas relacionadas. A decisão de se candidatar é sua.')],
      const SizedBox(height: 24), FilledButton.icon(onPressed: () { Navigator.pop(context); apply(job); }, icon: const Icon(Icons.send_outlined), label: const Text('Avaliar candidatura')),
    ]))));
  }
  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null && items.isEmpty) return EmptyState(icon: Icons.cloud_off_outlined, title: 'As oportunidades estão chegando', message: error is ApiException ? (error as ApiException).message : 'Não conseguimos carregar suas vagas.', onRetry: load);
    final visible = items.where((e) => category == 'high' ? e['category'] == 'high' : e['category'] == 'observation').toList();
    return RefreshIndicator(onRefresh: load, child: ListView(padding: const EdgeInsets.all(20), physics: const AlwaysScrollableScrollPhysics(), children: [
      Wrap(spacing: 10, runSpacing: 8, children: [
        OutlinedButton.icon(onPressed: _editPreferences, icon: const Icon(Icons.tune), label: const Text('Filtros e Preferências')),
        FilledButton.icon(onPressed: () => showAutomationPanel(context, api: widget.api, onChanged: _refreshAfterAutomation), icon: const Icon(Icons.bolt), label: const Text('Automação Premium ⚡')),
      ]),
      const SizedBox(height: 12),
      const SectionTitle(title: 'Seu próximo capítulo', subtitle: 'Oportunidades alinhadas às competências e aos critérios do seu perfil.'),
      LayoutBuilder(builder: (context, constraints) => SingleChildScrollView(scrollDirection: Axis.horizontal, child: SizedBox(width: constraints.maxWidth < 340 ? 340 : constraints.maxWidth, child: SegmentedButton<String>(segments: const [ButtonSegment(value: 'high', label: Text('Match alto'), icon: Icon(Icons.bolt)), ButtonSegment(value: 'observation', label: Text('Possíveis vagas'), icon: Icon(Icons.travel_explore))], selected: {category}, onSelectionChanged: (v) => setState(() => category = v.first))))),
      const SizedBox(height: 18),
      if (category == 'observation') const Padding(padding: EdgeInsets.only(bottom: 16), child: Text('Vagas próximas do seu perfil, com 40% a 69% de compatibilidade. Conheça as lacunas e decida se faz sentido se candidatar.')),
      if (visible.isEmpty && collectorStatus['configured'] == false) const Panel(child: Text('Configure cargo, Cidade/UF e palavras-chave nas preferências para consultar oportunidades brasileiras.')),
      if (visible.isEmpty && collectorStatus['configured'] == true && (collectorStatus['failed_sources'] as num? ?? 0) == 0) const Panel(child: Text('As fontes consultadas não retornaram vagas aprovadas compatíveis agora. Tente novamente mais tarde ou ajuste os filtros.')),
      if (visible.isEmpty) const Panel(child: EmptyState(icon: Icons.manage_search, title: 'Vamos explorar novas possibilidades?', message: 'Nenhuma vaga desta página se encaixa nesta categoria. Confira seus critérios no perfil ou carregue mais oportunidades.')),
      for (final item in visible) _jobCard(item),
      if ((collectorStatus['search_channels'] as List? ?? const []).isNotEmpty) ...[
        const SectionTitle(title: 'Explorar portais brasileiros', subtitle: 'Buscas com seus critérios; os resultados são conferidos no portal e não contam como vagas analisadas.'),
        for (final channel in (collectorStatus['search_channels'] as List)) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${channel['source_name'] ?? 'Portal brasileiro'}', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          Text('${channel['query'] ?? 'Vagas'} · ${channel['location'] ?? 'Brasil'}'),
          OpportunityDetails(row: {...Map<String, dynamic>.from(channel as Map), 'status': 'search_channel'}, showHeader: false, showReasons: false),
        ])),
      ],
      if (error != null) OutlinedButton.icon(onPressed: () => load(more: true), icon: const Icon(Icons.refresh), label: const Text('Tentar carregar novamente')),
      if (next != null) OutlinedButton(onPressed: loadingMore ? null : () => load(more: true), child: loadingMore ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Explorar mais oportunidades')),
      const SizedBox(height: 16),
    ]));
  }
  Widget _jobCard(Map<String, dynamic> item) {
    final job = Map<String, dynamic>.from(item['job']);
    final id = job['id'].toString();
    return Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [CircleAvatar(backgroundColor: Brand.teal.withValues(alpha: .12), child: const Icon(Icons.business_outlined, color: Brand.teal)), const SizedBox(width: 12), Expanded(child: Text(job['company'], style: Theme.of(context).textTheme.titleMedium)), Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7), decoration: BoxDecoration(color: Brand.teal.withValues(alpha: .1), borderRadius: BorderRadius.circular(10)), child: Text('${item['match_score']}%', style: const TextStyle(color: Brand.teal, fontWeight: FontWeight.w800)))]),
      const SizedBox(height: 18), Text(job['title'], style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
      OpportunityDetails(row: {...job, 'match_reasons': item['match_reasons']}, showHeader: false, showScore: false),
      if ((item['missing_skills'] as List? ?? []).isNotEmpty) Padding(padding: const EdgeInsets.only(top: 12), child: Text('Para desenvolver: ${(item['missing_skills'] as List).join(', ')}', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant))),
      const SizedBox(height: 16), Row(children: [Expanded(child: OutlinedButton(onPressed: () => details(item), child: const Text('Ver detalhes'))), const SizedBox(width: 12), Expanded(child: FilledButton(onPressed: pending.contains(id) || applied.contains(id) ? null : () => apply(job), child: pending.contains(id) ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : Text(applied.contains(id) ? 'Enviada' : job['source_url'] != null && job['recruiter_id'] == null ? 'Abrir vaga' : 'Candidatar')))]),
    ]));
  }
}

String modalityLabel(dynamic modality) => const {'remote': 'Remoto', 'hybrid': 'Híbrido', 'onsite': 'Presencial'}[modality] ?? modality.toString();
