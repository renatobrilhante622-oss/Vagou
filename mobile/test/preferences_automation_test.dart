import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/api.dart';
import 'package:vagou/automation_panel.dart';
import 'package:vagou/candidate.dart';
import 'package:vagou/preferences.dart';
import 'package:vagou/ui.dart';

http.Response jsonResponse(Object body) => http.Response(jsonEncode(body), 200,
    headers: {'content-type': 'application/json'});

void main() {
  testWidgets('profile keeps preferences out and refreshes access independently', (tester) async {
    final requests = <http.Request>[];
    final api = Api(client: MockClient((request) async {
      requests.add(request);
      return jsonResponse({'is_premium': true, 'plan': 'premium', 'automation_enabled': false});
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(theme: Brand.theme(Brightness.light), home: Scaffold(body: CandidateProfile(
      api: api,
      user: {'id': '1', 'email': 'candidate@example.com', 'name': 'Candidato', 'skills': [], 'is_premium': false, 'has_resume': false},
      onChanged: () async {},
    ))));

    expect(find.text('Filtros e Preferências'), findsNothing);
    expect(find.text('Meu Plano'), findsOneWidget);
    await tester.ensureVisible(find.text('Atualizar meu acesso'));
    await tester.tap(find.text('Atualizar meu acesso'));
    await tester.pumpAndSettle();
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/v1/candidate/entitlements');
    expect(find.text('Premium Ativo'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('city and state-only preference save succeeds with optional filters empty', (tester) async {
    Map<String, dynamic>? saved;
    final api = Api(client: MockClient((request) async {
      if (request.method == 'PUT' && request.url.path == '/v1/me/preferences') {
        saved = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse(saved!);
      }
      return jsonResponse({});
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(theme: Brand.theme(Brightness.light), home: Builder(builder: (context) => Scaffold(
      body: Center(child: FilledButton(onPressed: () => showPreferencesSheet(context,
        api: api, preferences: const {}, onSaved: () async {}), child: const Text('Abrir filtros'))),
    ))));
    await tester.tap(find.text('Abrir filtros'));
    await tester.pumpAndSettle();
    final city = find.byWidgetPredicate((widget) => widget is TextField && widget.decoration?.labelText == 'Cidade');
    await tester.enterText(city, 'Recife');
    await tester.ensureVisible(find.text('Salvar preferências'));
    await tester.tap(find.text('Salvar preferências'));
    await tester.pumpAndSettle();

    expect(saved?['locations'], ['Recife']);
    expect(saved?['titles'], isEmpty);
    expect(saved?['modalities'], isEmpty);
    expect(saved?['min_salary'], 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('automation panel displays run progress from the status endpoint', (tester) async {
    const runId = 'c0ffee00-0000-4000-8000-000000000001';
    final requests = <String>[];
    final api = Api(client: MockClient((request) async {
      requests.add('${request.method} ${request.url.path}');
      if (request.url.path == '/v1/me') {
        return jsonResponse({'is_premium': true, 'automation_enabled': true, 'has_resume': true,
          'preferences': {'titles': ['Analista'], 'locations': ['Recife / PE'], 'modalities': ['onsite']}});
      }
      if (request.url.path == '/v1/automation/runs') return jsonResponse({'items': []});
      if (request.method == 'POST' && request.url.path == '/v1/automation/run') return jsonResponse({'run_id': runId});
      if (request.url.path == '/v1/automation/runs/$runId/status') {
        return jsonResponse({'id': runId, 'status': 'complete', 'scanned_jobs': 8, 'filtered_jobs': 5,
          'eligible_jobs': 3, 'submitted_applications': 2, 'manual_review_jobs': 1, 'progress': {}});
      }
      if (request.url.path == '/v1/automation/runs/$runId/events') return jsonResponse({'items': []});
      return jsonResponse({});
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(theme: Brand.theme(Brightness.light), home: Builder(builder: (context) => Scaffold(
      body: Center(child: FilledButton(onPressed: () => showAutomationPanel(context, api: api, onChanged: () async {}), child: const Text('Abrir robô'))),
    ))));
    await tester.tap(find.text('Abrir robô'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Iniciar Varredura e Envio Agora'));
    await tester.tap(find.text('Iniciar Varredura e Envio Agora'));
    await tester.pumpAndSettle();

    expect(requests, contains('POST /v1/automation/run'));
    expect(requests, contains('GET /v1/automation/runs/$runId/status'));
    expect(find.textContaining('8 analisadas · 5 descartadas · 3 compatíveis · 2 candidaturas · 1 para sua avaliação'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}