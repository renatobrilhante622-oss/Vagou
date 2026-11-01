import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:vagou/api.dart';
import 'package:vagou/automation_panel.dart';
import 'package:vagou/ui.dart';

void main() {
  for (final searchOnly in [false, true]) {
    testWidgets(searchOnly ? 'regional search links remain distinct from verified vacancies' : 'application metadata shows destination and notification state', (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = Api(client: MockClient((request) async {
        dynamic result;
        if (request.url.path == '/v1/me') {
          result = {'is_premium': true, 'automation_enabled': false, 'has_resume': true, 'preferences': {}};
        } else if (request.url.path == '/v1/automation/runs') {
          result = {'items': [{'id': 'round', 'status': 'complete', 'scanned_jobs': searchOnly ? 0 : 1, 'submitted_applications': searchOnly ? 0 : 1}]};
        } else if (request.url.path == '/v1/automation/runs/round/events') {
          result = {'items': [searchOnly ? {
            'status': 'search_channel', 'source_name': 'Gupy', 'location': 'Brasília / DF',
            'external_url': 'https://portal.gupy.io/job-search/term=analista',
            'detail': 'Busca regional disponível no portal oficial.',
          } : {
            'status': 'submitted', 'job_title': 'Analista de Operações',
            'company_name': 'Empresa Exemplo', 'location': 'Brasília / DF',
            'source_name': 'Parceiro autorizado', 'match_score': 80,
            'match_reasons': ['Competências alinhadas'], 'destination_channel': 'smtp',
            'delivery_status': 'pending', 'external_url': 'https://example.com/jobs/1',
          }]};
        } else {
          throw StateError('Unexpected route ${request.url.path}');
        }
        return http.Response(jsonEncode(result), 200, headers: {'content-type': 'application/json'});
      }));
      addTearDown(api.client.close);
      await tester.pumpWidget(MaterialApp(theme: Brand.theme(Brightness.light), home: Builder(builder: (context) => Scaffold(body: FilledButton(
        onPressed: () => showAutomationPanel(context, api: api, onChanged: () async {}), child: const Text('Abrir'),
      )))));
      await tester.tap(find.text('Abrir'));
      await tester.pumpAndSettle();
      final target = searchOnly ? 'Explorar canais regionais' : 'Empresa Exemplo · Brasília / DF';
      await tester.scrollUntilVisible(find.text(target), 250, scrollable: find.byType(Scrollable).last);
      await tester.ensureVisible(find.text(target));
      await tester.pumpAndSettle();
      if (searchOnly) {
        expect(find.text('Links de busca com seus critérios. Não são anúncios confirmados nem candidaturas enviadas.'), findsOneWidget);
        expect(find.text('Abrir busca no portal'), findsOneWidget);
        expect(find.textContaining('% de compatibilidade'), findsNothing);
      } else {
        expect(find.text('Canal de destino: contato de recrutamento por e-mail'), findsOneWidget);
        expect(find.text('Notificação aguardando envio.'), findsOneWidget);
        expect(find.text('Competências alinhadas'), findsOneWidget);
        expect(find.text('80% de compatibilidade'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
