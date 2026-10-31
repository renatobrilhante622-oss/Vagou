import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vagou/onboarding.dart';
import 'package:vagou/ui.dart';

void main() {
  testWidgets('introduces the platform and completes the three-page onboarding', (tester) async {
    tester.view.physicalSize = const Size(430, 932);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var completed = false;
    await tester.pumpWidget(MaterialApp(
      theme: Brand.theme(Brightness.light),
      home: OnboardingScreen(onComplete: () async { completed = true; }),
    ));
    expect(find.text('Sua carreira merece um novo espaço.'), findsOneWidget);
    expect(completed, false);

    await tester.tap(find.text('Continuar'));
    await tester.pumpAndSettle();
    expect(find.text('Oportunidades com o seu perfil.'), findsOneWidget);
    expect(completed, false);

    await tester.tap(find.text('Continuar'));
    await tester.pumpAndSettle();
    expect(find.text('Confiança em cada próximo passo.'), findsOneWidget);

    await tester.tap(find.text('Começar minha jornada'));
    await tester.pump();
    expect(completed, true);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('allows skipping onboarding through the same completion callback', (tester) async {
    tester.view.physicalSize = const Size(430, 932);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var calls = 0;
    await tester.pumpWidget(MaterialApp(home: OnboardingScreen(onComplete: () async { calls++; })));
    await tester.tap(find.text('Pular'));
    await tester.pump();
    expect(calls, 1);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
