import 'package:flutter/material.dart';
import 'api.dart';
import 'candidate.dart';
import 'courses.dart';
import 'jobs.dart';
import 'reporting.dart';
import 'recruiter.dart';
import 'ui.dart';

class HomeScreen extends StatefulWidget {
  final Api api;
  final Map<String, dynamic> user;
  final Future<void> Function() onRefreshUser, onSignedOut;
  const HomeScreen({
    super.key,
    required this.api,
    required this.user,
    required this.onRefreshUser,
    required this.onSignedOut,
  });
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0, reportGeneration = 0;
  bool busy = false, refreshingPlan = false;
  bool get recruiter => widget.user['role'] == 'recruiter';
  @override
  void didUpdateWidget(covariant HomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!recruiter && tab == 1 && !identical(oldWidget.user, widget.user))
      reportGeneration++;
  }

  Future<void> refreshAccess() async {
    if (refreshingPlan) return;
    setState(() => refreshingPlan = true);
    try {
      await widget.onRefreshUser();
    } catch (error) {
      if (mounted) await friendlyError(context, error);
    } finally {
      if (mounted) setState(() => refreshingPlan = false);
    }
  }

  void selectTab(int value) {
    setState(() => tab = value);
    if (!recruiter && (value == 1 || value == 3)) refreshAccess();
  }

  Future<void> logout() async {
    setState(() => busy = true);
    try {
      await widget.api.request('POST', '/auth/logout');
      await widget.onSignedOut();
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> deleteAccount() async {
    final result = await showDialog<String>(
      context: context,
      builder: (_) => const _DeleteDialog(),
    );
    if (result == null) return;
    setState(() => busy = true);
    try {
      await widget.api.request('DELETE', '/me', {'password': result});
      await widget.onSignedOut();
    } catch (e) {
      if (mounted) await friendlyError(context, e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final access = PlanAccess.fromUser(widget.user);
    final name = (widget.user['name']?.toString() ?? '').split(' ').first;
    final screens = recruiter
        ? <Widget>[
            RecruiterView(api: widget.api, user: widget.user),
            RecruiterApplications(api: widget.api),
            CompanyProfile(user: widget.user),
          ]
        : <Widget>[
            JobsView(api: widget.api),
            ReportsView(key: ValueKey(reportGeneration), api: widget.api),
            CoursesView(api: widget.api),
            CandidateProfile(
              api: widget.api,
              user: widget.user,
              onChanged: widget.onRefreshUser,
            ),
          ];
    return Scaffold(
      appBar: AppBar(
        title: const BrandMark(size: 32),
        actions: [
          if (access.canAutomate)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Chip(
                label: Text(
                  access.isTestAccess ? 'Teste autorizado' : 'Premium',
                ),
                avatar: const Icon(Icons.auto_awesome, size: 16),
              ),
            ),
          IconButton(
            tooltip: 'Atualizar perfil e plano',
            onPressed: busy || refreshingPlan ? null : refreshAccess,
            icon: refreshingPlan
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.sync_rounded),
          ),
          PopupMenuButton<String>(
            enabled: !busy,
            tooltip: 'Minha conta',
            onSelected: (value) {
              if (value == 'logout')
                logout();
              else
                deleteAccount();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(
                value: 'logout',
                child: Text('Sair de todas as sessões'),
              ),
              PopupMenuItem(
                value: 'delete',
                child: Text('Excluir conta e dados'),
              ),
            ],
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 10),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Olá, $name. ${recruiter ? 'Vamos conectar talentos?' : 'Qual será seu próximo passo?'}',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                if (busy)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
          ),
          Expanded(
            child: IndexedStack(index: tab, children: screens),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: selectTab,
        destinations: recruiter
            ? const [
                NavigationDestination(
                  icon: Icon(Icons.work_outline),
                  selectedIcon: Icon(Icons.work),
                  label: 'Minhas vagas',
                ),
                NavigationDestination(
                  icon: Icon(Icons.people_outline),
                  selectedIcon: Icon(Icons.people),
                  label: 'Candidaturas',
                ),
                NavigationDestination(
                  icon: Icon(Icons.business_outlined),
                  selectedIcon: Icon(Icons.business),
                  label: 'Empresa',
                ),
              ]
            : const [
                NavigationDestination(
                  icon: Icon(Icons.work_outline),
                  selectedIcon: Icon(Icons.work),
                  label: 'Vagas',
                ),
                NavigationDestination(
                  icon: Icon(Icons.insights_outlined),
                  selectedIcon: Icon(Icons.insights),
                  label: 'Relatórios',
                ),
                NavigationDestination(
                  icon: Icon(Icons.school_outlined),
                  selectedIcon: Icon(Icons.school),
                  label: 'Cursos',
                ),
                NavigationDestination(
                  icon: Icon(Icons.person_outline),
                  selectedIcon: Icon(Icons.person),
                  label: 'Perfil',
                ),
              ],
      ),
    );
  }
}

class _DeleteDialog extends StatefulWidget {
  const _DeleteDialog();
  @override
  State<_DeleteDialog> createState() => _DeleteDialogState();
}

class _DeleteDialogState extends State<_DeleteDialog> {
  final password = TextEditingController();
  @override
  void dispose() {
    password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    icon: const Icon(Icons.person_remove_outlined),
    title: const Text('Excluir sua conta?'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          'Seu perfil, currículo e candidaturas serão excluídos. Para empresas, suas vagas também serão removidas. Essa ação não pode ser desfeita.',
        ),
        const SizedBox(height: 20),
        TextField(
          controller: password,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Confirme sua senha'),
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton(
        onPressed: () {
          if (password.text.isNotEmpty) Navigator.pop(context, password.text);
        },
        child: const Text('Excluir permanentemente'),
      ),
    ],
  );
}
