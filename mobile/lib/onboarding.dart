import 'package:flutter/material.dart';
import 'ui.dart';

class OnboardingScreen extends StatefulWidget {
  final Future<void> Function() onComplete;
  const OnboardingScreen({super.key, required this.onComplete});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final pages = PageController();
  int page = 0;
  bool busy = false;
  static const slides = [
    (Icons.home_work_rounded, 'Sua carreira merece um novo espaço.', 'No Vagou!, candidatos e empresas se encontram com transparência. Faça-se sentir em casa.', 'CONEXÕES QUE FAZEM SENTIDO'),
    (Icons.auto_awesome_rounded, 'Oportunidades com o seu perfil.', 'Escolha cargo, salário, cidade e modalidade. Entenda sua compatibilidade e descubra o que desenvolver.', 'MAIS CLAREZA PARA ESCOLHER'),
    (Icons.shield_outlined, 'Confiança em cada próximo passo.', 'Confirme seu e-mail, acompanhe suas candidaturas e controle suas automações. Empresas publicam vagas sujeitas à aprovação.', 'VOCÊ NO CONTROLE'),
  ];
  @override
  void dispose() { pages.dispose(); super.dispose(); }
  Future<void> complete() async {
    setState(() => busy = true);
    try { await widget.onComplete(); }
    catch (e) { if (mounted) { setState(() => busy = false); await friendlyError(context, e); } }
  }
  @override
  Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Column(children: [
    Padding(padding: const EdgeInsets.fromLTRB(24, 20, 16, 0), child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const BrandMark(size: 38), TextButton(onPressed: busy ? null : complete, child: const Text('Pular'))])),
    Expanded(child: PageView.builder(controller: pages, onPageChanged: (v) => setState(() => page = v), itemCount: slides.length, itemBuilder: (context, index) {
      final item = slides[index];
      return Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Center(child: Stack(alignment: Alignment.center, children: [
          Container(width: 240, height: 240, decoration: BoxDecoration(shape: BoxShape.circle, color: Brand.teal.withValues(alpha: .08))),
          Container(width: 188, height: 188, decoration: BoxDecoration(color: Theme.of(context).colorScheme.surface, borderRadius: BorderRadius.circular(44), boxShadow: [BoxShadow(color: Brand.teal.withValues(alpha: .12), blurRadius: 35, offset: const Offset(0, 16))]), child: Icon(item.$1, size: 94, color: Brand.teal)),
          const Positioned(top: 12, right: 4, child: CircleAvatar(backgroundColor: Brand.coral, radius: 24, child: Icon(Icons.check_rounded, color: Colors.white))),
        ])),
        const SizedBox(height: 48), Text(item.$4, style: const TextStyle(color: Brand.teal, letterSpacing: 1.4, fontWeight: FontWeight.w800, fontSize: 11)),
        const SizedBox(height: 14), Text(item.$2, style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900, height: 1.15)),
        const SizedBox(height: 18), Text(item.$3, style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.6)),
      ]));
    })),
    Padding(padding: const EdgeInsets.all(28), child: Column(children: [
      Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(slides.length, (index) => AnimatedContainer(duration: const Duration(milliseconds: 250), width: page == index ? 32 : 8, height: 8, margin: const EdgeInsets.symmetric(horizontal: 4), decoration: BoxDecoration(color: page == index ? Brand.teal : Brand.teal.withValues(alpha: .2), borderRadius: BorderRadius.circular(8))))),
      const SizedBox(height: 24), SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: busy ? null : page == slides.length - 1 ? complete : () => pages.nextPage(duration: const Duration(milliseconds: 350), curve: Curves.easeInOut), icon: busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.arrow_forward_rounded), label: Text(page == slides.length - 1 ? 'Começar minha jornada' : 'Continuar'))),
    ])),
  ])));
}
