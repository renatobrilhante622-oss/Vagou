import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/api.dart';
import 'package:vagou/jobs.dart';
import 'package:vagou/opportunity_details.dart';
import 'package:vagou/reporting.dart';
import 'package:vagou/ui.dart';

const description =
    'Atenda chamados de usuários, investigue incidentes de rede e acompanhe os sistemas corporativos. '
    'Requisitos: suporte técnico, comunicação clara e conhecimento de redes. Benefícios e condições devem ser confirmados no anúncio oficial.';
const contact = 'selecao.suporte.brasilia@empresa-exemplo.com.br';
const opportunity = {
  'job_id': 'brasilia-support',
  'job_title': 'Analista de Suporte e Sistemas N2',
  'company_name': 'Empresa Brasileira de Tecnologia',
  'city': 'Brasília',
  'state': 'DF',
  'location': 'Brasília / DF',
  'source_name': 'Gupy',
  'match_score': 55,
  'status': 'possible_match',
  'salary_min': 3000,
  'salary_max': 4500,
  'modality': 'hybrid',
  'contract_type': 'clt',
  'description': description,
  'contact_email': contact,
  'external_url': 'https://example.com/vagas/suporte-brasilia',
  'match_reasons': [
    'Competências próximas do perfil.',
    'Competências próximas do perfil.'
  ],
  'detail':
      'Competências próximas do perfil.; Competências próximas do perfil.',
};

http.Response response(Object value) => http.Response(jsonEncode(value), 200,
    headers: {'content-type': 'application/json'});

void viewport(WidgetTester tester, double width) {
  tester.view.physicalSize = Size(width, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  test('salary ranges use Brazilian formatting and collapse equal values', () {
    expect(
        opportunitySalary(
            {...opportunity, 'salary_min': 1750.0, 'salary_max': 1750}),
        'R\$ 1.750');
    expect(
        opportunitySalary(
            {...opportunity, 'salary_min': 2500, 'salary_max': 3500}),
        'R\$ 2.500 a R\$ 3.500');
  });

  test('repeated reasons and historical detail become a single explanation',
      () {
    expect(
        uniqueOpportunityReasons(opportunity['match_reasons'],
            detail: '${opportunity['detail']}'),
        ['Competências próximas do perfil.']);
    expect(
        uniqueOpportunityReasons(['Conhecimento de .NET.', 'Cargo diferente.'],
            detail:
                'Conhecimento de .NET.; Cargo diferente.; Confirme a inscrição no portal.'),
        [
          'Conhecimento de .NET.',
          'Cargo diferente.',
          'Confirme a inscrição no portal.'
        ]);
  });

  for (final width in [320.0, 430.0]) {
    testWidgets(
        'rich opportunity supports description and email copy at ${width.toInt()}px',
        (tester) async {
      viewport(tester, width);
      String? copied;
      tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.setData')
          copied = (call.arguments as Map)['text'] as String;
        return null;
      });
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null));
      await tester.pumpWidget(MaterialApp(
          theme: Brand.theme(Brightness.light),
          home: Scaffold(
              body: ListView(
            padding: const EdgeInsets.all(20),
            children: const [
              Panel(child: OpportunityDetails(row: opportunity))
            ],
          ))));
      await tester.pumpAndSettle();
      expect(find.text('Empresa Brasileira de Tecnologia · Brasília / DF'),
          findsOneWidget);
      expect(find.text('55% de compatibilidade'), findsOneWidget);
      expect(find.text('R\$ 3.000 a R\$ 4.500'), findsOneWidget);
      expect(find.text('Híbrido'), findsOneWidget);
      expect(find.text('CLT'), findsOneWidget);
      expect(find.text('Competências próximas do perfil.'), findsOneWidget);
      expect(tester.widget<Text>(find.text(description)).maxLines, 3);
      await tester.ensureVisible(find.text('Expandir resumo'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Expandir resumo'));
      await tester.pumpAndSettle();
      expect(tester.widget<Text>(find.text(description)).maxLines, isNull);
      await tester.ensureVisible(find.text('Copiar e-mail'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Copiar e-mail'));
      await tester.pumpAndSettle();
      expect(copied, contact);
      expect(find.text(contact), findsOneWidget);
      expect(find.text('Abrir link oficial'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets(
      'possible feed retains Brazilian metadata without a technical source warning at 320px',
      (tester) async {
    viewport(tester, 320);
    final api = Api(client: MockClient((request) async {
      if (request.url.path == '/v1/me')
        return response({'preferences': {}, 'is_premium': true});
      if (request.url.path == '/v1/internal-jobs')
        return response({'items': [], 'next_offset': null});
      if (request.url.path == '/v1/radar')
        return response({
          'items': [
            {
              'category': 'observation',
              'match_score': 55,
              'missing_skills': [],
              'match_reasons': opportunity['match_reasons'],
              'job': {
                ...opportunity,
                'id': 'brasilia-support',
                'title': opportunity['job_title'],
                'company': opportunity['company_name'],
                'source_url': opportunity['external_url']
              }
            }
          ],
          'next_offset': null,
          'collector_status': {'configured': true, 'failed_sources': 1},
        });
      throw StateError('Unexpected request ${request.url}');
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: Scaffold(body: JobsView(api: api, onUserChanged: () async {}))));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Radar de Vagas (IA)'));
    await tester.tap(find.text('Radar de Vagas (IA)'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Possíveis vagas'));
    await tester.tap(find.text('Possíveis vagas'));
    await tester.pumpAndSettle();
    expect(find.textContaining('fonte(s) externa(s) não responderam'),
        findsNothing);
    await tester.scrollUntilVisible(find.text('📧 E-mail RH'), 250,
        scrollable: find.byType(Scrollable).first);
    expect(find.text(contact), findsOneWidget);
    expect(find.text('Competências próximas do perfil.'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'reports deduplicate the same possible vacancy across rounds and retain rich metadata at 320px',
      (tester) async {
    viewport(tester, 320);
    final api = Api(client: MockClient((request) async {
      final path = request.url.path;
      if (path == '/v1/dashboard')
        return response({
          'total_applications': 0,
          'manual': 0,
          'automatic': 0,
          'by_status': {}
        });
      if (path == '/v1/applications' || path == '/v1/notifications')
        return response([]);
      if (path == '/v1/automation/runs')
        return response({
          'items': [
            {'id': 'r1'},
            {'id': 'r2'}
          ]
        });
      if (path.endsWith('/events'))
        return response({
          'items': [opportunity]
        });
      throw StateError('Unexpected request ${request.url}');
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: Scaffold(body: ReportsView(api: api))));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
        find.text('Analista de Suporte e Sistemas N2'), 350,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Analista de Suporte e Sistemas N2'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('📧 E-mail RH'), 250,
        scrollable: find.byType(Scrollable).first);
    expect(find.text(contact), findsOneWidget);
    expect(find.text('Competências próximas do perfil.'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
