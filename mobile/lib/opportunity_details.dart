import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';
import 'preferences.dart';
import 'ui.dart';

String opportunityValue(Map row, List<String> fields, [String fallback = '']) {
  for (final field in fields) {
    final value = row[field]?.toString().trim();
    if (value != null && value.isNotEmpty) return value;
  }
  return fallback;
}

String opportunityLocation(Map row) {
  final city = opportunityValue(row, const ['city']);
  final state = opportunityValue(row, const ['state']);
  if (city.isNotEmpty && state.isNotEmpty) return '$city / $state';
  return opportunityValue(row, const ['location'], 'Localização não informada');
}

String opportunityModality(dynamic value) =>
    const {
      'remote': 'Remoto Brasil',
      'remoto': 'Remoto Brasil',
      'hybrid': 'Híbrido',
      'hibrido': 'Híbrido',
      'híbrido': 'Híbrido',
      'onsite': 'Presencial',
      'presencial': 'Presencial',
    }[value?.toString()] ??
    'Modalidade não informada';

String opportunitySalary(Map row) {
  final minimum = num.tryParse('${row['salary_min']}') ?? 0;
  final maximum = num.tryParse('${row['salary_max']}') ?? 0;
  String amount(num value) => value
      .toStringAsFixed(value == value.roundToDouble() ? 0 : 2)
      .replaceAll('.', ',');
  if (minimum <= 0 && maximum <= 0) return 'Faixa salarial não informada';
  if (minimum <= 0) return 'Até R\$ ${amount(maximum)}';
  if (maximum <= 0 || minimum == maximum) return 'R\$ ${amount(minimum)}';
  return 'R\$ ${amount(minimum)} a R\$ ${amount(maximum)}';
}

/// Events used to repeat their reasons in both `match_reasons` and `detail`.
/// Split only sentence/semicolon separators, preserving technology names.
List<String> uniqueOpportunityReasons(dynamic reasons, {String? detail}) {
  final values = <String>[
    if (reasons is List) ...reasons.map((value) => value.toString()),
    if (detail != null && detail.trim().isNotEmpty) detail,
  ];
  final seen = <String>{};
  final result = <String>[];
  for (final value in values) {
    for (final part in value.split(RegExp(r'[;·]\s*|(?<=[.!?])\s+'))) {
      final text = part.replaceAll(RegExp(r'\s+'), ' ').trim();
      final key = text.toLowerCase().replaceAll(RegExp(r'[.!?]+$'), '');
      if (key.isNotEmpty && seen.add(key)) result.add(text);
    }
  }
  return result;
}

class OpportunityReasons extends StatelessWidget {
  const OpportunityReasons({super.key, required this.row});
  final Map row;
  @override
  Widget build(BuildContext context) {
    final reasons = uniqueOpportunityReasons(row['match_reasons'],
        detail: row['detail']?.toString());
    return reasons.isEmpty
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(reasons.join(' · '),
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
          );
  }
}

/// A shared presentation for feed cards, round events and report history.
/// Missing metadata stays explicit, including records from older executions.
class OpportunityDetails extends StatefulWidget {
  const OpportunityDetails(
      {super.key,
      required this.row,
      this.showHeader = true,
      this.initiallyExpanded = false,
      this.showReasons = true,
      this.showScore = true});
  final Map row;
  final bool showHeader, initiallyExpanded, showReasons, showScore;
  @override
  State<OpportunityDetails> createState() => _OpportunityDetailsState();
}

class _OpportunityDetailsState extends State<OpportunityDetails> {
  late bool expanded = widget.initiallyExpanded;

  Future<void> _email(String email) async {
    try {
      if (!await launchUrl(Uri(scheme: 'mailto', path: email),
          mode: LaunchMode.externalApplication)) {
        throw const ApiException(
            'Não foi possível abrir seu aplicativo de e-mail. Você pode copiar o endereço.');
      }
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    }
  }

  Future<void> _copy(String email) async {
    await Clipboard.setData(ClipboardData(text: email));
    if (mounted)
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('E-mail da vaga copiado.')));
  }

  Future<void> _open(String link) async {
    try {
      await externalLink(link);
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final row = widget.row;
    final title =
        opportunityValue(row, const ['title', 'job_title'], 'Oportunidade');
    final company = opportunityValue(
        row, const ['company_name', 'company'], 'Empresa não informada');
    final source = opportunityValue(row, const ['source_name'], 'Vagou!');
    final contact =
        opportunityValue(row, const ['contact_email', 'recruiter_email']);
    final link =
        opportunityValue(row, const ['external_url', 'source_url', 'job_url']);
    final uri = Uri.tryParse(link);
    final publicLink = uri != null &&
        ['https', 'http'].contains(uri.scheme) &&
        uri.host.isNotEmpty;
    final contract = opportunityValue(row, const ['contract_type']);
    final description = opportunityValue(
        row, const ['description', 'job_description', 'description_summary']);
    final search = row['status'] == 'search_channel';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (widget.showHeader) ...[
        Text(title,
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text('$company · ${opportunityLocation(row)}'),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 4, children: [
        if (!search && widget.showScore && row['match_score'] != null)
          Chip(label: Text('${row['match_score']}% de compatibilidade')),
        Chip(label: Text(source)),
        if (row['status'] != null)
          Chip(
              label: Text(const {
                    'search_channel': 'Busca no portal',
                    'limit_reached': 'Limite da rodada'
                  }[row['status']] ??
                  statusLabel('${row['status']}'))),
        if (row['modality'] != null)
          Chip(label: Text(opportunityModality(row['modality']))),
        if (contract.isNotEmpty)
          Chip(label: Text(contractLabels[contract] ?? contract.toUpperCase())),
      ]),
      if (!search) ...[
        const SizedBox(height: 6),
        if (!widget.showHeader) Text(opportunityLocation(row)),
        Text(opportunitySalary(row),
            style: const TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        Text('Resumo da vaga',
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Text(
            description.isEmpty
                ? 'Descrição não disponível neste registro. Consulte os detalhes da oportunidade.'
                : description,
            maxLines: expanded ? null : 3,
            overflow: expanded ? null : TextOverflow.ellipsis),
        if (description.isNotEmpty)
          TextButton.icon(
            onPressed: () => setState(() => expanded = !expanded),
            icon: Icon(expanded ? Icons.expand_less : Icons.expand_more),
            label: Text(expanded
                ? 'Recolher descrição'
                : row['title'] != null
                    ? 'Ver descrição completa'
                    : 'Expandir resumo'),
          ),
      ],
      if (widget.showReasons) OpportunityReasons(row: row),
      if (contact.isNotEmpty) ...[
        const SizedBox(height: 14),
        Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
                color: Brand.teal.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(12)),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('📧 E-mail da vaga',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              SelectableText(contact),
              Wrap(spacing: 8, runSpacing: 4, children: [
                TextButton.icon(
                    onPressed: () => _email(contact),
                    icon: const Icon(Icons.mail_outline),
                    label: const Text('Enviar e-mail')),
                TextButton.icon(
                    onPressed: () => _copy(contact),
                    icon: const Icon(Icons.copy_outlined),
                    label: const Text('Copiar e-mail')),
              ]),
            ])),
      ],
      if (publicLink) ...[
        const SizedBox(height: 8),
        Text('🔗 Fonte: $source',
            style: const TextStyle(fontWeight: FontWeight.w700)),
        TextButton.icon(
            onPressed: () => _open(link),
            icon: const Icon(Icons.open_in_new),
            label: const Text('Abrir link oficial')),
      ],
    ]);
  }
}
