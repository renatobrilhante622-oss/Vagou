import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';

class CoursesView extends StatefulWidget {
  const CoursesView({super.key, required this.api});
  final Api api;
  @override
  State<CoursesView> createState() => _CoursesViewState();
}

class _CoursesViewState extends State<CoursesView> {
  late Future<dynamic> _data;
  @override
  void initState() { super.initState(); _reload(); }
  void _reload() { _data = widget.api.request('GET', '/courses'); }
  Future<void> _open(Map<String, dynamic> course) async {
    await showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true, builder: (sheetContext) => FractionallySizedBox(heightFactor: .88, child: SingleChildScrollView(padding: const EdgeInsets.fromLTRB(24, 4, 24, 32), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: Brand.teal.withValues(alpha: .10), borderRadius: BorderRadius.circular(18)), child: const Icon(Icons.school_rounded, color: Brand.teal, size: 32)),
      const SizedBox(height: 18), Text('${course['provider']}', style: const TextStyle(color: Brand.teal, fontWeight: FontWeight.w800)), const SizedBox(height: 8),
      Text('${course['title']}', style: Theme.of(sheetContext).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 20), Text('${course['summary'] ?? 'Explore a formação no catálogo oficial e escolha um percurso alinhado às suas competências e objetivos profissionais.'}'),
      const SizedBox(height: 24), const SectionTitle(title: 'O que você pode desenvolver'),
      for (final objective in (course['objectives'] as List? ?? ['Desenvolver competências relacionadas a ${(course['skills'] as List? ?? []).join(', ')}.', 'Conectar o aprendizado a situações práticas da sua área.'])) Padding(padding: const EdgeInsets.only(bottom: 12), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [const Icon(Icons.check_circle_outline, color: Brand.teal, size: 20), const SizedBox(width: 10), Expanded(child: Text('$objective'))])),
      const SizedBox(height: 16), Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Row(children: [Icon(Icons.trending_up, color: Brand.teal), SizedBox(width: 10), Text('Impacto na sua carreira', style: TextStyle(fontWeight: FontWeight.w800))]), const SizedBox(height: 12), Text('${course['career_impact'] ?? 'Pode apoiar o desenvolvimento das competências identificadas nas suas vagas em observação. O resultado depende da prática e das exigências de cada oportunidade.'}'), const SizedBox(height: 16), const Text('Valor para o currículo', style: TextStyle(fontWeight: FontWeight.w800)), const SizedBox(height: 8), Text('${course['resume_value'] ?? 'Inclua a formação concluída, a instituição e as competências efetivamente desenvolvidas. Só informe certificado quando ele for emitido pela instituição.'}') ])),
      const SizedBox(height: 8), Row(crossAxisAlignment: CrossAxisAlignment.start, children: [const Icon(Icons.verified_outlined, size: 20), const SizedBox(width: 10), Expanded(child: Text('${course['certificate'] ?? 'Consulte as regras de conclusão e certificação no site oficial.'}', style: Theme.of(sheetContext).textTheme.bodySmall))]),
      const SizedBox(height: 24), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: () async { try { await externalLink('${course['url']}'); } catch (error) { if (sheetContext.mounted) friendlyError(sheetContext, error); } }, icon: const Icon(Icons.open_in_new), label: const Text('Conhecer no site oficial'))),
      const SizedBox(height: 10), const Text('Você será direcionado à instituição. A disponibilidade, a gratuidade e a certificação seguem as regras de cada oferta.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12)),
    ]))));
  }
  @override
  Widget build(BuildContext context) => FutureBuilder<dynamic>(future: _data, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return EmptyState(icon: Icons.school_outlined, title: 'Seus próximos aprendizados', message: 'Não foi possível carregar as formações agora.', onRetry: () => setState(_reload));
    final courses = snapshot.data as List? ?? [];
    if (courses.isEmpty) return const EmptyState(icon: Icons.school_outlined, title: 'Novas formações em breve', message: 'Volte mais tarde para explorar oportunidades de aprendizado.');
    return RefreshIndicator(onRefresh: () async { setState(_reload); await _data; }, child: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
      const SectionTitle(title: 'Seu próximo nível', subtitle: 'Aprenda com instituições reconhecidas e fortaleça seu perfil.'),
      for (final entry in courses) InkWell(borderRadius: BorderRadius.circular(24), onTap: () => _open(Map<String, dynamic>.from(entry as Map)), child: Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [Container(padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: Brand.teal.withValues(alpha: .1), borderRadius: BorderRadius.circular(14)), child: const Icon(Icons.auto_stories_outlined, color: Brand.teal)), const SizedBox(width: 12), Expanded(child: Text('${entry['provider']}', style: const TextStyle(color: Brand.teal, fontWeight: FontWeight.w700))), const Icon(Icons.arrow_forward_rounded)]),
        const SizedBox(height: 16), Text('${entry['title']}', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)), const SizedBox(height: 12),
        Wrap(spacing: 6, runSpacing: 6, children: [for (final skill in (entry['skills'] as List? ?? [])) Chip(label: Text('$skill'), visualDensity: VisualDensity.compact)]),
        const SizedBox(height: 8), const Text('Veja os objetivos, o impacto profissional e as regras de certificado.'),
      ]))),
    ]));
  });
}
