import 'package:flutter/material.dart';
import 'api.dart';
import 'forms.dart';
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
  int _loadVersion = 0;
  bool loading = true, loadingMore = false;
  String category = 'high';
  bool radar = false;
  Object? error;
  Map<String, dynamic> user = {}, preferences = {};
  Map<String, dynamic> collectorStatus = {};
  final Set<String> pending = {}, applied = {};
  @override
  void initState() {
    super.initState();
    load();
    _loadAccount();
  }

  Future<void> _loadAccount() async {
    try {
      final result = Map<String, dynamic>.from(
          await widget.api.request('GET', '/me') as Map);
      if (mounted)
        setState(() {
          user = result;
          preferences = Map<String, dynamic>.from(
              result['preferences'] as Map? ?? const {});
        });
    } catch (_) {}
  }

  Future<void> _editPreferences() async {
    if (user.isEmpty) await _loadAccount();
    if (!mounted) return;
    await showPreferencesSheet(context,
        api: widget.api, preferences: preferences, onSaved: () async {
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
    final version = ++_loadVersion;
    if (radar && user['is_premium'] != true) {
      if (mounted)
        setState(() {
          loading = false;
          loadingMore = false;
          items.clear();
          next = null;
          error = null;
          collectorStatus = {};
        });
      return;
    }
    setState(() {
      if (more) {
        loadingMore = true;
      } else {
        loading = true;
      }
      error = null;
    });
    try {
      final result = await widget.api.request('GET',
          '${radar ? '/radar' : '/internal-jobs'}?offset=${more ? next ?? 0 : 0}&limit=30');
      if (!mounted || version != _loadVersion) return;
      setState(() {
        if (!more) items.clear();
        items.addAll(
            (result['items'] as List).map((e) => Map<String, dynamic>.from(e)));
        next = result['next_offset'] as int?;
        collectorStatus = Map<String, dynamic>.from(
            result['collector_status'] as Map? ?? const {});
      });
    } catch (e) {
      if (mounted && version == _loadVersion) setState(() => error = e);
    } finally {
      if (mounted && version == _loadVersion)
        setState(() {
          loading = false;
          loadingMore = false;
        });
    }
  }

  Future<void> apply(Map<String, dynamic> job) async {
    if (user.isEmpty) await _loadAccount();
    if (!mounted) return;
    if (user['has_resume'] != true) {
      await requireResume(context);
      return;
    }
    final id = job['id'].toString();
    if (pending.contains(id)) return;
    // Imported external opportunities require the candidate's manual review.
    if (job['source_url'] != null &&
        job['source_url'].toString().isNotEmpty &&
        job['recruiter_id'] == null) {
      try {
        await externalLink(job['source_url']);
      } catch (e) {
        if (mounted) await friendlyError(context, e);
      }
      return;
    }
    setState(() => pending.add(id));
    try {
      final result = await widget.api.request('POST', '/jobs/$id/applications');
      if (!mounted) return;
      if (result['status'] == 'requires_manual') {
        final link = result['external_url'] ??
            result['source_url'] ??
            result['job_url'] ??
            job['source_url'];
        if (link is String && link.isNotEmpty) {
          await externalLink(link);
        }
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text(
                'Esta vaga exige candidatura no site oficial. Nenhum envio automático foi registrado.')));
        return;
      }
      setState(() => applied.add(id));
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(result['created'] == true
              ? 'Candidatura enviada. Boa sorte no próximo passo!'
              : 'Sua candidatura já estava registrada.')));
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => pending.remove(id));
    }
  }

  Future<void> details(Map<String, dynamic> item) async {
    final job = Map<String, dynamic>.from(item['job']);
    await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (context) => SafeArea(
            child: DraggableScrollableSheet(
                expand: false,
                initialChildSize: .78,
                maxChildSize: .95,
                minChildSize: .4,
                builder: (context, controller) => ListView(
                        controller: controller,
                        padding: const EdgeInsets.all(24),
                        children: [
                          SectionTitle(
                              title: job['title'],
                              subtitle:
                                  '${job['company']} · ${job['location']}'),
                          OpportunityDetails(row: {
                            ...job,
                            'match_score': item['match_score'],
                            'match_reasons': item['match_reasons']
                          }, showHeader: false, initiallyExpanded: true),
                          const SizedBox(height: 24),
                          Text('Competências da oportunidade',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 10),
                          Wrap(spacing: 8, children: [
                            for (final skill in job['keywords'] ?? [])
                              Chip(label: Text('$skill'))
                          ]),
                          if ((item['missing_skills'] as List? ?? [])
                              .isNotEmpty) ...[
                            const SizedBox(height: 18),
                            Text('O que pode fortalecer seu perfil',
                                style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            Text((item['missing_skills'] as List).join(' · ')),
                            const SizedBox(height: 8),
                            const Text(
                                'Visite a aba Cursos para encontrar trilhas relacionadas. A decisão de se candidatar é sua.')
                          ],
                          const SizedBox(height: 24),
                          FilledButton.icon(
                              onPressed: () {
                                Navigator.pop(context);
                                apply(job);
                              },
                              icon: const Icon(Icons.send_outlined),
                              label: const Text('Avaliar candidatura')),
                        ]))));
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    if (error != null && items.isEmpty)
      return EmptyState(
          icon: Icons.cloud_off_outlined,
          title: 'As oportunidades estão chegando',
          message: error is ApiException
              ? (error as ApiException).message
              : 'Não conseguimos carregar suas vagas.',
          onRetry: load);
    final visible = items
        .where((e) =>
            !radar ||
            (category == 'high'
                ? e['category'] == 'high'
                : e['category'] == 'observation'))
        .toList();
    return RefreshIndicator(
        onRefresh: load,
        child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              Row(children: [
                const Expanded(
                    child: SectionTitle(
                        title: 'Oportunidades', subtitle: 'Busca & filtros')),
                IconButton(
                    onPressed: _editPreferences,
                    tooltip: 'Editar critérios de busca',
                    icon: const Icon(Icons.tune))
              ]),
              Wrap(spacing: 8, runSpacing: 6, children: [
                for (final title
                    in (preferences['titles'] as List? ?? []).take(2))
                  Chip(
                      avatar: const Icon(Icons.work_outline, size: 16),
                      label: Text('$title')),
                for (final location
                    in (preferences['locations'] as List? ?? []).take(1))
                  Chip(
                      avatar: const Icon(Icons.location_on_outlined, size: 16),
                      label: Text('$location')),
                ActionChip(
                    onPressed: _editPreferences,
                    avatar: const Icon(Icons.tune, size: 16),
                    label: const Text('Filtros e Preferências')),
              ]),
              const SizedBox(height: 12),
              Wrap(spacing: 8, runSpacing: 8, children: [
                ChoiceChip(
                    label: const Text('Vagas no App (Empresas)'),
                    selected: !radar,
                    onSelected: (_) {
                      setState(() => radar = false);
                      load();
                    }),
                ChoiceChip(
                    label: const Text('Radar de Vagas (IA)'),
                    selected: radar,
                    onSelected: (_) async {
                      if (user.isEmpty) await _loadAccount();
                      if (!mounted) return;
                      setState(() => radar = true);
                      load();
                    }),
              ]),
              const SizedBox(height: 12),
              if (radar && user['is_premium'] != true)
                Panel(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      const Text('Radar exclusivo PRO',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      const Text(
                          'Pesquisa regional, compatibilidade e automação com seu currículo.'),
                      OutlinedButton(
                          onPressed: () async {
                            await _loadAccount();
                            if (user['is_premium'] == true) await load();
                          },
                          child: const Text('Conhecer PRO / atualizar acesso')),
                    ])),
              if (radar && user['is_premium'] == true) ...[
                FilledButton.icon(
                    onPressed: () => showAutomationPanel(context,
                        api: widget.api, onChanged: _refreshAfterAutomation),
                    icon: const Icon(Icons.bolt),
                    label: const Text('Robô de Automação')),
                const SizedBox(height: 12),
                LayoutBuilder(
                    builder: (context, constraints) => SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: SizedBox(
                            width: constraints.maxWidth < 340
                                ? 340
                                : constraints.maxWidth,
                            child: SegmentedButton<String>(
                                segments: const [
                                  ButtonSegment(
                                      value: 'high',
                                      label: Text('Match alto'),
                                      icon: Icon(Icons.bolt)),
                                  ButtonSegment(
                                      value: 'observation',
                                      label: Text('Possíveis vagas'),
                                      icon: Icon(Icons.travel_explore))
                                ],
                                selected: {
                                  category
                                },
                                onSelectionChanged: (v) =>
                                    setState(() => category = v.first))))),
              ],
              const SizedBox(height: 18),
              if (radar && category == 'observation')
                const Padding(
                    padding: EdgeInsets.only(bottom: 16),
                    child: Text(
                        'Vagas próximas do seu perfil, com 40% a 69% de compatibilidade. Conheça as lacunas e decida se faz sentido se candidatar.')),
              if (visible.isEmpty && collectorStatus['configured'] == false)
                const Panel(
                    child: Text(
                        'Configure cargo, Cidade/UF e palavras-chave nas preferências para consultar oportunidades brasileiras.')),
              if (visible.isEmpty &&
                  collectorStatus['configured'] == true &&
                  (collectorStatus['failed_sources'] as num? ?? 0) == 0)
                const Panel(
                    child: Text(
                        'As fontes consultadas não retornaram vagas aprovadas compatíveis agora. Tente novamente mais tarde ou ajuste os filtros.')),
              if (!radar && visible.isEmpty)
                const Panel(
                    child: Text(
                        'Novas vagas de empresas aparecerão aqui após aprovação. Nenhum anúncio fictício é publicado.')),
              if (radar && visible.isEmpty && user['is_premium'] == true)
                const Panel(
                    child: EmptyState(
                        icon: Icons.manage_search,
                        title: 'Vamos explorar novas possibilidades?',
                        message:
                            'Nenhuma vaga desta página se encaixa nesta categoria. Confira seus critérios no perfil ou carregue mais oportunidades.')),
              for (final item in visible) _jobCard(item),
              if ((collectorStatus['search_channels'] as List? ?? const [])
                  .isNotEmpty) ...[
                const SectionTitle(
                    title: 'Explorar portais brasileiros',
                    subtitle:
                        'Buscas com seus critérios; os resultados são conferidos no portal e não contam como vagas analisadas.'),
                for (final channel
                    in (collectorStatus['search_channels'] as List))
                  Panel(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Text('${channel['source_name'] ?? 'Portal brasileiro'}',
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        Text(
                            '${channel['query'] ?? 'Vagas'} · ${channel['location'] ?? 'Brasil'}'),
                        OpportunityDetails(row: {
                          ...Map<String, dynamic>.from(channel as Map),
                          'status': 'search_channel'
                        }, showHeader: false, showReasons: false),
                      ])),
              ],
              if (error != null)
                OutlinedButton.icon(
                    onPressed: () => load(more: true),
                    icon: const Icon(Icons.refresh),
                    label: const Text('Tentar carregar novamente')),
              if (next != null)
                OutlinedButton(
                    onPressed: loadingMore ? null : () => load(more: true),
                    child: loadingMore
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Explorar mais oportunidades')),
              const SizedBox(height: 16),
            ]));
  }

  Widget _jobCard(Map<String, dynamic> item) {
    final job = Map<String, dynamic>.from(item['job']);
    final id = job['id'].toString();
    return Panel(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          OpportunityDetails(row: {
            ...job,
            'match_score': item['match_score'],
            'match_reasons': item['match_reasons']
          }, showScore: radar),
          if (job['company_verified'] == true)
            const Chip(
                avatar: Icon(Icons.verified, size: 16),
                label: Text('Empresa Verificada')),
          if ((item['missing_skills'] as List? ?? []).isNotEmpty)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                    'Para desenvolver: ${(item['missing_skills'] as List).join(', ')}',
                    style: Theme.of(context).textTheme.bodySmall)),
          const Divider(height: 28),
          Wrap(spacing: 10, runSpacing: 8, children: [
            OutlinedButton(
                onPressed: () => details(item),
                child: const Text('Ver detalhes')),
            FilledButton.icon(
                onPressed: pending.contains(id) || applied.contains(id)
                    ? null
                    : () => apply(job),
                icon: pending.contains(id)
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.arrow_outward, size: 18),
                label: Text(applied.contains(id)
                    ? 'Enviada'
                    : job['source_url'] != null && job['recruiter_id'] == null
                        ? 'Abrir vaga'
                        : 'Candidatar-se com 1 Toque')),
          ]),
        ]));
  }
}

String modalityLabel(dynamic modality) =>
    const {
      'remote': 'Remoto',
      'hybrid': 'Híbrido',
      'onsite': 'Presencial'
    }[modality] ??
    modality.toString();
