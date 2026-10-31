import 'package:flutter/material.dart';
import 'api.dart';
import 'auth.dart';
import 'home.dart';
import 'onboarding.dart';
import 'ui.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VagouApp());
}

class VagouApp extends StatefulWidget {
  const VagouApp({super.key});
  @override
  State<VagouApp> createState() => _VagouAppState();
}

class _VagouAppState extends State<VagouApp> with WidgetsBindingObserver {
  final api = Api();
  final navigator = GlobalKey<NavigatorState>();
  Map<String, dynamic>? user;
  bool loading = true, onboarding = false;
  Object? error;
  Future<void>? _refreshingUser;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    api.onUnauthorized = () {
      if (mounted) setState(() => user = null);
      navigator.currentState?.popUntil((route) => route.isFirst);
    };
    initialize();
  }

  Future<void> initialize() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      onboarding = await api.storage.read(key: 'onboarding_seen') != 'true';
      if (await api.restore())
        user = Map<String, dynamic>.from(await api.request('GET', '/me'));
    } catch (e) {
      if (e is! ApiException || e.status != 401) error = e;
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> authenticated() async {
    final result = Map<String, dynamic>.from(await api.request('GET', '/me'));
    if (mounted)
      setState(() {
        user = result;
        error = null;
      });
  }

  Future<void> refreshUser() {
    return _refreshingUser ??= _fetchCurrentUser().whenComplete(() {
      _refreshingUser = null;
    });
  }

  Future<void> _fetchCurrentUser() async {
    final accountId = user?['id'];
    if (accountId == null) return;
    final result = Map<String, dynamic>.from(await api.request('GET', '/me'));
    if (mounted && user?['id'] == accountId) setState(() => user = result);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && user != null && !loading) {
      refreshUser().catchError((Object failure) {
        final context = navigator.currentContext;
        if (mounted && context != null && user != null)
          friendlyError(context, failure);
      });
    }
  }

  Future<void> endSession() async {
    await api.clear();
    if (mounted) setState(() => user = null);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    api.client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: navigator,
    title: 'Vagou!',
    debugShowCheckedModeBanner: false,
    theme: Brand.theme(Brightness.light),
    darkTheme: Brand.theme(Brightness.dark),
    themeMode: ThemeMode.system,
    home: Builder(
      builder: (context) {
        if (loading)
          return const Scaffold(
            body: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  BrandMark(size: 62),
                  SizedBox(height: 28),
                  CircularProgressIndicator(),
                ],
              ),
            ),
          );
        if (error != null)
          return Scaffold(
            body: EmptyState(
              icon: Icons.cloud_off_rounded,
              title: 'Vamos reconectar?',
              message: error is ApiException
                  ? (error as ApiException).message
                  : 'Não foi possível acessar sua conta agora.',
              onRetry: initialize,
            ),
          );
        if (onboarding)
          return OnboardingScreen(
            onComplete: () async {
              await api.storage.write(key: 'onboarding_seen', value: 'true');
              if (mounted) setState(() => onboarding = false);
            },
          );
        if (user == null)
          return AuthScreen(api: api, onAuthenticated: authenticated);
        return HomeScreen(
          api: api,
          user: user!,
          onRefreshUser: refreshUser,
          onSignedOut: endSession,
        );
      },
    ),
  );
}
