import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:vagou/api.dart';

void main() {
  test(
    'authoritative capability overrides a stale premium flag in both directions',
    () {
      expect(
        PlanAccess.fromUser({
          'is_premium': false,
          'entitlements': {'can_automate': true, 'is_test_access': false},
        }).canAutomate,
        isTrue,
      );
      expect(
        PlanAccess.fromUser({
          'is_premium': true,
          'entitlements': {'can_automate': false},
        }).canAutomate,
        isFalse,
      );
    },
  );

  test(
    'test access is explicit and cannot be inferred from local strings or email',
    () {
      final access = PlanAccess.fromUser({
        'is_premium': false,
        'entitlements': {'can_automate': true, 'is_test_access': true},
      });
      expect(access.plan, 'test');
      expect(access.isTestAccess, isTrue);
      expect(access.label, 'Acesso de teste autorizado');
      expect(
        PlanAccess.fromUser({
          'is_premium': 'true',
          'email': 'test@example.com',
        }).canAutomate,
        isFalse,
      );
      expect(
        PlanAccess.fromUser({
          'entitlements': {'can_automate': 'true', 'is_test_access': true},
        }).canAutomate,
        isFalse,
      );
      expect(PlanAccess.fromUser({'is_premium': true}).canAutomate, isTrue);
    },
  );

  test(
    'automation conflicts explain prerequisites instead of duplicate registration',
    () async {
      final api = Api();
      addTearDown(api.client.close);
      final response = http.Response(
        jsonEncode({
          'detail': {'code': 'automation_disabled'},
        }),
        409,
      );
      await expectLater(
        api.decode(response, authenticated: false),
        throwsA(
          isA<ApiException>()
              .having((error) => error.code, 'code', 'automation_disabled')
              .having(
                (error) => error.message.contains('cadastro'),
                'not a registration error',
                isFalse,
              )
              .having(
                (error) => error.message.contains('preferências'),
                'actionable prerequisite',
                isTrue,
              ),
        ),
      );
    },
  );
}
