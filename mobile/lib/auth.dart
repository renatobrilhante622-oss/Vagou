import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api.dart';
import 'ui.dart';
import 'company.dart';

class AuthScreen extends StatefulWidget {
  final Api api;
  final Future<void> Function() onAuthenticated;
  const AuthScreen({super.key, required this.api, required this.onAuthenticated});
  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final form = GlobalKey<FormState>();
  final email = TextEditingController(), password = TextEditingController(), name = TextEditingController();
  final cnpj = TextEditingController(), company = TextEditingController(), contact = TextEditingController(), phone = TextEditingController();
  bool register = false, consent = false, busy = false, obscure = true;
  String role = 'candidate';
  @override
  void dispose() { for (final c in [email, password, name, cnpj, company, contact, phone]) { c.dispose(); } super.dispose(); }
  String? requiredField(String? value) => value == null || value.trim().isEmpty ? 'Preencha este campo.' : null;
  String? emailValidator(String? value) => RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(value?.trim() ?? '') ? null : 'Informe um e-mail válido.';

  Future<bool> verify() async {
    final verified = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => VerificationScreen(api: widget.api, email: email.text.trim())));
    return verified == true;
  }

  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    if (register && !consent) { await friendlyError(context, const ApiException('Leia e aceite a política de privacidade para criar sua conta.')); return; }
    setState(() => busy = true);
    try {
      if (register) {
        final registration = await widget.api.request('POST', '/auth/register', {
          'email': email.text.trim(), 'password': password.text, 'name': name.text.trim(), 'role': role, 'privacy_version': '2026-01', 'consent': true,
          if (role == 'recruiter') ...{'company_cnpj': normalizeCnpj(cnpj.text), 'company_name': company.text.trim(), 'company_contact_email': contact.text.trim(), 'company_phone': phone.text.trim()},
        });
        if (!mounted) return;
        if (registration['delivery_status'] == 'retrying') {
          await friendlyError(context, const ApiException('O e-mail ainda não foi entregue; o sistema tentará novamente. Confira a caixa de entrada e solicite novo código após um minuto.'));
          if (!mounted) return;
        }
        if (registration['delivery_status'] == 'configuration_required') {
          await friendlyError(context, const ApiException('Sua conta foi criada, mas o serviço de e-mail ainda precisa ser configurado pelo operador. Após a ativação, solicite um novo código para confirmar seu cadastro.'));
          if (!mounted) return;
        }
        final verified = await verify();
        if (mounted && verified) { setState(() => register = false); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('E-mail confirmado. Entre com sua senha para continuar.'))); }
      } else {
        await widget.api.login(email.text.trim(), password.text);
        await widget.onAuthenticated();
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.code == 'email_verification_required') { if (await verify()) { await widget.api.login(email.text.trim(), password.text); await widget.onAuthenticated(); } }
      else { await friendlyError(context, e); }
    } catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => busy = false); }
  }

  Widget field(TextEditingController controller, String label, IconData icon, {TextInputType? type, String? Function(String?)? validator, bool secret = false}) => Padding(padding: const EdgeInsets.only(bottom: 16), child: TextFormField(
    controller: controller, enabled: !busy, onChanged: controller == email ? (_) => setState(() {}) : null, keyboardType: type, obscureText: secret && obscure, autocorrect: !secret, enableSuggestions: !secret,
    textInputAction: TextInputAction.next, validator: validator ?? requiredField,
    decoration: InputDecoration(labelText: label, prefixIcon: Icon(icon), suffixIcon: secret ? IconButton(onPressed: () => setState(() => obscure = !obscure), icon: Icon(obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined)) : null),
  ));

  @override
  Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 540), child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: AutofillGroup(child: Form(key: form, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    const SizedBox(height: 20), const BrandMark(size: 48), const SizedBox(height: 36),
    Text(register ? 'Um novo começo\npassa por aqui.' : 'Bom ter você\nde volta.', style: Theme.of(context).textTheme.headlineLarge?.copyWith(fontWeight: FontWeight.w900, height: 1.15)),
    const SizedBox(height: 12), Text(register ? 'Crie sua conta e conecte talento a oportunidades.' : 'Entre para acompanhar seus próximos passos.', style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant)),
    const SizedBox(height: 28),
    if (register) ...[
      SegmentedButton<String>(segments: const [ButtonSegment(value: 'candidate', icon: Icon(Icons.person_outline), label: Text('Candidato')), ButtonSegment(value: 'recruiter', icon: Icon(Icons.business_outlined), label: Text('Empresa'))], selected: {role}, onSelectionChanged: busy ? null : (v) => setState(() => role = v.first)),
      const SizedBox(height: 24), field(name, role == 'recruiter' ? 'Nome do responsável' : 'Nome completo', Icons.person_outline),
    ],
    field(email, 'E-mail de acesso', Icons.mail_outline_rounded, type: TextInputType.emailAddress, validator: emailValidator),
    field(password, 'Senha', Icons.lock_outline_rounded, secret: true, validator: (v) => v == null || v.isEmpty ? 'Informe sua senha.' : register && v.length < 12 ? 'Use no mínimo 12 caracteres.' : null),
    if (register && role == 'recruiter') ...[
      const SectionTitle(title: 'Sua empresa', subtitle: 'Esses dados ajudam a criar um ambiente de confiança.'),
      field(cnpj, 'CNPJ', Icons.badge_outlined, validator: (v) => validCnpj(v ?? '') ? null : 'Confira os 14 caracteres e os dígitos verificadores do CNPJ.'),
      field(company, 'Razão social', Icons.business_outlined),
      field(contact, 'E-mail corporativo', Icons.alternate_email, type: TextInputType.emailAddress, validator: emailValidator),
      field(phone, 'Contato corporativo (+55 e DDD)', Icons.phone_outlined, type: TextInputType.phone, validator: (v) => RegExp(r'^\+55\d{10,11}$').hasMatch(v ?? '') ? null : 'Use +55 seguido de DDD e número.'),
    ],
    if (register) Row(crossAxisAlignment: CrossAxisAlignment.center, children: [Checkbox(value: consent, onChanged: busy ? null : (v) => setState(() => consent = v ?? false)), Expanded(child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [const Text('Li e aceito a '), TextButton(onPressed: () => showPrivacy(context), child: const Text('política de privacidade'))]))]),
    SizedBox(width: double.infinity, child: FilledButton(onPressed: busy ? null : submit, child: busy ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)) : Text(register ? 'Criar conta e confirmar e-mail' : 'Entrar na minha conta'))),
    const SizedBox(height: 12), Center(child: TextButton(onPressed: busy ? null : () => setState(() { register = !register; form.currentState?.reset(); }), child: Text(register ? 'Já tenho conta · Entrar' : 'Ainda não tem conta? Cadastre-se'))),
    if (!register) Center(child: TextButton(onPressed: busy || emailValidator(email.text) != null ? null : verify, child: const Text('Confirmar meu e-mail'))),
    const SizedBox(height: 20), const Center(child: Text('Seu talento. Seu espaço. Seu próximo passo.', textAlign: TextAlign.center)),
  ]))))))));
}

Future<void> showPrivacy(BuildContext context) => showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, builder: (context) => SafeArea(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
  const SectionTitle(title: 'Privacidade e controle', subtitle: 'Versão 2026-01'),
  const Text('O Vagou! utiliza seus dados de cadastro, currículo e critérios para operar sua conta, recomendar oportunidades e registrar candidaturas. Ao se candidatar, você autoriza o acesso do recrutador responsável ao currículo atual.\n\nA automação é opcional e exige autorização específica. Você pode atualizar suas preferências, desativar a automação e excluir sua conta no aplicativo. As empresas fornecem dados corporativos, confirmam o e-mail e têm suas vagas submetidas à moderação.\n\nCursos são acessados nos sites oficiais dos provedores, que possuem políticas próprias. O aceite desta versão fica registrado junto à sua conta. Consulte o operador da plataforma para informações sobre retenção, direitos do titular e o canal de atendimento.'),
  const SizedBox(height: 24), SizedBox(width: double.infinity, child: FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Entendi'))),
]))));

class VerificationScreen extends StatefulWidget {
  final Api api;
  final String email;
  const VerificationScreen({super.key, required this.api, required this.email});
  @override
  State<VerificationScreen> createState() => _VerificationScreenState();
}
class _VerificationScreenState extends State<VerificationScreen> {
  final code = TextEditingController();
  bool busy = false;
  @override
  void dispose() { code.dispose(); super.dispose(); }
  Future<void> send(bool resend) async {
    if (!resend && !RegExp(r'^\d{6}$').hasMatch(code.text)) { await friendlyError(context, const ApiException('Digite os 6 números enviados para seu e-mail.')); return; }
    setState(() => busy = true);
    try {
      final response = await widget.api.request('POST', resend ? '/auth/resend-verification' : '/auth/verify-email', {'email': widget.email, if (!resend) 'code': code.text});
      if (!mounted) return;
      if (resend) {
        if (response is Map && response['delivery_status'] == 'configuration_required') {
          await friendlyError(context, const ApiException('O envio de e-mails ainda precisa ser configurado pelo operador. Após a ativação, solicite um novo código.'));
        } else { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Se o cadastro estiver pendente, um novo código será enviado. Confira também o spam.'))); }
      }
      else { Navigator.pop(context, true); }
    } catch (e) { if (mounted) await friendlyError(context, e); }
    finally { if (mounted) setState(() => busy = false); }
  }
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Confirme seu e-mail')), body: ListView(padding: const EdgeInsets.all(24), children: [
    const SizedBox(height: 28), const Icon(Icons.mark_email_read_outlined, size: 76, color: Brand.teal), const SizedBox(height: 28),
    const SectionTitle(title: 'Quase lá!', subtitle: 'Digite o código de 6 dígitos recebido por e-mail. Confira sua caixa de entrada e a pasta de spam.'),
    Text(widget.email, style: Theme.of(context).textTheme.titleMedium, textAlign: TextAlign.center), const SizedBox(height: 28),
    TextField(controller: code, enabled: !busy, keyboardType: TextInputType.number, maxLength: 6, textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineMedium?.copyWith(letterSpacing: 12), inputFormatters: [FilteringTextInputFormatter.digitsOnly], decoration: const InputDecoration(labelText: 'Código de confirmação', counterText: '')),
    const SizedBox(height: 20), FilledButton(onPressed: busy ? null : () => send(false), child: busy ? const CircularProgressIndicator() : const Text('Confirmar e-mail')),
    TextButton(onPressed: busy ? null : () => send(true), child: const Text('Não recebi · Enviar novo código')),
    const Text('O código expira em 10 minutos. Aguarde pelo menos um minuto antes de solicitar outro.', textAlign: TextAlign.center),
  ]));
}
