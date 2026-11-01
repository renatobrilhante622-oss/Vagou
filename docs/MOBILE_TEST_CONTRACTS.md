# Contratos dos testes mobile

Inventário de seletores; métodos State e contratos da API preservados.

## api_test.dart

```dart
```

## automation_metadata_test.dart

```dart
await tester.tap(find.text('Abrir'));
await tester.scrollUntilVisible(find.text(target), 250, scrollable: find.byType(Scrollable).last);
await tester.ensureVisible(find.text(target));
expect(find.text('Links de busca com seus critérios. Não são anúncios confirmados nem candidaturas enviadas.'), findsOneWidget);
expect(find.text('Abrir busca no portal'), findsOneWidget);
expect(find.textContaining('% de compatibilidade'), findsNothing);
expect(find.text('Canal de destino: contato de recrutamento por e-mail'), findsOneWidget);
expect(find.text('Notificação aguardando envio.'), findsOneWidget);
expect(find.text('Competências alinhadas'), findsOneWidget);
expect(find.text('80% de compatibilidade'), findsOneWidget);
```

## company_test.dart

```dart
```

## onboarding_test.dart

```dart
expect(find.text('Sua carreira merece um novo espaço.'), findsOneWidget);
await tester.tap(find.text('Continuar'));
expect(find.text('Oportunidades com o seu perfil.'), findsOneWidget);
await tester.tap(find.text('Continuar'));
expect(find.text('Confiança em cada próximo passo.'), findsOneWidget);
await tester.tap(find.text('Começar minha jornada'));
await tester.tap(find.text('Pular'));
```

## opportunity_cards_test.dart

```dart
expect(find.text('Empresa Brasileira de Tecnologia · Brasília / DF'),
expect(find.text('55% de compatibilidade'), findsOneWidget);
expect(find.text('R\$ 3.000 a R\$ 4.500'), findsOneWidget);
expect(find.text('Híbrido'), findsOneWidget);
expect(find.text('CLT'), findsOneWidget);
expect(find.text('Competências próximas do perfil.'), findsOneWidget);
expect(tester.widget<Text>(find.text(description)).maxLines, 3);
await tester.ensureVisible(find.text('Expandir resumo'));
await tester.tap(find.text('Expandir resumo'));
expect(tester.widget<Text>(find.text(description)).maxLines, isNull);
await tester.ensureVisible(find.text('Copiar e-mail'));
await tester.tap(find.text('Copiar e-mail'));
expect(find.text(contact), findsOneWidget);
expect(find.text('Abrir link oficial'), findsOneWidget);
await tester.ensureVisible(find.text('Possíveis vagas'));
await tester.tap(find.text('Possíveis vagas'));
expect(find.textContaining('fonte(s) externa(s) não responderam'),
await tester.scrollUntilVisible(find.text('📧 E-mail da vaga'), 250,
scrollable: find.byType(Scrollable).first);
expect(find.text(contact), findsOneWidget);
expect(find.text('Competências próximas do perfil.'), findsOneWidget);
find.text('Analista de Suporte e Sistemas N2'), 350,
scrollable: find.byType(Scrollable).first);
expect(find.text('Analista de Suporte e Sistemas N2'), findsOneWidget);
await tester.scrollUntilVisible(find.text('📧 E-mail da vaga'), 250,
scrollable: find.byType(Scrollable).first);
expect(find.text(contact), findsOneWidget);
expect(find.text('Competências próximas do perfil.'), findsOneWidget);
```

## preferences_automation_test.dart

```dart
expect(find.text('Filtros e Preferências'), findsNothing);
await tester.scrollUntilVisible(find.text('Meu Plano'), 250,
scrollable: find.byType(Scrollable).first);
expect(find.text('Meu Plano'), findsOneWidget);
await tester.scrollUntilVisible(find.text('Atualizar meu acesso'), 300,
scrollable: find.byType(Scrollable).first);
await tester.tap(find.text('Atualizar meu acesso'));
expect(find.text('Premium Ativo'), findsOneWidget);
await tester.tap(find.text('Abrir filtros'));
final city = find.byWidgetPredicate((widget) => widget is TextField && widget.decoration?.labelText == 'Cidade');
await tester.scrollUntilVisible(find.text('Salvar preferências'), 250,
scrollable: find.byType(Scrollable).first);
await tester.tap(find.text('Salvar preferências'));
await tester.tap(find.text('Abrir robô'));
await tester.ensureVisible(find.text('Iniciar Varredura e Envio Agora'));
await tester.tap(find.text('Iniciar Varredura e Envio Agora'));
await tester.scrollUntilVisible(find.text(metric.key), 200,
scrollable: find.byType(Scrollable).last);
await tester.ensureVisible(find.text(metric.key));
final column = tester.widget<Column>(find.byWidgetPredicate((widget) =>
await tester.scrollUntilVisible(find.text('4 externas analisadas · 5 descartadas'), 200,
scrollable: find.byType(Scrollable).last);
expect(find.text('4 externas analisadas · 5 descartadas'), findsOneWidget);
```

## recruiter_contact_test.dart

```dart
await tester.scrollUntilVisible(find.text(email), 250, scrollable: find.byType(Scrollable).first);
await tester.ensureVisible(find.text(email));
await tester.tap(find.text(email));
expect(find.text('Contato do candidato'), findsOneWidget);
expect(find.text('Enviar e-mail'), findsOneWidget);
expect(find.text('Ligar para candidato'), findsOneWidget);
expect(find.text('+5511999999999'), findsOneWidget);
expect(find.text('Resumo do currículo'), findsOneWidget);
expect(find.text('Competências declaradas: Python · Atendimento ao cliente'), findsOneWidget);
```

## redesign_flows_test.dart

```dart
expect(find.text('IA de Recrutamento & Automação de Carreira'),
find.text('Sou Recrutador / Empresa'), 160,
scrollable: find.byType(Scrollable).first);
await tester.tap(find.text('Sou Recrutador / Empresa'));
find.text('Ainda não tem conta? Cadastre-se'), 200,
scrollable: find.byType(Scrollable).first);
await tester.tap(find.text('Ainda não tem conta? Cadastre-se'));
await tester.scrollUntilVisible(find.text('Sua empresa'), 200,
scrollable: find.byType(Scrollable).first);
expect(find.text('CNPJ (com ou sem máscara)'), findsOneWidget);
expect(find.text('Central de Recrutamento'), findsOneWidget);
expect(find.text('PRO'), findsOneWidget);
expect(find.text('01 · Identidade da oportunidade'), findsOneWidget);
await tester.scrollUntilVisible(find.text('Enviar para aprovação'), 250,
scrollable: find.byType(Scrollable).first);
expect(find.text('03 · Perfil ideal'), findsOneWidget);
expect(find.text('PRO'), findsOneWidget);
expect(find.text('Sua carreira merece um novo espaço.'), findsOneWidget);
expect(find.text('Continuar'), findsOneWidget);
```
