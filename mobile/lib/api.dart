import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiException implements Exception {
  final String message;
  final int? status;
  final String? code;
  const ApiException(this.message, {this.status, this.code});
  @override
  String toString() => message;
}

class Api {
  static const base = String.fromEnvironment('API_BASE_URL', defaultValue: 'https://nest-gents-sudden.ngrok-free.dev');
  final storage = const FlutterSecureStorage();
  Api({http.Client? client}) : client = client ?? http.Client();
  final http.Client client;
  String? _token;
  void Function()? onUnauthorized;

  Future<bool> restore() async {
    _token = await storage.read(key: 'access_token');
    return _token != null;
  }

  Uri uri(String path) {
    final root = Uri.parse(base);
    const localOrigin = 'http://192.168.18.128:8000';
    if (root.host.isEmpty || root.hasQuery || root.hasFragment ||
        (root.scheme != 'https' && root.origin != localOrigin)) {
      throw const ApiException('O endereço do serviço não está configurado corretamente.');
    }
    return Uri.parse('${base.replaceFirst(RegExp(r'/+$'), '')}/v1$path');
  }

  Future<dynamic> request(String method, String path, [Object? body]) async {
    try {
      final req = http.Request(method, uri(path));
      req.headers['Content-Type'] = 'application/json';
      if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
      if (body != null) req.body = jsonEncode(body);
      final streamed = await client.send(req).timeout(const Duration(seconds: 25));
      final response = await http.Response.fromStream(streamed).timeout(const Duration(seconds: 25));
      return await decode(response, authenticated: _token != null && !path.startsWith('/auth/'));
    } on TimeoutException {
      throw const ApiException('A conexão demorou mais que o esperado. Tente novamente.');
    } on SocketException {
      throw const ApiException('Não conseguimos conectar. Verifique sua internet e tente novamente.');
    } on http.ClientException {
      throw const ApiException('O serviço está indisponível no momento. Tente novamente em instantes.');
    }
  }

  Future<dynamic> decode(http.Response response, {bool authenticated = true}) async {
    dynamic body;
    try {
      body = response.bodyBytes.isEmpty ? null : jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw const ApiException('O serviço enviou uma resposta inesperada. Tente novamente.');
    }
    if (response.statusCode == 401 && authenticated) {
      await clear();
      onUnauthorized?.call();
      throw const ApiException('Sua sessão expirou. Entre novamente para continuar.', status: 401);
    }
    if (response.statusCode >= 400) {
      throw ApiException(_friendly(response.statusCode, body), status: response.statusCode,
        code: body is Map && body['detail'] is Map ? body['detail']['code']?.toString() : null);
    }
    return body;
  }

  String _friendly(int status, dynamic body) {
    final detail = body is Map ? body['detail'] : null;
    final errors = body is Map ? body['errors'] : null;
    if (status == 422 && errors is List && errors.isNotEmpty) {
      final error = errors.first;
      final message = error is Map ? error['message'] : null;
      if (message is String && message.isNotEmpty && message.length <= 300) return message;
    }
    if (detail is List && detail.isNotEmpty) {
      final entry = detail.first;
      if (entry is Map) {
        final loc = entry['loc'];
        final field = loc is List && loc.isNotEmpty ? loc.last.toString() : '';
        final type = entry['type']?.toString() ?? '';
        if (field == 'password' && type == 'string_too_short') return 'Sua senha precisa ter no mínimo 12 caracteres.';
        if (field.contains('email')) return 'Informe um endereço de e-mail válido.';
        if (field == 'company_cnpj') return 'Informe um CNPJ válido com 14 caracteres e dígitos verificadores corretos.';
        if (field == 'min_salary') return 'Confira a pretensão salarial informada.';
        if (field == 'locations') return 'Confira a cidade e a UF informadas para filtrar vagas presenciais ou híbridas.';
        if (field == 'modalities') return 'Escolha ao menos uma modalidade de trabalho.';
        if (field == 'code') return 'Digite os 6 números enviados para o seu e-mail.';
        if (field.contains('phone')) return 'Informe o telefone com +55, DDD e número.';
        if (field == 'name') return 'Informe seu nome completo.';
        if (field == 'company_name') return 'Informe a razão social da empresa.';
      }
      return 'Confira os campos informados e tente novamente.';
    }
    final code = detail is Map ? detail['code'] : null;
    if (code == 'email_verification_required') return 'Confirme seu e-mail com o código de 6 dígitos antes de entrar.';
    final text = detail is String ? detail.toLowerCase() : '';
    if (status == 409) return 'Já existe um cadastro com este e-mail ou CNPJ. Entre na sua conta ou solicite um novo código.';
    if (text.contains('cnpj')) return 'O CNPJ informado não é válido. Confira os dados da empresa.';
    if (text.contains('premium')) return 'Esta funcionalidade está disponível para assinantes Premium.';
    if (text.contains('resume') || text.contains('currículo')) return 'Envie seu currículo PDF no perfil antes de se candidatar.';
    if (text.contains('privacy')) return 'Leia e aceite a versão atual da política de privacidade.';
    if (text.contains('expired') || text.contains('expir')) return 'Este código expirou. Solicite um novo código.';
    if (text.contains('verification') || text.contains('código')) return 'Não foi possível confirmar este código. Confira os números ou solicite outro.';
    switch (status) {
      case 400: return 'Não foi possível concluir a operação. Confira os dados informados.';
      case 401: return 'E-mail ou senha incorretos. Confira seus dados.';
      case 403: return 'Sua conta não tem acesso a esta funcionalidade.';
      case 404: return 'Este conteúdo não está mais disponível.';
      case 409: return 'Já existe um cadastro com esses dados, ou a operação já foi realizada.';
      case 413: return 'O arquivo é muito grande. Escolha um PDF de até 5 MB.';
      case 415: return 'Escolha um currículo no formato PDF.';
      case 422: return 'Confira os campos informados e tente novamente.';
      case 429: return 'Você fez várias tentativas. Aguarde um minuto e tente novamente.';
      default: return 'Não foi possível concluir agora. Tente novamente em instantes.';
    }
  }

  Future<void> login(String email, String password) async {
    final result = await request('POST', '/auth/login', {'email': email, 'password': password});
    _token = result['access_token'] as String;
    await storage.write(key: 'access_token', value: _token);
  }

  Future<void> upload(List<int> bytes) async {
    final boundary = 'vagou-${DateTime.now().microsecondsSinceEpoch}';
    final raw = http.Request('PUT', uri('/me/resume'));
    raw.headers.addAll({'Authorization': 'Bearer $_token', 'Content-Type': 'multipart/form-data; boundary=$boundary'});
    raw.bodyBytes = [...utf8.encode('--$boundary\r\nContent-Disposition: form-data; name="file"; filename="curriculo.pdf"\r\nContent-Type: application/pdf\r\n\r\n'), ...bytes, ...utf8.encode('\r\n--$boundary--\r\n')];
    try {
      final response = await client.send(raw).timeout(const Duration(seconds: 30));
      await decode(await http.Response.fromStream(response).timeout(const Duration(seconds: 30)));
    } on TimeoutException {
      throw const ApiException('O envio demorou mais que o esperado. Tente novamente.');
    } on http.ClientException {
      throw const ApiException('Não foi possível enviar o currículo. Confira a conexão.');
    }
  }

  Future<Uint8List> downloadPdf(String path) async {
    try {
      final response = await client.get(uri(path), headers: {
        if (_token != null) 'Authorization': 'Bearer $_token',
        'Accept': 'application/pdf',
      }).timeout(const Duration(seconds: 30));
      if (response.statusCode == 404) {
        throw const ApiException('Este currículo não está mais disponível. O candidato pode tê-lo atualizado ou removido.');
      }
      if (response.statusCode >= 400) {
        await decode(response);
        throw const ApiException('Não foi possível acessar este currículo.');
      }
      if (!(response.headers['content-type'] ?? '').startsWith('application/pdf')) {
        throw const ApiException('O currículo não está disponível em formato PDF.');
      }
      return response.bodyBytes;
    } on TimeoutException {
      throw const ApiException('O download demorou mais que o esperado. Tente novamente.');
    } on http.ClientException {
      throw const ApiException('Não foi possível baixar o currículo. Confira a conexão.');
    } on SocketException {
      throw const ApiException('Não conseguimos conectar para baixar o currículo.');
    }
  }

  Future<void> clear() async {
    _token = null;
    await storage.delete(key: 'access_token');
  }
}
