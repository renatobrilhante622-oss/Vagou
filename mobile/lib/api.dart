import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class Api {
  static const base = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://192.168.18.128:8000',
  );
  final storage = const FlutterSecureStorage();
  final client = http.Client();
  String? _token;

  Future<bool> restore() async {
    _token = await storage.read(key: 'access_token');
    return _token != null;
  }

  Uri uri(String path) {
    final root = Uri.parse(base);
    if ((root.scheme != 'http' && root.scheme != 'https') || root.host.isEmpty) {
      throw ApiException('Configure API_BASE_URL corretamente.');
    }
    return Uri.parse('$base/v1$path');
  }

  Future<dynamic> request(String method, String path, [Object? body]) async {
    final req = http.Request(method, uri(path));
    req.headers['Content-Type'] = 'application/json';
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    if (body != null) req.body = jsonEncode(body);
    final streamed = await client.send(req).timeout(const Duration(seconds: 20));
    return decode(await http.Response.fromStream(streamed).timeout(const Duration(seconds: 20)));
  }

  dynamic decode(http.Response response) {
    final dynamic body = response.body.isEmpty ? null : jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode == 401) {
      _token = null;
      storage.delete(key: 'access_token');
      throw ApiException('Sessão expirada. Entre novamente.');
    }
    if (response.statusCode >= 400) throw ApiException('Falha (${response.statusCode}): ${body?['detail']}');
    return body;
  }

  Future<void> login(String email, String password) async {
    final result = await request('POST', '/auth/login', {'email': email, 'password': password});
    _token = result['access_token'] as String;
    await storage.write(key: 'access_token', value: _token);
  }

  Future<void> upload(List<int> bytes) async {
    // Explicit MIME type is supplied by the generated multipart body below.
    final boundary = 'vagou-${DateTime.now().microsecondsSinceEpoch}';
    final raw = http.Request('PUT', uri('/me/resume'));
    raw.headers.addAll({'Authorization': 'Bearer $_token', 'Content-Type': 'multipart/form-data; boundary=$boundary'});
    raw.bodyBytes = [
      ...utf8.encode('--$boundary\r\nContent-Disposition: form-data; name="file"; filename="curriculo.pdf"\r\nContent-Type: application/pdf\r\n\r\n'),
      ...bytes,
      ...utf8.encode('\r\n--$boundary--\r\n'),
    ];
    final response = await client.send(raw).timeout(const Duration(seconds: 30));
    decode(await http.Response.fromStream(response).timeout(const Duration(seconds: 30)));
  }

  Future<void> clear() async {
    _token = null;
    await storage.delete(key: 'access_token');
  }
}