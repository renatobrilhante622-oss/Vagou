import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/home.dart';
import 'package:vagou/recruiter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vagou/api.dart';
import 'package:vagou/auth.dart';
import 'package:vagou/onboarding.dart';
import 'package:vagou/ui.dart';

void main() {
  for (final width in [320.0, 360.0]) {
    testWidgets(
        'welcome and company registration remain usable at ${width.toInt()}px',
        (tester) async {
      tester.view.physicalSize = Size(width, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = Api();
      addTearDown(api.client.close);
      await tester.pumpWidget(MaterialApp(
          theme: Brand.theme(Brightness.light),
          home: AuthScreen(api: api, onAuthenticated: () async {})));
      await tester.pumpAndSettle();
      expect(find.text('IA de Recrutamento & Automação de Carreira'),
          findsOneWidget);
      await tester.scrollUntilVisible(find.text('Sou Recrutador'), 160,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Sou Recrutador'));
      await tester.scrollUntilVisible(
          find.text('Ainda não tem conta? Cadastre-se'), 200,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Ainda não tem conta? Cadastre-se'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Sua empresa'), 200,
          scrollable: find.byType(Scrollable).first);
      expect(find.text('CNPJ (com ou sem máscara)'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
  testWidgets('ATS dashboard and publication sections fit 320px',
      (tester) async {
    tester.view.physicalSize = const Size(320, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = Api(client: MockClient((request) async {
      final path = request.url.path;
      final Object result = path.endsWith('/jobs')
          ? []
          : path.endsWith('/applicants')
              ? {'items': []}
              : {
                  'active_jobs': 3,
                  'total_applications': 8,
                  'strong_candidates': 2,
                  'applications_by_job': {}
                };
      return http.Response(jsonEncode(result), 200,
          headers: {'content-type': 'application/json'});
    }));
    addTearDown(api.client.close);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: HomeScreen(
            api: api,
            user: const {
              'role': 'recruiter',
              'name': 'Empresa Teste',
              'company_name': 'Empresa Teste',
              'email': 'rh@example.com',
              'is_premium': true
            },
            onRefreshUser: () async {},
            onSignedOut: () async {})));
    await tester.pumpAndSettle();
    expect(find.text('Central de Recrutamento'), findsOneWidget);
    expect(find.text('PRO'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: JobEditor(api: api, companyName: 'Empresa Teste')));
    await tester.pumpAndSettle();
    expect(find.text('01 · Identidade da oportunidade'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Enviar para aprovação'), 250,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('03 · Perfil ideal'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('premium vector identity and onboarding fit narrow screen',
      (tester) async {
    tester.view.physicalSize = const Size(320, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: const VagouBrandMark(premium: true))));
    expect(find.text('PRO'), findsOneWidget);
    await tester.pumpWidget(MaterialApp(
        theme: Brand.theme(Brightness.light),
        home: OnboardingScreen(onComplete: () async {})));
    await tester.pumpAndSettle();
    expect(find.text('Sua carreira merece um novo espaço.'), findsOneWidget);
    expect(find.text('Continuar'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
