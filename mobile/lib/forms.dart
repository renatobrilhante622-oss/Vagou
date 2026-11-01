import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

String formatBrazilPhone(String input) {
  var digits = input.replaceAll(RegExp(r'\D'), '');
  if (input.trimLeft().startsWith('+55') ||
      digits.length > 11 && digits.startsWith('55'))
    digits = digits.substring(2);
  if (digits.length > 11) digits = digits.substring(0, 11);
  if (digits.isEmpty) return '+55 ';
  if (digits.length < 3) return '+55 ($digits';
  final local = digits.substring(2);
  final split = local.length > 8 ? 5 : 4;
  return '+55 (${digits.substring(0, 2)}) ${local.length > split ? '${local.substring(0, split)}-${local.substring(split)}' : local}';
}

String? brazilPhonePayload(String input) {
  final digits = input.replaceAll(RegExp(r'\D'), '');
  return digits.length <= 2 ? null : '+$digits';
}

class BrazilPhoneFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    final text = formatBrazilPhone(newValue.text);
    return TextEditingValue(
        text: text, selection: TextSelection.collapsed(offset: text.length));
  }
}

String birthDateDisplay(dynamic value) {
  final date = DateTime.tryParse('$value');
  return date == null
      ? ''
      : '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year}';
}

class CandidateDetailsFields extends StatelessWidget {
  final Map<String, TextEditingController> controllers;
  final bool enabled;
  const CandidateDetailsFields(
      {super.key, required this.controllers, this.enabled = true});
  @override
  Widget build(BuildContext context) => Column(children: [
        for (final item in const [
          (
            'birth_date',
            'Data de Nascimento (DD/MM/AAAA)',
            Icons.cake_outlined
          ),
          ('cpf', 'CPF (opcional)', Icons.badge_outlined),
          ('candidate_city', 'Cidade', Icons.location_city),
          ('candidate_state', 'UF', Icons.map_outlined),
          ('linkedin_url', 'LinkedIn (https://...)', Icons.link),
          (
            'desired_salary',
            'Pretensão Salarial (R\$)',
            Icons.payments_outlined
          ),
          (
            'professional_summary',
            'Resumo profissional',
            Icons.description_outlined
          )
        ])
          Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: TextFormField(
                  controller: controllers[item.$1],
                  enabled: enabled,
                  maxLines: item.$1 == 'professional_summary' ? 3 : 1,
                  keyboardType: item.$1 == 'desired_salary'
                      ? const TextInputType.numberWithOptions(decimal: true)
                      : item.$1 == 'birth_date'
                          ? TextInputType.datetime
                          : TextInputType.text,
                  decoration: InputDecoration(
                      labelText: item.$2, prefixIcon: Icon(item.$3)))),
        DropdownButtonFormField<String>(
            isExpanded: true,
            initialValue: controllers['seniority']!.text.isEmpty
                ? null
                : controllers['seniority']!.text,
            decoration: const InputDecoration(
                labelText: 'Senioridade',
                prefixIcon: Icon(Icons.stairs_outlined)),
            items: [
              for (final item in const [
                ('estagio', 'Estágio'),
                ('junior', 'Júnior'),
                ('pleno', 'Pleno'),
                ('senior', 'Sênior'),
                ('especialista', 'Especialista'),
                ('gestor', 'Gestão')
              ])
                DropdownMenuItem(value: item.$1, child: Text(item.$2))
            ],
            onChanged: enabled
                ? (value) => controllers['seniority']!.text = value ?? ''
                : null),
      ]);
}

Map<String, dynamic> candidateDetailsPayload(
        Map<String, TextEditingController> fields) =>
    {
      for (final entry in fields.entries)
        entry.key: entry.key == 'desired_salary'
            ? (num.tryParse(entry.value.text.contains(',')
                    ? entry.value.text.replaceAll('.', '').replaceAll(',', '.')
                    : entry.value.text) ??
                0)
            : entry.value.text.trim().isEmpty
                ? null
                : entry.value.text.trim()
    };
Future<void> requireResume(BuildContext context) => showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
            icon: const Icon(Icons.upload_file),
            title: const Text('Currículo PDF obrigatório'),
            content: const Text(
                'Envie seu currículo PDF na aba Perfil antes de se candidatar ou iniciar o robô.'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Ir ao Perfil e enviar PDF'))
            ]));
