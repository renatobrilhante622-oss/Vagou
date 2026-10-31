import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:vagou/api.dart';

void main() {
  late Api api;
  setUp(() { api = Api(); });
  tearDown(() { api.client.close(); });

  test('preserves the configured HTTPS origin and API prefix', () {
    final uri = api.uri('/jobs?limit=20');
    expect(uri.origin, 'https://nest-gents-sudden.ngrok-free.dev');
    expect(uri.path, '/v1/jobs');
    expect(uri.queryParameters['limit'], '20');
  });

  test('explains legacy Pydantic password validation in Portuguese', () async {
    final response = http.Response(jsonEncode({
      'detail': [
        {'loc': ['body', 'password'], 'type': 'string_too_short', 'msg': 'String should have at least 12 characters'}
      ]
    }), 422);
    await expectLater(api.decode(response, authenticated: false), throwsA(
      isA<ApiException>()
        .having((error) => error.status, 'status', 422)
        .having((error) => error.message, 'message', 'Sua senha precisa ter no mínimo 12 caracteres.'),
    ));
  });

  test('uses curated validation messages from the backend', () async {
    const message = 'Informe uma cidade e estado para vagas presenciais.';
    final response = http.Response(jsonEncode({
      'detail': 'Confira os dados informados.',
      'errors': [{'field': 'locations', 'message': message}]
    }), 422);
    await expectLater(api.decode(response, authenticated: false), throwsA(
      isA<ApiException>().having((error) => error.message, 'message', message),
    ));
  });

  test('verification-required response retains actionable code and friendly message', () async {
    final response = http.Response(jsonEncode({
      'detail': {'code': 'email_verification_required', 'message': 'Confirme seu e-mail.'}
    }), 403);
    await expectLater(api.decode(response, authenticated: false), throwsA(
      isA<ApiException>()
        .having((error) => error.code, 'code', 'email_verification_required')
        .having((error) => error.message, 'message', 'Confirme seu e-mail com o código de 6 dígitos antes de entrar.'),
    ));
  });

  test('invalid JSON becomes a user message without exposing the response', () async {
    const internalResponse = '<html>private stack trace /srv/backend/database.py</html>';
    final response = http.Response(internalResponse, 502);
    await expectLater(api.decode(response, authenticated: false), throwsA(
      isA<ApiException>()
        .having((error) => error.message, 'message', 'O serviço enviou uma resposta inesperada. Tente novamente.')
        .having((error) => error.message.contains('/srv/backend'), 'does not expose server paths', false),
    ));
  });

  test('malformed curated errors fall back to a safe validation message', () async {
    final response = http.Response(jsonEncode({'errors': ['unexpected'], 'detail': 'SQLAlchemy stack trace'}), 422);
    await expectLater(api.decode(response, authenticated: false), throwsA(
      isA<ApiException>().having((error) => error.message, 'message', 'Confira os campos informados e tente novamente.'),
    ));
  });
}
