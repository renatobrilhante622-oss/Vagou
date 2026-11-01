import 'dart:async';
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

class _JobsViewState extends State<JobsView>
    with SingleTickerProviderStateMixin {
  final List<Map<String, dynamic>> items = [];
  final _snapshots = <bool, Map<String, dynamic>>{};
  final _scroll = {false: ScrollController(), true: ScrollController()};
  late final TabController _tabs;
  int? next;
  int _loadVersion = 0, _selectionVersion = 0;
  bool loading = true, loadingMore = false, radar = false, fallback = false;
  String category = 'high';
  Object? error;
  Map<String, dynamic> user = {}, preferences = {}, collectorStatus = {};
  final Set<String> pending = {}, applied = {};
  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    load();
    _loadAccount();
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final controller in _scroll.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _selectMode(int index) async {
    final selection = ++_selectionVersion;
    if (index == 1 && user.isEmpty) await _loadAccount();
    if (!mounted || selection != _selectionVersion) return;
    setState(() {
      radar = index == 1;
      items.clear();
      final saved = _snapshots[radar];
      if (saved != null)
        items.addAll(List<Map<String, dynamic>>.from(saved['items']));
      next = saved?['next_offset'];
      collectorStatus =
          Map<String, dynamic>.from(saved?['collector_status'] ?? {});
      error = null;
      fallback = false;
    });
    await load();
  }

  Future<void> _loadAccount() async {
    try {
      final result = Map<String, dynamic>.from(await widget.api
          .request('GET', '/me')
          .timeout(const Duration(seconds: 8)) as Map);
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
    final mode = radar;
    if (mode && user['is_premium'] != true) {
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
      loading = !more;
      loadingMore = more;
      error = null;
    });
    final offset = more ? next ?? 0 : 0;
    try {
      Map<String, dynamic> result;
      bool usedFallback = false;
      try {
        result = Map<String, dynamic>.from(await widget.api
            .request('GET',
                '${mode ? '/radar' : '/internal-jobs'}?offset=$offset&limit=30')
            .timeout(const Duration(seconds: 14)) as Map);
      } catch (failure) {
        if (failure is ApiException && [401, 403].contains(failure.status))
          rethrow;
        // A failure never reclassifies external ads as official partner jobs.
        if (mode || items.isNotEmpty || version != _loadVersion) rethrow;
        final native = await widget.api
            .request('GET', '/jobs?internal_only=true&offset=$offset&limit=30')
            .timeout(const Duration(seconds: 8)) as List;
        final approved = native.whereType<Map>().where((job) =>
            job['active'] != false &&
            job['moderation_status'] == 'approved' &&
            (job['source_url'] == null || '${job['source_url']}'.isEmpty) &&
            '${job['source_name'] ?? 'Vagou!'}'.startsWith('Vagou!'));
        result = {
          'items': [
            for (final job in approved)
              {'job': Map<String, dynamic>.from(job), 'category': 'internal'}
          ],
          'next_offset': native.length == 30 ? offset + 30 : null
        };
        usedFallback = true;
      }
      if (!mounted || version != _loadVersion || mode != radar) return;
      final fetched = (result['items'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map));
      setState(() {
        if (!more) items.clear();
        for (final item in fetched) {
          final id = (item['job'] as Map)['id'];
          if (!items.any((existing) => (existing['job'] as Map)['id'] == id))
            items.add(item);
        }
        next = result['next_offset'] as int?;
        collectorStatus =
            Map<String, dynamic>.from(result['collector_status'] as Map? ?? {});
        fallback = usedFallback;
        _snapshots[mode] = {
          'items': List<Map<String, dynamic>>.from(items),
          'next_offset': next,
          'collector_status': collectorStatus
        };
      });
    } catch (failure) {
      if (mounted && version == _loadVersion && mode == radar)
        setState(() => error = failure);
    } finally {
      if (mounted && version == _loadVersion && mode == radar)
        setState(() {
          loading = false;
          loadingMore = false;
        });
    }
  }

  Future<void> apply(Map<String, dynamic> job) async {
    await _loadAccount();
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
    final job = Map<String, dynamic>.from(item['job'] as Map);
    // This route owns its scroll controller; the feed is never reloaded on close.
    await showModalBottomSheet<void>(
        context: context,
        useSafeArea: true,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (sheetContext) => DraggableScrollableSheet(
            expand: false,
            initialChildSize: .82,
            minChildSize: .4,
            maxChildSize: .96,
            builder: (sheetContext, controller) => ListView(
                    controller: controller,
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
                    children: [
                      OpportunityDetails(
                          row: {...job, 'match_score': item['match_score']},
                          initiallyExpanded: true,
                          showReasons: false,
                          showScore: radar),
                      const SizedBox(height: 16),
                      const SectionTitle(title: 'Requisitos da vaga'),
                      if ((job['keywords'] as List? ?? []).isEmpty)
                        const Text(
                            'Consulte os requisitos na descrição oficial.'),
                      Wrap(spacing: 6, runSpacing: 4, children: [
                        for (final skill in job['keywords'] ?? [])
                          Chip(label: Text('$skill'))
                      ]),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                          onPressed: pending.contains('${job['id']}') ||
                                  applied.contains('${job['id']}')
                              ? null
                              : () {
                                  Navigator.pop(sheetContext);
                                  apply(job);
                                },
                          icon: const Icon(Icons.send_outlined),
                          label: Text(applied.contains('${job['id']}')
                              ? 'Candidatura registrada'
                              : 'Candidatar-se com 1 Toque')),
                    ])));
  }

  @override
  Widget build(BuildContext context) {
    final premium = user['is_premium'] == true;
    final visible =
        items.where((item) => !radar || item['category'] == category).toList();
    return Column(children: [
      Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: TabBar(
              controller: _tabs,
              onTap: _selectMode,
              labelPadding: const EdgeInsets.symmetric(horizontal: 5),
              tabs: const [
                Tab(
                    height: 54,
                    child: Text('Vagas no App (Empresas)',
                        textAlign: TextAlign.center, maxLines: 2)),
                Tab(
                    height: 54,
                    child: Text('Radar de Vagas (IA)',
                        textAlign: TextAlign.center, maxLines: 2))
              ])),
      if (loading || loadingMore) const LinearProgressIndicator(minHeight: 2),
      Expanded(
          child: RefreshIndicator(
              onRefresh: load,
              child: ListView(
                  key: PageStorageKey('jobs-$radar'),
                  controller: _scroll[radar],
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                  children: [
                    if (radar && !premium)
                      Panel(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                            const Icon(Icons.workspace_premium_outlined,
                                color: Brand.teal),
                            const SectionTitle(
                                title: 'Radar exclusivo PRO',
                                subtitle:
                                    'Busca externa, compatibilidade e automação com seus critérios.'),
                            OutlinedButton(
                                onPressed: () async {
                                  await _loadAccount();
                                  if (user['is_premium'] == true) await load();
                                },
                                child: const Text(
                                    'Conhecer PRO / atualizar acesso')),
                          ])),
                    if (radar && premium) ...[
                      Wrap(spacing: 8, runSpacing: 8, children: [
                        ActionChip(
                            onPressed: _editPreferences,
                            avatar: const Icon(Icons.tune, size: 18),
                            label: const Text('Filtros e Preferências')),
                        ActionChip(
                            onPressed: () => showAutomationPanel(context,
                                api: widget.api,
                                onChanged: _refreshAfterAutomation),
                            avatar: const Icon(Icons.bolt, size: 18),
                            label: const Text('Robô de Automação')),
                      ]),
                      const SizedBox(height: 10),
                      Wrap(spacing: 8, children: [
                        for (final item in const [
                          ('high', 'Match Alto'),
                          ('observation', 'Possíveis Vagas')
                        ])
                          ChoiceChip(
                              selected: category == item.$1,
                              label: Text(item.$2),
                              onSelected: (_) =>
                                  setState(() => category = item.$1))
                      ]),
                      const SizedBox(height: 10),
                    ],
                    if (loading && items.isEmpty) const _FeedLoading(),
                    if (error != null)
                      Panel(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                            Text(
                                items.isEmpty
                                    ? 'Vamos reconectar suas vagas?'
                                    : 'Exibindo a última consulta desta sessão.',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            const SizedBox(height: 6),
                            Text(error is ApiException
                                ? (error as ApiException).message
                                : 'A consulta demorou ou o serviço está temporariamente indisponível.'),
                            TextButton.icon(
                                onPressed: loading ? null : load,
                                icon: const Icon(Icons.refresh),
                                label: const Text('Tentar novamente')),
                          ])),
                    if (fallback && error == null)
                      const Padding(
                          padding: EdgeInsets.only(bottom: 8),
                          child: Text(
                              'Vagas oficiais recuperadas pelo catálogo de contingência.')),
                    if (!loading &&
                        visible.isEmpty &&
                        error == null &&
                        (!radar || premium))
                      Panel(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                            Icon(radar ? Icons.radar : Icons.business_outlined,
                                color: Brand.teal),
                            SectionTitle(
                                title: radar
                                    ? 'Nenhum resultado nesta categoria'
                                    : 'Nenhuma vaga oficial aprovada disponível',
                                subtitle: radar
                                    ? 'Ajuste os filtros ou consulte os canais oficiais abaixo.'
                                    : 'As vagas de empresas parceiras aparecem após aprovação. Você pode atualizar a lista ou explorar o Radar.'),
                            Wrap(spacing: 8, children: [
                              OutlinedButton(
                                  onPressed: load,
                                  child: const Text('Atualizar vagas')),
                              if (!radar)
                                TextButton(
                                    onPressed: () {
                                      _tabs.animateTo(1);
                                      _selectMode(1);
                                    },
                                    child: const Text('Explorar Radar')),
                              if (radar)
                                TextButton(
                                    onPressed: _editPreferences,
                                    child: const Text('Ajustar filtros'))
                            ]),
                          ])),
                    for (final item in visible) _jobCard(item),
                    if (radar &&
                        premium &&
                        (collectorStatus['search_channels'] as List? ?? [])
                            .isNotEmpty) ...[
                      const SectionTitle(
                          title: 'Canais oficiais de pesquisa',
                          subtitle:
                              'Links de busca; não representam anúncios confirmados.'),
                      for (final channel
                          in collectorStatus['search_channels'] as List)
                        Panel(
                            child: ListTile(
                                contentPadding: EdgeInsets.zero,
                                title: Text('${channel['source_name']}'),
                                subtitle:
                                    Text('${channel['location'] ?? 'Brasil'}'),
                                trailing: const Icon(Icons.open_in_new),
                                onTap: () async {
                                  try {
                                    await externalLink(
                                        '${channel['external_url']}');
                                  } catch (e) {
                                    if (context.mounted)
                                      await friendlyError(context, e);
                                  }
                                })),
                    ],
                    if (next != null && (!radar || premium))
                      OutlinedButton(
                          onPressed: loading || loadingMore
                              ? null
                              : () => load(more: true),
                          child: const Text('Explorar mais oportunidades')),
                  ]))),
    ]);
  }

  Widget _jobCard(Map<String, dynamic> item) => OpportunitySummary(
      key: ValueKey('job-${item['job']['id']}'),
      row: {
        ...Map<String, dynamic>.from(item['job'] as Map),
        'match_score': item['match_score']
      },
      onTap: () => details(item));
}

class _FeedLoading extends StatelessWidget {
  const _FeedLoading();
  @override
  Widget build(BuildContext context) => Column(children: [
        const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('Consultando oportunidades…')),
        for (var i = 0; i < 3; i++)
          Panel(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Container(
                    height: 14,
                    width: 140,
                    color:
                        Theme.of(context).colorScheme.surfaceContainerHighest),
                const SizedBox(height: 12),
                Container(
                    height: 18,
                    width: double.infinity,
                    color:
                        Theme.of(context).colorScheme.surfaceContainerHighest),
                const SizedBox(height: 10),
                Container(
                    height: 12,
                    width: 190,
                    color:
                        Theme.of(context).colorScheme.surfaceContainerHighest),
              ])),
      ]);
}

String modalityLabel(dynamic modality) =>
    const {
      'remote': 'Remoto',
      'hybrid': 'Híbrido',
      'onsite': 'Presencial'
    }[modality] ??
    modality.toString();
