import 'package:flutter/material.dart';
import 'ui.dart';

/// Presentational dossier header; account actions remain in CandidateProfile.
class ExecutiveDossier extends StatelessWidget {
  final String name, email;
  final bool premium, verified;
  final int completion;
  const ExecutiveDossier(
      {super.key,
      required this.name,
      required this.email,
      required this.premium,
      required this.verified,
      required this.completion});
  @override
  Widget build(BuildContext context) => Panel(
      padding: EdgeInsets.zero,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
            height: 76,
            decoration: const BoxDecoration(
                gradient: LinearGradient(
                    colors: [Color(0xFF1E40AF), Color(0xFF3B82F6)]),
                borderRadius: BorderRadius.vertical(top: Radius.circular(12))),
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(children: [
                  const Expanded(
                      child: Text('DOSSIÊ EXECUTIVO',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              letterSpacing: 1.4,
                              fontWeight: FontWeight.w700))),
                  VagouBrandMark(size: 34, showName: false, premium: premium)
                ]))),
        Padding(
            padding: const EdgeInsets.all(18),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                CompanyAvatar(company: name),
                const SizedBox(width: 12),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text(name,
                          style: Theme.of(context)
                              .textTheme
                              .titleLarge
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      Text(email, style: Theme.of(context).textTheme.bodySmall)
                    ]))
              ]),
              const SizedBox(height: 12),
              Wrap(spacing: 8, children: [
                Chip(
                    avatar: Icon(
                        verified
                            ? Icons.verified
                            : Icons.mark_email_unread_outlined,
                        size: 16),
                    label: Text(verified ? 'Verificada' : 'Pendente')),
                if (premium)
                  const Chip(
                      label: Text('Premium'),
                      avatar: Icon(Icons.workspace_premium, size: 16))
              ]),
              const SizedBox(height: 12),
              Row(children: [
                const Expanded(child: Text('Força do perfil')),
                Text('$completion%',
                    style: const TextStyle(fontWeight: FontWeight.w800))
              ]),
              const SizedBox(height: 8),
              LinearProgressIndicator(
                  value: completion / 100,
                  minHeight: 7,
                  borderRadius: BorderRadius.circular(7)),
              const SizedBox(height: 8),
              Text(completion == 100
                  ? 'Dossiê completo.'
                  : 'Complete os campos pendentes para fortalecer seu dossiê.'),
            ])),
      ]));
}
