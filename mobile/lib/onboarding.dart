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
    (
      Icons.home_work_rounded,
      'Sua carreira merece um novo espaço.',
      'No Vagou!, candidatos e empresas se encontram com transparência. Faça-se sentir em casa.',
      'CONEXÕES QUE FAZEM SENTIDO'
    ),
    (
      Icons.auto_awesome_rounded,
      'Oportunidades com o seu perfil.',
      'Escolha cargo, salário, cidade e modalidade. Entenda sua compatibilidade e descubra o que desenvolver.',
      'MAIS CLAREZA PARA ESCOLHER'
    ),
    (
      Icons.shield_outlined,
      'Confiança em cada próximo passo.',
      'Confirme seu e-mail, acompanhe suas candidaturas e controle suas automações. Empresas publicam vagas sujeitas à aprovação.',
      'VOCÊ NO CONTROLE'
    ),
  ];
  @override
  void dispose() {
    pages.dispose();
    super.dispose();
  }

  Future<void> complete() async {
    setState(() => busy = true);
    try {
      await widget.onComplete();
    } catch (e) {
      if (mounted) {
        setState(() => busy = false);
        await friendlyError(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
          body: SafeArea(
              child: Column(children: [
        Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 16, 0),
            child: Row(children: [
              const Expanded(child: VagouBrandMark(size: 36)),
              TextButton(
                  onPressed: busy ? null : complete, child: const Text('Pular'))
            ])),
        Expanded(
            child: PageView.builder(
                controller: pages,
                onPageChanged: (v) => setState(() => page = v),
                itemCount: slides.length,
                itemBuilder: (context, index) {
                  final item = slides[index];
                  return LayoutBuilder(
                      builder: (context, constraints) => SingleChildScrollView(
                          padding: const EdgeInsets.all(24),
                          child: ConstrainedBox(
                              constraints: BoxConstraints(
                                  minHeight: (constraints.maxHeight - 48)
                                      .clamp(0, double.infinity)),
                              child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                        width: double.infinity,
                                        padding: const EdgeInsets.symmetric(
                                            vertical: 38),
                                        decoration: BoxDecoration(
                                            gradient: const LinearGradient(
                                                colors: [
                                                  Color(0xFF1E40AF),
                                                  Color(0xFF3B82F6)
                                                ]),
                                            borderRadius:
                                                BorderRadius.circular(28)),
                                        child: Column(children: [
                                          const VagouBrandMark(
                                              size: 72, showName: false),
                                          const SizedBox(height: 20),
                                          Icon(item.$1,
                                              size: 44, color: Colors.white),
                                          const SizedBox(height: 14),
                                          Text('0${index + 1} / 03',
                                              style: const TextStyle(
                                                  color: Colors.white70,
                                                  letterSpacing: 2))
                                        ])),
                                    const SizedBox(height: 28),
                                    Text(item.$4,
                                        style: const TextStyle(
                                            color: Brand.teal,
                                            letterSpacing: 1.3,
                                            fontWeight: FontWeight.w700,
                                            fontSize: 10)),
                                    const SizedBox(height: 12),
                                    Text(item.$2,
                                        style: Theme.of(context)
                                            .textTheme
                                            .headlineSmall
                                            ?.copyWith(
                                                fontWeight: FontWeight.w800,
                                                height: 1.2)),
                                    const SizedBox(height: 14),
                                    Text(item.$3,
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodyLarge
                                            ?.copyWith(height: 1.5)),
                                  ]))));
                })),
        Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 20),
            child: Column(children: [
              Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List.generate(
                      slides.length,
                      (index) => AnimatedContainer(
                          duration: const Duration(milliseconds: 250),
                          width: page == index ? 28 : 7,
                          height: 7,
                          margin: const EdgeInsets.symmetric(horizontal: 4),
                          decoration: BoxDecoration(
                              color: page == index
                                  ? Brand.teal
                                  : const Color(0xFFCBD5E1),
                              borderRadius: BorderRadius.circular(8))))),
              const SizedBox(height: 18),
              SizedBox(
                  width: double.infinity,
                  child: GradientAction(
                      onPressed: busy
                          ? null
                          : page == slides.length - 1
                              ? complete
                              : () => pages.nextPage(
                                  duration: const Duration(milliseconds: 350),
                                  curve: Curves.easeInOut),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        Flexible(
                            child: Text(page == slides.length - 1
                                ? 'Começar minha jornada'
                                : 'Continuar')),
                        const SizedBox(width: 10),
                        busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.arrow_forward_rounded)
                      ]))),
            ])),
      ])));
}
