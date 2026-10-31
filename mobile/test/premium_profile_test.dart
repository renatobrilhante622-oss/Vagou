import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vagou/api.dart';
import 'package:vagou/candidate.dart';
import 'package:vagou/ui.dart';

void main() {
  testWidgets(
    'server plan refresh unlocks automation without replacing unsaved profile text',
    (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = Api();
      addTearDown(api.client.close);
      final user = <String, dynamic>{
        'id': 'candidate',
        'name': 'Ana Original',
        'email': 'ana@example.com',
        'skills': ['python'],
        'has_resume': true,
        'is_premium': false,
        'automation_enabled': false,
        'preferences': {
          'titles': ['Python'],
          'modalities': ['remote'],
          'min_salary': 2000,
        },
        'entitlements': {'can_automate': false, 'is_test_access': false},
      };
      Widget profile(Map<String, dynamic> value) => MaterialApp(
            theme: Brand.theme(Brightness.light),
            home: Scaffold(
              body: CandidateProfile(
                  api: api, user: value, onChanged: () async {}),
            ),
          );
      await tester.pumpWidget(profile(user));
      final name = find.byWidgetPredicate(
        (widget) =>
            widget is TextFormField &&
            widget.controller?.text == 'Ana Original',
      );
      await tester.ensureVisible(name);
      await tester.enterText(name, 'Ana Editando');
      await tester.pump();

      final updated = <String, dynamic>{
        ...user,
        'entitlements': {'can_automate': true, 'is_test_access': true},
      };
      await tester.pumpWidget(profile(updated));
      await tester.pump();
      expect(
        find.byWidgetPredicate(
          (widget) =>
              widget is TextFormField &&
              widget.controller?.text == 'Ana Editando',
        ),
        findsOneWidget,
      );
      await tester.scrollUntilVisible(
        find.text('Autorizar candidaturas automáticas'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      final toggle = tester.widget<SwitchListTile>(find.byType(SwitchListTile));
      expect(toggle.onChanged, isNotNull);
      expect(
        find.text('Acesso de teste autorizado pelo servidor.'),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'saves the salary range without overwriting courses, then explicitly queues a cycle',
    (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = RecordingApi();
      addTearDown(api.client.close);
      var refreshed = 0;
      final user = <String, dynamic>{
        'id': 'candidate',
        'name': 'Ana',
        'email': 'ana@example.com',
        'skills': ['python'],
        'has_resume': true,
        'is_premium': false,
        'automation_enabled': true,
        'preferences': {
          'titles': ['Python'],
          'modalities': ['remote'],
          'min_salary': 2000,
          'max_salary': 3500,
          'completed_course_ids': ['bradesco-python'],
        },
        'entitlements': {'can_automate': true, 'is_test_access': true},
      };
      await tester.pumpWidget(
        MaterialApp(
          theme: Brand.theme(Brightness.light),
          home: Scaffold(
            body: CandidateProfile(
              api: api,
              user: user,
              onChanged: () async {
                refreshed++;
              },
            ),
          ),
        ),
      );
      await tester.scrollUntilVisible(
        find.text('Salvar preferências'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(find.text('Salvar preferências'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Salvar preferências'));
      await tester.pumpAndSettle();
      expect(api.requests.length, 1);
      expect(api.requests.first.$1, 'PUT');
      expect(api.requests.first.$2, '/me/preferences');
      final payload = api.requests.first.$3 as Map;
      expect(payload['min_salary'], 2000);
      expect(payload['max_salary'], 3500);
      expect(payload['automation_enabled'], isTrue);
      expect(payload.containsKey('completed_course_ids'), isFalse);
      expect(refreshed, 1);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Iniciar busca agora'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(find.text('Iniciar busca agora'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Iniciar busca agora'));
      await tester.pumpAndSettle();
      expect(api.requests.last.$1, 'POST');
      expect(api.requests.last.$2, '/automation/run');
      expect(refreshed, 2);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}

class RecordingApi extends Api {
  final requests = <(String, String, Object?)>[];
  @override
  Future<dynamic> request(String method, String path, [Object? body]) async {
    requests.add((method, path, body));
    return path == '/automation/run' ? {'status': 'queued'} : body;
  }
}
