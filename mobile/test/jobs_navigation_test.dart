import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/api.dart';
import 'package:vagou/jobs.dart';
import 'package:vagou/home.dart';
import 'package:vagou/access.dart';
import 'package:vagou/recruiter.dart';
import 'package:vagou/resume.dart';
import 'package:vagou/ui.dart';

Map<String, dynamic> job(int index) => {
      'id': 'job-$index',
      'title': 'Analista de Suporte $index',
      'company': 'Empresa Parceira $index',
      'description':
          'Descrição completa de suporte técnico, com redes e atendimento de chamados.',
      'keywords': ['Windows', 'Redes'],
      'location': 'Brasília / DF',
      'modality': 'onsite',
      'salary_min': 3500,
      'salary_max': 3500,
      'active': true,
      'moderation_status': 'approved',
      'source_name': 'Vagou!',
    };
http.Response jsonResponse(Object value) =>
    http.Response(jsonEncode(value), 200,
        headers: {'content-type': 'application/json'});
void viewport(WidgetTester tester, double width) {
  tester.view.physicalSize = Size(width, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Widget app(Api api) => MaterialApp(
    theme: Brand.theme(Brightness.light),
    home: Scaffold(body: JobsView(api: api, onUserChanged: () async {})));

void main() {
  for (final width in [320.0, 360.0]) {
    testWidgets('details preserve scroll and requests at ${width.toInt()}px',
        (tester) async {
      viewport(tester, width);
      var calls = 0;
      final api = Api(client: MockClient((request) async {
        if (request.url.path == '/v1/me')
          return jsonResponse({'is_premium': true, 'has_resume': true});
        calls++;
        return jsonResponse({
          'items': [
            for (var i = 0; i < 20; i++) {'job': job(i), 'category': 'internal'}
          ]
        });
      }));
      addTearDown(api.client.close);
      await tester.pumpWidget(app(api));
      await tester.pumpAndSettle();
      final feed = find.byKey(const PageStorageKey('jobs-false'));
      await tester.scrollUntilVisible(find.text('Analista de Suporte 8'), 300,
          scrollable: find
              .descendant(of: feed, matching: find.byType(Scrollable))
              .first);
      await tester.ensureVisible(find.text('Analista de Suporte 8'));
      await tester.pumpAndSettle();
      final before = tester.widget<ListView>(feed).controller!.offset;
      expect(before, greaterThan(0));
      expect(find.text(job(8)['description']), findsNothing);
      expect(find.text('Candidatar-se com 1 Toque'), findsNothing);
      await tester.tap(find.text('Analista de Suporte 8'));
      await tester.pumpAndSettle();
      expect(find.byType(BottomSheet), findsOneWidget);
      expect(find.text(job(8)['description']), findsOneWidget);
      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();
      expect(tester.widget<ListView>(feed).controller!.offset,
          closeTo(before, .1));
      expect(calls, 1);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
  testWidgets(
      'official contingency excludes external ads and keeps tabs accessible',
      (tester) async {
    viewport(tester, 320);
    final api = Api(client: MockClient((request) async {
      if (request.url.path == '/v1/me')
        return jsonResponse({'is_premium': false});
      if (request.url.path == '/v1/internal-jobs')
        return http.Response('{}', 503);
      expect(request.url.queryParameters['internal_only'], 'true');
      return jsonResponse([
        job(1),
        {
          ...job(2),
          'source_name': 'External Portal',
          'source_url': 'https://example.com/vaga'
        }
      ]);
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(app(api));
    await tester.pumpAndSettle();
    expect(find.text('Analista de Suporte 1'), findsOneWidget);
    expect(find.text('Analista de Suporte 2'), findsNothing);
    await tester.tap(find.text('Radar de Vagas (IA / VIP)'));
    await tester.pumpAndSettle();
    expect(find.text('Radar exclusivo PRO'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'a stalled primary feed times out and recovers through contingency',
      (tester) async {
    viewport(tester, 320);
    final stalled = Completer<http.Response>();
    final api = Api(client: MockClient((request) {
      if (request.url.path == '/v1/me')
        return Future.value(jsonResponse({'is_premium': false}));
      if (request.url.path == '/v1/internal-jobs') return stalled.future;
      return Future.value(jsonResponse([job(1)]));
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(app(api));
    await tester.pump();
    expect(find.text('Vagas no App (Oficiais)'), findsOneWidget);
    await tester.pump(const Duration(seconds: 15));
    await tester.pumpAndSettle();
    expect(find.text('Analista de Suporte 1'), findsOneWidget);
    expect(find.text('Consultando oportunidades…'), findsNothing);
    stalled.complete(jsonResponse({'items': []}));
    await tester.pumpAndSettle();
    expect(find.text('Analista de Suporte 1'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('refresh failure retains the real session snapshot',
      (tester) async {
    viewport(tester, 320);
    var calls = 0;
    final api = Api(client: MockClient((request) async {
      if (request.url.path == '/v1/me')
        return jsonResponse({'is_premium': true});
      calls++;
      return calls == 1
          ? jsonResponse({
              'items': [
                {'job': job(1), 'category': 'internal'}
              ]
            })
          : http.Response('{}', 503);
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(app(api));
    await tester.pumpAndSettle();
    unawaited(tester
        .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
        .show());
    await tester.pumpAndSettle();
    expect(find.text('Analista de Suporte 1'), findsOneWidget);
    expect(
        find.text('Exibindo a última consulta desta sessão.'), findsOneWidget);
    expect(calls, 2);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  test(
      'contact intents contain the candidate and vacancy and preserve encoding',
      () {
    final candidate = {
      'candidate_name': 'Ana & João',
      'job_title': 'Suporte N2',
      'candidate_phone': '+55 (61) 99999-1234',
      'candidate_email': 'ana@example.com'
    };
    final whatsapp = candidateWhatsAppUri(candidate)!;
    expect(whatsapp.host, 'wa.me');
    expect(whatsapp.path, '/5561999991234');
    expect(whatsapp.queryParameters['text'], contains('Ana & João'));
    expect(whatsapp.queryParameters['text'], contains('Suporte N2'));
    final email = candidateEmailUri(candidate)!;
    expect(email.scheme, 'mailto');
    expect(email.path, 'ana@example.com');
    expect(email.queryParameters['body'], contains('Ana & João'));
    expect(candidateWhatsAppUri({'candidate_phone': ''}), isNull);
  });
  testWidgets(
      'upload in another tab refreshes resume eligibility before applying',
      (tester) async {
    viewport(tester, 320);
    var hasResume = false;
    var submitted = false;
    final api = Api(client: MockClient((request) async {
      if (request.url.path == '/v1/me')
        return jsonResponse({'is_premium': false, 'has_resume': hasResume});
      if (request.method == 'POST') {
        submitted = true;
        return jsonResponse({'created': true, 'status': 'submitted'});
      }
      return jsonResponse({
        'items': [
          {'job': job(1), 'category': 'internal'}
        ]
      });
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(app(api));
    await tester.pumpAndSettle();
    hasResume = true;
    await tester.tap(find.text('Analista de Suporte 1'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Candidatar-se com 1 Toque'), 200,
        scrollable: find.byType(Scrollable).last);
    await tester.ensureVisible(find.text('Candidatar-se com 1 Toque'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Candidatar-se com 1 Toque'));
    await tester.pumpAndSettle();
    expect(submitted, isTrue);
    expect(find.text('Currículo PDF obrigatório'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('owner has one-tap Admin in AppBar and Profile at 320px',
      (tester) async {
    viewport(tester, 320);
    const user = {
      'role': 'super_admin',
      'email': 'rbrilhante001@gmail.com',
      'name': 'Renato',
      'is_premium': true,
      'has_resume': false,
      'skills': []
    };
    var adminCalls = 0;
    final api = Api(client: MockClient((request) async {
      final path = request.url.path;
      if (path == '/v1/me') return jsonResponse(user);
      if (path == '/v1/admin/dashboard') {
        adminCalls++;
        return jsonResponse({'candidates': 3, 'last_sync': null});
      }
      if (path == '/v1/dashboard')
        return jsonResponse({
          'manual': 0,
          'automatic': 0,
          'total_applications': 0,
          'by_status': {}
        });
      if (path == '/v1/internal-jobs' || path == '/v1/automation/runs')
        return jsonResponse({'items': []});
      return jsonResponse([]);
    }));
    addTearDown(api.client.close);
    expect(hasAdminAccess(user), isTrue);
    expect(
        hasAdminAccess(
            {'email': 'rbrilhante001@gmail.com', 'role': 'candidate'}),
        isFalse);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: HomeScreen(
            api: api,
            user: user,
            onRefreshUser: () async {},
            onSignedOut: () async {})));
    await tester.pumpAndSettle();
    await tester.tap(find.text('🛡️ Admin'));
    await tester.pumpAndSettle();
    expect(find.text('Candidatos'), findsOneWidget);
    tester.state<NavigatorState>(find.byType(Navigator)).pop();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Perfil'));
    await tester.pumpAndSettle();
    expect(find.text('🛡️ Admin'), findsNWidgets(2));
    await tester.tap(find.text('🛡️ Admin').last);
    await tester.pumpAndSettle();
    expect(adminCalls, 2);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('PDF failures stay friendly after authenticated download',
      (tester) async {
    viewport(tester, 320);
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('io.scer.pdf_renderer'),
        (call) async => throw PlatformException(
            code: 'invalid', message: 'private-renderer-path'));
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(
            const MethodChannel('io.scer.pdf_renderer'), null));
    final api = Api(client: MockClient((request) async {
      expect(request.url.path, '/v1/me/resume');
      expect(request.headers['ngrok-skip-browser-warning'], 'true');
      return http.Response('%PDF-1.4', 200,
          headers: {'content-type': 'application/pdf'});
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(
        MaterialApp(home: ResumeViewer(api: api, path: '/me/resume')));
    await tester.pumpAndSettle();
    expect(find.text('Não foi possível abrir o currículo'), findsOneWidget);
    expect(find.textContaining('private-renderer-path'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
