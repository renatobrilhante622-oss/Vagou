import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api.dart';

void main() => runApp(const VagouApp());
final api = Api();

class VagouApp extends StatelessWidget {
  const VagouApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Vagou!', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
    darkTheme: ThemeData(colorSchemeSeed: Colors.teal, brightness: Brightness.dark, useMaterial3: true),
    themeMode: ThemeMode.system, home: const LoginScreen(),
  );
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginState();
}

class _LoginState extends State<LoginScreen> {
  final email = TextEditingController();
  final password = TextEditingController();
  final name = TextEditingController();
  bool register = false, consent = false, busy = false;
  String role = 'candidate';
  String? error;
  @override
  void dispose() { email.dispose(); password.dispose(); name.dispose(); super.dispose(); }
  Future<void> submit() async {
    setState(() { busy = true; error = null; });
    try {
      if (register) {
        if (!consent) throw ApiException('Aceite a política de privacidade antes de continuar.');
        await api.request('POST', '/auth/register', {'email': email.text.trim(), 'password': password.text, 'name': name.text.trim(), 'role': role, 'consent': true, 'privacy_version': '2026-01'});
      }
      await api.login(email.text.trim(), password.text);
      if (mounted) Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeScreen()));
    } catch (e) { if (mounted) setState(() => error = '$e'); }
    finally { if (mounted) setState(() => busy = false); }
  }
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Vagou!')), body: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 480), child: ListView(padding: const EdgeInsets.all(24), shrinkWrap: true, children: [
    Text(register ? 'Crie sua conta' : 'Encontre sua próxima oportunidade', style: Theme.of(context).textTheme.headlineSmall),
    if (register) TextField(controller: name, decoration: const InputDecoration(labelText: 'Nome')),
    TextField(controller: email, keyboardType: TextInputType.emailAddress, autocorrect: false, decoration: const InputDecoration(labelText: 'E-mail')),
    TextField(controller: password, obscureText: true, enableSuggestions: false, autocorrect: false, decoration: const InputDecoration(labelText: 'Senha (mínimo 12 caracteres no cadastro)')),
    if (register) DropdownButton<String>(value: role, items: const [DropdownMenuItem(value: 'candidate', child: Text('Candidato')), DropdownMenuItem(value: 'recruiter', child: Text('Recrutador'))], onChanged: busy ? null : (v) => setState(() => role = v!)),
    if (register) CheckboxListTile(value: consent, title: const Text('Li e aceito a política de privacidade publicada pelo operador.'), onChanged: busy ? null : (v) => setState(() => consent = v ?? false)),
    if (error != null) Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
    const SizedBox(height: 16),
    if (busy) const Center(child: CircularProgressIndicator()) else FilledButton(onPressed: submit, child: Text(register ? 'Cadastrar' : 'Entrar')),
    TextButton(onPressed: busy ? null : () => setState(() => register = !register), child: Text(register ? 'Já tenho conta' : 'Criar conta')),
  ]))));
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeState();
}

class _HomeState extends State<HomeScreen> {
  int tab = 0;
  late Future<dynamic> data;
  final skills = TextEditingController(), phone = TextEditingController(), name = TextEditingController();
  final titles = TextEditingController(), salary = TextEditingController();
  bool automatic = false;
  String modality = 'remote';
  @override
  void initState() { super.initState(); reload(); }
  @override
  void dispose() { for (final c in [skills, phone, name, titles, salary]) { c.dispose(); } super.dispose(); }
  void reload() {
    data = api.request('GET', ['/matches', '/dashboard', '/courses', '/me'][tab]);
  }
  Future<void> action(Future<void> Function() callback) async {
    try { await callback(); if (mounted) { setState(reload); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Operação concluída.'))); } }
    catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e'))); }
  }
  List<String> terms(String value) => value.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
  Widget feed(dynamic result) => ListView(children: [
    const Padding(padding: EdgeInsets.all(16), child: Text('Compatibilidade considera as competências declaradas. Vagas descartadas não aparecem no feed.')),
    for (final item in result['items']) if (item['category'] != 'discarded') Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(item['job']['title'], style: Theme.of(context).textTheme.titleLarge),
      Text('${item['job']['company']} • ${item['job']['location']}'),
      Text('${item['match_score']}% • ${item['category'] == 'high' ? 'Match alto' : 'Observação'}'),
      Text(item['job']['description']),
      if ((item['missing_skills'] as List).isNotEmpty) Text('Competências a desenvolver: ${(item['missing_skills'] as List).join(', ')}'),
      FilledButton(onPressed: () => action(() async { await api.request('POST', '/jobs/${item['job']['id']}/applications'); }), child: const Text('Candidatar-me')),
    ]))),
    if (result['next_offset'] != null) TextButton(onPressed: () => setState(() { data = api.request('GET', '/matches?offset=${result['next_offset']}'); }), child: const Text('Próximas vagas')),
  ]);
  Widget dashboard(dynamic result) => ListView(padding: const EdgeInsets.all(16), children: [
    for (final entry in {'Candidaturas': result['total_applications'], 'Manuais': result['manual'], 'Automáticas': result['automatic'], 'Em observação': result['observation_jobs'], 'Compatibilidade média': '${result['average_match_score']}%'}.entries)
      Card(child: ListTile(title: Text(entry.key), trailing: Text('${entry.value}'))),
    for (final entry in (result['by_status'] as Map).entries) ListTile(title: Text('${entry.key}'), trailing: Text('${entry.value}')),
  ]);
  Widget profile(dynamic user) => ListView(padding: const EdgeInsets.all(16), children: [
    Text('${user['name']} • ${user['is_premium'] ? 'Premium' : 'Gratuito'}'),
    Text('Competências atuais: ${(user['skills'] as List).join(', ')}'),
    TextField(controller: name, decoration: const InputDecoration(labelText: 'Nome completo')),
    TextField(controller: phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Telefone +55DDD... (opcional)')),
    TextField(controller: skills, decoration: const InputDecoration(labelText: 'Competências separadas por vírgula')),
    FilledButton(onPressed: () => action(() async { await api.request('PUT', '/me/profile', {'name': name.text, 'phone': phone.text.isEmpty ? null : phone.text, 'skills': terms(skills.text)}); }), child: const Text('Salvar perfil')),
    OutlinedButton(onPressed: () => action(() async {
      final file = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['pdf'], withData: true);
      if (file == null) return;
      final bytes = file.files.single.bytes;
      if (bytes == null || bytes.length > 5 * 1024 * 1024) throw ApiException('Selecione um PDF de até 5 MiB.');
      await api.upload(bytes);
    }), child: Text(user['has_resume'] ? 'Substituir currículo PDF' : 'Enviar currículo PDF')),
    TextField(controller: titles, decoration: const InputDecoration(labelText: 'Cargos desejados separados por vírgula')),
    TextField(controller: salary, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Salário mínimo em R\$')),
    DropdownButton<String>(value: modality, items: const [DropdownMenuItem(value: 'remote', child: Text('Remoto')), DropdownMenuItem(value: 'hybrid', child: Text('Híbrido')), DropdownMenuItem(value: 'onsite', child: Text('Presencial'))], onChanged: (v) => setState(() => modality = v!)),
    SwitchListTile(title: const Text('Autorizar candidaturas automáticas (Premium)'), value: automatic, onChanged: user['is_premium'] ? (v) => setState(() => automatic = v) : null),
    FilledButton(onPressed: () => action(() async { await api.request('PUT', '/me/preferences', {'titles': terms(titles.text), 'min_salary': double.tryParse(salary.text.replaceAll(',', '.')) ?? 0, 'modalities': [modality], 'locations': [], 'automation_enabled': automatic}); }), child: const Text('Salvar critérios')),
    TextButton(onPressed: () => action(() async { await api.request('POST', '/auth/logout'); await api.clear(); if (mounted) Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const LoginScreen()), (_) => false); }), child: const Text('Sair de todas as sessões')),
    TextButton(onPressed: deleteAccount, child: const Text('Excluir conta e dados')),
  ]);
  Future<void> deleteAccount() async {
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(title: const Text('Excluir permanentemente?'), content: Column(mainAxisSize: MainAxisSize.min, children: [const Text('Perfil, currículo e candidaturas serão removidos. Confirme sua senha.'), TextField(controller: password, obscureText: true)]), actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Excluir'))]));
    final secret = password.text;
    // Dispose after the dialog route finishes its exit animation.
    Future.delayed(const Duration(seconds: 1), password.dispose);
    if (confirmed != true) return;
    await action(() async { await api.request('DELETE', '/me', {'password': secret}); await api.clear(); if (mounted) Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const LoginScreen()), (_) => false); });
  }
  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Vagou!'), actions: [IconButton(onPressed: () => setState(reload), icon: const Icon(Icons.refresh))]), body: FutureBuilder<dynamic>(future: data, builder: (context, snapshot) {
    if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
    if (snapshot.hasError) return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Text('${snapshot.error}'), TextButton(onPressed: () => Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const LoginScreen())), child: const Text('Entrar novamente'))]));
    if (tab == 0) return feed(snapshot.data);
    if (tab == 1) return dashboard(snapshot.data);
    if (tab == 3) return profile(snapshot.data);
    return ListView(children: [for (final course in snapshot.data) ListTile(title: Text(course['provider']), subtitle: Text('${course['title']}\n${course['certificate']}'), trailing: const Icon(Icons.open_in_new), onTap: () => action(() async { if (!await launchUrl(Uri.parse(course['url']), mode: LaunchMode.externalApplication)) throw ApiException('Não foi possível abrir o curso.'); }))]);
  }), bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (v) => setState(() { tab = v; reload(); }), destinations: const [NavigationDestination(icon: Icon(Icons.work), label: 'Vagas'), NavigationDestination(icon: Icon(Icons.bar_chart), label: 'Relatórios'), NavigationDestination(icon: Icon(Icons.school), label: 'Cursos'), NavigationDestination(icon: Icon(Icons.person), label: 'Perfil')]));
}