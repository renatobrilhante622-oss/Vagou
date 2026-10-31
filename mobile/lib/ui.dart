import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';

class Brand {
  static const navy = Color(0xFF102A43);
  static const teal = Color(0xFF087F8C);
  static const coral = Color(0xFFEF8354);
  static ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(seedColor: teal, brightness: brightness);
    return ThemeData(
      useMaterial3: true, brightness: brightness, colorScheme: scheme,
      scaffoldBackgroundColor: dark ? const Color(0xFF0B1520) : const Color(0xFFF3F6FA),
      appBarTheme: const AppBarTheme(centerTitle: false, elevation: 0, scrolledUnderElevation: 0),
      inputDecorationTheme: InputDecorationTheme(
        filled: true, fillColor: scheme.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: scheme.outlineVariant)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: scheme.outlineVariant)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: scheme.primary, width: 2)),
      ),
      filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(minimumSize: const Size(0, 52), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)))),
      outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(minimumSize: const Size(0, 48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)))),
      navigationBarTheme: NavigationBarThemeData(indicatorColor: scheme.primaryContainer, height: 74),
    );
  }
}

class BrandMark extends StatelessWidget {
  final double size;
  const BrandMark({super.key, this.size = 48});
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
    Container(width: size, height: size, alignment: Alignment.center, decoration: BoxDecoration(color: Brand.navy, borderRadius: BorderRadius.circular(size * .28)), child: Text('V!', style: TextStyle(color: const Color(0xFF17D6BA), fontSize: size * .57, fontWeight: FontWeight.w900, letterSpacing: -2))),
    const SizedBox(width: 12), Text('Vagou!', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900, letterSpacing: -1)),
  ]);
}

class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(20)});
  @override
  Widget build(BuildContext context) => Container(margin: const EdgeInsets.only(bottom: 16), padding: padding, decoration: BoxDecoration(
    color: Theme.of(context).colorScheme.surface, borderRadius: BorderRadius.circular(24),
    border: Border.all(color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: .5)),
    boxShadow: [BoxShadow(color: Brand.navy.withValues(alpha: .035), blurRadius: 18, offset: const Offset(0, 5))],
  ), child: child);
}

class SectionTitle extends StatelessWidget {
  final String title;
  final String? subtitle;
  const SectionTitle({super.key, required this.title, this.subtitle});
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.only(bottom: 18, top: 8), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(title, style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
    if (subtitle != null) ...[const SizedBox(height: 6), Text(subtitle!, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant))],
  ]));
}

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title, message;
  final VoidCallback? onRetry;
  const EmptyState({super.key, required this.icon, required this.title, required this.message, this.onRetry});
  @override
  Widget build(BuildContext context) => Center(child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
    Icon(icon, size: 52, color: Theme.of(context).colorScheme.primary), const SizedBox(height: 16),
    Text(title, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)), const SizedBox(height: 8),
    Text(message, textAlign: TextAlign.center),
    if (onRetry != null) Padding(padding: const EdgeInsets.only(top: 16), child: OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Tentar novamente'))),
  ])));
}

Future<void> friendlyError(BuildContext context, Object error) => showDialog<void>(context: context, builder: (context) => AlertDialog(
  icon: const Icon(Icons.info_outline_rounded, size: 34), title: const Text('Vamos tentar de novo?'),
  content: Text(error is ApiException ? error.message : 'Não foi possível concluir agora. Confira sua conexão e tente novamente.'),
  actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Entendi'))],
));

String statusLabel(String status) => const {
  'submitted': 'Enviada', 'reviewing': 'Em análise', 'interview': 'Entrevista', 'rejected': 'Não selecionada', 'hired': 'Contratação',
  'pending': 'Aguardando aprovação', 'approved': 'Aprovada', 'complete': 'Concluída', 'completed': 'Concluída', 'running': 'Em andamento', 'failed': 'Não concluída',
  'already_applied': 'Já enviada', 'requires_manual': 'Requer sua avaliação', 'missing_resume': 'Currículo pendente',
}[status] ?? status;

String formatDate(dynamic value) {
  final date = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  if (date == null) return 'Data não informada';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(date.day)}/${two(date.month)}/${date.year} • ${two(date.hour)}:${two(date.minute)}';
}

Future<void> externalLink(String value) async {
  final uri = Uri.tryParse(value);
  if (uri == null || !['http', 'https'].contains(uri.scheme) || !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
    throw const ApiException('Não foi possível abrir este endereço. Tente novamente.');
  }
}
