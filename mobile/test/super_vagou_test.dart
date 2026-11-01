import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/admin.dart';
import 'package:vagou/api.dart';
import 'package:vagou/forms.dart';
import 'package:vagou/jobs.dart';
import 'package:vagou/ui.dart';

http.Response response(Object body) => http.Response(jsonEncode(body), 200,
    headers: {'content-type': 'application/json'});
void narrow(WidgetTester tester) {
  tester.view.physicalSize = const Size(320, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  test('Brazil phone formatting and decimal salary preserve API values', () {
    expect(formatBrazilPhone('61999991234'), '+55 (61) 99999-1234');
    expect(formatBrazilPhone('+55 (61) 99999-1234'), '+55 (61) 99999-1234');
    expect(formatBrazilDate('14051990'), '14/05/1990');
    expect(validBrazilDate('29/02/2024'), isTrue);
    expect(validBrazilDate('29/02/2023'), isFalse);
    expect(validBrazilDate('31/04/2024'), isFalse);
    expect(validBrazilDate('01/01/1899'), isFalse);
    expect(validBrazilDate('01/01/2999'), isFalse);
    expect(
        brazilPhonePayload(formatBrazilPhone('61999991234')), '+5561999991234');
    expect(brazilPhonePayload('+55 '), isNull);
    for (final text in ['1750.0', '1.750,00']) {
      final field = TextEditingController(text: text);
      expect(
          candidateDetailsPayload({'desired_salary': field})['desired_salary'],
          1750);
      field.dispose();
    }
  });
  test('ngrok header accompanies JSON, uploads and PDF downloads', () async {
    final routes = <String>[];
    final api = Api(client: MockClient((request) async {
      expect(request.headers['ngrok-skip-browser-warning'], 'true');
      routes.add(request.url.path);
      if (request.method == 'GET' && request.url.path.endsWith('/resume'))
        return http.Response('%PDF-1.4', 200,
            headers: {'content-type': 'application/pdf'});
      return response({});
    }));
    addTearDown(api.client.close);
    await api.request('GET', '/me');
    await api.upload(utf8.encode('%PDF-1.4'));
    await api.downloadPdf('/me/resume');
    expect(routes.length, 3);
  });
  testWidgets(
      'native jobs are the default and PDF is required before application',
      (tester) async {
    narrow(tester);
    final requests = <String>[];
    final api = Api(client: MockClient((request) async {
      requests.add(request.url.path);
      if (request.url.path == '/v1/me')
        return response(
            {'has_resume': false, 'is_premium': false, 'preferences': {}});
      if (request.url.path == '/v1/internal-jobs')
        return response({
          'items': [
            {
              'category': 'internal',
              'match_score': 85,
              'job': {
                'id': 'native-1',
                'title': 'Analista de Suporte',
                'company': 'Empresa Verificada',
                'location': 'Brasília / DF',
                'company_verified': true,
                'modality': 'onsite',
                'description': 'Suporte técnico de computadores e redes.',
                'salary_min': 3000,
                'salary_max': 3000,
              }
            }
          ],
          'next_offset': null
        });
      throw StateError('Unexpected request ${request.url}');
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: Scaffold(body: JobsView(api: api, onUserChanged: () async {}))));
    await tester.pumpAndSettle();
    expect(find.text('Vagas no App (Empresas)'), findsOneWidget);
    expect(find.text('Empresa Verificada'), findsOneWidget);
    expect(find.byTooltip('Empresa Verificada'), findsOneWidget);
    expect(find.text('85%'), findsOneWidget);
    expect(requests, isNot(contains('/v1/radar')));
    expect(find.text('Candidatar-se com 1 Toque'), findsNothing);
    await tester.tap(find.text('Analista de Suporte'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Candidatar-se com 1 Toque'), 250,
        scrollable: find.byType(Scrollable).first);
    await tester.ensureVisible(find.text('Candidatar-se com 1 Toque'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Candidatar-se com 1 Toque'));
    await tester.pumpAndSettle();
    expect(find.text('Currículo PDF obrigatório'), findsOneWidget);
    expect(tester.takeException(), isNull);
    expect(requests.where((p) => p.endsWith('/applications')), isEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('admin dashboard and five real tabs fit 320px', (tester) async {
    narrow(tester);
    final routes = <String>[];
    final api = Api(client: MockClient((request) async {
      routes.add(request.url.path);
      if (request.url.path == '/v1/admin/dashboard')
        return response({'candidates': 4, 'last_sync': null});
      if (request.url.path == '/v1/admin/audit')
        return response(
            {'smtp_acceptance_rate': 0, 'smtp': {}, 'runs': [], 'actions': []});
      return response([]);
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: AdminScreen(api: api, user: const {'role': 'super_admin'})));
    await tester.pumpAndSettle();
    expect(find.text('Candidatos'), findsOneWidget);
    for (final label in [
      'Moderação',
      'Empresas',
      'Usuários e Equipe',
      'Auditoria'
    ]) {
      await tester.ensureVisible(find.text(label));
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    }
    expect(routes.toSet().length, 5);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
