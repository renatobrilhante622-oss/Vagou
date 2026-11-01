import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/api.dart';
import 'package:vagou/recruiter.dart';
import 'package:vagou/ui.dart';

void main() {
  for (final width in [320.0, 430.0]) {
    testWidgets('candidate contact modal preserves contact and resume details at ${width.toInt()}px', (tester) async {
      tester.view.physicalSize = Size(width, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const email = 'candidato.profissional@example.com';
      final api = Api(client: MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/v1/recruiter/applicants');
        return http.Response(jsonEncode({'items': [{
          'id': 'application-id', 'candidate_name': 'Ana Profissional',
          'candidate_email': email, 'candidate_phone': '+5511999999999',
          'candidate_skills': ['Python', 'Atendimento ao cliente'],
          'preferred_locations': ['São Paulo / SP'], 'salary_expectation': 5000,
          'job_title': 'Analista de atendimento e operações', 'match_score': 85,
          'status': 'submitted', 'created_at': '2026-10-31T12:00:00Z',
        }]}), 200, headers: {'content-type': 'application/json'});
      }));
      addTearDown(api.client.close);
      await tester.pumpWidget(MaterialApp(theme: Brand.theme(Brightness.light), home: Scaffold(body: RecruiterApplications(api: api))));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text(email), 250, scrollable: find.byType(Scrollable).first);
      await tester.ensureVisible(find.text(email));
      await tester.pumpAndSettle();
      await tester.tap(find.text(email));
      await tester.pumpAndSettle();
      expect(find.text('Contato do candidato'), findsOneWidget);
      expect(find.text('Enviar e-mail'), findsOneWidget);
      expect(find.text('Ligar para candidato'), findsOneWidget);
      expect(find.text('+5511999999999'), findsOneWidget);
      expect(find.text('Resumo do currículo'), findsOneWidget);
      expect(find.text('Competências declaradas: Python · Atendimento ao cliente'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
