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
  final salary = formatSalaryRange(row['salary_min'], row['salary_max']);
  return salary == 'Salário não informado'
      ? 'Faixa salarial não informada'
      : salary;
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
    final labels = <String>[];
    for (final reason in reasons) {
      final text = reason.toLowerCase();
      final label = text.contains('cargo compatível')
          ? '✓ Cargo Compatível'
          : text.contains('cidade/uf compat') ||
                  text.contains('localização compat')
              ? '✓ ${opportunityLocation(row)}'
              : text.contains('%') ||
                      text.contains('palavras-chave') ||
                      text.contains('pendentes') ||
                      text.contains('inferidas') ||
                      reason.length > 65
                  ? null
                  : reason;
      if (label != null && !labels.contains(label)) labels.add(label);
    }
    return labels.isEmpty
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(spacing: 6, runSpacing: 4, children: [
              for (final label in labels.take(3))
                Chip(
                    visualDensity: VisualDensity.compact,
                    label: Text(label, softWrap: true))
            ]),
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
    final description = opportunityValue(row,
            const ['description', 'job_description', 'description_summary'])
        .replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll(RegExp(r'\s+'), ' ')
        .replaceAllMapped(RegExp(r':(?=[A-Za-zÀ-ÿ])'), (m) => ': ')
        .trim();
    final search = row['status'] == 'search_channel';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (widget.showHeader) ...[
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CompanyAvatar(company: company),
          const SizedBox(width: 12),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text('$company · ${opportunityLocation(row)}',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: Theme.of(context).colorScheme.onSurfaceVariant)),
                const SizedBox(height: 8),
                Text(title,
                    style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        height: 1.3)),
              ]))
        ]),
      ],
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 4, children: [
        if (!search && widget.showScore && row['match_score'] != null)
          Chip(
              backgroundColor:
                  (num.tryParse('${row['match_score']}') ?? 0) >= 70
                      ? const Color(0xFFECFDF5)
                      : const Color(0xFFFFFBEB),
              labelStyle: TextStyle(
                  color: (num.tryParse('${row['match_score']}') ?? 0) >= 70
                      ? const Color(0xFF059669)
                      : const Color(0xFFD97706),
                  fontWeight: FontWeight.w700),
              label: Text('${row['match_score']}% de compatibilidade')),
        Chip(label: Text(source)),
        if (row['status'] != null)
          Chip(
              label: Text(const {
                    'search_channel': 'Busca no portal',
                    'limit_reached': 'Limite da rodada'
                  }[row['status']] ??
                  statusLabel('${row['status']}'))),
        if (row['modality'] != null)
          Chip(
              avatar: const Icon(Icons.location_on_outlined, size: 16),
              label: Text(opportunityModality(row['modality']))),
        if (contract.isNotEmpty)
          Chip(
              avatar: const Icon(Icons.business_center_outlined, size: 16),
              label: Text(contractLabels[contract] ?? contract.toUpperCase())),
      ]),
      if (!search) ...[
        const SizedBox(height: 6),
        if (!widget.showHeader) Text(opportunityLocation(row)),
        Chip(
            avatar: const Icon(Icons.payments_outlined, size: 16),
            label: Text(opportunitySalary(row),
                style: const TextStyle(fontWeight: FontWeight.w600))),
        const SizedBox(height: 12),
        Text('Resumo da vaga',
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
                color: Theme.of(context).brightness == Brightness.dark
                    ? const Color(0xFF1E293B)
                    : const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE2E8F0))),
            child: Text(
                description.isEmpty
                    ? 'Descrição não disponível neste registro. Consulte os detalhes da oportunidade.'
                    : description,
                maxLines: expanded ? null : 3,
                overflow: expanded ? null : TextOverflow.ellipsis)),
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
              const Text('📧 E-mail RH',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              const Text('Canal direto do RH', style: TextStyle(fontSize: 11)),
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

/// Only essential information belongs in the feed. Full data lives in the sheet.
class OpportunitySummary extends StatelessWidget {
  final Map row;
  final VoidCallback onTap;
  const OpportunitySummary({super.key, required this.row, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final company =
        opportunityValue(row, const ['company', 'company_name'], 'Empresa');
    final score = row['match_score'];
    return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Material(
            color: Theme.of(context).colorScheme.surface,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: const BorderSide(color: Color(0xFFE2E8F0))),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
                onTap: onTap,
                child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                CompanyAvatar(company: company),
                                const SizedBox(width: 10),
                                Expanded(
                                    child: Text(company,
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w600))),
                                if (score is num) ...[
                                  const SizedBox(width: 6),
                                  Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 5),
                                      decoration: BoxDecoration(
                                          color: score >= 70
                                              ? const Color(0xFFECFDF5)
                                              : const Color(0xFFFFFBEB),
                                          borderRadius:
                                              BorderRadius.circular(8)),
                                      child: Text('${score.round()}%',
                                          style: TextStyle(
                                              fontWeight: FontWeight.w700,
                                              color: score >= 70
                                                  ? const Color(0xFF059669)
                                                  : const Color(0xFFD97706))))
                                ],
                                if (row['company_verified'] == true)
                                  const Padding(
                                      padding: EdgeInsets.only(left: 6),
                                      child: Tooltip(
                                          message: 'Empresa Verificada',
                                          child: Icon(Icons.verified,
                                              size: 20, color: Brand.teal))),
                              ]),
                          const SizedBox(height: 10),
                          Text(
                              opportunityValue(row,
                                  const ['title', 'job_title'], 'Oportunidade'),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleMedium
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                          const SizedBox(height: 8),
                          SingleChildScrollView(
                              scrollDirection: Axis.horizontal,
                              child: Text(
                                  '📍 ${opportunityLocation(row)}  •  💼 ${opportunityModality(row['modality'])}  •  💰 ${opportunitySalary(row)}',
                                  maxLines: 1,
                                  style:
                                      Theme.of(context).textTheme.bodySmall)),
                        ])))));
  }
}
