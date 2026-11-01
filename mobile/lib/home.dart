import 'package:flutter/material.dart';
import 'api.dart';
import 'admin.dart';
import 'access.dart';
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
  const HomeScreen(
      {super.key,
      required this.api,
      required this.user,
      required this.onRefreshUser,
      required this.onSignedOut});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;
  bool busy = false;
  bool get recruiter => widget.user['role'] == 'recruiter';
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
        context: context, builder: (_) => const _DeleteDialog());
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
    final screens = recruiter
        ? <Widget>[
            RecruiterView(api: widget.api, user: widget.user),
            RecruiterApplications(api: widget.api),
            CompanyProfile(user: widget.user),
          ]
        : <Widget>[
            JobsView(api: widget.api, onUserChanged: widget.onRefreshUser),
            ReportsView(api: widget.api),
            CoursesView(api: widget.api),
            CandidateProfile(
                api: widget.api,
                user: widget.user,
                onChanged: widget.onRefreshUser),
          ];
    return Scaffold(
      appBar: AppBar(
          title: VagouBrandMark(
              size: 34, premium: widget.user['is_premium'] == true),
          actions: [
            if (hasAdminAccess(widget.user))
              TextButton(
                  onPressed: () => openAdmin(context, widget.api, widget.user),
                  child: const Text('🛡️ Admin')),
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
                          child: Text('Sair de todas as sessões')),
                      PopupMenuItem(
                          value: 'delete', child: Text('Excluir conta e dados'))
                    ]),
          ]),
      body: Column(children: [
        if (recruiter)
          Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SegmentedButton<int>(
                      segments: const [
                        ButtonSegment(
                            value: 0, label: Text('Vagas Publicadas')),
                        ButtonSegment(
                            value: 1, label: Text('Talentos & Candidatos')),
                        ButtonSegment(value: 2, label: Text('Minha Empresa'))
                      ],
                      selected: {
                        tab
                      },
                      onSelectionChanged: (values) =>
                          setState(() => tab = values.first)))),
        Expanded(child: IndexedStack(index: tab, children: screens)),
      ]),
      bottomNavigationBar: recruiter
          ? null
          : Container(
              margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                  boxShadow: [
                    BoxShadow(
                        color: Brand.navy.withValues(alpha: .06),
                        blurRadius: 18,
                        offset: const Offset(0, 4))
                  ]),
              child: NavigationBar(
                  selectedIndex: tab,
                  onDestinationSelected: (v) => setState(() => tab = v),
                  destinations: recruiter
                      ? const [
                          NavigationDestination(
                              icon: Icon(Icons.work_outline),
                              selectedIcon: Icon(Icons.work),
                              label: 'Vagas Publicadas'),
                          NavigationDestination(
                              icon: Icon(Icons.people_outline),
                              selectedIcon: Icon(Icons.people),
                              label: 'Talentos & Candidatos'),
                          NavigationDestination(
                              icon: Icon(Icons.business_outlined),
                              selectedIcon: Icon(Icons.business),
                              label: 'Minha Empresa'),
                        ]
                      : const [
                          NavigationDestination(
                              icon: Icon(Icons.work_outline),
                              selectedIcon: Icon(Icons.work),
                              label: 'Vagas'),
                          NavigationDestination(
                              icon: Icon(Icons.insights_outlined),
                              selectedIcon: Icon(Icons.insights),
                              label: 'Relatórios'),
                          NavigationDestination(
                              icon: Icon(Icons.school_outlined),
                              selectedIcon: Icon(Icons.school),
                              label: 'Cursos'),
                          NavigationDestination(
                              icon: Icon(Icons.person_outline),
                              selectedIcon: Icon(Icons.person),
                              label: 'Perfil'),
                        ])),
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
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text(
                'Seu perfil, currículo e candidaturas serão excluídos. Para empresas, suas vagas também serão removidas. Essa ação não pode ser desfeita.'),
            const SizedBox(height: 20),
            TextField(
                controller: password,
                obscureText: true,
                decoration:
                    const InputDecoration(labelText: 'Confirme sua senha'))
          ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancelar')),
            FilledButton(
                onPressed: () {
                  if (password.text.isNotEmpty)
                    Navigator.pop(context, password.text);
                },
                child: const Text('Excluir permanentemente'))
          ]);
}
