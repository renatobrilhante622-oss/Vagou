import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';

class Brand {
  static const navy = Color(0xFF0F172A);
  static const teal = Color(0xFF2563EB);
  static const coral = Color(0xFFEF8354);
  static ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme =
        ColorScheme.fromSeed(seedColor: teal, brightness: brightness).copyWith(
      primary: dark ? const Color(0xFF93C5FD) : navy,
      secondary: teal,
      surface: dark ? const Color(0xFF131F2E) : Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor:
          dark ? const Color(0xFF0B1520) : const Color(0xFFF8FAFC),
      appBarTheme: AppBarTheme(
          centerTitle: false,
          elevation: 0,
          scrolledUnderElevation: 0,
          backgroundColor: scheme.surface,
          shape: const Border(bottom: BorderSide(color: Color(0xFFE2E8F0)))),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? scheme.surface : const Color(0xFFF8FAFC),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: scheme.outlineVariant)),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: scheme.outlineVariant)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: teal, width: 2)),
      ),
      filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
              minimumSize: const Size(0, 52),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)))),
      outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
              minimumSize: const Size(0, 48),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)))),
      navigationBarTheme: NavigationBarThemeData(
          backgroundColor: scheme.surface,
          indicatorColor: const Color(0xFFDBEAFE),
          iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
              color: states.contains(WidgetState.selected)
                  ? teal
                  : const Color(0xFF64748B))),
          height: 68),
    );
  }
}

class VagouBrandMark extends StatelessWidget {
  final double size;
  final bool premium, showName;
  const VagouBrandMark(
      {super.key, this.size = 48, this.premium = false, this.showName = true});
  @override
  Widget build(BuildContext context) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Semantics(
            label: 'Vagou! Conexões profissionais',
            child: Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                    gradient: const LinearGradient(
                        colors: [Color(0xFF1E40AF), Color(0xFF3B82F6)]),
                    borderRadius: BorderRadius.circular(size * .28),
                    boxShadow: [
                      BoxShadow(
                          color: Brand.teal.withValues(alpha: .18),
                          blurRadius: 14,
                          offset: const Offset(0, 4))
                    ]),
                child: CustomPaint(painter: _VagouMarkPainter()))),
        if (showName) ...[
          const SizedBox(width: 10),
          Flexible(
              child: Text('Vagou!',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800, letterSpacing: -.7)))
        ],
        if (premium) ...[
          const SizedBox(width: 6),
          Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
              decoration: BoxDecoration(
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFD6B35A))),
              child: const Text('PRO',
                  style: TextStyle(
                      color: Color(0xFF047857),
                      fontWeight: FontWeight.w800,
                      fontSize: 10)))
        ],
      ]);
}

class _VagouMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 100, size.height / 100);
    final stroke = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 9
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(
        Path()
          ..moveTo(25, 39)
          ..lineTo(43, 66)
          ..lineTo(72, 28),
        stroke);
    canvas.drawPath(
        Path()
          ..moveTo(59, 28)
          ..lineTo(72, 28)
          ..lineTo(72, 41),
        Paint()
          ..color = const Color(0xFFBFDBFE)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 6
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round);
    canvas.drawCircle(
        const Offset(27, 24), 4, Paint()..color = const Color(0xFFBFDBFE));
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _VagouMarkPainter oldDelegate) => false;
}

// Compatibility entry point retained for existing screens and integrations.
class BrandMark extends StatelessWidget {
  final double size;
  const BrandMark({super.key, this.size = 48});
  @override
  Widget build(BuildContext context) => VagouBrandMark(size: size);
}

class ExecutiveHero extends StatelessWidget {
  final String title, subtitle, eyebrow;
  final Widget? trailing;
  const ExecutiveHero(
      {super.key,
      required this.title,
      required this.subtitle,
      this.eyebrow = 'VAGOU! WORKSPACE',
      this.trailing});
  @override
  Widget build(BuildContext context) => Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
          gradient: const LinearGradient(
              colors: [Color(0xFF0F172A), Color(0xFF1E293B)]),
          borderRadius: BorderRadius.circular(18)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(eyebrow,
            style: const TextStyle(
                color: Color(0xFF93C5FD),
                fontSize: 10,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
              child: Text(title,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      height: 1.25,
                      fontWeight: FontWeight.w700))),
          if (trailing != null) ...[const SizedBox(width: 12), trailing!]
        ]),
        const SizedBox(height: 8),
        Text(subtitle,
            style: const TextStyle(color: Color(0xFFCBD5E1), height: 1.5)),
      ]));
}

class ExecutiveMetric extends StatelessWidget {
  final String label, value;
  final IconData icon;
  const ExecutiveMetric(
      {super.key,
      required this.label,
      required this.value,
      required this.icon});
  @override
  Widget build(BuildContext context) => Panel(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
                color: Brand.teal.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(10)),
            child: Icon(icon, color: Brand.teal, size: 20)),
        const SizedBox(height: 12),
        Text(value,
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ]));
}

class CompanyAvatar extends StatelessWidget {
  final String company;
  const CompanyAvatar({super.key, required this.company});
  @override
  Widget build(BuildContext context) {
    final words = company
        .trim()
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .take(2);
    final initials =
        words.map((word) => word.substring(0, 1).toUpperCase()).join();
    return Container(
        width: 44,
        height: 44,
        alignment: Alignment.center,
        decoration: BoxDecoration(
            color: const Color(0xFFEFF6FF),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFDBEAFE))),
        child: Text(initials.isEmpty ? 'V' : initials,
            style: const TextStyle(
                fontWeight: FontWeight.w800, color: Color(0xFF1E40AF))));
  }
}

class GradientAction extends StatelessWidget {
  final VoidCallback? onPressed;
  final Widget child;
  const GradientAction(
      {super.key, required this.onPressed, required this.child});
  @override
  Widget build(BuildContext context) => DecoratedBox(
      decoration: BoxDecoration(
          gradient: LinearGradient(
              colors: onPressed == null
                  ? [Colors.grey.shade400, Colors.grey.shade500]
                  : const [Color(0xFF1E40AF), Color(0xFF3B82F6)]),
          borderRadius: BorderRadius.circular(12)),
      child: FilledButton(
          style: FilledButton.styleFrom(
              backgroundColor: Colors.transparent,
              disabledBackgroundColor: Colors.transparent,
              foregroundColor: Colors.white,
              shadowColor: Colors.transparent),
          onPressed: onPressed,
          child: child));
}

class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  const Panel(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(20)});
  @override
  Widget build(BuildContext context) => Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: padding,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE2E8F0)),
        boxShadow: [
          BoxShadow(
              color: Brand.navy.withValues(alpha: .035),
              blurRadius: 12,
              offset: const Offset(0, 3))
        ],
      ),
      child: child);
}

class SectionTitle extends StatelessWidget {
  final String title;
  final String? subtitle;
  const SectionTitle({super.key, required this.title, this.subtitle});
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 12, top: 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontSize: 17, fontWeight: FontWeight.w700)),
        if (subtitle != null) ...[
          const SizedBox(height: 6),
          Text(subtitle!,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant))
        ],
      ]));
}

String formatBrlAmount(dynamic value) {
  final amount = num.tryParse('${value ?? ''}'.trim().replaceAll(',', '.'));
  if (amount == null) return '0';
  final fixed =
      amount.abs().toStringAsFixed(amount == amount.roundToDouble() ? 0 : 2);
  final parts = fixed.split('.');
  final digits = parts.first;
  final grouped = StringBuffer();
  for (var index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) grouped.write('.');
    grouped.write(digits[index]);
  }
  final sign = amount < 0 ? '-' : '';
  return '$sign$grouped${parts.length == 1 ? '' : ',${parts[1]}'}';
}

String formatBrlCurrency(dynamic value) => 'R\$ ${formatBrlAmount(value)}';

String formatSalaryRange(dynamic minimumValue, dynamic maximumValue) {
  final minimum = num.tryParse('${minimumValue ?? ''}') ?? 0;
  final maximum = num.tryParse('${maximumValue ?? ''}') ?? 0;
  if (minimum <= 0 && maximum <= 0) return 'Salário não informado';
  if (minimum <= 0) return 'Até ${formatBrlCurrency(maximum)}';
  if (maximum <= 0 || minimum == maximum) return formatBrlCurrency(minimum);
  return '${formatBrlCurrency(minimum)} a ${formatBrlCurrency(maximum)}';
}

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title, message;
  final VoidCallback? onRetry;
  const EmptyState(
      {super.key,
      required this.icon,
      required this.title,
      required this.message,
      this.onRetry});
  @override
  Widget build(BuildContext context) => Center(
      child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 52, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 16),
            Text(title,
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            if (onRetry != null)
              Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: OutlinedButton.icon(
                      onPressed: onRetry,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Tentar novamente'))),
          ])));
}

Future<void> friendlyError(BuildContext context, Object error) =>
    showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
              icon: const Icon(Icons.info_outline_rounded, size: 34),
              title: const Text('Vamos tentar de novo?'),
              content: Text(error is ApiException
                  ? error.message
                  : 'Não foi possível concluir agora. Confira sua conexão e tente novamente.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Entendi'))
              ],
            ));

String statusLabel(String status) =>
    const {
      'submitted': 'Enviada',
      'reviewing': 'Em análise',
      'interview': 'Entrevista',
      'rejected': 'Não selecionada',
      'hired': 'Contratação',
      'pending': 'Aguardando aprovação',
      'approved': 'Aprovada',
      'queued': 'Na fila',
      'complete': 'Concluída',
      'completed': 'Concluída',
      'running': 'Em andamento',
      'failed': 'Não concluída',
      'cancelled': 'Cancelada',
      'already_applied': 'Já enviada',
      'requires_manual': 'Encaminhada ao portal oficial',
      'possible_match': 'Possível match',
      'missing_resume': 'Currículo pendente',
      'filtered': 'Descartada pelos filtros',
    }[status] ??
    status;

String formatDate(dynamic value) {
  final date = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (date == null) return 'Data não informada';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}/${two(date.month)}/${date.year} • ${two(date.hour)}:${two(date.minute)}';
}

Future<void> externalLink(String value) async {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !['http', 'https'].contains(uri.scheme) ||
      !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
    throw const ApiException(
        'Não foi possível abrir este endereço. Tente novamente.');
  }
}
